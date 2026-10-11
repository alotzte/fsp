import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, select

from app.config import SettingsDep
from app.errors import UnauthorizedError
from app.services.auth.keycloak import KeycloakClientDep
from app.services.auth.login_flow import LoginFlow, LoginFlowSigner
from app.services.db.models import AuthSession, User
from app.services.db.session import SessionDep
from app.services.tokens import generate_token, hash_token

# Должен совпадать с redirectUris клиента в infra/keycloak/realm-fsp.json.
AUTH_CALLBACK_PATH = "/api/v1/auth/callback"


class LoginStateMismatchError(UnauthorizedError):
    message = "Ответ Keycloak не относится к начатому входу"


class AuthService:
    """Вход через Keycloak (Authorization Code + PKCE) и сессии браузера."""

    def __init__(self, session: SessionDep, keycloak: KeycloakClientDep, settings: SettingsDep):
        self._session = session
        self._keycloak = keycloak
        self._settings = settings
        self._flow_signer = LoginFlowSigner(settings.secret_key.get_secret_value())
        self._callback_url = f"{settings.public_url}{AUTH_CALLBACK_PATH}"

    def begin_login(self, *, next_path: str, register: bool) -> tuple[str, str]:
        """Возвращает адрес Keycloak для редиректа и cookie с состоянием входа."""
        flow = LoginFlow.start(next_path)
        redirect_url = self._keycloak.authorization_url(
            redirect_uri=self._callback_url,
            state=flow.state,
            nonce=flow.nonce,
            code_challenge=flow.code_challenge,
            register=register,
        )
        return redirect_url, self._flow_signer.dump(flow)

    async def complete_login(self, *, code: str, state: str, flow_cookie: str) -> tuple[str, str]:
        """Завершает вход.

        Возвращает токен новой сессии и адрес фронта, куда вернуть пользователя.
        """
        flow = self._flow_signer.load(flow_cookie)
        if not secrets.compare_digest(state, flow.state):
            raise LoginStateMismatchError

        id_token = await self._keycloak.exchange_code(
            code=code, code_verifier=flow.code_verifier, redirect_uri=self._callback_url
        )
        identity = await self._keycloak.verify_id_token(id_token, nonce=flow.nonce)

        user = await self._session.scalar(select(User).where(User.keycloak_sub == identity.sub))
        if user is None:
            user = User(keycloak_sub=identity.sub)
            self._session.add(user)
        # Email и имя могли поменяться в Keycloak: источник правды там.
        user.email = identity.email
        user.first_name = identity.first_name
        user.last_name = identity.last_name
        await self._session.flush()
        session_token = await self.open_session(user, id_token=id_token)
        return session_token, f"{self._settings.effective_frontend_url}{flow.next_path}"

    async def open_session(self, user: User, *, id_token: str) -> str:
        """Создаёт сессию браузера и возвращает её токен для cookie. Коммитит транзакцию.

        id_token пуст у демо-сессий жюри: они открываются без Keycloak.
        """
        now = datetime.now(UTC)
        await self._session.execute(
            delete(AuthSession).where(
                AuthSession.user_id == user.id, AuthSession.expires_at <= now
            )
        )
        session_token = generate_token()
        self._session.add(
            AuthSession(
                token_hash=hash_token(session_token),
                user_id=user.id,
                id_token=id_token,
                expires_at=now + self.session_lifetime,
            )
        )
        await self._session.commit()
        return session_token

    async def logout(self, session_token: str | None) -> str:
        """Удаляет сессию и возвращает адрес выхода из Keycloak (или главной без сессии)."""
        home_url = f"{self._settings.public_url}/"
        if session_token is None:
            return home_url
        auth_session = await self._session.get(AuthSession, hash_token(session_token))
        if auth_session is None:
            return home_url
        id_token = auth_session.id_token
        await self._session.delete(auth_session)
        await self._session.commit()
        if not id_token:
            # Демо-сессия жюри: в Keycloak выходить не из чего.
            return home_url
        # Keycloak разрешает возврат только на PUBLIC_URL (post.logout.redirect.uris в realm).
        return self._keycloak.logout_url(id_token=id_token, post_logout_redirect_uri=home_url)

    async def get_user_by_session_token(self, session_token: str) -> User | None:
        return await self._session.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == hash_token(session_token),
                AuthSession.expires_at > datetime.now(UTC),
            )
        )

    @property
    def session_lifetime(self) -> timedelta:
        return timedelta(hours=self._settings.session_lifetime_hours)


AuthServiceDep = Annotated[AuthService, Depends()]
