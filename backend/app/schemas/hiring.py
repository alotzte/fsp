import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.assessment import CompetencyResultRead
from app.schemas.candidates import CandidateEmployerView, LongText, ShortText, mask_contacts
from app.schemas.common import DbInt, SkillCheckRead
from app.schemas.companies import company_logo_url
from app.schemas.dictionaries import GradeRead, SpecializationRead
from app.schemas.fsp import FspRankRead, FspResultRead
from app.schemas.invitations import EmployerInvitationRead, SalaryRangeInput
from app.services.db.models import InvitationStatus, SkillKind, WorkFormat

if TYPE_CHECKING:
    from app.services.db.models import HiringNeed
    from app.services.hiring import (
        CandidateDetails,
        CandidateMatch,
        CategoryCount,
        PoolCandidate,
        SearchResult,
    )
    from app.services.invitations import VacancyItem
    from app.services.scoring import MatchResult

MAX_NEED_SKILLS = 30
DUPLICATE_SKILLS_ERROR = "Навык указан дважды"


class NeedSkillInput(BaseModel):
    skill_id: DbInt
    must_have: bool = True


class HiringNeedInput(SalaryRangeInput):
    title: ShortText
    # Чем занимается команда и какие задачи у специалиста.
    description: LongText = ""
    specialization_id: DbInt
    grade_id: DbInt
    skills: Annotated[
        list[NeedSkillInput], Field(default_factory=list, max_length=MAX_NEED_SKILLS)
    ]
    work_formats: list[WorkFormat] = Field(default_factory=list)
    city: Annotated[str, Field(max_length=100)] = ""
    # Опубликовать как вакансию: кандидаты направления увидят её и смогут откликнуться.
    published: bool = False

    @field_validator("skills")
    @classmethod
    def _unique_skills(cls, value: list[NeedSkillInput]) -> list[NeedSkillInput]:
        if len({s.skill_id for s in value}) != len(value):
            raise ValueError(DUPLICATE_SKILLS_ERROR)
        return value

    @field_validator("work_formats")
    @classmethod
    def _unique_formats(cls, value: list[WorkFormat]) -> list[WorkFormat]:
        return list(dict.fromkeys(value))


class NeedSkillRead(BaseModel):
    skill_id: int
    title: str
    must_have: bool


class HiringNeedRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    specialization: SpecializationRead
    grade: GradeRead
    skills: list[NeedSkillRead]
    work_formats: list[WorkFormat]
    city: str
    salary_from_rub: int
    salary_to_rub: int
    published_at: datetime | None
    created_at: datetime

    @classmethod
    def from_need(cls, need: "HiringNeed") -> "HiringNeedRead":
        return cls(
            id=need.id,
            title=need.title,
            description=need.description,
            specialization=SpecializationRead.model_validate(need.specialization),
            grade=GradeRead.model_validate(need.grade),
            skills=[
                NeedSkillRead(skill_id=s.skill_id, title=s.skill.title, must_have=s.must_have)
                for s in need.skills
            ],
            work_formats=[WorkFormat(f) for f in need.work_formats],
            city=need.city,
            salary_from_rub=need.salary_from_rub,
            salary_to_rub=need.salary_to_rub,
            published_at=need.published_at,
            created_at=need.created_at,
        )


class ContributionRead(BaseModel):
    key: str
    title: str
    value: float
    weight: float


class MatchRead(BaseModel):
    """Почему кандидат на этой позиции: итоговый скор, вклады и объяснения из них."""

    score: float
    # Верх вилки не ниже скрытых ожиданий кандидата: иначе приглашение не отправить.
    salary_compatible: bool
    # Кандидат рассматривает хотя бы один из форматов работы потребности.
    format_compatible: bool
    contributions: list[ContributionRead]
    reasons: list[str]
    skills: list[SkillCheckRead]

    @classmethod
    def from_result(cls, result: "MatchResult") -> "MatchRead":
        return cls(
            score=result.score,
            salary_compatible=result.salary_compatible,
            format_compatible=result.format_compatible,
            contributions=[
                ContributionRead.model_validate(c.model_dump()) for c in result.contributions
            ],
            reasons=result.reasons,
            skills=[SkillCheckRead.model_validate(s.model_dump()) for s in result.skills],
        )


class CategoryCountRead(BaseModel):
    """Категория банка: направление × грейд, сколько кандидатов и сколько подтвердили грейд."""

    specialization: SpecializationRead
    # Нет: кандидаты, ещё не начинавшие тест.
    grade: GradeRead | None
    total: int
    confirmed: int

    @classmethod
    def from_count(cls, count: "CategoryCount") -> "CategoryCountRead":
        return cls(
            specialization=SpecializationRead.model_validate(count.specialization),
            grade=GradeRead.model_validate(count.grade) if count.grade else None,
            total=count.total,
            confirmed=count.confirmed,
        )


class CandidateCategoryRead(BaseModel):
    specialization: SpecializationRead | None
    grade: GradeRead | None
    confirmed: bool
    confirmed_at: datetime | None

    @classmethod
    def from_candidate(cls, candidate: "PoolCandidate") -> "CandidateCategoryRead":
        category = candidate.category
        specialization = category.specialization if category else candidate.profile.specialization
        grade = candidate.grade
        return cls(
            specialization=(
                SpecializationRead.model_validate(specialization) if specialization else None
            ),
            grade=GradeRead.model_validate(grade) if grade else None,
            confirmed=candidate.confirmed,
            confirmed_at=category.confirmed_at if category else None,
        )


class CandidateCardRead(BaseModel):
    """Кандидат в выдаче: обезличенно, с категорией и объяснением позиции."""

    candidate_number: int
    category: CandidateCategoryRead
    # Победы, призовые места и финалы в реестре ФСП.
    fsp_achievements: int
    # Верно решённых кейсов недели за 30 дней.
    recent_cases: int
    technologies: list[str]
    total_experience_months: int
    city: str
    work_formats: list[WorkFormat]
    match: MatchRead
    invitation_status: InvitationStatus | None
    contacts_revealed: bool
    # Отобран в шортлист потребности, по которой строится выдача.
    shortlisted: bool

    @classmethod
    def from_match(cls, item: "CandidateMatch") -> "CandidateCardRead":
        profile = item.candidate.profile

        def text(value: str) -> str:
            # Свои теги и город это свободный текст: до принятия приглашения без контактов.
            return value if item.contacts_revealed else mask_contacts(value)

        return cls(
            candidate_number=profile.candidate_number,
            category=CandidateCategoryRead.from_candidate(item.candidate),
            fsp_achievements=item.candidate.fsp.achievements,
            recent_cases=item.candidate.recent_cases,
            technologies=[
                s.skill.title if s.skill else text(s.custom_title or "")
                for s in profile.skills
                if s.kind == SkillKind.TECHNOLOGY
            ],
            total_experience_months=item.total_experience_months,
            city=text(profile.city),
            work_formats=[WorkFormat(f) for f in profile.work_formats],
            match=MatchRead.from_result(item.match),
            invitation_status=item.invitation.status if item.invitation else None,
            contacts_revealed=item.contacts_revealed,
            shortlisted=item.shortlisted,
        )


class CandidateSearchRead(BaseModel):
    need: HiringNeedRead | None
    candidates: list[CandidateCardRead]
    # Отобранные в потребность: независимо от фильтров, чтобы уточнение их не теряло.
    shortlist: list[CandidateCardRead]

    @classmethod
    def from_result(cls, result: "SearchResult") -> "CandidateSearchRead":
        return cls(
            need=HiringNeedRead.from_need(result.need) if result.need else None,
            candidates=[CandidateCardRead.from_match(item) for item in result.candidates],
            shortlist=[CandidateCardRead.from_match(item) for item in result.shortlist],
        )


class CandidateContactsRead(BaseModel):
    """Контакты: только после того, как кандидат принял приглашение компании."""

    last_name: str
    first_name: str
    middle_name: str
    email: str
    phone: str
    telegram: str


class EmployerCandidateRead(BaseModel):
    profile: CandidateEmployerView
    category: CandidateCategoryRead
    test_results: list[CompetencyResultRead]
    # Результаты из реестра ФСП; пусто: ФСП ID не привязан или истории нет (без штрафа).
    fsp_linked: bool
    fsp_results: list[FspResultRead]
    fsp_sport_rank: FspRankRead | None
    # Верно решённых кейсов недели за 30 дней.
    recent_cases: int
    # Неверных ответов в тесте, совпавших с эталоном чужого варианта задания: признак утечки,
    # на грейд не влияет (такие ответы не засчитаны).
    foreign_answers: int
    match: MatchRead | None
    contacts: CandidateContactsRead | None
    invitations: list[EmployerInvitationRead]

    @classmethod
    def from_details(cls, details: "CandidateDetails") -> "EmployerCandidateRead":
        profile = details.candidate.profile
        user = details.contacts
        return cls(
            profile=CandidateEmployerView.from_profile(
                profile, details.total_experience_months, contacts_revealed=user is not None
            ),
            category=CandidateCategoryRead.from_candidate(details.candidate),
            test_results=[
                CompetencyResultRead(title=r.title, correct=r.correct, total=r.total)
                for r in details.test_results
            ],
            fsp_linked=details.fsp.link is not None,
            fsp_sport_rank=FspRankRead.from_profile(details.fsp),
            recent_cases=details.candidate.recent_cases,
            foreign_answers=details.candidate.foreign_answers,
            fsp_results=[
                FspResultRead.from_result(r, with_team=user is not None)
                for r in details.fsp.results
            ],
            match=MatchRead.from_result(details.match) if details.match else None,
            contacts=(
                CandidateContactsRead(
                    last_name=profile.last_name,
                    first_name=profile.first_name,
                    middle_name=profile.middle_name,
                    email=user.email,
                    phone=profile.phone,
                    telegram=profile.telegram,
                )
                if user is not None
                else None
            ),
            invitations=[
                EmployerInvitationRead.from_invitation(
                    inv, profile.candidate_number, contacts_shared=user is not None
                )
                for inv in details.invitations
            ],
        )


class VacancyCompanyRead(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None
    verified_domain: str


class VacancyRead(BaseModel):
    """Вакансия в ленте кандидата: суть, вилка и совпадение с его профилем."""

    need: HiringNeedRead
    company: VacancyCompanyRead
    # Совпадение профиля с вакансией тем же скором, что в подборке работодателя (0..1),
    # и навыки вакансии с пометками «подтверждён тестом / заявлен / нет».
    match_score: float
    skills: list[SkillCheckRead]
    # Статус последнего отклика; нет: не откликались.
    application_status: InvitationStatus | None
    # Почему откликнуться нельзя (правила отклика); нет: можно.
    apply_block: str | None

    @classmethod
    def from_item(cls, item: "VacancyItem") -> "VacancyRead":
        vacancy = item.vacancy
        company = vacancy.need.company
        return cls(
            need=HiringNeedRead.from_need(vacancy.need),
            company=VacancyCompanyRead(
                id=company.id,
                name=company.name,
                logo_url=company_logo_url(company.id, company.logo_file_id),
                verified_domain=company.verified_domain,
            ),
            match_score=vacancy.match.score,
            skills=[SkillCheckRead.model_validate(s.model_dump()) for s in vacancy.match.skills],
            application_status=item.application_status,
            apply_block=item.apply_block.message if item.apply_block else None,
        )
