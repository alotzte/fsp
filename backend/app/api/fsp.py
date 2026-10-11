import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse

from app.api.auth import BROWSER_REDIRECT_TAG
from app.config import Settings, SettingsDep
from app.errors import DomainError, error_responses
from app.schemas.fsp import FspProfileRead
from app.services.auth.dependencies import ROLE_ERRORS, CandidateUserDep
from app.services.auth.login_flow import LOGIN_FLOW_MAX_AGE_SECONDS
from app.services.fsp import (
    FSP_CALLBACK_PATH,
    FspConsentRequiredError,
    FspIdAlreadyLinkedError,
    FspServiceDep,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidate/fsp", tags=["fsp"])

FSP_LINK_FLOW_COOKIE = "fsp_id_link_flow"
NextPath = Annotated[
    str, Query(alias="next", description="Путь фронта, куда вернуть после привязки")
]


def _flow_cookie_path(settings: Settings) -> str:
    return f"{settings.public_path}{FSP_CALLBACK_PATH}"


@router.get("", responses=error_responses(*ROLE_ERRORS))
async def get_my_fsp(user: CandidateUserDep, fsp: FspServiceDep) -> FspProfileRead:
    """Привязанный ФСП ID и результаты из реестра ФСП."""
    return FspProfileRead.from_profile(await fsp.get_profile(user.id))


@router.get(
    "/link",
    response_class=RedirectResponse,
    status_code=307,
    tags=[BROWSER_REDIRECT_TAG],
    responses=error_responses(*ROLE_ERRORS),
)
async def link_fsp_id(
    user: CandidateUserDep, fsp: FspServiceDep, settings: SettingsDep, next_path: NextPath = "/"
) -> RedirectResponse:
    """Переход браузера на вход в ФСП ID. Открывается навигацией, не fetch."""
    try:
        url, flow_cookie = await fsp.begin_link(user, next_path)
    except FspConsentRequiredError:
        return _failed(settings, "consent")
    response = RedirectResponse(url)
    response.set_cookie(
        FSP_LINK_FLOW_COOKIE,
        flow_cookie,
        max_age=LOGIN_FLOW_MAX_AGE_SECONDS,
        path=_flow_cookie_path(settings),
        httponly=True,
        secure=settings.uses_https,
        samesite="lax",
    )
    return response


@router.get("/callback", response_class=RedirectResponse, status_code=307, include_in_schema=False)
async def fsp_id_callback(
    request: Request,
    user: CandidateUserDep,
    fsp: FspServiceDep,
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    flow_cookie = request.cookies.get(FSP_LINK_FLOW_COOKIE)
    # Без code ФСП ID вернул ошибку (например, пользователь отменил вход).
    if code is None or state is None or flow_cookie is None:
        return _failed(settings, "cancelled")
    try:
        redirect_url = await fsp.complete_link(
            user, code=code, state=state, flow_cookie=flow_cookie
        )
    except FspIdAlreadyLinkedError:
        return _failed(settings, "taken")
    except FspConsentRequiredError:
        return _failed(settings, "consent")
    except DomainError:
        logger.warning("Привязка ФСП ID не удалась", exc_info=True)
        return _failed(settings, "failed")
    response = RedirectResponse(redirect_url)
    response.delete_cookie(FSP_LINK_FLOW_COOKIE, path=_flow_cookie_path(settings))
    return response


def _failed(settings: Settings, reason: str) -> RedirectResponse:
    # Callback приходит навигацией браузера, поэтому вместо JSON возвращаем в кабинет с пометкой.
    response = RedirectResponse(
        f"{settings.effective_frontend_url}/candidate?tab=edit&fsp_error={reason}"
    )
    response.delete_cookie(FSP_LINK_FLOW_COOKIE, path=_flow_cookie_path(settings))
    return response


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(*ROLE_ERRORS))
async def unlink_fsp_id(user: CandidateUserDep, fsp: FspServiceDep) -> None:
    """Отвязать ФСП ID: достижения перестают учитываться в подборках."""
    await fsp.unlink(user)
