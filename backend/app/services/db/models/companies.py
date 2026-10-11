import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db.base import Base
from app.services.db.models.dictionaries import Industry
from app.services.db.models.users import User
from app.services.db.types import str_enum_column_type


class CompanyRole(StrEnum):
    OWNER = "owner"
    RECRUITER = "recruiter"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    industry_id: Mapped[int | None] = mapped_column(
        ForeignKey("industries.id", ondelete="SET NULL")
    )
    website: Mapped[str] = mapped_column(String(300), default="")
    # Общие контакты отдела найма. Контакт для конкретного приглашения указывается в нём самом.
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    # Уровень доверия: 0: новая компания, 1: подтверждён домен (или выставлено в админке).
    # От него зависит, сколько приглашений могут одновременно ждать ответа.
    trust_level: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Домен сайта, на адрес в котором пришло и было подтверждено письмо.
    verified_domain: Mapped[str] = mapped_column(String(253), default="", server_default="")
    # Заморожена жалобами кандидатов: новые приглашения и вакансии недоступны до разбора в админке.
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    industry: Mapped[Industry | None] = relationship(lazy="raise")

    def __str__(self) -> str:
        return self.name


class ReportReason(StrEnum):
    FAKE_VACANCY = "fake_vacancy"
    ASKED_MONEY = "asked_money"
    TERMS_DIFFER = "terms_differ"


class CompanyReport(Base):
    """Жалоба кандидата на компанию, которая ему писала. Одна от кандидата на компанию:
    иначе один человек заморозил бы компанию сам."""

    __tablename__ = "company_reports"
    __table_args__ = (UniqueConstraint("company_id", "candidate_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invitations.id", ondelete="SET NULL")
    )
    reason: Mapped[ReportReason] = mapped_column(str_enum_column_type(ReportReason))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(lazy="raise")


class CompanyMember(Base):
    """Рекрутер в компании.

    user_id: первичный ключ: один пользователь состоит максимум в одной компании.
    """

    __tablename__ = "company_members"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[CompanyRole] = mapped_column(str_enum_column_type(CompanyRole))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(lazy="raise")
    company: Mapped[Company] = relationship(lazy="raise")


class CompanyInvite(Base):
    """Одноразовая ссылка для вступления рекрутера в компанию. Хранится только хеш токена."""

    __tablename__ = "company_invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CompanyApiToken(Base):
    """Токен ATS компании: по нему внешняя система забирает ленту событий. В БД только хеш."""

    __tablename__ = "company_api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Для кого выпущен: «Хантфлоу», «Talantix», чтобы владелец знал, что отзывать.
    title: Mapped[str] = mapped_column(String(100))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
