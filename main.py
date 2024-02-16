import logging
import os

from ptb_bot import PTBBot

logging.getLogger("httpx").setLevel(logging.WARNING)

log_file_path_errors = "logs/errors.txt"
log_file_path_info = "logs/info.txt"
os.makedirs("logs", exist_ok=True)

errors_handler = logging.FileHandler(log_file_path_errors, encoding="utf-8")
errors_handler.setLevel(logging.ERROR)

info_handler = logging.FileHandler(log_file_path_info, encoding="utf-8")
info_handler.setLevel(logging.INFO)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        # info_handler,
        # errors_handler,
        logging.StreamHandler()
    ]
)


def run_bot():
    config_path = "config/bot_config.yaml"
    settings_path = "config/settings.yaml"
    bot = PTBBot(
        config_path=config_path,
        settings_path=settings_path,

        log_file_path_errors=log_file_path_errors,
        log_file_path_info=log_file_path_info)

    bot.run_polling()
    # or
    # bot.run_webhook()


if __name__ == '__main__':
    run_bot()
