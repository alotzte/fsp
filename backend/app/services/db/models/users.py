import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.services.db.base import Base
from app.services.db.types import str_enum_column_type

# Префикс keycloak_sub у песочниц жюри: настоящий sub из Keycloak это UUID, пересечься не может.
JURY_DEMO_PREFIX = "jury:"
# Пользователи демо-сида (app.demo_seed): кандидаты и общие демо-компании стенда.
SEED_DEMO_PREFIX = "demo:"


class UserRole(StrEnum):
    CANDIDATE = "candidate"
    EMPLOYER = "employer"


class User(Base):
    """Пользователь платформы. Логин и пароль живут в Keycloak, а здесь роль и связи."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keycloak_sub: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    # Имя из Keycloak, обновляется при каждом входе. Подставляется в новый профиль кандидата.
    first_name: Mapped[str] = mapped_column(String(100), default="")
    last_name: Mapped[str] = mapped_column(String(100), default="")
    # None до экрана выбора роли при первом входе. После выбора не меняется.
    role: Mapped[UserRole | None] = mapped_column(str_enum_column_type(UserRole))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __str__(self) -> str:
        return self.email

    @property
    def is_jury_demo(self) -> bool:
        """Песочница жюри (см. app/services/demo.py): создана без Keycloak."""
        return self.keycloak_sub.startswith(JURY_DEMO_PREFIX)

    @property
    def sees_sandboxes(self) -> bool:
        """Кандидатов и вакансии песочниц жюри видят только песочницы (вторая роль в инкогнито)
        и засеянные демо-данные. У обычных пользователей нет клонов демо-кандидата и вакансии."""
        return self.keycloak_sub.startswith((JURY_DEMO_PREFIX, SEED_DEMO_PREFIX))


class AuthSession(Base):
    """Сессия браузера. В cookie лежит случайный токен, а здесь только его SHA-256."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Нужен как id_token_hint, чтобы выход завершал и сессию в Keycloak.
    id_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
