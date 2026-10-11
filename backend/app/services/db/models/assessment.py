import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db.base import Base
from app.services.db.models.dictionaries import Grade, Specialization
from app.services.db.types import str_enum_column_type


class ItemKind(StrEnum):
    # Совпадает с видами заданий сервиса scoring.
    CHOICE = "choice"
    TEXT = "text"


class CandidateGrade(Base):
    """Категория кандидата: направление × грейд. Одна на кандидата.

    claimed: грейд, который кандидат выбрал сам; confirmed: подтверждённый тестом.
    Пока confirmed пуст, работодатель видит кандидата с пометкой «грейд не подтверждён».
    """

    __tablename__ = "candidate_grades"
    __table_args__ = (
        CheckConstraint(
            "(offered_grade_id IS NULL) = (offer_expires_at IS NULL)", name="offer_complete"
        ),
        CheckConstraint(
            "(confirmed_grade_id IS NULL) = (confirmed_at IS NULL)", name="confirmation_complete"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id"))
    claimed_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    confirmed_grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Оценка уровня из последней попытки в направлении категории (пройденной или нет): по ней
    # подбор уточняет заявленный грейд и ранжирует кандидатов внутри категории.
    theta: Mapped[float | None] = mapped_column(Float)
    theta_se: Mapped[float | None] = mapped_column(Float)
    # Следующий шаг, который система предложила по итогам попытки (грейд ниже после
    # неудачи или выше после уверенного прохождения). Его можно пройти без ожидания.
    offered_grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id"))
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    specialization: Mapped[Specialization] = relationship(lazy="raise")
    claimed_grade: Mapped[Grade] = relationship(foreign_keys=[claimed_grade_id], lazy="raise")
    confirmed_grade: Mapped[Grade | None] = relationship(
        foreign_keys=[confirmed_grade_id], lazy="raise"
    )
    offered_grade: Mapped[Grade | None] = relationship(
        foreign_keys=[offered_grade_id], lazy="raise"
    )


class AssessmentAttempt(Base):
    """Попытка теста на грейд. Задания собираются при старте и не меняются."""

    __tablename__ = "assessment_attempts"
    __table_args__ = (
        CheckConstraint("(finished_at IS NULL) = (passed IS NULL)", name="finished_has_result"),
        # Не больше одной незавершённой попытки на кандидата: защищает от двойного старта.
        Index(
            "uq_assessment_attempts_one_active",
            "user_id",
            unique=True,
            postgresql_where=text("finished_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Экспресс-тест песочницы жюри: короче, поэтому точность ниже.
    is_express: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    theta: Mapped[float | None] = mapped_column(Float)
    theta_se: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    # Уровень, который подтверждает попытка: ниже заявленного при неудаче, выше при
    # уверенном прохождении.
    estimated_level: Mapped[int | None] = mapped_column(Integer)
    # Сколько раз попытку продлевали заданиями у порога: решение было неуверенным.
    extensions: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    # Вероятность, что повторная попытка на этот грейд даст то же решение (считает scoring).
    retest_agreement: Mapped[float | None] = mapped_column(Float)
    # Сколько неверных ответов совпали с эталоном чужого экземпляра того же задания: признак
    # утечки. На грейд не влияет: такой ответ и так не засчитан.
    foreign_answers: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)

    specialization: Mapped[Specialization] = relationship(lazy="raise")
    grade: Mapped[Grade] = relationship(lazy="raise")
    items: Mapped[list["AttemptItem"]] = relationship(
        lazy="raise", cascade="all, delete-orphan", order_by="AttemptItem.position"
    )


class AttemptItem(Base):
    """Экземпляр задания в попытке вместе с эталоном. Эталон (answer) кандидату не отдаётся."""

    __tablename__ = "attempt_items"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64))
    competency: Mapped[str] = mapped_column(String(32))
    competency_title: Mapped[str] = mapped_column(String(128))
    a: Mapped[float] = mapped_column(Float)
    b: Mapped[float] = mapped_column(Float)
    kind: Mapped[ItemKind] = mapped_column(str_enum_column_type(ItemKind))
    prompt: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    answer: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
