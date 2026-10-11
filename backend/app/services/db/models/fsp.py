import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db.base import Base
from app.services.db.types import str_enum_column_type


class FspDiscipline(StrEnum):
    # Дисциплины вида спорта «спортивное программирование» (приказ Минспорта № 584).
    ALGORITHMIC = "algorithmic"
    PRODUCT = "product"
    INFOSEC = "infosec"
    ROBOTICS = "robotics"
    UAS = "uas"


class FspAward(StrEnum):
    WINNER = "winner"
    PRIZE = "prize"
    FINALIST = "finalist"
    PARTICIPANT = "participant"


class FspSportRank(StrEnum):
    # Разряды и звания ЕВСК по спортивному программированию, от младшего к старшему.
    THIRD = "third"
    SECOND = "second"
    FIRST = "first"
    CMS = "cms"  # кандидат в мастера спорта
    MS = "ms"  # мастер спорта


class FspLink(Base):
    """Привязка профиля кандидата к ФСП ID. Один ФСП ID у одного пользователя платформы."""

    __tablename__ = "fsp_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    fsp_id: Mapped[str] = mapped_column(String(64), unique=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Реестр ФСП ---
# ponytail: mock реестра: таблицы в нашей БД с демо-данными (app.demo_seed). API и структуры
# данных ФСП организаторы намеренно не дают; модель ниже: наше предложение. Для реальной
# интеграции меняются только registry_results и registry_rank в app/services/fsp.py (запрос
# к API ФСП вместо этих таблиц).


class FspEvent(Base):
    __tablename__ = "fsp_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    discipline: Mapped[FspDiscipline] = mapped_column(str_enum_column_type(FspDiscipline))
    starts_on: Mapped[date] = mapped_column(Date)
    # Номер в Едином календарном плане Минспорта: работодатель сверит соревнование
    # с официальным календарём.
    ekp_number: Mapped[str | None] = mapped_column(String(32))

    def __str__(self) -> str:
        return f"{self.title} ({self.starts_on:%d.%m.%Y})"


class FspResult(Base):
    """Результат участника (или его команды) в соревновании."""

    __tablename__ = "fsp_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("fsp_events.id", ondelete="CASCADE"))
    fsp_id: Mapped[str] = mapped_column(String(64), index=True)
    award: Mapped[FspAward] = mapped_column(str_enum_column_type(FspAward))
    place: Mapped[int | None] = mapped_column(Integer)
    team_name: Mapped[str | None] = mapped_column(String(200))

    event: Mapped[FspEvent] = relationship(lazy="raise")


class FspAthleteRank(Base):
    """Спортивный разряд или звание участника. Присваиваются приказами по результатам
    соревнований, поэтому на скор не влияют: бонус уже дают сами результаты."""

    __tablename__ = "fsp_athlete_ranks"

    fsp_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rank: Mapped[FspSportRank] = mapped_column(str_enum_column_type(FspSportRank))
    assigned_on: Mapped[date] = mapped_column(Date)
