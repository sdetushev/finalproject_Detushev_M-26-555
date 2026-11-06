"""Клиенты внешних API для получения валютных курсов."""

import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


def _validate_rate(value: Any, pair: str) -> float:
    """Проверить положительное конечное значение курса."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ApiRequestError(f"Некорректный курс для пары {pair}")

    return float(value)


def _to_utc_iso(timestamp: int) -> str:
    """Преобразовать Unix-время в ISO UTC."""
    try:
        dt = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError) as error:
        raise ApiRequestError("Некорректная временная метка API") from error

    return dt.isoformat().replace("+00:00", "Z")


def _request_json(
    url: str,
    source: str,
    timeout: int,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Выполнить HTTP-запрос и проверить JSON-ответ."""
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as error:
        raise ApiRequestError(
            f"{source}: ошибка сети ({type(error).__name__})"
        ) from error

    if response.status_code == 429:
        raise ApiRequestError(f"{source}: превышен лимит запросов (HTTP 429)")

    if response.status_code in (401, 403):
        raise ApiRequestError(f"{source}: ошибка доступа (HTTP {response.status_code})")

    if response.status_code != 200:
        raise ApiRequestError(f"{source}: ошибка HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError as error:
        raise ApiRequestError(f"{source}: некорректный JSON-ответ") from error

    if not isinstance(data, dict):
        raise ApiRequestError(f"{source}: ожидался JSON-объект")

    return data


class BaseApiClient(ABC):
    """Определить общий интерфейс клиентов валютных API."""

    def __init__(
        self,
        config: ParserConfig | None = None,
    ) -> None:
        """Сохранить конфигурацию и метаданные обновлений."""
        self.config = config if config is not None else ParserConfig()
        self.last_updated_at: dict[str, str] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы валют относительно базовой валюты."""


class CoinGeckoClient(BaseApiClient):
    """Получать котировки криптовалют из CoinGecko."""

    def fetch_rates(self) -> dict[str, float]:
        """Запросить и нормализовать курсы криптовалют."""
        self.last_updated_at = {}

        base = self.config.BASE_FIAT_CURRENCY
        codes = self.config.CRYPTO_CURRENCIES

        if not codes:
            return {}

        ids = [self.config.CRYPTO_ID_MAP[code] for code in codes]

        params = {
            "ids": ",".join(ids),
            "vs_currencies": base.lower(),
            "include_last_updated_at": "true",
        }

        headers: dict[str, str] = {}

        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY

        data = _request_json(
            url=self.config.COINGECKO_URL,
            source="CoinGecko",
            timeout=self.config.REQUEST_TIMEOUT,
            params=params,
            headers=headers,
        )

        rates: dict[str, float] = {}
        timestamps: dict[str, str] = {}

        for code in codes:
            coin_id = self.config.CRYPTO_ID_MAP[code]
            pair = f"{code}_{base}"
            coin_data = data.get(coin_id)

            if not isinstance(coin_data, dict):
                raise ApiRequestError(f"CoinGecko: отсутствуют данные для {code}")

            rates[pair] = _validate_rate(
                coin_data.get(base.lower()),
                pair,
            )

            raw_timestamp = coin_data.get("last_updated_at")

            if (
                isinstance(raw_timestamp, int)
                and not isinstance(raw_timestamp, bool)
                and raw_timestamp > 0
            ):
                timestamps[pair] = _to_utc_iso(raw_timestamp)

        self.last_updated_at = timestamps
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Получать фиатные котировки из ExchangeRate-API."""

    def fetch_rates(self) -> dict[str, float]:
        """Запросить и обратить курсы относительно USD."""
        self.last_updated_at = {}

        api_key = self.config.EXCHANGERATE_API_KEY

        if not api_key:
            raise ApiRequestError("ExchangeRate-API: не задан EXCHANGERATE_API_KEY")

        base = self.config.BASE_FIAT_CURRENCY

        url = f"{self.config.EXCHANGERATE_API_URL.rstrip('/')}/{api_key}/latest/{base}"

        data = _request_json(
            url=url,
            source="ExchangeRate-API",
            timeout=self.config.REQUEST_TIMEOUT,
        )

        if data.get("result") != "success":
            error_type = data.get("error-type")

            known_errors = {
                "invalid-key",
                "inactive-account",
                "quota-reached",
                "unsupported-code",
                "malformed-request",
            }

            if error_type not in known_errors:
                error_type = "unknown-error"

            raise ApiRequestError(f"ExchangeRate-API: {error_type}")

        if data.get("base_code") != base:
            raise ApiRequestError("ExchangeRate-API: неверная базовая валюта")

        conversion_rates = data.get("conversion_rates")

        if not isinstance(conversion_rates, dict):
            raise ApiRequestError(
                "ExchangeRate-API: отсутствует словарь conversion_rates"
            )

        codes = self.config.FIAT_CURRENCIES
        rates: dict[str, float] = {}

        for code in codes:
            pair = f"{code}_{base}"

            # Ответ latest/USD содержит USD→EUR.
            # Для хранения EUR_USD нужен обратный курс.
            direct_rate = _validate_rate(
                conversion_rates.get(code),
                f"{base}_{code}",
            )

            rates[pair] = _validate_rate(
                1.0 / direct_rate,
                pair,
            )

        timestamp: str | None = None
        raw_unix = data.get("time_last_update_unix")

        if (
            isinstance(raw_unix, int)
            and not isinstance(raw_unix, bool)
            and raw_unix > 0
        ):
            timestamp = _to_utc_iso(raw_unix)

        elif isinstance(data.get("time_last_update_utc"), str):
            try:
                dt = parsedate_to_datetime(data["time_last_update_utc"])

                if dt.tzinfo is None:
                    raise ValueError("Отсутствует часовой пояс")

                timestamp = (
                    dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                )

            except (TypeError, ValueError) as error:
                raise ApiRequestError(
                    "ExchangeRate-API: некорректная дата обновления"
                ) from error

        if timestamp is not None:
            self.last_updated_at = {pair: timestamp for pair in rates}

        return rates
