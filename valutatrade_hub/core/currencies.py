import math
import re
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Абстрактный базовый класс валюты."""

    def __init__(self, name: str, code: str) -> None:
        """Проверить и сохранить название и код валюты."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")

        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2,5}", code):
            raise ValueError(
                "Код валюты должен содержать от 2 до 5 заглавных латинских букв"
            )

        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Вернуть строковое представление валюты."""


class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны или зоны эмиссии."""

    def __init__(
        self,
        name: str,
        code: str,
        issuing_country: str,
    ) -> None:
        """Инициализировать фиатную валюту."""
        super().__init__(name, code)

        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Страна или зона эмиссии не может быть пустой")

        self.issuing_country = issuing_country.strip()

    def get_display_info(self) -> str:
        """Вернуть информацию о фиатной валюте."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и рыночной капитализацией."""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ) -> None:
        """Инициализировать криптовалюту."""
        super().__init__(name, code)

        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")

        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or not math.isfinite(market_cap)
            or market_cap < 0
        ):
            raise ValueError(
                "Рыночная капитализация должна быть неотрицательным конечным числом"
            )

        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        """Вернуть информацию о криптовалюте."""
        formatted_cap = f"{self.market_cap:.2e}".replace("e+", "e")

        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {formatted_cap})"
        )


# Капитализации ниже — демонстрационные, не актуальные онлайн-данные.
CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Keccak-256", 3.20e11),
}


def get_currency(code: str) -> Currency:
    """Получить валюту из реестра по её коду."""
    if not isinstance(code, str):
        raise CurrencyNotFoundError(str(code))

    normalized_code = code.strip().upper()

    try:
        return CURRENCY_REGISTRY[normalized_code]
    except KeyError as error:
        raise CurrencyNotFoundError(normalized_code) from error
