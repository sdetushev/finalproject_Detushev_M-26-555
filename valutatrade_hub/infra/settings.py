from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, ClassVar


class SettingsLoader:
    """Единый загрузчик конфигурации проекта (Singleton)."""

    _instance: ClassVar[SettingsLoader | None] = None

    def __new__(cls) -> SettingsLoader:
        """Создать экземпляр только при первом обращении."""
        # __new__ выбран для простой и читаемой реализации Singleton.
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """Загрузить конфигурацию при первой инициализации."""
        if getattr(self, "_initialized", False):
            return

        self._project_root = Path(__file__).resolve().parents[2]
        self._config: dict[str, Any] = {}

        self.reload()
        self._initialized = True

    @property
    def project_root(self) -> Path:
        """Вернуть корневой каталог проекта."""
        return self._project_root

    def get(self, key: str, default: Any = ...) -> Any:
        """Получить значение настройки или значение по умолчанию."""
        if key in self._config:
            return self._config[key]

        if default is not ...:
            return default

        raise KeyError(f"Неизвестная настройка '{key}'")

    def reload(self) -> None:
        """Перезагрузить настройки из pyproject.toml."""
        config_path = self._project_root / "pyproject.toml"

        with config_path.open("rb") as file:
            data = tomllib.load(file)

        settings = data.get("tool", {}).get("valutatrade", {})

        if not isinstance(settings, dict):
            raise ValueError("Некорректная секция [tool.valutatrade]")

        required_keys = (
            "data_dir",
            "users_file",
            "portfolios_file",
            "rates_file",
            "rates_ttl_seconds",
            "default_base_currency",
            "log_dir",
            "log_level",
            "log_format",
            "log_max_bytes",
            "log_backup_count",
        )

        missing = [key for key in required_keys if key not in settings]

        if missing:
            raise ValueError(
                "Отсутствуют обязательные настройки: " + ", ".join(missing)
            )

        positive_int_keys = (
            "rates_ttl_seconds",
            "log_max_bytes",
            "log_backup_count",
        )

        for key in positive_int_keys:
            value = settings[key]

            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(
                    f"Настройка '{key}' должна быть положительным целым числом"
                )

        string_keys = (
            "data_dir",
            "users_file",
            "portfolios_file",
            "rates_file",
            "default_base_currency",
            "log_dir",
            "log_level",
            "log_format",
        )

        for key in string_keys:
            value = settings[key]

            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Настройка '{key}' должна быть непустой строкой")

        if settings["log_level"] not in ("DEBUG", "INFO"):
            raise ValueError("log_level должен быть DEBUG или INFO")

        if settings["log_format"] not in ("text", "json"):
            raise ValueError("log_format должен быть text или json")

        self._config = settings.copy()
