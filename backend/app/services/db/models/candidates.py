import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db.base import Base
from app.services.db.models.dictionaries import Skill, SkillKind, Specialization
from app.services.db.types import str_enum_column_type


class WorkFormat(StrEnum):
    OFFICE = "office"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ProfileSection(StrEnum):
    """Разделы профиля, которые кандидат может скрыть от работодателя до принятия приглашения.
    Город, форматы и навыки скрыть нельзя: по ним считается совместимость в подборе."""

    ABOUT = "about"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SOFT_SKILLS = "soft_skills"


class CandidateProfile(Base):
    """Профиль кандидата. Один на пользователя; создаётся при первом сохранении."""

    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint(
            "work_formats <@ ARRAY[{}]::varchar[]".format(
                ", ".join(f"'{work_format.value}'" for work_format in WorkFormat)
            ),
            name="work_formats_known",
        ),
        CheckConstraint(
            "hidden_sections <@ ARRAY[{}]::varchar[]".format(
                ", ".join(f"'{section.value}'" for section in ProfileSection)
            ),
            name="hidden_sections_known",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Публичный номер «Кандидат №1042»: под ним работодатель видит профиль до принятия
    # приглашения. Последовательный, но не связан с id пользователя.
    candidate_number: Mapped[int] = mapped_column(Integer, Identity(start=1001), unique=True)
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    telegram: Mapped[str] = mapped_column(String(64), default="")
    specialization_id: Mapped[int | None] = mapped_column(
        ForeignKey("specializations.id", ondelete="SET NULL")
    )
    # Массив строк: Enum внутри ARRAY с CHECK генерирует неверный SQL. Допустимые значения
    # проверяет CHECK ниже, а в коде значения приводятся к WorkFormat.
    work_formats: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    city: Mapped[str] = mapped_column(String(100), default="")
    salary_expectation_rub: Mapped[int | None] = mapped_column(Integer)
    about: Mapped[str] = mapped_column(Text, default="")
    # Разделы, скрытые от работодателя до принятия приглашения (значения ProfileSection).
    hidden_sections: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), default=list, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    specialization: Mapped[Specialization | None] = relationship(lazy="raise")
    skills: Mapped[list["CandidateSkill"]] = relationship(
        lazy="raise", cascade="all, delete-orphan", order_by="CandidateSkill.id"
    )
    experience: Mapped[list["WorkExperience"]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="(WorkExperience.started_on.desc(), WorkExperience.id)",
    )
    education: Mapped[list["Education"]] = relationship(
        lazy="raise", cascade="all, delete-orphan", order_by="Education.id"
    )


class CandidateSkill(Base):
    """Навык кандидата: ссылка на справочник или свой тег (custom_title), ровно одно из двух."""

    __tablename__ = "candidate_skills"
    __table_args__ = (
        CheckConstraint(
            "(skill_id IS NULL) <> (custom_title IS NULL)", name="skill_or_custom_title"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.user_id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[SkillKind] = mapped_column(str_enum_column_type(SkillKind))
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    custom_title: Mapped[str | None] = mapped_column(String(64))

    skill: Mapped[Skill | None] = relationship(lazy="raise")


class WorkExperience(Base):
    __tablename__ = "work_experience"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.user_id", ondelete="CASCADE"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(200))
    # Точность до месяца: храним первое число месяца. ended_on = NULL: работает сейчас.
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")


class Education(Base):
    __tablename__ = "education"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.user_id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(300))
    specialty: Mapped[str] = mapped_column(String(300), default="")
    graduation_year: Mapped[int | None] = mapped_column(Integer)
