import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


class ActionFormatter(logging.Formatter):
    """Форматировать записи журнала с временем в UTC."""

    def __init__(self, output_format: str = "text") -> None:
        """Выбрать текстовый формат или JSON."""
        super().__init__()
        self._output_format = output_format

    def format(self, record: logging.LogRecord) -> str:
        """Сформировать запись журнала с ISO-временем."""
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")

        message = record.getMessage()

        if self._output_format == "json":
            return json.dumps(
                {
                    "level": record.levelname,
                    "timestamp": timestamp,
                    "message": message,
                },
                ensure_ascii=False,
            )

        return f"{record.levelname} {timestamp} {message}"


def configure_logging() -> logging.Logger:
    """Настроить журнал операций с ротацией файлов."""
    settings = SettingsLoader()

    logger = logging.getLogger("valutatrade.actions")

    log_level = settings.get("log_level")
    logger.setLevel(getattr(logging, log_level))

    # Не дублируем записи в корневом логгере.
    logger.propagate = False

    # Повторный вызов не должен создавать новые обработчики.
    if logger.handlers:
        return logger

    log_dir = Path(settings.get("log_dir"))

    if not log_dir.is_absolute():
        log_dir = settings.project_root / log_dir

    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "actions.log"

    handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding="utf-8",
    )

    handler.setFormatter(ActionFormatter(settings.get("log_format")))

    logger.addHandler(handler)

    return logger
