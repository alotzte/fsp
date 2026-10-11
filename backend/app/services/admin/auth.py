import secrets

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.config import Settings

SESSION_USER_KEY = "user_id"


class AdminAuthBackend(AuthenticationBackend):
    """Вход в админку по логину и паролю из env. Временное решение до подключения Keycloak."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(secret_key=settings.secret_key.get_secret_value())
        self._username = settings.admin_username
        self._password = settings.admin_password.get_secret_value()

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        # compare_digest: сравнение за постоянное время, без утечки через тайминги.
        is_valid = secrets.compare_digest(username, self._username) & secrets.compare_digest(
            password, self._password
        )
        if is_valid:
            request.session[SESSION_USER_KEY] = username
        return is_valid

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return SESSION_USER_KEY in request.session
