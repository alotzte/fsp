from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.services.db.models import FspAward, FspDiscipline, FspSportRank
from app.services.fsp import ACHIEVEMENT_AWARDS

if TYPE_CHECKING:
    from app.services.db.models import FspResult
    from app.services.fsp import FspProfile


class FspResultRead(BaseModel):
    """Результат из реестра ФСП: проверенные данные, а не самоописание кандидата."""

    event_title: str
    discipline: FspDiscipline
    starts_on: date
    # Номер соревнования в Едином календарном плане (ЕКП) Минспорта.
    ekp_number: str | None
    award: FspAward
    place: int | None
    # Команда вместе с соревнованием выдаёт человека, поэтому работодателю она
    # показывается только вместе с контактами.
    team_name: str | None

    @classmethod
    def from_result(cls, result: "FspResult", *, with_team: bool = True) -> "FspResultRead":
        return cls(
            event_title=result.event.title,
            discipline=result.event.discipline,
            starts_on=result.event.starts_on,
            ekp_number=result.event.ekp_number,
            award=result.award,
            place=result.place,
            team_name=result.team_name if with_team else None,
        )


class FspRankRead(BaseModel):
    """Спортивный разряд или звание по реестру ФСП; на скор не влияет."""

    rank: FspSportRank
    assigned_on: date

    @classmethod
    def from_profile(cls, profile: "FspProfile") -> "FspRankRead | None":
        rank = profile.rank
        return cls(rank=rank.rank, assigned_on=rank.assigned_on) if rank else None


class FspProfileRead(BaseModel):
    linked: bool
    fsp_id: str | None
    linked_at: datetime | None
    sport_rank: FspRankRead | None
    # Победы, призовые места и финалы: то, что учитывается в подборках.
    achievements: int
    results: list[FspResultRead]

    @classmethod
    def from_profile(cls, profile: "FspProfile") -> "FspProfileRead":
        return cls(
            linked=profile.link is not None,
            fsp_id=profile.link.fsp_id if profile.link else None,
            linked_at=profile.link.linked_at if profile.link else None,
            sport_rank=FspRankRead.from_profile(profile),
            achievements=sum(r.award in ACHIEVEMENT_AWARDS for r in profile.results),
            results=[FspResultRead.from_result(r) for r in profile.results],
        )
