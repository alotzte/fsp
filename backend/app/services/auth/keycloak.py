import asyncio
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Depends, Request

from app.config import Settings
from app.errors import UnauthorizedError

ID_TOKEN_ALGORITHMS = ["RS256"]
# Допуск на расхождение часов между контейнерами.
CLOCK_SKEW_SECONDS = 30


class KeycloakError(UnauthorizedError):
    """Keycloak отклонил вход или вернул неожиданный ответ. Подробности: в __cause__."""

    message = "Не удалось войти через Keycloak"


class KeycloakUnavailableError(KeycloakError):
    message = "Keycloak недоступен"


class AuthorizationCodeRejectedError(KeycloakError):
    message = "Keycloak отклонил код авторизации"


class InvalidIdTokenError(KeycloakError):
    message = "ID-токен не прошёл проверку"


class EmailNotVerifiedError(KeycloakError):
    message = "Email не подтверждён"


@dataclass(frozen=True)
class OidcRealm:
    """Реалм Keycloak и наш клиент в нём. Браузер ходит по public_base (через gateway),
    бэк: по internal_base (сеть compose)."""

    public_base: str
    internal_base: str
    realm: str
    client_id: str
    client_secret: str

    @classmethod
    def login(cls, settings: Settings) -> "OidcRealm":
        """Реалм входа на платформу."""
        return cls(
            public_base=settings.keycloak_public_url,
            internal_base=settings.keycloak_internal_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret.get_secret_value(),
        )

    @classmethod
    def fsp_id(cls, settings: Settings) -> "OidcRealm":
        """ФСП ID: на стенде это mock-реалм в нашем Keycloak, в проде Keycloak ФСП."""
        return cls(
            public_base=settings.fsp_id_public_url or settings.keycloak_public_url,
            internal_base=settings.fsp_id_internal_url or settings.keycloak_internal_url,
            realm=settings.fsp_id_realm,
            client_id=settings.fsp_id_client_id,
            client_secret=settings.fsp_id_client_secret.get_secret_value(),
        )


@dataclass(frozen=True)
class IdentityClaims:
    sub: str
    email: str
    first_name: str
    last_name: str


class KeycloakClient:
    """OIDC-клиент к realm Keycloak.

    Адреса для браузера строятся от публичного URL (через gateway),
    а обмен кода и ключи подписи: по внутреннему адресу в сети compose.
    """

    def __init__(self, realm: OidcRealm, http_client: httpx.AsyncClient) -> None:
        self._realm = realm
        self._http = http_client
        realm_path = f"/realms/{realm.realm}"
        self.issuer = f"{realm.public_base}{realm_path}"
        self._public_oidc = f"{self.issuer}/protocol/openid-connect"
        self._internal_oidc = f"{realm.internal_base}{realm_path}/protocol/openid-connect"
        self._signing_keys: dict[str, jwt.PyJWK] = {}
        self._signing_keys_lock = asyncio.Lock()

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        register: bool,
        force_login: bool = False,
    ) -> str:
        # У Keycloak отдельный endpoint сразу на форму регистрации; параметры те же.
        endpoint = "registrations" if register else "auth"
        params = {
            "client_id": self._realm.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if force_login:
            params["prompt"] = "login"
        return f"{self._public_oidc}/{endpoint}?{urlencode(params)}"

    def logout_url(self, *, id_token: str, post_logout_redirect_uri: str) -> str:
        query = urlencode(
            {
                "id_token_hint": id_token,
                "post_logout_redirect_uri": post_logout_redirect_uri,
            }
        )
        return f"{self._public_oidc}/logout?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> str:
        """Меняет authorization code на токены и возвращает ID-токен."""
        try:
            response = await self._http.post(
                f"{self._internal_oidc}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                },
                auth=(self._realm.client_id, self._realm.client_secret),
            )
        except httpx.HTTPError as exc:
            raise KeycloakUnavailableError from exc
        if not response.is_success:
            raise AuthorizationCodeRejectedError
        id_token = response.json().get("id_token")
        if not isinstance(id_token, str):
            raise AuthorizationCodeRejectedError
        return id_token

    async def verify_id_token(self, id_token: str, *, nonce: str) -> IdentityClaims:
        """Проверяет ID-токен входа: нужен подтверждённый email."""
        claims = await self.decode_id_token(id_token, nonce=nonce)
        email = claims.get("email")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise EmailNotVerifiedError
        return IdentityClaims(
            sub=str(claims["sub"]),
            email=email,
            first_name=str(claims.get("given_name", "")),
            last_name=str(claims.get("family_name", "")),
        )

    async def decode_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        """Проверяет подпись, издателя, аудиторию, срок и nonce; возвращает claims."""
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
        except jwt.PyJWTError as exc:
            raise InvalidIdTokenError from exc
        if not isinstance(kid, str):
            raise InvalidIdTokenError
        signing_key = await self._get_signing_key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=signing_key,
                algorithms=ID_TOKEN_ALGORITHMS,
                audience=self._realm.client_id,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iat", "sub", "nonce"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidIdTokenError from exc

        # nonce защищает от подстановки чужого ID-токена в наш callback.
        if claims["nonce"] != nonce:
            raise InvalidIdTokenError
        return claims

    async def _get_signing_key(self, kid: str) -> jwt.PyJWK:
        if kid in self._signing_keys:
            return self._signing_keys[kid]
        # Неизвестный kid: Keycloak мог сменить ключи.
        # Перечитываем JWKS один раз на всех ожидающих.
        async with self._signing_keys_lock:
            if kid not in self._signing_keys:
                self._signing_keys = await self._fetch_signing_keys()
        if kid not in self._signing_keys:
            raise InvalidIdTokenError
        return self._signing_keys[kid]

    async def _fetch_signing_keys(self) -> dict[str, jwt.PyJWK]:
        try:
            response = await self._http.get(f"{self._internal_oidc}/certs")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KeycloakUnavailableError from exc
        keys: dict[str, jwt.PyJWK] = {}
        for jwk in response.json().get("keys", []):
            if jwk.get("use") == "sig" and jwk.get("alg") in ID_TOKEN_ALGORITHMS:
                keys[jwk["kid"]] = jwt.PyJWK(jwk)
        return keys


def get_keycloak_client(request: Request) -> KeycloakClient:
    # Один экземпляр на приложение (lifespan): в нём кэш ключей подписи.
    client: KeycloakClient = request.app.state.keycloak
    return client


def get_fsp_id_client(request: Request) -> KeycloakClient:
    client: KeycloakClient = request.app.state.fsp_id
    return client


KeycloakClientDep = Annotated[KeycloakClient, Depends(get_keycloak_client)]
FspIdClientDep = Annotated[KeycloakClient, Depends(get_fsp_id_client)]
