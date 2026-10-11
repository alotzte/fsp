from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.errors import PermissionDeniedError, UnauthorizedError
from app.services.auth.service import AuthServiceDep
from app.services.db.models import User, UserRole

SESSION_COOKIE = "fsp_session"
LOGIN_FLOW_COOKIE = "fsp_login_flow"


class AuthenticationRequiredError(UnauthorizedError):
    message = "Требуется вход"


class SessionExpiredError(UnauthorizedError):
    message = "Сессия истекла, войдите снова"


class RoleNotChosenError(PermissionDeniedError):
    message = "Сначала выберите роль"


class RoleForbiddenError(PermissionDeniedError):
    message = "Раздел недоступен для вашей роли"


async def get_current_user(request: Request, auth: AuthServiceDep) -> User:
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token is None:
        raise AuthenticationRequiredError
    user = await auth.get_user_by_session_token(session_token)
    if user is None:
        raise SessionExpiredError
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_role(role: UserRole) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUserDep) -> User:
        if user.role is None:
            raise RoleNotChosenError
        if user.role != role:
            raise RoleForbiddenError
        return user

    return dependency


CandidateUserDep = Annotated[User, Depends(require_role(UserRole.CANDIDATE))]
EmployerUserDep = Annotated[User, Depends(require_role(UserRole.EMPLOYER))]

# Ошибки зависимостей для OpenAPI (`error_responses` у ручек).
CURRENT_USER_ERRORS = (AuthenticationRequiredError, SessionExpiredError)
ROLE_ERRORS = (*CURRENT_USER_ERRORS, RoleNotChosenError, RoleForbiddenError)
