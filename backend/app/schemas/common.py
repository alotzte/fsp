import re
from typing import Annotated, Literal

from annotated_types import Ge, Le
from pydantic import BaseModel

# id и номера из запроса: целое Postgres. Без границ огромное число давало 500 вместо 422.
DbInt = Annotated[int, Ge(1), Le(2**31 - 1)]

# Сообщения валидации уходят пользователю в ответе 422.
PHONE_ERROR = "Телефон: цифры, пробелы, скобки и дефисы, 7-20 символов"
EMAIL_ERROR = "Некорректный email"
URL_ERROR = "Ссылка должна начинаться с http:// или https://"

_PHONE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")
# Простая проверка формата: доставку всё равно подтверждает только письмо.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def validate_optional_phone(value: str) -> str:
    # Формат допускает скобки и дефисы, но цифр должно быть не меньше 7: «-------» не телефон.
    if value and (not _PHONE.match(value) or sum(ch.isdigit() for ch in value) < 7):  # noqa: PLR2004
        raise ValueError(PHONE_ERROR)
    return value


def validate_optional_email(value: str) -> str:
    if value and not _EMAIL.match(value):
        raise ValueError(EMAIL_ERROR)
    return value


def validate_optional_url(value: str) -> str:
    if value and not _URL.match(value):
        raise ValueError(URL_ERROR)
    return value


class SkillCheckRead(BaseModel):
    """Навык потребности: подтверждён тестом на грейд, только заявлен или отсутствует."""

    title: str
    must_have: bool
    status: Literal["verified", "claimed", "missing"]
