import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import error_responses
from app.schemas.ats import (
    AtsEventRead,
    AtsEventsRead,
    AtsTokenInput,
    AtsTokenIssuedRead,
    AtsTokenRead,
)
from app.services.ats import AtsServiceDep, AtsTokenInvalidError, AtsTokenNotFoundError
from app.services.auth.dependencies import ROLE_ERRORS, EmployerUserDep
from app.services.companies import NotCompanyOwnerError, NotInCompanyError

tokens_router = APIRouter(prefix="/companies/my/ats-tokens", tags=["companies"])
ats_router = APIRouter(prefix="/ats", tags=["ats"])

_bearer = HTTPBearer(auto_error=False, description="API-токен компании из кабинета")


async def get_ats_company(
    ats: AtsServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    if credentials is None:
        raise AtsTokenInvalidError
    return await ats.company_by_token(credentials.credentials)


AtsCompanyDep = Annotated[uuid.UUID, Depends(get_ats_company)]


@tokens_router.get(
    "", responses=error_responses(*ROLE_ERRORS, NotInCompanyError, NotCompanyOwnerError)
)
async def list_ats_tokens(user: EmployerUserDep, ats: AtsServiceDep) -> list[AtsTokenRead]:
    """Действующие токены ATS компании (только владелец)."""
    return [AtsTokenRead.from_token(t) for t in await ats.list_tokens(user)]


@tokens_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(*ROLE_ERRORS, NotInCompanyError, NotCompanyOwnerError),
)
async def issue_ats_token(
    payload: AtsTokenInput, user: EmployerUserDep, ats: AtsServiceDep
) -> AtsTokenIssuedRead:
    """Выпустить токен для ATS. Сам токен показывается один раз: в БД только его хеш."""
    return AtsTokenIssuedRead.from_issued(await ats.issue_token(user, payload.title))


@tokens_router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *ROLE_ERRORS, NotInCompanyError, NotCompanyOwnerError, AtsTokenNotFoundError
    ),
)
async def revoke_ats_token(token_id: uuid.UUID, user: EmployerUserDep, ats: AtsServiceDep) -> None:
    await ats.revoke_token(user, token_id)


@ats_router.get("/events", responses=error_responses(AtsTokenInvalidError))
async def list_ats_events(
    company_id: AtsCompanyDep, ats: AtsServiceDep, since: datetime | None = None
) -> AtsEventsRead:
    """Лента событий компании для ATS: новые отклики, ответы на приглашения и отклики, сообщения.

    Авторизация: `Authorization: Bearer <токен из кабинета>`. Передавайте в since значение
    next_since из прошлого ответа; события с уже виденным id отбрасывайте. Контакты кандидата:
    только пока у компании есть к ним доступ: после отзыва кандидатом в новых событиях их нет.
    """
    events = await ats.events(company_id, since)
    return AtsEventsRead(
        events=[AtsEventRead.from_event(e) for e in events],
        next_since=events[-1].occurred_at if events else since,
    )
