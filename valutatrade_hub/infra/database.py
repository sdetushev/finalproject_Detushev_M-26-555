from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, ClassVar

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Единая точка доступа к JSON-хранилищу (Singleton)."""

    _instance: ClassVar[DatabaseManager | None] = None
    _singleton_lock = Lock()

    def __new__(cls) -> DatabaseManager:
        """Создать только один экземпляр DatabaseManager."""
        # __new__ выбран за простоту и читаемость.
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """Инициализировать хранилище только один раз."""
        with self._singleton_lock:
            if getattr(self, "_initialized", False):
                return

            settings = SettingsLoader()

            data_dir = Path(settings.get("data_dir"))

            if not data_dir.is_absolute():
                data_dir = settings.project_root / data_dir

            self._data_dir = data_dir

            self._defaults: dict[str, Any] = {
                settings.get("users_file"): [],
                settings.get("portfolios_file"): [],
                settings.get("rates_file"): {},
            }

            self._lock = RLock()
            self._initialized = True

    @property
    def data_dir(self) -> Path:
        """Вернуть путь к каталогу JSON-хранилища."""
        return self._data_dir

    def _get_path(self, filename: str) -> Path:
        """Проверить имя файла и вернуть полный путь."""
        if filename not in self._defaults:
            raise ValueError(f"Недопустимый файл хранилища: '{filename}'")

        return self._data_dir / filename

    def initialize_storage(self) -> None:
        """Создать каталог и отсутствующие JSON-файлы."""
        with self._lock:
            self._data_dir.mkdir(parents=True, exist_ok=True)

            for filename, default_data in self._defaults.items():
                path = self._get_path(filename)

                if not path.exists():
                    with path.open("w", encoding="utf-8") as file:
                        json.dump(
                            default_data,
                            file,
                            ensure_ascii=False,
                            indent=2,
                        )

    def read_json(self, filename: str) -> Any:
        """Прочитать данные из JSON-файла."""
        with self._lock:
            path = self._get_path(filename)
            self.initialize_storage()

            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

    def write_json(self, filename: str, data: Any) -> None:
        """Безопасно записать данные через временный файл."""
        with self._lock:
            path = self._get_path(filename)
            self.initialize_storage()

            temp_path: Path | None = None

            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._data_dir,
                    prefix=f".{filename}.",
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:
                    temp_path = Path(temp_file.name)

                    json.dump(
                        data,
                        temp_file,
                        ensure_ascii=False,
                        indent=2,
                    )
                    temp_file.write("\n")

                os.replace(temp_path, path)

            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

    def update_json(
        self,
        filename: str,
        transform: Callable[[Any], Any],
    ) -> Any:
        """Выполнить чтение, изменение и запись под одной блокировкой."""
        with self._lock:
            data = self.read_json(filename)
            updated_data = transform(data)

            self.write_json(filename, updated_data)

            return updated_data
