import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.config import Settings, SettingsDep
from app.errors import UnauthorizedError
from app.schemas.auth import LogoutRead
from app.services.auth.dependencies import LOGIN_FLOW_COOKIE, SESSION_COOKIE
from app.services.auth.login_flow import LOGIN_FLOW_MAX_AGE_SECONDS
from app.services.auth.service import AUTH_CALLBACK_PATH, AuthServiceDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
# Тег для переходов браузера (не fetch): фронт исключает его из генерации клиента.
BROWSER_REDIRECT_TAG = "auth-browser-redirects"

NextPath = Annotated[str, Query(alias="next", description="Путь фронта, куда вернуть после входа")]


def _flow_cookie_path(settings: Settings) -> str:
    return f"{settings.public_path}{AUTH_CALLBACK_PATH}"


def _start_login(
    auth: AuthServiceDep, settings: SettingsDep, next_path: str, *, register: bool
) -> RedirectResponse:
    redirect_url, flow_cookie = auth.begin_login(next_path=next_path, register=register)
    response = RedirectResponse(redirect_url)
    response.set_cookie(
        LOGIN_FLOW_COOKIE,
        flow_cookie,
        max_age=LOGIN_FLOW_MAX_AGE_SECONDS,
        path=_flow_cookie_path(settings),
        httponly=True,
        secure=settings.uses_https,
        # Lax: cookie уходит при возврате из Keycloak (top-level GET), но не в межсайтовых POST.
        samesite="lax",
    )
    return response


@router.get(
    "/login", response_class=RedirectResponse, status_code=307, tags=[BROWSER_REDIRECT_TAG]
)
async def login(
    auth: AuthServiceDep, settings: SettingsDep, next_path: NextPath = "/"
) -> RedirectResponse:
    """Переход браузера на страницу входа Keycloak. Открывается навигацией, не fetch."""
    return _start_login(auth, settings, next_path, register=False)


@router.get(
    "/register", response_class=RedirectResponse, status_code=307, tags=[BROWSER_REDIRECT_TAG]
)
async def register(
    auth: AuthServiceDep, settings: SettingsDep, next_path: NextPath = "/"
) -> RedirectResponse:
    """Переход браузера сразу на форму регистрации Keycloak."""
    return _start_login(auth, settings, next_path, register=True)


@router.get("/callback", response_class=RedirectResponse, status_code=307, include_in_schema=False)
async def callback(
    request: Request,
    auth: AuthServiceDep,
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    flow_cookie = request.cookies.get(LOGIN_FLOW_COOKIE)
    # Без code Keycloak вернул ошибку (например, пользователь отменил вход).
    if code is None or state is None or flow_cookie is None:
        return _login_failed_redirect(settings)
    try:
        session_token, redirect_url = await auth.complete_login(
            code=code, state=state, flow_cookie=flow_cookie
        )
    except UnauthorizedError:
        logger.warning("Вход через Keycloak не удался", exc_info=True)
        return _login_failed_redirect(settings)

    response = RedirectResponse(redirect_url)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=int(auth.session_lifetime.total_seconds()),
        path=f"{settings.public_path}/",
        httponly=True,
        secure=settings.uses_https,
        samesite="lax",
    )
    response.delete_cookie(LOGIN_FLOW_COOKIE, path=_flow_cookie_path(settings))
    return response


def _login_failed_redirect(settings: Settings) -> RedirectResponse:
    # Callback приходит навигацией браузера, а не API-запросом, поэтому вместо JSON
    # возвращаем на фронт с пометкой.
    response = RedirectResponse(f"{settings.effective_frontend_url}/?auth_error=1")
    response.delete_cookie(LOGIN_FLOW_COOKIE, path=_flow_cookie_path(settings))
    return response


@router.post("/logout")
async def logout(
    request: Request, response: Response, auth: AuthServiceDep, settings: SettingsDep
) -> LogoutRead:
    """Завершает сессию. Фронт затем переходит по logout_url, чтобы выйти и из Keycloak."""
    logout_url = await auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path=f"{settings.public_path}/")
    return LogoutRead(logout_url=logout_url)
