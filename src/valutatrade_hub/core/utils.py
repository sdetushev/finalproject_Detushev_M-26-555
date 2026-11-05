import json
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")

INITIAL_DATA: dict[str, list[Any] | dict[str, Any]] = {
    "users.json": [],
    "portfolios.json": [],
    "rates.json": {},
}


def initialize_storage() -> None:
    """Создать каталог и JSON-файлы при их отсутствии."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for filename, initial_data in INITIAL_DATA.items():
        path = DATA_DIR / filename

        if not path.exists():
            save_json(filename, initial_data)


def load_json(filename: str) -> list[Any] | dict[str, Any]:
    """Загрузить данные из JSON-файла."""
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, (list, dict)):
        raise ValueError(f"Некорректный формат данных в файле '{filename}'")

    return data


def save_json(filename: str, data: list[Any] | dict[str, Any]) -> None:
    """Сохранить данные в JSON-файл."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    path = DATA_DIR / filename

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")
