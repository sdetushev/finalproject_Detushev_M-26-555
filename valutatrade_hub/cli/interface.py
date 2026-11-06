import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCY_REGISTRY
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import (
    buy_currency,
    get_portfolio_summary,
    get_rate_info,
    login_user,
    register_user,
    sell_currency,
)
from valutatrade_hub.infra.settings import SettingsLoader


def print_currency_error(error: CurrencyNotFoundError) -> None:
    """Показать ошибку валюты и список поддерживаемых кодов."""
    print(error)
    print("Поддерживаемые валюты: " + ", ".join(sorted(CURRENCY_REGISTRY)))


def print_api_error(error: ApiRequestError) -> None:
    """Показать сообщение о недоступности источника курсов."""
    print(error)
    print("Повторите попытку позже или проверьте подключение к сети.")


def parse_auth_args(args: list[str], command: str) -> tuple[str, str]:
    """Разобрать аргументы регистрации или авторизации."""
    usage = f"Использование: {command} --username <имя> --password <пароль>"

    if len(args) != 4:
        raise ValueError(usage)

    options: dict[str, str] = {}

    for index in range(0, len(args), 2):
        option = args[index]
        value = args[index + 1]

        if option not in ("--username", "--password"):
            raise ValueError(usage)

        if option in options:
            raise ValueError(f"Аргумент '{option}' указан повторно")

        options[option] = value

    if "--username" not in options or "--password" not in options:
        raise ValueError(usage)

    return options["--username"], options["--password"]


def handle_register(args: list[str]) -> None:
    """Обработать регистрацию пользователя."""
    try:
        username, password = parse_auth_args(args, "register")
        user = register_user(username, password)

        print(f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}).")

    except ValueError as error:
        print(error)


def handle_login(args: list[str]) -> User | None:
    """Авторизовать пользователя и вернуть его объект."""
    try:
        username, password = parse_auth_args(args, "login")
        user = login_user(username, password)

        print(f"Вы вошли как '{user.username}'")
        return user

    except ValueError as error:
        print(error)
        return None


def parse_portfolio_args(args: list[str]) -> str:
    """Разобрать базовую валюту для просмотра портфеля."""
    if not args:
        return SettingsLoader().get("default_base_currency").strip().upper()

    if len(args) != 2 or args[0] != "--base":
        raise ValueError("Использование: show-portfolio [--base <валюта>]")

    base_currency = args[1].strip().upper()

    if not base_currency:
        raise ValueError("Код базовой валюты не может быть пустым")

    return base_currency


def parse_trade_args(args: list[str], command: str) -> tuple[str, float]:
    """Разобрать аргументы команды покупки или продажи валюты."""
    usage = f"Использование: {command} --currency <валюта> --amount <количество>"

    if len(args) != 4:
        raise ValueError(usage)

    options: dict[str, str] = {}

    for index in range(0, len(args), 2):
        option = args[index]
        value = args[index + 1]

        if option not in ("--currency", "--amount"):
            raise ValueError(usage)

        if option in options:
            raise ValueError(f"Аргумент '{option}' указан повторно")

        options[option] = value

    if "--currency" not in options or "--amount" not in options:
        raise ValueError(usage)

    try:
        amount = float(options["--amount"])
    except ValueError:
        raise ValueError("'amount' должен быть положительным числом") from None

    return options["--currency"], amount


def parse_rate_args(args: list[str]) -> tuple[str, str]:
    """Разобрать параметры команды получения валютного курса."""
    usage = "Использование: get-rate --from <валюта> --to <валюта>"

    if len(args) != 4:
        raise ValueError(usage)

    options: dict[str, str] = {}

    for index in range(0, len(args), 2):
        flag = args[index]
        value = args[index + 1].strip()

        if flag not in ("--from", "--to") or flag in options or not value:
            raise ValueError(usage)

        options[flag] = value.upper()

    if set(options) != {"--from", "--to"}:
        raise ValueError(usage)

    return options["--from"], options["--to"]


def handle_show_portfolio(args: list[str], user: User | None) -> None:
    """Отобразить валютные кошельки авторизованного пользователя."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        base_currency = parse_portfolio_args(args)
        rows, total = get_portfolio_summary(user, base_currency)

    except CurrencyNotFoundError as error:
        if error.code == base_currency:
            print(f"Неизвестная базовая валюта '{error.code}'")
        else:
            print_currency_error(error)
        return

    except ApiRequestError as error:
        print_api_error(error)
        return

    except (ValueError, TypeError) as error:
        print(error)
        return

    print(f"Портфель пользователя '{user.username}' (база: {base_currency}):")

    if not rows:
        print("В портфеле пока нет кошельков.")

    else:
        table = PrettyTable()
        table.field_names = [
            "Валюта",
            "Баланс",
            f"Стоимость ({base_currency})",
        ]

        for currency_code, balance, value in rows:
            table.add_row(
                [
                    currency_code,
                    f"{balance:.4f}",
                    f"{value:,.2f}",
                ]
            )

        print(table)

    print(f"ИТОГО: {total:,.2f} {base_currency}")


def handle_buy(args: list[str], user: User | None) -> None:
    """Обработать команду покупки валюты."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        currency_code, amount = parse_trade_args(args, "buy")
        result = buy_currency(user.user_id, currency_code, amount)

    except CurrencyNotFoundError as error:
        print_currency_error(error)
        return

    except ApiRequestError as error:
        print_api_error(error)
        return

    except (ValueError, TypeError) as error:
        print(error)
        return

    print(
        f"Покупка выполнена: "
        f"{result['amount']:.4f} {result['currency_code']} "
        f"по курсу {result['rate']:.8g} USD"
    )

    print("Изменения в портфеле:")
    print(
        f"- {result['currency_code']}: "
        f"было {result['balance_before']:.4f} → "
        f"стало {result['balance_after']:.4f}"
    )

    print(f"Оценочная стоимость покупки: {result['cost_usd']:.2f} USD")


def handle_sell(args: list[str], user: User | None) -> None:
    """Обработать команду продажи валюты."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        currency_code, amount = parse_trade_args(args, "sell")
        result = sell_currency(user.user_id, currency_code, amount)

    except InsufficientFundsError as error:
        print(error)
        return

    except CurrencyNotFoundError as error:
        print_currency_error(error)
        return

    except ApiRequestError as error:
        print_api_error(error)
        return

    except (ValueError, TypeError) as error:
        print(error)
        return

    print(
        f"Продажа выполнена: "
        f"{result['amount']:.4f} {result['currency_code']} "
        f"по курсу {result['rate']:.8g} USD"
    )

    print("Изменения в портфеле:")
    print(
        f"- {result['currency_code']}: "
        f"было {result['balance_before']:.4f} → "
        f"стало {result['balance_after']:.4f}"
    )

    print(f"Оценочная выручка от продажи: {result['revenue_usd']:.2f} USD")


def handle_get_rate(args: list[str]) -> None:
    """Показать прямой и обратный курсы без промежуточного округления."""
    try:
        from_code, to_code = parse_rate_args(args)
        result = get_rate_info(from_code, to_code)

    except CurrencyNotFoundError as error:
        print_currency_error(error)
        return

    except ApiRequestError as error:
        print_api_error(error)
        return

    except (ValueError, TypeError) as error:
        print(error)
        return

    def format_rate(rate: float) -> str:
        """Форматировать валютный курс без лишних знаков."""
        precision = 8 if rate >= 1 else 12
        text = f"{rate:.{precision}f}".rstrip("0").rstrip(".")
        return text if text and text != "0" else f"{rate:.12g}"

    print(f"Курс {from_code}→{to_code}: {format_rate(result['rate'])}")
    print(f"Обратный курс {to_code}→{from_code}: {format_rate(result['reverse_rate'])}")

    source = result["source"]
    if source == "fixed_snapshot":
        print("Источник: фиксированные котировки (не онлайн)")
    else:
        print(f"Источник: {source}")

    if result["snapshot_date"]:
        print(f"Дата снимка котировок: {result['snapshot_date']}")

    if result["updated_at"]:
        print(f"Время получения исходных курсов: {result['updated_at']} (UTC)")

    if result["saved_at"]:
        print(f"Время сохранения в JSON: {result['saved_at']} (UTC)")


def run_cli() -> None:
    """Запустить интерактивный интерфейс валютного кошелька."""
    current_user: User | None = None

    print("Валютный кошелёк")
    print(
        "Доступные команды: register, login, show-portfolio, "
        "buy, sell, get-rate, help, exit"
    )

    while True:
        prompt = (
            f"\n{current_user.username}> "
            if current_user is not None
            else "\nВведите команду: "
        )

        try:
            command = input(prompt).strip()

        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение работы.")
            break

        if not command:
            continue

        try:
            parts = shlex.split(command)

        except ValueError:
            print("Некорректный формат команды. Проверьте кавычки.")
            continue

        if not parts:
            continue

        action = parts[0]
        args = parts[1:]

        if action == "register":
            handle_register(args)

        elif action == "login":
            user = handle_login(args)

            if user is not None:
                current_user = user

        elif action == "show-portfolio":
            handle_show_portfolio(args, current_user)

        elif action == "buy":
            handle_buy(args, current_user)

        elif action == "sell":
            handle_sell(args, current_user)

        elif action == "get-rate":
            handle_get_rate(args)

        elif action == "help":
            print("register --username <имя> --password <пароль>")
            print("login --username <имя> --password <пароль>")
            print("show-portfolio [--base <валюта>]")
            print("buy --currency <валюта> --amount <количество>")
            print("sell --currency <валюта> --amount <количество>")
            print("get-rate --from <валюта> --to <валюта>")
            print("help — показать доступные команды")
            print("exit — завершить работу")

        elif action == "exit":
            print("Завершение работы.")
            break

        else:
            print(f"Неизвестная команда '{action}'. Введите help.")
