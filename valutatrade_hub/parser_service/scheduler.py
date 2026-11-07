"""Периодическое обновление валютных курсов."""

import logging
import math
from threading import Event

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import (
    RatesUpdater,
    configure_parser_logging,
)


class RatesScheduler:
    """Периодически запускать обновление валютных курсов."""

    def __init__(
        self,
        updater: RatesUpdater,
        interval_seconds: int | float = 300,
        logger: logging.Logger | None = None,
    ) -> None:
        """Настроить обновление, интервал и возможность остановки."""
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "Интервал обновления должен быть положительным конечным числом"
            )

        self.updater = updater
        self.interval_seconds = interval_seconds
        self.logger = logger if logger is not None else configure_parser_logging()
        self._stop_event = Event()

    def stop(self) -> None:
        """Запросить остановку периодического обновления."""
        self._stop_event.set()

    def run(self, source: str | None = None) -> None:
        """Обновлять курсы до получения сигнала остановки."""
        self.logger.info(
            "Планировщик запущен: интервал=%s секунд, источник=%s",
            self.interval_seconds,
            source or "все",
        )

        try:
            while not self._stop_event.is_set():
                try:
                    result = self.updater.run_update(source=source)

                except ApiRequestError as error:
                    # Временная недоступность API не останавливает
                    # выполнение следующих обновлений.
                    self.logger.warning(
                        "Плановое обновление не выполнено: %s",
                        error,
                    )

                except (OSError, ValueError):
                    # Ошибку хранилища или конфигурации
                    # не следует считать обычным отказом API.
                    self.logger.exception("Критическая ошибка планировщика")
                    raise

                else:
                    self.logger.info(
                        "Плановое обновление завершено: "
                        "статус=%s получено=%d обновлено=%d",
                        result["status"],
                        result["fetched_count"],
                        result["updated_count"],
                    )

                # Event.wait позволяет прервать ожидание
                # сразу после вызова stop().
                if self._stop_event.wait(self.interval_seconds):
                    break

        finally:
            self.logger.info("Планировщик остановлен")


def main() -> None:
    """Создать и запустить периодическое обновление курсов."""
    config = ParserConfig()

    clients = {
        "coingecko": CoinGeckoClient(config),
        "exchangerate": ExchangeRateApiClient(config),
    }

    updater = RatesUpdater(
        clients=clients,
        storage=RatesStorage(config),
    )

    interval = SettingsLoader().get(
        "rates_update_interval_seconds",
        300,
    )

    scheduler = RatesScheduler(
        updater=updater,
        interval_seconds=interval,
    )

    print("Периодическое обновление курсов запущено. Для остановки нажмите Ctrl+C.")

    try:
        scheduler.run()
    except KeyboardInterrupt:
        scheduler.stop()
        print("Периодическое обновление остановлено.")


if __name__ == "__main__":
    main()
