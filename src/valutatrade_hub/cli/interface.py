import shlex

from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import login_user, register_user


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


def run_cli() -> None:
    """Запустить интерактивный интерфейс валютного кошелька."""
    current_user: User | None = None

    print("Валютный кошелёк")
    print("Доступные команды: register, login, help, exit")

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

        elif action == "help":
            print("register --username <имя> --password <пароль>")
            print("login --username <имя> --password <пароль>")
            print("help — показать доступные команды")
            print("exit — завершить работу")

        elif action == "exit":
            print("Завершение работы.")
            break

        else:
            print(f"Неизвестная команда '{action}'. Введите help.")
