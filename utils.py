import datetime

from yaml import load, dump

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def load_dict_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return load(f, Loader)


def save_config_to_file(dict_file, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        return dump(dict_file, f, Dumper, encoding="utf-8")


def remaining_time_until_future_date(future_date: datetime):
    current_datetime = datetime.datetime.utcnow()

    if future_date < current_datetime:
        return None

    time_difference = future_date - current_datetime

    days = time_difference.days
    seconds = time_difference.seconds
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    time_parts = []
    if days > 0:
        time_parts.append(f"{days} д.")
    if hours > 0:
        time_parts.append(f"{hours} ч.")
    if minutes > 0:
        time_parts.append(f"{minutes} мин.")
    if seconds > 0:
        time_parts.append(f"{seconds} сек.")

    return ' '.join(time_parts)