"""Конфигурация сервиса получения валютных курсов."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    FiatCurrency,
    get_currency,
)
from valutatrade_hub.infra.settings import SettingsLoader


def _resolve_data_file(setting_key: str, default_name: str) -> Path:
    """Получить путь к файлу данных из общих настроек проекта."""
    settings = SettingsLoader()

    data_dir = settings.project_root / settings.get("data_dir", "data")
    filename = settings.get(setting_key, default_name)

    return data_dir / filename


@dataclass(frozen=True, slots=True)
class ParserConfig:
    """Хранить настройки API, валют и файлов Parser Service."""

    EXCHANGERATE_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY"),
        repr=False,
    )

    COINGECKO_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY"),
        repr=False,
    )

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"

    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_FIAT_CURRENCY: str = "USD"

    FIAT_CURRENCIES: tuple[str, ...] = (
        "EUR",
        "RUB",
    )

    CRYPTO_CURRENCIES: tuple[str, ...] = (
        "BTC",
        "ETH",
    )

    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
        }
    )

    RATES_FILE_PATH: Path = field(
        default_factory=lambda: _resolve_data_file(
            "rates_file",
            "rates.json",
        )
    )

    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: _resolve_data_file(
            "exchange_rates_file",
            "exchange_rates.json",
        )
    )

    REQUEST_TIMEOUT: int = 10

    def __post_init__(self) -> None:
        """Проверить согласованность настроек с реестром валют."""
        base_currency = get_currency(self.BASE_FIAT_CURRENCY)

        if not isinstance(base_currency, FiatCurrency):
            raise ValueError("Базовая валюта должна быть фиатной")

        for code in self.FIAT_CURRENCIES:
            currency = get_currency(code)

            if not isinstance(currency, FiatCurrency):
                raise ValueError(f"Валюта '{code}' не является фиатной")

        for code in self.CRYPTO_CURRENCIES:
            currency = get_currency(code)

            if not isinstance(currency, CryptoCurrency):
                raise ValueError(f"Валюта '{code}' не является криптовалютой")

        if set(self.CRYPTO_ID_MAP) != set(self.CRYPTO_CURRENCIES):
            raise ValueError(
                "CRYPTO_ID_MAP должен соответствовать списку CRYPTO_CURRENCIES"
            )

        if self.REQUEST_TIMEOUT <= 0:
            raise ValueError("REQUEST_TIMEOUT должен быть положительным")
