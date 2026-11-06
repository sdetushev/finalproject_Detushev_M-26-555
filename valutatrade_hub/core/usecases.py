import math
from datetime import datetime, timedelta, timezone

from valutatrade_hub.core import utils
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.models import (
    DEFAULT_EXCHANGE_RATES,
    ExchangeRateNotFoundError,
    Portfolio,
    User,
    Wallet,
)
from valutatrade_hub.decorators import add_log_context, log_action
from valutatrade_hub.infra.settings import SettingsLoader


def register_user(username: str, password: str) -> User:
    """Зарегистрировать пользователя и создать пустой портфель."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    username = username.strip()
    created_user: User | None = None

    def add_user(data: utils.JsonData) -> utils.JsonData:
        """Добавить нового пользователя в JSON-хранилище."""
        nonlocal created_user

        if not isinstance(data, list):
            raise ValueError("Некорректный формат файла пользователей")

        if any(not isinstance(record, dict) for record in data):
            raise ValueError("Некорректная запись в файле пользователей")

        if any(record.get("username") == username for record in data):
            raise ValueError(f"Имя пользователя '{username}' уже занято")

        user_id = (
            max(
                (record["user_id"] for record in data),
                default=0,
            )
            + 1
        )

        user = User.create(
            user_id=user_id,
            username=username,
            password=password,
        )

        created_user = user

        return [
            *data,
            {
                "user_id": user.user_id,
                "username": user.username,
                "hashed_password": user.hashed_password,
                "salt": user.salt,
                "registration_date": user.registration_date.isoformat(),
            },
        ]

    utils.update_json("users.json", add_user)

    if created_user is None:
        raise RuntimeError("Не удалось создать пользователя")

    def add_portfolio(data: utils.JsonData) -> utils.JsonData:
        """Добавить пустой портфель нового пользователя."""
        if not isinstance(data, list):
            raise ValueError("Некорректный формат файла портфелей")

        if any(not isinstance(record, dict) for record in data):
            raise ValueError("Некорректная запись в файле портфелей")

        if any(record.get("user_id") == created_user.user_id for record in data):
            raise ValueError("Портфель пользователя уже существует")

        return [
            *data,
            {
                "user_id": created_user.user_id,
                "wallets": {},
            },
        ]

    try:
        utils.update_json("portfolios.json", add_portfolio)

    except Exception:
        # Компенсация ошибки: удаляем только созданного пользователя.
        def rollback_user(data: utils.JsonData) -> utils.JsonData:
            """Отменить добавление пользователя при ошибке портфеля."""
            if not isinstance(data, list):
                raise ValueError("Некорректный формат файла пользователей")

            return [
                record
                for record in data
                if not (
                    isinstance(record, dict)
                    and record.get("user_id") == created_user.user_id
                )
            ]

        try:
            utils.update_json("users.json", rollback_user)

        except Exception as rollback_error:
            raise RuntimeError(
                "Не удалось отменить регистрацию. "
                "Проверьте users.json и portfolios.json"
            ) from rollback_error

        raise

    return created_user


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
    """Сохранить портфель через безопасное обновление JSON."""
    if not isinstance(portfolio, Portfolio):
        raise TypeError("Портфель должен быть объектом Portfolio")

    wallets_data = {
        currency_code: {"balance": wallet.balance}
        for currency_code, wallet in portfolio.wallets.items()
    }

    def update_portfolios(data: utils.JsonData) -> utils.JsonData:
        """Обновить запись нужного пользователя в списке портфелей."""
        if not isinstance(data, list):
            raise ValueError("Некорректный формат файла портфелей")

        for index, portfolio_data in enumerate(data):
            if not isinstance(portfolio_data, dict):
                raise ValueError("Некорректная запись в файле портфелей")

            if portfolio_data.get("user_id") != portfolio.user_id:
                continue

            data[index] = {
                "user_id": portfolio.user_id,
                "wallets": wallets_data,
            }

            return data

        raise ValueError(f"Портфель пользователя с ID {portfolio.user_id} не найден")

    utils.update_json("portfolios.json", update_portfolios)


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


@log_action("BUY", verbose=True)
def buy_currency(
    user_id: int,
    currency_code: str,
    amount: float,
) -> dict[str, str | float]:
    """Купить валюту без списания USD и безопасно обновить портфель."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным целым числом")

    code = _normalize_currency(currency_code)

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    rate = _get_usd_rate(code, load_usd_rates())
    add_log_context(rate=rate, base="USD")
    estimated_cost_usd = amount * rate

    if not math.isfinite(estimated_cost_usd):
        raise ValueError("Оценочная стоимость покупки слишком велика")

    balances: dict[str, float] = {}

    def update_portfolio(data: utils.JsonData) -> utils.JsonData:
        """Увеличить баланс валюты внутри защищённой операции."""
        if not isinstance(data, list):
            raise ValueError("Некорректный формат файла портфелей")

        for index, portfolio_data in enumerate(data):
            if not isinstance(portfolio_data, dict):
                raise ValueError("Некорректная запись в файле портфелей")

            if portfolio_data.get("user_id") != user_id:
                continue

            wallets_data = portfolio_data.get("wallets")

            if not isinstance(wallets_data, dict):
                raise ValueError("Некорректный формат валютных кошельков")

            wallet_data = wallets_data.get(code)

            if wallet_data is None:
                wallet = Wallet(code)
            else:
                if not isinstance(wallet_data, dict) or "balance" not in wallet_data:
                    raise ValueError(f"Некорректные данные кошелька '{code}'")

                wallet = Wallet(code, wallet_data["balance"])

            balance_before = wallet.balance

            if not math.isfinite(balance_before + amount):
                raise ValueError("Баланс после покупки слишком велик")

            wallet.deposit(amount)

            updated_wallets = {
                **wallets_data,
                code: {"balance": wallet.balance},
            }

            data[index] = {
                **portfolio_data,
                "wallets": updated_wallets,
            }

            balances["before"] = balance_before
            balances["after"] = wallet.balance

            return data

        raise ValueError(f"Портфель пользователя с ID {user_id} не найден")

    utils.update_json("portfolios.json", update_portfolio)

    return {
        "currency_code": code,
        "amount": float(amount),
        "rate": rate,
        "base": "USD",
        "cost_usd": estimated_cost_usd,
        "balance_before": balances["before"],
        "balance_after": balances["after"],
    }


@log_action("SELL", verbose=True)
def sell_currency(
    user_id: int,
    currency_code: str,
    amount: float,
) -> dict[str, str | float]:
    """Продать валюту без начисления USD и безопасно обновить портфель."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным целым числом")

    code = _normalize_currency(currency_code)

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    rate = _get_usd_rate(code, load_usd_rates())
    add_log_context(rate=rate, base="USD")
    estimated_revenue_usd = amount * rate

    if not math.isfinite(estimated_revenue_usd):
        raise ValueError("Оценочная выручка слишком велика")

    balances: dict[str, float] = {}

    def update_portfolio(data: utils.JsonData) -> utils.JsonData:
        """Уменьшить баланс валюты внутри защищённой операции."""
        if not isinstance(data, list):
            raise ValueError("Некорректный формат файла портфелей")

        for index, portfolio_data in enumerate(data):
            if not isinstance(portfolio_data, dict):
                raise ValueError("Некорректная запись в файле портфелей")

            if portfolio_data.get("user_id") != user_id:
                continue

            wallets_data = portfolio_data.get("wallets")

            if not isinstance(wallets_data, dict):
                raise ValueError("Некорректный формат валютных кошельков")

            wallet_data = wallets_data.get(code)

            if wallet_data is None:
                raise ValueError(f"У вас нет кошелька '{code}'")

            if not isinstance(wallet_data, dict) or "balance" not in wallet_data:
                raise ValueError(f"Некорректные данные кошелька '{code}'")

            wallet = Wallet(code, wallet_data["balance"])
            balance_before = wallet.balance

            # Wallet.withdraw выбрасывает InsufficientFundsError,
            # если средств недостаточно.
            wallet.withdraw(amount)

            updated_wallets = {
                **wallets_data,
                code: {"balance": wallet.balance},
            }

            data[index] = {
                **portfolio_data,
                "wallets": updated_wallets,
            }

            balances["before"] = balance_before
            balances["after"] = wallet.balance

            return data

        raise ValueError(f"Портфель пользователя с ID {user_id} не найден")

    utils.update_json("portfolios.json", update_portfolio)

    return {
        "currency_code": code,
        "amount": float(amount),
        "rate": rate,
        "base": "USD",
        "revenue_usd": estimated_revenue_usd,
        "balance_before": balances["before"],
        "balance_after": balances["after"],
    }


def _normalize_currency(currency_code: str) -> str:
    """Проверить валютный код через общую функцию валидации."""
    return utils.normalize_currency_code(currency_code)


def _read_usd_records() -> dict[str, dict[str, str | float]]:
    """Прочитать котировки X_USD и обновить устаревший кэш."""
    now = datetime.now(timezone.utc)
    ttl_seconds = SettingsLoader().get("rates_ttl_seconds")
    ttl = timedelta(seconds=ttl_seconds)

    records: dict[str, dict[str, str | float]] = {
        "USD": {"rate": 1.0, "source": "base_currency"}
    }

    def update_rates(data: utils.JsonData) -> utils.JsonData:
        """Проверить, при необходимости обновить и вернуть данные."""
        if not isinstance(data, dict):
            raise ValueError("Некорректный формат rates.json")

        # Первая инициализация фиксированными котировками.
        if not data:
            data = {
                f"{code}_USD": {
                    "rate": rate,
                    "source": "fixed_snapshot",
                    "snapshot_date": "2026-11-05",
                    "updated_at": now.isoformat(),
                    "saved_at": now.isoformat(),
                }
                for code, rate in DEFAULT_EXCHANGE_RATES.items()
                if code != "USD"
            }

        # Поддержка прежнего формата BTC/USD и USD/BTC.
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

        for code in DEFAULT_EXCHANGE_RATES:
            if code == "USD":
                continue

            entry = data.get(f"{code}_USD")

            if entry is None:
                continue

            if isinstance(entry, (int, float)) and not isinstance(entry, bool):
                record: dict[str, str | float] = {"rate": float(entry)}

            elif isinstance(entry, dict):
                record = entry.copy()

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

            # Проверяем актуальность сохранённой записи.
            saved_at = record.get("saved_at")
            is_fresh = False

            if isinstance(saved_at, str):
                try:
                    saved_time = datetime.fromisoformat(saved_at)

                    if saved_time.tzinfo is not None:
                        age = now - saved_time
                        is_fresh = timedelta(0) <= age < ttl

                except ValueError:
                    pass

            if not is_fresh:
                # До подключения Parser Service используем заглушку.
                try:
                    new_rate = get_stub_rate(code, "USD")

                except Exception as error:
                    raise ApiRequestError(str(error)) from error

                record = {
                    "rate": new_rate,
                    "source": "fixed_snapshot",
                    "snapshot_date": "2026-11-05",
                    "updated_at": now.isoformat(),
                    "saved_at": now.isoformat(),
                }

                data[f"{code}_USD"] = record

            records[code] = record

        return data

    utils.update_json("rates.json", update_rates)

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
    direct_rate = utils.convert_amount(1.0, from_usd, to_usd)
    reverse_rate = utils.convert_amount(1.0, to_usd, from_usd)

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

    update_times: list[datetime] = []

    for code in affected:
        raw_time = records[code].get("updated_at")

        if not isinstance(raw_time, str) or not raw_time:
            break

        try:
            parsed_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            break

        if parsed_time.tzinfo is None:
            break

        update_times.append(parsed_time.astimezone(timezone.utc))

    updated_at = (
        min(update_times).isoformat() if len(update_times) == len(affected) else ""
    )

    return {
        "rate": direct_rate,
        "reverse_rate": reverse_rate,
        "source": sources.pop() if len(sources) == 1 else "mixed_sources",
        "snapshot_date": dates.pop() if len(dates) == 1 else "разные даты",
        "updated_at": updated_at,
        "saved_at": saved_times.pop() if len(saved_times) == 1 else "",
    }
