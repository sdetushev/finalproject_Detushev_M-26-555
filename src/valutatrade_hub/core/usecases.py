from datetime import datetime

from valutatrade_hub.core import utils
from valutatrade_hub.core.models import User


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
