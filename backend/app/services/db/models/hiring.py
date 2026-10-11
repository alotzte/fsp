import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db.base import Base
from app.services.db.models.candidates import WorkFormat
from app.services.db.models.companies import Company
from app.services.db.models.dictionaries import Grade, Skill, Specialization
from app.services.db.types import str_enum_column_type

# Вилка обязательна и в потребности, и в приглашении (ТЗ, правила видимости, п. 1).
_SALARY_RANGE = "salary_from_rub > 0 AND salary_to_rub >= salary_from_rub"


class HiringNeed(Base):
    """Потребность работодателя: кого ищем. По ней строится подборка кандидатов."""

    __tablename__ = "hiring_needs"
    __table_args__ = (
        CheckConstraint(_SALARY_RANGE, name="salary_range"),
        CheckConstraint(
            "work_formats <@ ARRAY[{}]::varchar[]".format(
                ", ".join(f"'{work_format.value}'" for work_format in WorkFormat)
            ),
            name="work_formats_known",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    # Чем занимается команда и какие задачи у специалиста.
    description: Mapped[str] = mapped_column(Text, default="")
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    work_formats: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    city: Mapped[str] = mapped_column(String(100), default="")
    salary_from_rub: Mapped[int] = mapped_column(Integer)
    salary_to_rub: Mapped[int] = mapped_column(Integer)
    # Опубликована как вакансия: кандидаты своего направления видят её и могут откликнуться.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company] = relationship(lazy="raise")
    specialization: Mapped[Specialization] = relationship(lazy="raise")
    grade: Mapped[Grade] = relationship(lazy="raise")
    skills: Mapped[list["HiringNeedSkill"]] = relationship(
        lazy="raise", cascade="all, delete-orphan", order_by="HiringNeedSkill.skill_id"
    )


class HiringNeedSkill(Base):
    __tablename__ = "hiring_need_skills"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    must_have: Mapped[bool] = mapped_column(Boolean)

    skill: Mapped[Skill] = relationship(lazy="raise")


class ShortlistEntry(Base):
    """Кандидат, отобранный в потребность. Шортлист не зависит от фильтров выдачи: уточнение
    запроса не теряет уже отобранных (ТЗ). Скрывший профиль кандидат выпадает из выдачи шортлиста,
    потому что она строится только по опубликованным профилям."""

    __tablename__ = "shortlist_entries"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvitationStatus(StrEnum):
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class InvitationDirection(StrEnum):
    # Кто начал контакт: работодатель (приглашение) или кандидат (отклик на вакансию).
    EMPLOYER = "employer"
    CANDIDATE = "candidate"


# Приглашение ждёт ответа кандидата, отклик: ответа работодателя.
PENDING_STATUSES = (InvitationStatus.SENT, InvitationStatus.VIEWED)


class DeclineReason(StrEnum):
    # Структурированная причина: обратная связь работодателю и сигнал для подбора.
    SALARY = "salary"
    STACK = "stack"
    FORMAT = "format"
    NOT_LOOKING = "not_looking"
    OTHER = "other"


class Invitation(Base):
    """Приглашение работодателя кандидату (основной сценарий выхода на контакт) или отклик
    кандидата на вакансию (`direction`).

    Привязка к потребности или вакансии не обязательна. Вилка видна кандидату сразу.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(_SALARY_RANGE, name="salary_range"),
        # Одно ожидающее ответа приглашение от компании кандидату: без спама повторами.
        Index(
            "uq_invitations_one_pending",
            "company_id",
            "candidate_user_id",
            unique=True,
            postgresql_where=text("status IN ('sent', 'viewed')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sent_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    need_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    salary_from_rub: Mapped[int] = mapped_column(Integer)
    salary_to_rub: Mapped[int] = mapped_column(Integer)
    # Как связаться с работодателем: виден кандидату сразу, вместе с вилкой.
    contact: Mapped[str] = mapped_column(String(300))
    # Почему пригласили: снимок совпадения с потребностью на момент отправки (без потребности:
    # None). Кандидат видит, за что его выбрали, даже если потребность потом изменят.
    match_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Короткий открытый кейс от компании и решение кандидата: оно приходит вместе с принятием.
    case_task: Mapped[str | None] = mapped_column(Text)
    case_answer: Mapped[str | None] = mapped_column(Text)
    # Встречное предложение кандидата: «готов при вилке от X». Число раскрывает только он сам;
    # компания может поднять вилку одним действием, контакты при этом не раскрываются.
    counter_salary_rub: Mapped[int | None] = mapped_column(Integer)
    # Отклик кандидата хранится той же записью: статусы, переписка и раскрытие контактов общие.
    direction: Mapped[InvitationDirection] = mapped_column(
        str_enum_column_type(InvitationDirection),
        default=InvitationDirection.EMPLOYER,
        server_default=InvitationDirection.EMPLOYER.value,
    )
    status: Mapped[InvitationStatus] = mapped_column(
        str_enum_column_type(InvitationStatus), default=InvitationStatus.SENT
    )
    decline_reason: Mapped[DeclineReason | None] = mapped_column(
        str_enum_column_type(DeclineReason)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # До какого сообщения переписку прочитала каждая сторона: счётчики непрочитанных.
    # Компания считается одной стороной: прочитал любой сотрудник, прочитано для всех (общий ящик).
    candidate_read_message_id: Mapped[int | None] = mapped_column(Integer)
    company_read_message_id: Mapped[int | None] = mapped_column(Integer)

    company: Mapped[Company] = relationship(lazy="raise")
    need: Mapped[HiringNeed | None] = relationship(lazy="raise")


class ContactReveal(Base):
    """Доступ компании к контактам кандидата. Появляется, когда кандидат принял приглашение;
    кандидат может его отозвать. Только через эту запись контакты уходят работодателю."""

    __tablename__ = "contact_reveals"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invitations.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvitationMessage(Base):
    """Сообщение в переписке по принятому приглашению."""

    __tablename__ = "invitation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
