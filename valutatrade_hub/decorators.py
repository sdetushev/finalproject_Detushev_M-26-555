import inspect
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from valutatrade_hub.logging_config import configure_logging

P = ParamSpec("P")
R = TypeVar("R")


def _format_log_fields(fields: dict[str, Any]) -> str:
    """Преобразовать поля операции в текстовую запись журнала."""
    parts = []

    for key, value in fields.items():
        if value is None:
            continue

        if key in ("action", "result"):
            parts.append(f"{key}={value}")
        else:
            parts.append(f"{key}={value!r}")

    return " ".join(parts)


def _get_result_field(result: Any, field: str) -> Any:
    """Получить поле результата из словаря или объекта."""
    if isinstance(result, Mapping):
        return result.get(field)

    return getattr(result, field, None)


def log_action(
    action: str,
    *,
    verbose: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Создать декоратор логирования доменной операции."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """Обернуть функцию логированием результата и ошибок."""

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Выполнить операцию и записать результат в журнал."""
            logger = configure_logging()

            signature = inspect.signature(func)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()

            parameters = bound.arguments

            user = parameters.get("user")

            user_id = parameters.get(
                "user_id",
                getattr(user, "user_id", None),
            )

            username = parameters.get(
                "username",
                getattr(user, "username", None),
            )

            fields: dict[str, Any] = {
                "action": action.upper(),
                "user_id": user_id,
                "username": username,
                "currency_code": parameters.get("currency_code"),
                "amount": parameters.get("amount"),
            }

            try:
                result = func(*args, **kwargs)

            except Exception as error:
                error_fields = {
                    **fields,
                    "result": "ERROR",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }

                logger.info(_format_log_fields(error_fields))
                raise

            # Дополнительные сведения из результата операции.
            for field in ("rate", "base"):
                value = _get_result_field(result, field)

                if value is None:
                    value = parameters.get(field)

                if value is not None:
                    fields[field] = value

            # Расширенное логирование состояния кошелька.
            if verbose:
                for field in ("balance_before", "balance_after"):
                    value = _get_result_field(result, field)

                    if value is not None:
                        fields[field] = value

            fields["result"] = "OK"

            logger.info(_format_log_fields(fields))

            return result

        return wrapper

    return decorator
