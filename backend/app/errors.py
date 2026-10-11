from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError


class DomainError(Exception):
    """Базовая бизнес-ошибка: на каждый случай свой класс со своим сообщением.

    Имя класса уходит в ответ как код ошибки (`error`), по нему фронт и ветвится.
    Наследники задают HTTP-код, сервисы про HTTP не знают.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    message = "Некорректный запрос"

    def __init__(self) -> None:
        super().__init__(self.message)


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Требуется вход"


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "Не найдено"


class PermissionDeniedError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    message = "Недостаточно прав"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    message = "Конфликт с текущим состоянием"


class ErrorRead(BaseModel):
    """Тело ответа с бизнес-ошибкой."""

    error: str = Field(description="Код ошибки (имя класса), по нему ветвится фронт")
    detail: str = Field(description="Сообщение для пользователя")


def error_responses(*errors: type[DomainError]) -> dict[int | str, dict[str, Any]]:
    """Ошибки ручки для OpenAPI: по каждому коду перечислены классы ошибок и их сообщения."""
    by_code: dict[int, list[type[DomainError]]] = defaultdict(list)
    for error in errors:
        by_code[error.status_code].append(error)
    return {
        code: {
            "model": ErrorRead,
            "description": "\n\n".join(f"`{e.__name__}`: {e.message}" for e in group),
        }
        for code, group in sorted(by_code.items())
    }


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": type(exc).__name__, "detail": exc.message},
    )


# Класс SQLSTATE 22: «данные не подходят» (NUL в строке, выход за int32): это ввод клиента, а не
# сбой сервера. Pydantic такие значения пропускает, Postgres отвергает.
_DATA_EXCEPTION_CLASS = "22"


async def _handle_db_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DBAPIError)
    if str(getattr(exc.orig, "pgcode", "") or "").startswith(_DATA_EXCEPTION_CLASS):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"error": "InvalidDataError", "detail": "Недопустимые символы или значения"},
        )
    raise exc


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(DBAPIError, _handle_db_error)
