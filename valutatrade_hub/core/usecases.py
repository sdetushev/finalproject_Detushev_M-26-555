import math
from datetime import datetime

from valutatrade_hub.core import utils
from valutatrade_hub.core.models import DEFAULT_EXCHANGE_RATES, Portfolio, User, Wallet


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
    """Купить валюту за USD и сохранить обновлённый портфель."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    code = currency_code.strip().upper()

    if code == "USD":
        raise ValueError("Покупка USD за USD не поддерживается")

    if code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Не удалось получить курс для {code}→USD")

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    rate = DEFAULT_EXCHANGE_RATES[code]
    cost_usd = amount * rate

    if not math.isfinite(cost_usd) or cost_usd <= 0:
        raise ValueError("Некорректная стоимость покупки")

    portfolio = load_portfolio(user)

    try:
        usd_wallet = portfolio.get_wallet("USD")
    except ValueError:
        raise ValueError("В портфеле отсутствует USD-кошелёк") from None

    if usd_wallet.balance < cost_usd:
        raise ValueError(
            f"Недостаточно средств: доступно {usd_wallet.balance:.2f} USD, "
            f"требуется {cost_usd:.2f} USD"
        )

    try:
        currency_wallet = portfolio.get_wallet(code)
    except ValueError:
        portfolio.add_currency(code)
        currency_wallet = portfolio.get_wallet(code)

    balance_before = currency_wallet.balance

    if not math.isfinite(balance_before + amount):
        raise ValueError("Баланс после покупки слишком велик")

    usd_wallet.withdraw(cost_usd)
    currency_wallet.deposit(amount)

    save_portfolio(portfolio)

    return {
        "currency_code": code,
        "amount": float(amount),
        "rate": rate,
        "cost_usd": cost_usd,
        "balance_before": balance_before,
        "balance_after": currency_wallet.balance,
        "usd_balance_after": usd_wallet.balance,
    }


def sell_currency(
    user: User,
    currency_code: str,
    amount: float,
) -> dict[str, str | float]:
    """Продать валюту за USD и сохранить обновлённый портфель."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")

    code = currency_code.strip().upper()

    if code == "USD":
        raise ValueError("Продажа USD за USD не поддерживается")

    if code not in DEFAULT_EXCHANGE_RATES:
        raise ValueError(f"Не удалось получить курс для {code}→USD")

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    rate = DEFAULT_EXCHANGE_RATES[code]
    revenue_usd = amount * rate

    if not math.isfinite(revenue_usd) or revenue_usd <= 0:
        raise ValueError("Некорректная стоимость продажи")

    portfolio = load_portfolio(user)

    try:
        currency_wallet = portfolio.get_wallet(code)
    except ValueError:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            "Добавьте валюту: она создаётся автоматически при первой покупке."
        ) from None

    if currency_wallet.balance < amount:
        raise ValueError(
            f"Недостаточно средств: доступно "
            f"{currency_wallet.balance:.4f} {code}, "
            f"требуется {amount:.4f} {code}"
        )

    try:
        usd_wallet = portfolio.get_wallet("USD")
    except ValueError:
        portfolio.add_currency("USD")
        usd_wallet = portfolio.get_wallet("USD")

    if not math.isfinite(usd_wallet.balance + revenue_usd):
        raise ValueError("Баланс USD после продажи слишком велик")

    balance_before = currency_wallet.balance

    currency_wallet.withdraw(amount)
    usd_wallet.deposit(revenue_usd)

    save_portfolio(portfolio)

    return {
        "currency_code": code,
        "amount": float(amount),
        "rate": rate,
        "revenue_usd": revenue_usd,
        "balance_before": balance_before,
        "balance_after": currency_wallet.balance,
        "usd_balance_after": usd_wallet.balance,
    }
