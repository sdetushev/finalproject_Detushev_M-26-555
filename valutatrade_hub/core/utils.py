import math
from collections.abc import Callable
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.infra.database import DatabaseManager

JsonData = list[Any] | dict[str, Any]


def normalize_currency_code(currency_code: str) -> str:
    """Проверить и нормализовать код через единый реестр валют."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    return get_currency(currency_code).code


def convert_amount(
    amount: float,
    from_usd_rate: float,
    to_usd_rate: float,
) -> float:
    """Конвертировать сумму по котировкам к USD без округления."""
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount < 0
    ):
        raise ValueError("Сумма должна быть неотрицательным конечным числом")

    for rate in (from_usd_rate, to_usd_rate):
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ValueError("Курс должен быть положительным конечным числом")

    result = amount * from_usd_rate / to_usd_rate

    if not math.isfinite(result):
        raise ValueError("Результат конвертации слишком велик")

    return float(result)


def initialize_storage() -> None:
    """Создать отсутствующие JSON-файлы через DatabaseManager."""
    DatabaseManager().initialize_storage()


def load_json(filename: str) -> JsonData:
    """Прочитать JSON-файл через DatabaseManager."""
    data = DatabaseManager().read_json(filename)

    if not isinstance(data, (list, dict)):
        raise ValueError(f"Некорректный формат данных в файле '{filename}'")

    return data


def save_json(filename: str, data: JsonData) -> None:
    """Безопасно сохранить данные через DatabaseManager."""
    if not isinstance(data, (list, dict)):
        raise TypeError("Данные для JSON должны быть списком или словарём")

    DatabaseManager().write_json(filename, data)


def update_json(
    filename: str,
    transform: Callable[[JsonData], JsonData],
) -> JsonData:
    """Безопасно выполнить чтение, изменение и запись JSON."""

    def checked_transform(data: Any) -> JsonData:
        """Проверить структуру до и после изменения данных."""
        if not isinstance(data, (list, dict)):
            raise ValueError(f"Некорректный формат данных в файле '{filename}'")

        updated = transform(data)

        if not isinstance(updated, (list, dict)):
            raise ValueError("Результат обновления должен быть списком или словарём")

        return updated

    return DatabaseManager().update_json(filename, checked_transform)
