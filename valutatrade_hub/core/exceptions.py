class InsufficientFundsError(ValueError):
    """Ошибка недостаточности средств на валютном кошельке."""

    def __init__(
        self,
        available: float,
        required: float,
        code: str,
    ) -> None:
        """Сохранить параметры и сформировать сообщение об ошибке."""
        self.available = available
        self.required = required
        self.code = code

        super().__init__(
            f"Недостаточно средств: доступно {available:g} {code}, "
            f"требуется {required:g} {code}"
        )


class CurrencyNotFoundError(ValueError):
    """Ошибка обращения к неизвестной валюте."""

    def __init__(self, code: str) -> None:
        """Сохранить код валюты и сформировать сообщение об ошибке."""
        self.code = code

        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(RuntimeError):
    """Ошибка при обращении к внешнему API."""

    def __init__(self, reason: str) -> None:
        """Сохранить причину и сформировать сообщение об ошибке."""
        self.reason = reason

        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
