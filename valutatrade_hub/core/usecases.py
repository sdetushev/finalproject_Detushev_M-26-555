import math
from datetime import datetime, timezone

from valutatrade_hub.core import utils
from valutatrade_hub.core.models import DEFAULT_EXCHANGE_RATES, Portfolio, User, Wallet


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

    raise ValueError(f"Портфель пользователя '{portfolio.user.username}' не найден")


def get_portfolio_summary(
    user: User,
    base_currency: str = "USD",
) -> tuple[list[tuple[str, float, float]], float]:
    """Получить балансы кошельков и их стоимость в базовой валюте."""
    portfolio = load_portfolio(user)

    total_value = portfolio.get_total_value(base_currency)
    rows: list[tuple[str, float, float]] = []

    for currency_code, wallet in portfolio.wallets.items():
        single_wallet_portfolio = Portfolio(
            user=user,
            wallets={currency_code: wallet},
        )

        converted_value = single_wallet_portfolio.get_total_value(base_currency)

        rows.append(
            (
                currency_code,
                wallet.balance,
                converted_value,
            )
        )

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

    if currency_code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Не удалось получить курс для {currency_code}→USD")

    rate = DEFAULT_EXCHANGE_RATES[currency_code]
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

    if currency_code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Не удалось получить курс для {currency_code}→USD")

    rate = DEFAULT_EXCHANGE_RATES[currency_code]
    estimated_revenue_usd = amount * rate

    if not math.isfinite(estimated_revenue_usd):
        raise ValueError("Оценочная выручка слишком велика")

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


def get_stub_rate(from_currency: str, to_currency: str) -> float:
    """Рассчитать тестовый курс между двумя валютами через USD."""
    if (
        not isinstance(from_currency, str)
        or not isinstance(to_currency, str)
        or not from_currency.strip()
        or not to_currency.strip()
    ):
        raise ValueError("Коды валют не могут быть пустыми")

    from_code = from_currency.strip().upper()
    to_code = to_currency.strip().upper()

    if from_code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Неизвестная валюта: {from_code}")

    if to_code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Неизвестная валюта: {to_code}")

    from_rate_usd = DEFAULT_EXCHANGE_RATES[from_code]
    to_rate_usd = DEFAULT_EXCHANGE_RATES[to_code]

    return from_rate_usd / to_rate_usd


def get_rate_info(
    from_currency: str,
    to_currency: str,
) -> dict[str, str | float]:
    """Получить фиксированный курс и сохранить его в JSON."""
    rate = get_stub_rate(from_currency, to_currency)

    from_code = from_currency.strip().upper()
    to_code = to_currency.strip().upper()
    pair = f"{from_code}/{to_code}"

    rates = utils.load_json("rates.json")

    if not isinstance(rates, dict):
        raise ValueError("Некорректный формат rates.json")

    cached = rates.get(pair)

    if (
        isinstance(cached, dict)
        and cached.get("rate") == rate
        and cached.get("source") == "fixed_snapshot"
        and cached.get("snapshot_date") == "2026-11-05"
        and isinstance(cached.get("saved_at"), str)
    ):
        return cached

    rate_info = {
        "rate": rate,
        "source": "fixed_snapshot",
        "snapshot_date": "2026-11-05",
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    rates[pair] = rate_info
    utils.save_json("rates.json", rates)

    return rate_info
