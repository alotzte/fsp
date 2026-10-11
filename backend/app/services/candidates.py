from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Annotated, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.errors import NotFoundError
from app.services.consents import ConsentRequiredError, ConsentServiceDep, ConsentState
from app.services.db.models import (
    CandidateProfile,
    CandidateSkill,
    ConsentKind,
    Education,
    ProfileSection,
    SkillKind,
    User,
    WorkExperience,
)
from app.services.db.session import SessionDep
from app.services.dictionaries import DictionaryServiceDep, SkillRequest

if TYPE_CHECKING:
    from app.schemas.candidates import CandidateProfileInput, SkillInput

MONTHS_IN_YEAR = 12


class CandidateProfileNotFoundError(NotFoundError):
    message = "Профиль ещё не заполнен"


@dataclass(frozen=True)
class CandidateProfileOverview:
    user: User
    profile: CandidateProfile | None
    consents: list[ConsentState]
    total_experience_months: int

    @property
    def is_published(self) -> bool:
        return self.profile is not None and any(
            state.kind == ConsentKind.PROFILE_PUBLICATION and state.is_active
            for state in self.consents
        )


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * MONTHS_IN_YEAR + end.month - start.month


class Period(Protocol):
    @property
    def started_on(self) -> date: ...
    @property
    def ended_on(self) -> date | None: ...


def total_experience_months(experience: Sequence[Period]) -> int:
    """Общий стаж в месяцах. Пересекающиеся периоды (две работы одновременно) не суммируются."""
    this_month = datetime.now(UTC).date().replace(day=1)
    periods = sorted((entry.started_on, entry.ended_on or this_month) for entry in experience)
    total = 0
    current_start: date | None = None
    current_end: date | None = None
    for start, end in periods:
        if current_start is None or current_end is None or start > current_end:
            if current_start is not None and current_end is not None:
                total += _months_between(current_start, current_end) + 1
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_start is not None and current_end is not None:
        total += _months_between(current_start, current_end) + 1
    return total


def _skill_requests(items: "Sequence[SkillInput]") -> list[SkillRequest]:
    return [SkillRequest(skill_id=item.skill_id, title=item.title) for item in items]


class CandidateProfileService:
    def __init__(
        self,
        session: SessionDep,
        consents: ConsentServiceDep,
        dictionaries: DictionaryServiceDep,
    ) -> None:
        self._session = session
        self._consents = consents
        self._dictionaries = dictionaries

    async def get_overview(self, user: User) -> CandidateProfileOverview:
        profile = await self._load_profile(user)
        return CandidateProfileOverview(
            user=user,
            profile=profile,
            consents=await self._consents.get_states(user),
            total_experience_months=total_experience_months(profile.experience) if profile else 0,
        )

    async def save(self, user: User, data: "CandidateProfileInput") -> CandidateProfileOverview:
        if not await self._consents.is_active(user, ConsentKind.DATA_PROCESSING):
            raise ConsentRequiredError
        if data.specialization_id is not None:
            await self._dictionaries.require_specialization(data.specialization_id)
        technologies = await self._dictionaries.resolve_skills(
            _skill_requests(data.technologies), SkillKind.TECHNOLOGY
        )
        soft_skills = await self._dictionaries.resolve_skills(
            _skill_requests(data.soft_skills), SkillKind.SOFT
        )

        # Сохранения одного кандидата идут по очереди (две вкладки, повторная отправка), иначе
        # списки склеивались из разных запросов, а первое создание профиля падало на дубле ключа.
        await self._session.execute(select(User.id).where(User.id == user.id).with_for_update())
        profile = await self._load_profile(user)
        if profile is None:
            profile = CandidateProfile(user_id=user.id)
            self._session.add(profile)
        profile.last_name = data.last_name
        profile.first_name = data.first_name
        profile.middle_name = data.middle_name
        profile.phone = data.phone
        profile.telegram = data.telegram
        profile.specialization_id = data.specialization_id
        profile.work_formats = [work_format.value for work_format in data.work_formats]
        profile.city = data.city
        profile.salary_expectation_rub = data.salary_expectation_rub
        profile.about = data.about
        # Списки заменяются целиком: форма всегда присылает профиль полностью.
        profile.skills = [
            CandidateSkill(
                kind=kind,
                skill_id=item.skill.id if item.skill else None,
                custom_title=item.custom_title,
            )
            for kind, items in (
                (SkillKind.TECHNOLOGY, technologies),
                (SkillKind.SOFT, soft_skills),
            )
            for item in items
        ]
        profile.experience = [
            WorkExperience(
                company_name=entry.company_name,
                position=entry.position,
                started_on=entry.started_on,
                ended_on=entry.ended_on,
                description=entry.description,
            )
            for entry in data.experience
        ]
        profile.education = [
            Education(
                institution=entry.institution,
                specialty=entry.specialty,
                graduation_year=entry.graduation_year,
            )
            for entry in data.education
        ]
        await self._session.commit()
        # Перечитываем с нуля: связи (навыки со справочником, специализация) нужны загруженными.
        self._session.expunge(profile)
        return await self.get_overview(user)

    async def set_hidden_sections(
        self, user: User, sections: "Sequence[ProfileSection]"
    ) -> CandidateProfileOverview:
        """Какие разделы скрыть от работодателя до принятия приглашения."""
        profile = await self._load_profile(user)
        if profile is None:
            raise CandidateProfileNotFoundError
        profile.hidden_sections = [section.value for section in dict.fromkeys(sections)]
        await self._session.commit()
        self._session.expunge(profile)
        return await self.get_overview(user)

    async def _load_profile(self, user: User) -> CandidateProfile | None:
        return await self._session.scalar(
            select(CandidateProfile)
            .options(
                joinedload(CandidateProfile.specialization),
                selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill),
                selectinload(CandidateProfile.experience),
                selectinload(CandidateProfile.education),
            )
            .where(CandidateProfile.user_id == user.id)
        )


CandidateProfileServiceDep = Annotated[CandidateProfileService, Depends()]
