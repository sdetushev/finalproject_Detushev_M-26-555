import math
from datetime import datetime, timedelta, timezone

from valutatrade_hub.core import utils
from valutatrade_hub.core.models import (
    DEFAULT_EXCHANGE_RATES,
    CurrencyNotFoundError,
    ExchangeRateNotFoundError,
    Portfolio,
    User,
    Wallet,
)


class InsufficientFundsError(ValueError):
    """Ошибка отсутствия кошелька или недостаточности средств."""


def register_user(username: str, password: str) -> User:
    """Зарегистрировать пользователя и создать пустой портфель."""
    utils.initialize_storage()

    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    username = username.strip()

    users = utils.load_json("users.json")
    portfolios = utils.load_json("portfolios.json")

    if not isinstance(users, list):
        raise ValueError("Некорректный формат файла пользователей")

    if not isinstance(portfolios, list):
        raise ValueError("Некорректный формат файла портфелей")

    if any(user["username"] == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = (
        max(
            (user["user_id"] for user in users),
            default=0,
        )
        + 1
    )

    user = User.create(
        user_id=user_id,
        username=username,
        password=password,
    )

    users.append(
        {
            "user_id": user.user_id,
            "username": user.username,
            "hashed_password": user.hashed_password,
            "salt": user.salt,
            "registration_date": user.registration_date.isoformat(),
        }
    )

    portfolios.append(
        {
            "user_id": user.user_id,
            "wallets": {},
        }
    )

    utils.save_json("users.json", users)
    utils.save_json("portfolios.json", portfolios)

    return user


def login_user(username: str, password: str) -> User:
    """Авторизовать пользователя по имени и паролю."""
    utils.initialize_storage()

    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    username = username.strip()
    users = utils.load_json("users.json")

    if not isinstance(users, list):
        raise ValueError("Некорректный формат файла пользователей")

    for user_data in users:
        if user_data["username"] != username:
            continue

        user = User(
            user_id=user_data["user_id"],
            username=user_data["username"],
            hashed_password=user_data["hashed_password"],
            salt=user_data["salt"],
            registration_date=datetime.fromisoformat(user_data["registration_date"]),
        )

        if not user.verify_password(password):
            raise ValueError("Неверный пароль")

        return user

    raise ValueError(f"Пользователь '{username}' не найден")


def load_portfolio(user: User) -> Portfolio:
    """Загрузить портфель пользователя из JSON-хранилища."""
    if not isinstance(user, User):
        raise TypeError("Пользователь должен быть объектом User")

    utils.initialize_storage()
    portfolios = utils.load_json("portfolios.json")

    if not isinstance(portfolios, list):
        raise ValueError("Некорректный формат файла портфелей")

    for portfolio_data in portfolios:
        if not isinstance(portfolio_data, dict):
            raise ValueError("Некорректная запись в файле портфелей")

        if portfolio_data.get("user_id") != user.user_id:
            continue

        wallets_data = portfolio_data.get("wallets")

        if not isinstance(wallets_data, dict):
            raise ValueError("Некорректный формат валютных кошельков")

        wallets: dict[str, Wallet] = {}

        for currency_code, wallet_data in wallets_data.items():
            if not isinstance(wallet_data, dict) or "balance" not in wallet_data:
                raise ValueError(f"Некорректные данные кошелька '{currency_code}'")

            wallets[currency_code] = Wallet(
                currency_code=currency_code,
                balance=wallet_data["balance"],
            )

        return Portfolio(user=user, wallets=wallets)

    raise ValueError(f"Портфель пользователя '{user.username}' не найден")


def save_portfolio(portfolio: Portfolio) -> None:
    """Сохранить валютные кошельки пользователя в JSON."""
    if not isinstance(portfolio, Portfolio):
        raise TypeError("Портфель должен быть объектом Portfolio")

    utils.initialize_storage()
    portfolios = utils.load_json("portfolios.json")

    if not isinstance(portfolios, list):
        raise ValueError("Некорректный формат файла портфелей")

    for index, portfolio_data in enumerate(portfolios):
        if not isinstance(portfolio_data, dict):
            raise ValueError("Некорректная запись в файле портфелей")

        if portfolio_data.get("user_id") != portfolio.user_id:
            continue

        wallets_data = {
            currency_code: {"balance": wallet.balance}
            for currency_code, wallet in portfolio.wallets.items()
        }

        portfolios[index] = {
            "user_id": portfolio.user_id,
            "wallets": wallets_data,
        }

        utils.save_json("portfolios.json", portfolios)
        return

    raise ValueError(f"Портфель пользователя с ID {portfolio.user_id} не найден")


def get_portfolio_summary(
    user: User,
    base_currency: str = "USD",
) -> tuple[list[tuple[str, float, float]], float]:
    """Получить балансы и стоимость портфеля по курсам из JSON."""
    portfolio = load_portfolio(user)
    usd_rates = load_usd_rates()

    # Валидация базовой валюты выполняется даже при пустом портфеле.
    total_value = portfolio.get_total_value(base_currency, rates=usd_rates)
    rows: list[tuple[str, float, float]] = []

    for currency_code, wallet in portfolio.wallets.items():
        single_wallet_portfolio = Portfolio(
            user_id=user.user_id,
            user=user,
            wallets={currency_code: wallet},
        )
        converted_value = single_wallet_portfolio.get_total_value(
            base_currency, rates=usd_rates
        )
        rows.append((currency_code, wallet.balance, converted_value))

    return rows, total_value


def buy_currency(
    user: User,
    currency_code: str,
    amount: float,
) -> dict[str, str | float]:
    """Купить валюту без списания средств с USD-кошелька."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    currency_code = currency_code.strip().upper()

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    rate = _get_usd_rate(currency_code, load_usd_rates())
    estimated_cost_usd = amount * rate

    if not math.isfinite(estimated_cost_usd):
        raise ValueError("Оценочная стоимость покупки слишком велика")

    portfolio = load_portfolio(user)

    try:
        wallet = portfolio.get_wallet(currency_code)
    except ValueError:
        portfolio.add_currency(currency_code)
        wallet = portfolio.get_wallet(currency_code)

    balance_before = wallet.balance

    if not math.isfinite(balance_before + amount):
        raise ValueError("Баланс после покупки слишком велик")

    wallet.deposit(amount)
    save_portfolio(portfolio)

    return {
        "currency_code": currency_code,
        "amount": float(amount),
        "rate": rate,
        "cost_usd": estimated_cost_usd,
        "balance_before": balance_before,
        "balance_after": wallet.balance,
    }


def sell_currency(
    user: User,
    currency_code: str,
    amount: float,
) -> dict[str, str | float]:
    """Продать валюту без начисления средств на USD-кошелёк."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    currency_code = currency_code.strip().upper()

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    _normalize_currency(currency_code)
    portfolio = load_portfolio(user)

    try:
        wallet = portfolio.get_wallet(currency_code)
    except ValueError:
        raise InsufficientFundsError(f"У вас нет кошелька '{currency_code}'") from None

    balance_before = wallet.balance

    if balance_before < amount:
        raise InsufficientFundsError(
            f"Недостаточно средств: доступно "
            f"{balance_before:.8g} {currency_code}, "
            f"запрошено {amount:.8g} {currency_code}"
        )

    rate = _get_usd_rate(currency_code, load_usd_rates())
    estimated_revenue_usd = amount * rate

    if not math.isfinite(estimated_revenue_usd):
        raise ValueError("Оценочная выручка слишком велика")

    wallet.withdraw(amount)
    save_portfolio(portfolio)

    return {
        "currency_code": currency_code,
        "amount": float(amount),
        "rate": rate,
        "revenue_usd": estimated_revenue_usd,
        "balance_before": balance_before,
        "balance_after": wallet.balance,
    }


def _normalize_currency(currency_code: str) -> str:
    """Проверить, что валюта есть в реестре поддерживаемых."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    code = currency_code.strip().upper()
    if code not in DEFAULT_EXCHANGE_RATES:
        raise CurrencyNotFoundError(f"Неизвестная валюта: {code}")

    return code


def _read_usd_records() -> dict[str, dict[str, str | float]]:
    """Прочитать котировки X_USD и обновить устаревший кэш."""
    utils.initialize_storage()
    data = utils.load_json("rates.json")

    if not isinstance(data, dict):
        raise ValueError("Некорректный формат rates.json")

    # Первая инициализация — фиксированные котировки, не онлайн-обновление.
    if not data:
        data = {
            f"{code}_USD": {
                "rate": rate,
                "source": "fixed_snapshot",
                "snapshot_date": "2026-11-05",
            }
            for code, rate in DEFAULT_EXCHANGE_RATES.items()
            if code != "USD"
        }
        utils.save_json("rates.json", data)

    # Совместимость со старым кэшем вида BTC/USD, USD/BTC и EUR/RUB.
    elif any("/" in key for key in data) and not any(
        key.endswith("_USD") for key in data
    ):
        migrated = {
            f"{code}_USD": {
                "rate": rate,
                "source": "fixed_snapshot",
                "snapshot_date": "2026-11-05",
            }
            for code, rate in DEFAULT_EXCHANGE_RATES.items()
            if code != "USD"
        }

        for code in DEFAULT_EXCHANGE_RATES:
            if code == "USD":
                continue

            direct = data.get(f"{code}/USD")
            inverse = data.get(f"USD/{code}")

            if isinstance(direct, dict) and "rate" in direct:
                migrated[f"{code}_USD"] = direct.copy()

            elif isinstance(inverse, dict) and "rate" in inverse:
                inverse_rate = inverse["rate"]

                if (
                    isinstance(inverse_rate, bool)
                    or not isinstance(inverse_rate, (int, float))
                    or not math.isfinite(inverse_rate)
                    or inverse_rate <= 0
                ):
                    raise ValueError(f"Некорректный курс валюты '{code}'")

                record = inverse.copy()
                record["rate"] = 1 / inverse_rate
                migrated[f"{code}_USD"] = record

        data = migrated
        utils.save_json("rates.json", data)

    records: dict[str, dict[str, str | float]] = {
        "USD": {"rate": 1.0, "source": "base_currency"}
    }

    for code in DEFAULT_EXCHANGE_RATES:
        if code == "USD":
            continue

        entry = data.get(f"{code}_USD")

        if entry is None:
            continue

        if isinstance(entry, (int, float)) and not isinstance(entry, bool):
            record: dict[str, str | float] = {"rate": entry}

        elif isinstance(entry, dict):
            record = entry

        else:
            raise ValueError(f"Некорректная запись курса {code}_USD")

        rate = record.get("rate")

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ValueError(f"Некорректный курс валюты '{code}'")

        records[code] = record

    # Проверяем срок актуальности локального кэша.
    now = datetime.now(timezone.utc)
    cache_changed = False

    for code, record in records.items():
        if code == "USD":
            continue

        saved_at = record.get("saved_at")
        is_fresh = False

        if isinstance(saved_at, str):
            try:
                saved_time = datetime.fromisoformat(saved_at)

                if saved_time.tzinfo is not None:
                    age = now - saved_time
                    is_fresh = timedelta(0) <= age < timedelta(minutes=5)

            except ValueError:
                pass

        if is_fresh:
            continue

        # Пока Parser Service отсутствует, используем заглушку.
        fresh_record: dict[str, str | float] = {
            "rate": DEFAULT_EXCHANGE_RATES[code],
            "source": "fixed_snapshot",
            "snapshot_date": "2026-11-05",
            "saved_at": now.isoformat(),
        }

        data[f"{code}_USD"] = fresh_record
        records[code] = fresh_record
        cache_changed = True

    if cache_changed:
        utils.save_json("rates.json", data)

    return records


def load_usd_rates() -> dict[str, float]:
    """Вернуть курсы поддерживаемых валют в USD из rates.json."""
    records = _read_usd_records()
    return {code: float(record["rate"]) for code, record in records.items()}


def _get_usd_rate(code: str, rates: dict[str, float]) -> float:
    """Получить долларовую котировку поддерживаемой валюты."""
    code = _normalize_currency(code)
    if code not in rates:
        raise ExchangeRateNotFoundError(f"Не найден курс {code}→USD")
    return rates[code]


def get_stub_rate(from_currency: str, to_currency: str) -> float:
    """Рассчитать курс по фиксированным значениям без обращения к файлам."""
    from_code = _normalize_currency(from_currency)
    to_code = _normalize_currency(to_currency)
    return DEFAULT_EXCHANGE_RATES[from_code] / DEFAULT_EXCHANGE_RATES[to_code]


def get_rate_info(
    from_currency: str,
    to_currency: str,
) -> dict[str, str | float]:
    """Получить прямой и обратный курсы из сохранённых котировок USD."""
    from_code = _normalize_currency(from_currency)
    to_code = _normalize_currency(to_currency)
    records = _read_usd_records()
    rates = {code: float(record["rate"]) for code, record in records.items()}

    from_usd = _get_usd_rate(from_code, rates)
    to_usd = _get_usd_rate(to_code, rates)
    direct_rate = from_usd / to_usd
    reverse_rate = to_usd / from_usd

    if not math.isfinite(direct_rate) or not math.isfinite(reverse_rate):
        raise ValueError("Не удалось рассчитать курс валютной пары")

    # Для USD↔X источник и дата определяются котировкой X_USD.
    # Для X↔Y даты обоих исходных курсов должны совпадать.
    affected = [code for code in (from_code, to_code) if code != "USD"]
    if not affected:
        affected = ["USD"]
    sources = {str(records[code].get("source", "unknown")) for code in affected}
    dates = {str(records[code].get("snapshot_date", "")) for code in affected}
    saved_times = {str(records[code].get("saved_at", "")) for code in affected}

    return {
        "rate": direct_rate,
        "reverse_rate": reverse_rate,
        "source": sources.pop() if len(sources) == 1 else "mixed_sources",
        "snapshot_date": dates.pop() if len(dates) == 1 else "разные даты",
        "saved_at": saved_times.pop() if len(saved_times) == 1 else "",
    }
