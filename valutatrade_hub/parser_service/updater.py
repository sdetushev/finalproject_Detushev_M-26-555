"""Координация обновления валютных курсов."""

import logging
import time
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import BaseApiClient
from valutatrade_hub.parser_service.storage import RatesStorage

SOURCE_NAMES = {
    "coingecko": "CoinGecko",
    "exchangerate": "ExchangeRate-API",
}


def configure_parser_logging() -> logging.Logger:
    """Настроить отдельный журнал Parser Service."""
    settings = SettingsLoader()

    log_dir = settings.project_root / settings.get("log_dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / "parser.log"

    logger = logging.getLogger("valutatrade.parser")

    level_name = str(settings.get("log_level", "INFO")).upper()

    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False

    # Не создаём повторные обработчики журнала.
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == log_path.resolve()
        ):
            return logger

    handler = RotatingFileHandler(
        log_path,
        maxBytes=int(settings.get("log_max_bytes", 1_048_576)),
        backupCount=int(settings.get("log_backup_count", 3)),
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        fmt="%(levelname)s %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


class RatesUpdater:
    """Получать и сохранять курсы из доступных источников."""

    def __init__(
        self,
        clients: Mapping[str, BaseApiClient],
        storage: RatesStorage,
        logger: logging.Logger | None = None,
    ) -> None:
        """Сохранить клиентов, хранилище и журнал."""
        if not clients:
            raise ValueError("Необходимо передать хотя бы один API-клиент")

        unknown = set(clients) - set(SOURCE_NAMES)

        if unknown:
            raise ValueError("Неизвестные источники: " + ", ".join(sorted(unknown)))

        self.clients = dict(clients)
        self.storage = storage
        self.logger = logger if logger is not None else configure_parser_logging()

    def run_update(
        self,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Обновить курсы всех или одного выбранного источника."""
        if source is None:
            selected_clients = self.clients

        else:
            if not isinstance(source, str):
                raise ValueError("Источник должен быть строкой")

            source_key = source.strip().lower()

            if source_key not in self.clients:
                raise ValueError(f"Неизвестный источник '{source}'")

            selected_clients = {source_key: self.clients[source_key]}

        total_fetched = 0
        total_updated = 0

        results: dict[str, dict[str, int]] = {}
        errors: dict[str, str] = {}

        self.logger.info(
            "Начало обновления курсов: источники=%s",
            ",".join(selected_clients),
        )

        for source_key, client in selected_clients.items():
            source_name = SOURCE_NAMES[source_key]

            self.logger.info(
                "Запрос курсов: источник=%s",
                source_name,
            )

            try:
                rates = client.fetch_rates()

                if not isinstance(rates, dict) or not rates:
                    raise ApiRequestError(f"{source_name}: источник не вернул курсы")

            except ApiRequestError as error:
                errors[source_key] = str(error)

                self.logger.error(
                    "Ошибка получения курсов: источник=%s ошибка=%s",
                    source_name,
                    error,
                )
                continue

            # Ошибки записи не скрываем: повреждение хранилища
            # отличается от временной недоступности API.
            try:
                updated_count = self.storage.save_rates(
                    rates=rates,
                    source=source_name,
                    timestamps=client.last_updated_at,
                )

            except (OSError, ValueError):
                self.logger.exception(
                    "Не удалось сохранить курсы: источник=%s",
                    source_name,
                )
                raise

            fetched_count = len(rates)

            total_fetched += fetched_count
            total_updated += updated_count

            results[source_key] = {
                "fetched": fetched_count,
                "updated": updated_count,
            }

            self.logger.info(
                "Источник=%s получено=%d обновлено=%d",
                source_name,
                fetched_count,
                updated_count,
            )

        # Если ни один источник не ответил успешно,
        # вызывающий код получит специализированную ошибку.
        if not results:
            self.logger.error("Обновление не выполнено: все источники недоступны")

            raise ApiRequestError(
                "Не удалось обновить курсы ни из одного источника. "
                "Проверьте logs/parser.log"
            )

        cache = self.storage.load_cache()

        status = "partial" if errors else "success"

        self.logger.info(
            "Завершение обновления: статус=%s получено=%d обновлено=%d ошибок=%d",
            status,
            total_fetched,
            total_updated,
            len(errors),
        )

        return {
            "status": status,
            "fetched_count": total_fetched,
            "updated_count": total_updated,
            "sources": results,
            "errors": errors,
            "last_refresh": cache["last_refresh"],
        }
