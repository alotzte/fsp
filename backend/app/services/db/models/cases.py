import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.services.db.base import Base
from app.services.db.models.assessment import ItemKind
from app.services.db.types import str_enum_column_type


class WeeklyCase(Base):
    """Кейс недели: экземпляр семейства из банка, один на кандидата в неделю. Эталон (answer)
    не отдаётся; на грейд результат не влияет, это свежий сигнал для работодателя."""

    __tablename__ = "weekly_cases"
    __table_args__ = (UniqueConstraint("user_id", "week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Понедельник недели (UTC): кейс меняется раз в неделю без фоновых задач.
    week: Mapped[date] = mapped_column(Date)
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id"))
    family_id: Mapped[str] = mapped_column(String(64))
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
