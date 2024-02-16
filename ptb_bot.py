import asyncio
import logging
import os.path
from enum import Enum
from functools import wraps
from typing import Optional, Tuple

from ptbcontrib.ptb_jobstores.sqlalchemy import PTBSQLAlchemyJobStore
from telegram import Update, ChatMemberUpdated, ChatMember, Chat, helpers
from telegram._utils.types import FileInput
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, PicklePersistence, AIORateLimiter, Application, \
    CallbackQueryHandler, ChatMemberHandler, CallbackContext, CommandHandler, MessageHandler, filters

import utils


class PTBBot:
    def __init__(
            self,
            config_path="config/bot_config.yaml",
            settings_path="config/settings.yaml",
            log_file_path_errors="logs/errors.txt",
            log_file_path_info="logs/info.txt",
    ):
        self._config = utils.load_dict_from_file(config_path)
        self._settings_path = settings_path
        self._settings = utils.load_dict_from_file(settings_path)

        self._log_file_errors = log_file_path_errors
        self._log_file_info = log_file_path_info

        self._application = (ApplicationBuilder()
                             .token(self._config["bot_token"])
                             .concurrent_updates(True)
                             .rate_limiter(AIORateLimiter(overall_max_rate=20))
                             .build())

        db_uri = f"sqlite:///data/bot_job_database.db"
        self._application.job_queue.scheduler.add_jobstore(
            PTBSQLAlchemyJobStore(
                application=self._application,
                url=db_uri,
            )
        )
        self._application.job_queue.scheduler._job_defaults["misfire_grace_time"] = 7 * 24 * 60 * 60

        self._menu_commands = {
            "start": ("Старт", self._command_start),
            "help": ("Справка", self._command_help),
        }
        self._admin_commands = {
            "info_log": self._command_info_log,
            "error_log": self._command_error_log
        }
        self._other_commands = {}

        self.__set_handlers(self._application)

        self._application.post_init = self.__post_init
        self._application.post_stop = self.__post_stop

    def __set_handlers(self, application: Application):
        application.add_handler(CallbackQueryHandler(self.__callback_query_handle))

        application.add_handler(MessageHandler(filters=~filters.COMMAND, callback=self.__message_handle))

        application.add_handler(ChatMemberHandler(self.__track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

        self.__set_commands_handlers(application)

    def __set_commands_handlers(self, application):
        for name, command in self._menu_commands.items():
            application.add_handler(CommandHandler(name, command[1]))
        for name, command in self._other_commands.items():
            application.add_handler(CommandHandler(name, command))
        for name, command in self._admin_commands.items():
            application.add_handler(CommandHandler(name, command))

    async def __post_init(self, app: Application):
        await app.bot.set_my_commands([(key, value[0]) for key, value in self._menu_commands.items()])

        bot = await app.bot.get_me()
        logging.info(f"Bot «{bot.full_name}» is running! Link: {bot.link}")

    async def __post_stop(self, app: Application):
        pass

    def run_polling(self):
        self._application.run_polling()

    def run_webhook(self):
        self._application.run_webhook(
            port=self._config["port"],
            secret_token=self._config["secret_token"],
            cert=self._config["certificate_path"],
            webhook_url=self._config["webhook_url"],
            url_path=self._config["url_path"]
        )

    @staticmethod
    def __extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[Tuple[bool, bool]]:
        status_change = chat_member_update.difference().get("status")
        old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

        if status_change is None:
            return None

        old_status, new_status = status_change
        was_member = old_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
        is_member = new_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

        return was_member, is_member

    async def __track_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        result = self.__extract_status_change(update.my_chat_member)
        if result is None:
            return
        was_member, is_member = result
        if update.effective_user.is_bot:
            return
        cause_name = update.effective_user.full_name
        effective_chat_id = str(update.effective_chat.id)
        effective_chat_id = int(effective_chat_id.replace("-100", ""))
        chat_id = effective_chat_id

        chat = update.effective_chat
        if chat.type == Chat.PRIVATE:
            if not was_member and is_member:
                logging.info("%s unblocked the bot", cause_name)
                context.bot_data.setdefault("users", dict())[chat_id] = (cause_name, True)
            elif was_member and not is_member:
                logging.info("%s blocked the bot", cause_name)
                context.bot_data.setdefault("users", dict())[chat_id] = (cause_name, False)
        elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
            if not was_member and is_member:
                logging.info("%s added the bot to the group %s", cause_name, chat.title)
                await context.bot.leave_chat(update.effective_chat.id)
            elif was_member and not is_member:
                logging.info("%s removed the bot from the group %s", cause_name, chat.title)
        elif not was_member and is_member:
            logging.info("%s added the bot to the channel %s", cause_name, chat.title)
            context.bot.leave_chat(update.effective_chat.id)
        elif was_member and not is_member:
            logging.info("%s removed the bot from the channel %s", cause_name, chat.title)

    async def _command_start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        user_name = update.effective_user.full_name

        if chat.type == Chat.PRIVATE and chat.id not in context.bot_data.get("users", {}):
            logging.info("%s started a private chat with the bot", user_name)
            context.bot_data.setdefault("users", {}).setdefault(update.effective_user.id, (user_name, True))
            markdown_user_link = helpers.mention_markdown(update.effective_user.id, user_name)
            for admin_id in self._settings["admins"]:
                try:
                    await context.bot.send_message(
                        admin_id, f"Новый пользователь: {markdown_user_link}", parse_mode=ParseMode.MARKDOWN)
                except:
                    pass

        await update.message.reply_text("Привет!")

    def _check_rights(self, update: Update):
        if update.effective_user.id in self._settings["admins"]:
            return True
        return False

    async def _command_help(self, update: Update, context: CallbackContext):
        await update.message.reply_text("Помощь")

    async def _command_error_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_rights(update):
            return

        if os.path.exists(self._log_file_errors):
            document = open(self._log_file_errors, "r", encoding="utf-8")
            if len(document.read()) == 0:
                await update.message.reply_text("⚙️ Ошибки в логе отсутствуют.")
                document.close()
                return
            document.close()
            await update.message.reply_document(document=self._log_file_errors)

            with open(self._log_file_errors, "w", encoding="utf-8"):
                pass
            await asyncio.sleep(0.5)
            await update.message.reply_text("💾 Файл лога был очищен.")
        else:
            await update.message.reply_text("⚙️ Ошибки в логе отсутствуют.")

    async def _command_info_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_rights(update):
            return

        if os.path.exists(self._log_file_info):
            document = open(self._log_file_info, "r", encoding="utf-8")
            if len(document.read()) == 0:
                await update.message.reply_text("⚙️ Инфо в логе отсутствует.")
                document.close()
                return
            document.close()
            await update.message.reply_document(document=self._log_file_info)

            with open(self._log_file_info, "w", encoding="utf-8"):
                pass
            await asyncio.sleep(0.5)
            await update.message.reply_text("💾 Файл лога был очищен.")
        else:
            await update.message.reply_text("⚙️ Инфо в логе отсутствует.")

    async def __callback_query_handle(self, update: Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        data: str = query.data
        user_id = update.effective_user.id

    async def __message_handle(self, update: Update, context: CallbackContext):
        message = update.message
        user_id = update.effective_user.id
