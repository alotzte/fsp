from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from pydantic import PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    scoring_url: str = "http://localhost:8001"
    scoring_timeout_seconds: float = 10.0

    # Адрес gateway, через который браузер видит фронт, API и Keycloak.
    public_url: str = "http://localhost:8080"
    # Куда возвращать после входа. Пусто = public_url; в dev фронта: http://localhost:5173.
    frontend_url: str = ""

    # Подписывает cookie сессии админки и cookie состояния входа через Keycloak.
    secret_key: SecretStr
    admin_username: str
    admin_password: SecretStr

    # Бэк ходит в Keycloak напрямую (токены, ключи), браузер через public_url/auth.
    keycloak_internal_url: str = "http://localhost:8080/auth"
    keycloak_realm: str = "fsp"
    keycloak_client_id: str = "fsp-web"
    keycloak_client_secret: SecretStr
    keycloak_timeout_seconds: float = 10.0

    # ФСП ID: отдельный OIDC-провайдер, к нему привязывается профиль кандидата. На стенде это
    # mock-реалм fsp-id в нашем Keycloak; для настоящего ФСП ID задайте его адреса и клиента.
    fsp_id_public_url: str = ""
    fsp_id_internal_url: str = ""
    fsp_id_realm: str = "fsp-id"
    fsp_id_client_id: str = "fsp-career"
    fsp_id_client_secret: SecretStr

    # Демо-режим для жюри: вход в песочницы кандидата и работодателя без регистрации и
    # экспресс-тест. Только для стенда проверки, в проде: выключен.
    demo_mode: bool = False

    # Письма (уведомления о приглашениях). В Docker это Mailpit, письма никуда не уходят.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "ФСП Карьера <noreply@fsp-career.local>"
    smtp_timeout_seconds: float = 10.0

    # Каталог для LocalFileStorage. В Docker: volume, см. docker-compose.yml.
    upload_dir: str = "data/uploads"

    session_lifetime_hours: int = 24 * 7
    company_invite_lifetime_hours: int = 72

    @field_validator(
        "public_url",
        "frontend_url",
        "keycloak_internal_url",
        "fsp_id_public_url",
        "fsp_id_internal_url",
    )
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def effective_frontend_url(self) -> str:
        return self.frontend_url or self.public_url

    @property
    def public_path(self) -> str:
        """Префикс пути, под которым приложение опубликовано (/fsp), или пусто для корня."""
        return urlsplit(self.public_url).path

    @property
    def keycloak_public_url(self) -> str:
        return f"{self.public_url}/auth"

    @property
    def uses_https(self) -> bool:
        return self.public_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_app_settings(request: Request) -> Settings:
    # Настройки, с которыми создано приложение (create_app), а не глобальные:
    # так их можно подменить.
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
