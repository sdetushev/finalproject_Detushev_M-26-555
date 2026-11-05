import hashlib
import hmac
import math
import secrets
from datetime import datetime, timezone

DEFAULT_EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.1267,
    "BTC": 80442.71,
    "RUB": 1 / 81.6699,
    "ETH": 2424.46,
}


class CurrencyNotFoundError(ValueError):
    """Неизвестный код валюты."""


class ExchangeRateNotFoundError(ValueError):
    """Отсутствует курс для поддерживаемой валюты."""


class User:
    """Представлять пользователя валютной платформы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        """Инициализировать пользователя по его данным."""
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")

        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не может быть пустым")

        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не может быть пустой")

        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации должна иметь тип datetime")

        self._user_id = user_id
        self._username = ""
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создать пользователя с хешированным паролем и уникальной солью."""
        cls._validate_password(password)

        salt = secrets.token_hex(16)
        hashed_password = cls._hash_password(password, salt)

        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=datetime.now(timezone.utc),
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        """Проверить корректность пароля."""
        if not isinstance(password, str) or len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Вычислить SHA-256 хеш пароля с солью."""
        return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

    @property
    def user_id(self) -> int:
        """Вернуть идентификатор пользователя."""
        return self._user_id

    @property
    def username(self) -> str:
        """Вернуть имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Установить имя пользователя после проверки."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Вернуть хеш пароля для сохранения пользователя."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Вернуть соль для сохранения пользователя."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Вернуть дату регистрации пользователя."""
        return self._registration_date

    def get_user_info(self) -> dict[str, int | str]:
        """Вернуть информацию о пользователе без пароля."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Изменить пароль, создав новую соль и хеш."""
        self._validate_password(new_password)

        self._salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверить соответствие пароля сохранённому хешу."""
        if not isinstance(password, str):
            return False

        password_hash = self._hash_password(password, self._salt)

        return hmac.compare_digest(password_hash, self._hashed_password)


class Wallet:
    """Представлять кошелёк пользователя для одной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        """Инициализировать кошелёк с указанной валютой и балансом."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        self.currency_code = currency_code.strip().upper()
        self._balance = 0.0
        self.balance = balance

    @staticmethod
    def _validate_amount(amount: float) -> None:
        """Проверить, что сумма является положительным конечным числом."""
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount <= 0
        ):
            raise ValueError("Сумма должна быть положительным числом")

    @property
    def balance(self) -> float:
        """Вернуть текущий баланс кошелька."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Установить баланс после проверки значения."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")

        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом")

        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")

        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополнить баланс кошелька на указанную сумму."""
        self._validate_amount(amount)
        self.balance += amount

    def withdraw(self, amount: float) -> None:
        """Снять средства с кошелька при достаточном балансе."""
        self._validate_amount(amount)

        if amount > self.balance:
            raise ValueError(
                f"Недостаточно средств: доступно {self.balance:.4f} "
                f"{self.currency_code}, требуется {amount:.4f} "
                f"{self.currency_code}"
            )

        self.balance -= amount

    def get_balance_info(self) -> dict[str, str | float]:
        """Вернуть информацию о валюте и текущем балансе."""
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }


class Portfolio:
    """Управлять валютными кошельками одного пользователя."""

    def __init__(
        self,
        user_id: int | User | None = None,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        """Создать портфель по ID с необязательным объектом пользователя."""
        # Поддержка прежнего вызова Portfolio(user, wallets=...).
        if isinstance(user_id, User):
            if user is not None:
                raise ValueError("Пользователь передан дважды")
            user = user_id
            user_id = user.user_id

        if user is not None and not isinstance(user, User):
            raise TypeError("Пользователь должен быть объектом User")

        if user_id is None and user is not None:
            user_id = user.user_id

        if type(user_id) is not int or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")

        if user is not None and user.user_id != user_id:
            raise ValueError("ID пользователя не соответствует портфелю")

        self._user_id = user_id
        self._user = user
        self._wallets: dict[str, Wallet] = {}

        if wallets is not None:
            if not isinstance(wallets, dict):
                raise TypeError("Кошельки должны быть представлены словарём")

            for currency_code, wallet in wallets.items():
                if not isinstance(wallet, Wallet):
                    raise TypeError("Значение должно быть объектом Wallet")

                if currency_code != wallet.currency_code:
                    raise ValueError("Код валюты не соответствует кошельку")

                self._wallets[currency_code] = wallet

    @property
    def user(self) -> User | None:
        """Вернуть объект владельца портфеля, если он передан."""
        return self._user

    @property
    def user_id(self) -> int:
        """Вернуть идентификатор владельца портфеля."""
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Вернуть копию словаря валютных кошельков."""
        return self._wallets.copy()

    @staticmethod
    def _validate_currency_code(currency_code: str) -> str:
        """Проверить и нормализовать код валюты."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        return currency_code.strip().upper()

    def add_currency(self, currency_code: str) -> None:
        """Добавить новый валютный кошелёк в портфель."""
        code = self._validate_currency_code(currency_code)

        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует")

        self._wallets[code] = Wallet(currency_code=code)

    def get_wallet(self, currency_code: str) -> Wallet:
        """Вернуть кошелёк по указанному коду валюты."""
        code = self._validate_currency_code(currency_code)

        if code not in self._wallets:
            raise ValueError(f"Кошелёк '{code}' не найден")

        return self._wallets[code]

    def get_total_value(
        self,
        base_currency: str = "USD",
        rates: dict[str, float | dict[str, str | float]] | None = None,
        *,
        exchange_rates: dict[str, float | dict[str, str | float]] | None = None,
    ) -> float:
        """Рассчитать стоимость портфеля по курсам валют относительно USD."""
        base_code = self._validate_currency_code(base_currency)

        if base_code not in DEFAULT_EXCHANGE_RATES:
            raise CurrencyNotFoundError(f"Неизвестная базовая валюта '{base_code}'")

        if rates is not None and exchange_rates is not None:
            raise ValueError("Передайте только rates или exchange_rates")

        if rates is None:
            rates = exchange_rates

        if rates is None:
            rates = DEFAULT_EXCHANGE_RATES

        if not isinstance(rates, dict):
            raise TypeError("Курсы валют должны быть представлены словарём")

        def price_in_usd(code: str) -> float:
            """Проверить курс валюты относительно USD."""
            if code == "USD":
                return 1.0

            # Принимаем подготовленный словарь и пары вида BTC_USD.
            if code in rates:
                rate = rates[code]
            elif f"{code}_USD" in rates:
                rate = rates[f"{code}_USD"]
            else:
                raise ExchangeRateNotFoundError(f"Не найден курс {code}→USD")

            if isinstance(rate, dict):
                rate = rate.get("rate")
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(rate)
                or rate <= 0
            ):
                raise ValueError(f"Некорректный курс валюты '{code}'")

            return float(rate)

        base_rate = price_in_usd(base_code)
        total_usd = 0.0

        for wallet in self._wallets.values():
            code = wallet.currency_code
            if code not in DEFAULT_EXCHANGE_RATES:
                raise CurrencyNotFoundError(f"Неизвестная валюта '{code}'")
            total_usd += wallet.balance * price_in_usd(code)

        total = total_usd / base_rate
        if not math.isfinite(total):
            raise ValueError("Стоимость портфеля слишком велика")

        return total
