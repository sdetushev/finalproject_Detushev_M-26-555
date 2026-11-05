import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import (
    buy_currency,
    get_portfolio_summary,
    login_user,
    register_user,
    sell_currency,
)


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
        return "USD"

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


def handle_show_portfolio(args: list[str], user: User | None) -> None:
    """Отобразить валютные кошельки авторизованного пользователя."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        base_currency = parse_portfolio_args(args)
        rows, total = get_portfolio_summary(user, base_currency)

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
    """Обработать покупку валюты авторизованным пользователем."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        currency_code, amount = parse_trade_args(args, "buy")
        result = buy_currency(user, currency_code, amount)

    except (ValueError, TypeError) as error:
        print(error)
        return

    print(
        f"Покупка выполнена: {result['amount']:.4f} "
        f"{result['currency_code']} по курсу "
        f"{result['rate']:.2f} USD/{result['currency_code']}"
    )

    print("Изменения в портфеле:")
    print(
        f"- {result['currency_code']}: "
        f"было {result['balance_before']:.4f} → "
        f"стало {result['balance_after']:.4f}"
    )

    print(f"Стоимость покупки: {result['cost_usd']:,.2f} USD")
    print(f"Остаток USD: {result['usd_balance_after']:,.2f} USD")


def handle_sell(args: list[str], user: User | None) -> None:
    """Обработать продажу валюты авторизованным пользователем."""
    if user is None:
        print("Сначала выполните login")
        return

    try:
        currency_code, amount = parse_trade_args(args, "sell")
        result = sell_currency(user, currency_code, amount)

    except (ValueError, TypeError) as error:
        print(error)
        return

    print(
        f"Продажа выполнена: {result['amount']:.4f} "
        f"{result['currency_code']} по курсу "
        f"{result['rate']:.2f} USD/{result['currency_code']}"
    )

    print("Изменения в портфеле:")
    print(
        f"- {result['currency_code']}: "
        f"было {result['balance_before']:.4f} → "
        f"стало {result['balance_after']:.4f}"
    )

    print(f"Выручка от продажи: {result['revenue_usd']:,.2f} USD")
    print(f"Баланс USD: {result['usd_balance_after']:,.2f} USD")


def run_cli() -> None:
    """Запустить интерактивный интерфейс валютного кошелька."""
    current_user: User | None = None

    print("Валютный кошелёк")
    print("Доступные команды: register, login, show-portfolio, buy, sell, help, exit")

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

        elif action == "help":
            print("register --username <имя> --password <пароль>")
            print("login --username <имя> --password <пароль>")
            print("show-portfolio [--base <валюта>]")
            print("buy --currency <валюта> --amount <количество>")
            print("sell --currency <валюта> --amount <количество>")
            print("help — показать доступные команды")
            print("exit — завершить работу")

        elif action == "exit":
            print("Завершение работы.")
            break

        else:
            print(f"Неизвестная команда '{action}'. Введите help.")
