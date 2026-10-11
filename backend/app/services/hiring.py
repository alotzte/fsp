"""Подбор: потребности работодателя, выдача кандидатов с объяснением, карточка кандидата.

Выдача строится по категориям из тестирования (направление × грейд), а не по резюме.
Ранжирование и объяснения считает сервис scoring, а здесь данные и права.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy import Select, and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.errors import DomainError, NotFoundError
from app.services.candidates import total_experience_months
from app.services.cases import CaseServiceDep
from app.services.consents import CONSENT_DOCUMENTS
from app.services.db.models import (
    JURY_DEMO_PREFIX,
    PENDING_STATUSES,
    AssessmentAttempt,
    AttemptItem,
    CandidateGrade,
    CandidateProfile,
    CandidateSkill,
    Company,
    CompanyMember,
    Consent,
    ConsentKind,
    ContactReveal,
    Grade,
    HiringNeed,
    HiringNeedSkill,
    Invitation,
    InvitationStatus,
    ShortlistEntry,
    SkillKind,
    Specialization,
    User,
)
from app.services.db.session import SessionDep
from app.services.dictionaries import DictionaryServiceDep, SkillRequest
from app.services.fsp import NO_FSP, FspProfile, FspServiceDep, FspStanding
from app.services.scoring import (
    CandidateFeatures,
    MatchResult,
    NeedFeatures,
    NeedSkillFeature,
    ScoringClientDep,
)

if TYPE_CHECKING:
    from app.schemas.hiring import HiringNeedInput

# ponytail: выдача считается по всему пулу направления за один запрос к scoring.
# При тысячах кандидатов: предфильтр в SQL (pgvector/FTS) и топ-N в scoring.
MAX_POOL = 1000
MAX_RESULTS = 200
# Сколько вакансий в ленте кандидата: по каждой считается совпадение в scoring.
MAX_VACANCIES = 30
# Компетенция теста → навык справочника (slug), который она проверяет. У http_api, web, ml и
# stats своего навыка в справочнике нет: они подтверждают только грейд.
COMPETENCY_SKILLS = {
    "python": "python",
    "js": "javascript",
    "sql": "sql",
    "react": "react",
    "algorithms": "algorithms",
}
# Навык подтверждён, если по его компетенции верно не меньше половины заданий и заданий не
# меньше двух: одно задание экспресс-теста это угадывание, а не проверка. Ниже порога навык
# не «опровергнут», а просто заявлен: тест не штрафует.
VERIFIED_SHARE = 0.5
VERIFIED_MIN_ITEMS = 2


class HiringNeedNotFoundError(NotFoundError):
    message = "Потребность не найдена"


class CandidateNotFoundError(NotFoundError):
    message = "Кандидат не найден или скрыл профиль"


class VacancyNotFoundError(NotFoundError):
    message = "Вакансия не найдена или снята с публикации"


class UnknownGradeError(DomainError):
    message = "Грейд не найден в справочнике"


@dataclass(frozen=True)
class SearchFilters:
    specialization_id: int | None = None
    grade_id: int | None = None
    skill_ids: frozenset[int] = frozenset()
    confirmed_only: bool = False
    work_format: str | None = None
    # Только с подтверждёнными достижениями ФСП (победа, призовое место, финал).
    has_fsp: bool = False


@dataclass(frozen=True)
class CompetencyResult:
    competency: str
    title: str
    correct: int
    total: int


def verified_skill_slugs(results: Iterable[CompetencyResult]) -> set[str]:
    return {
        COMPETENCY_SKILLS[r.competency]
        for r in results
        if r.competency in COMPETENCY_SKILLS
        and r.total >= VERIFIED_MIN_ITEMS
        and r.correct >= VERIFIED_SHARE * r.total
    }


@dataclass(frozen=True)
class PoolCandidate:
    profile: CandidateProfile
    category: CandidateGrade | None
    fsp: FspStanding = NO_FSP
    # Итоги по компетенциям из попытки, подтвердившей текущий грейд.
    test_results: tuple[CompetencyResult, ...] = ()
    # Верно решённых кейсов недели за 30 дней: свежий сигнал «кандидат в форме».
    recent_cases: int = 0
    # Ответов от чужого варианта задания в подтвердившей грейд попытке (детектор утечки).
    # Считается только для карточки, в выдаче всегда 0.
    foreign_answers: int = 0

    @property
    def grade(self) -> Grade | None:
        if self.category is None:
            return None
        return self.category.confirmed_grade or self.category.claimed_grade

    @property
    def confirmed(self) -> bool:
        return self.category is not None and self.category.confirmed_grade is not None

    @property
    def skill_ids(self) -> frozenset[int]:
        return frozenset(s.skill_id for s in self.profile.skills if s.skill_id is not None)

    @property
    def verified_skill_ids(self) -> frozenset[int]:
        """Заявленные навыки, которые подтвердил тест: тест не дописывает навыки в профиль."""
        slugs = verified_skill_slugs(self.test_results)
        return frozenset(
            s.skill.id
            for s in self.profile.skills
            if s.skill is not None and s.skill.slug in slugs
        )


@dataclass(frozen=True)
class CandidateMatch:
    candidate: PoolCandidate
    match: MatchResult
    total_experience_months: int
    # Статус последнего приглашения от компании этому кандидату.
    invitation: Invitation | None
    contacts_revealed: bool
    shortlisted: bool = False


@dataclass(frozen=True)
class SearchResult:
    need: HiringNeed | None
    candidates: list[CandidateMatch]
    # Отобранные в потребность: всегда, независимо от фильтров. Без потребности пусто.
    shortlist: list[CandidateMatch]


@dataclass(frozen=True)
class CategoryCount:
    """Сколько опубликованных кандидатов в категории «направление × грейд»."""

    specialization: Specialization
    # Подтверждённый грейд, а пока его нет (заявленный; None, если тест ещё не начинали).
    grade: Grade | None
    total: int
    confirmed: int


@dataclass(frozen=True)
class CandidateDetails:
    candidate: PoolCandidate
    total_experience_months: int
    test_results: list[CompetencyResult]
    fsp: FspProfile
    match: MatchResult | None
    contacts: User | None
    invitations: list[Invitation]


@dataclass(frozen=True)
class Vacancy:
    need: HiringNeed
    match: MatchResult


def _sandbox_user_ids() -> Select[uuid.UUID]:
    return select(User.id).where(User.keycloak_sub.startswith(JURY_DEMO_PREFIX))


def _sandbox_company_ids() -> Select[uuid.UUID]:
    return select(CompanyMember.company_id).where(CompanyMember.user_id.in_(_sandbox_user_ids()))


def _published_user_ids(*, sandboxes: bool) -> Select[uuid.UUID]:
    """sandboxes: показывать ли песочницы жюри (`User.sees_sandboxes` того, кто смотрит)."""
    publication = CONSENT_DOCUMENTS[ConsentKind.PROFILE_PUBLICATION]
    query = select(Consent.user_id).where(
        Consent.kind == ConsentKind.PROFILE_PUBLICATION,
        Consent.revoked_at.is_(None),
        Consent.document_version == publication.version,
    )
    return query if sandboxes else query.where(Consent.user_id.not_in(_sandbox_user_ids()))


def published_candidates(*, sandboxes: bool) -> Select[CandidateProfile, CandidateGrade]:
    """Профили с действующим согласием на показ работодателям: только их видит работодатель."""
    return _candidates().where(
        CandidateProfile.user_id.in_(_published_user_ids(sandboxes=sandboxes))
    )


def _candidates() -> Select[CandidateProfile, CandidateGrade]:
    return (
        select(CandidateProfile, CandidateGrade)
        .outerjoin(CandidateGrade, CandidateGrade.user_id == CandidateProfile.user_id)
        .options(
            joinedload(CandidateProfile.specialization),
            selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
            joinedload(CandidateGrade.specialization),
            joinedload(CandidateGrade.claimed_grade),
            joinedload(CandidateGrade.confirmed_grade),
        )
    )


def _specialization_slug(profile: CandidateProfile, category: CandidateGrade | None) -> str | None:
    """Направление кандидата: категории, иначе профиля (то же правило, что у пула)."""
    if category is not None:
        return category.specialization.slug
    return profile.specialization.slug if profile.specialization else None


def _confirming_attempts(user_ids: Sequence[uuid.UUID]) -> Select[uuid.UUID]:
    """Последняя попытка каждого кандидата, подтвердившая его текущий грейд."""
    return (
        select(AssessmentAttempt.id)
        .join(
            CandidateGrade,
            and_(
                CandidateGrade.user_id == AssessmentAttempt.user_id,
                CandidateGrade.specialization_id == AssessmentAttempt.specialization_id,
                CandidateGrade.confirmed_grade_id == AssessmentAttempt.grade_id,
            ),
        )
        .where(AssessmentAttempt.user_id.in_(user_ids), AssessmentAttempt.passed.is_(True))
        .distinct(AssessmentAttempt.user_id)
        .order_by(AssessmentAttempt.user_id, AssessmentAttempt.finished_at.desc())
    )


def _need_features(need: HiringNeed) -> NeedFeatures:
    return NeedFeatures(
        grade_level=need.grade.level,
        skills=[
            NeedSkillFeature(id=s.skill_id, title=s.skill.title, must_have=s.must_have)
            for s in need.skills
        ],
        work_formats=need.work_formats,
        city=need.city,
        salary_to=need.salary_to_rub,
    )


def _candidate_features(c: PoolCandidate) -> CandidateFeatures:
    grade = c.grade
    category = c.category
    return CandidateFeatures(
        key=c.profile.candidate_number,
        grade_level=grade.level if grade else None,
        grade_title=grade.title if grade else None,
        confirmed=c.confirmed,
        theta=category.theta if category else None,
        theta_se=category.theta_se if category else None,
        skills=sorted(c.skill_ids),
        work_formats=c.profile.work_formats,
        city=c.profile.city,
        fsp_score=c.fsp.score,
        fsp_achievements=c.fsp.achievements,
        fsp_relevant=c.fsp.relevant,
        salary_expectation=c.profile.salary_expectation_rub,
        verified_skills=sorted(c.verified_skill_ids),
        recent_cases=c.recent_cases,
    )


def _passes(c: PoolCandidate, filters: SearchFilters, grade_levels: set[int] | None) -> bool:
    grade = c.grade
    # Без категории кандидат остаётся в подборке под потребность (ниже всех), но не проходит
    # явный фильтр по грейду.
    grade_ok = (
        grade_levels is None
        or (grade is None and filters.grade_id is None)
        or (grade is not None and grade.level in grade_levels)
    )
    return (
        grade_ok
        and (not filters.confirmed_only or c.confirmed)
        and filters.skill_ids <= c.skill_ids
        and (filters.work_format is None or filters.work_format in c.profile.work_formats)
        and (not filters.has_fsp or c.fsp.achievements > 0)
    )


class HiringService:
    def __init__(
        self,
        session: SessionDep,
        dictionaries: DictionaryServiceDep,
        scoring: ScoringClientDep,
        fsp: FspServiceDep,
        cases: CaseServiceDep,
    ) -> None:
        self._cases = cases
        self._session = session
        self._dictionaries = dictionaries
        self._scoring = scoring
        self._fsp = fsp

    # --- Потребности ---

    async def list_needs(self, member: CompanyMember) -> Sequence[HiringNeed]:
        result = await self._session.scalars(
            self._need_query()
            .where(HiringNeed.company_id == member.company_id)
            .order_by(HiringNeed.created_at.desc())
        )
        return result.all()

    async def get_need(self, member: CompanyMember, need_id: uuid.UUID) -> HiringNeed:
        need = await self._session.scalar(
            self._need_query().where(
                HiringNeed.id == need_id, HiringNeed.company_id == member.company_id
            )
        )
        if need is None:
            raise HiringNeedNotFoundError
        return need

    async def create_need(self, member: CompanyMember, data: "HiringNeedInput") -> HiringNeed:
        need = HiringNeed(company_id=member.company_id, created_by_id=member.user_id)
        await self._fill_need(need, data)
        self._session.add(need)
        await self._session.commit()
        return await self.get_need(member, need.id)

    async def update_need(
        self, member: CompanyMember, need_id: uuid.UUID, data: "HiringNeedInput"
    ) -> HiringNeed:
        need = await self.get_need(member, need_id)
        await self._fill_need(need, data)
        await self._session.commit()
        self._session.expunge(need)
        return await self.get_need(member, need_id)

    async def delete_need(self, member: CompanyMember, need_id: uuid.UUID) -> None:
        await self._session.delete(await self.get_need(member, need_id))
        await self._session.commit()

    async def _fill_need(self, need: HiringNeed, data: "HiringNeedInput") -> None:
        await self._dictionaries.require_specialization(data.specialization_id)
        if await self._session.get(Grade, data.grade_id) is None:
            raise UnknownGradeError
        resolved = await self._dictionaries.resolve_skills(
            [SkillRequest(skill_id=s.skill_id, title=None) for s in data.skills],
            SkillKind.TECHNOLOGY,
        )
        must_have = {s.skill_id: s.must_have for s in data.skills}
        need.title = data.title
        need.description = data.description
        need.specialization_id = data.specialization_id
        need.grade_id = data.grade_id
        need.work_formats = [f.value for f in data.work_formats]
        need.city = data.city
        need.salary_from_rub = data.salary_from_rub
        need.salary_to_rub = data.salary_to_rub
        # Дата публикации не сбрасывается при правке: вакансия не «всплывает» заново.
        if not data.published:
            need.published_at = None
        elif need.published_at is None:
            need.published_at = datetime.now(UTC)
        need.skills = [
            HiringNeedSkill(skill_id=item.skill.id, must_have=must_have[item.skill.id])
            for item in resolved
            if item.skill is not None
        ]

    @classmethod
    def _vacancy_query(cls, *, sandboxes: bool) -> Select[HiringNeed]:
        """Опубликованные вакансии; у замороженной жалобами компании их не видно, вакансии
        песочниц жюри: только тем, кто видит песочницы."""
        query = (
            cls._need_query()
            .join(Company, Company.id == HiringNeed.company_id)
            .options(joinedload(HiringNeed.company))
            .where(HiringNeed.published_at.is_not(None), Company.frozen_at.is_(None))
        )
        if sandboxes:
            return query
        return query.where(HiringNeed.company_id.not_in(_sandbox_company_ids()))

    @staticmethod
    def _need_query() -> Select[HiringNeed]:
        return select(HiringNeed).options(
            joinedload(HiringNeed.specialization),
            joinedload(HiringNeed.grade),
            selectinload(HiringNeed.skills).joinedload(HiringNeedSkill.skill),
        )

    # --- Выдача ---

    async def search(
        self, member: CompanyMember, *, need_id: uuid.UUID | None, filters: SearchFilters
    ) -> SearchResult:
        """Подборка под потребность (need_id) или поиск по банку (только фильтры).

        С потребностью: направление из неё, грейд запрошенный и соседние (кандидат на
        ступень ниже или выше тоже может подойти), кандидаты без подтверждённого грейда
        остаются в выдаче ниже. Фильтры дальше сужают подборку, не пересобирая её.
        """
        need = await self.get_need(member, need_id) if need_id else None
        specialization_id = need.specialization_id if need else filters.specialization_id
        grade_levels: set[int] | None = None
        if need is not None:
            grade_levels = {need.grade.level - 1, need.grade.level, need.grade.level + 1}
        if filters.grade_id is not None:
            grade = await self._session.get(Grade, filters.grade_id)
            if grade is None:
                raise UnknownGradeError
            grade_levels = {grade.level}

        sandboxes = await self._sees_sandboxes(member)
        query = published_candidates(sandboxes=sandboxes).limit(MAX_POOL)
        if specialization_id is not None:
            query = query.where(
                func.coalesce(CandidateGrade.specialization_id, CandidateProfile.specialization_id)
                == specialization_id
            )
        pool = [c for c in await self._pool(query) if _passes(c, filters, grade_levels)]
        if need is None:
            return SearchResult(None, await self._ranked(member, None, pool, set()), [])

        shortlisted_pool = await self._pool(
            published_candidates(sandboxes=sandboxes)
            .join(ShortlistEntry, ShortlistEntry.candidate_user_id == CandidateProfile.user_id)
            .where(ShortlistEntry.need_id == need.id)
        )
        shortlisted = {c.profile.user_id for c in shortlisted_pool}
        return SearchResult(
            need,
            await self._ranked(member, need, pool, shortlisted),
            await self._ranked(member, need, shortlisted_pool, shortlisted),
        )

    async def categories(self, member: CompanyMember) -> list[CategoryCount]:
        """Обзор банка по категориям: откуда начинать поиск. Категория считается так же, как
        в пуле выдачи: направление из категории (иначе из профиля), грейд подтверждённый,
        а пока его нет: заявленный."""
        sandboxes = await self._sees_sandboxes(member)
        specialization_id = func.coalesce(
            CandidateGrade.specialization_id, CandidateProfile.specialization_id
        )
        grade_id = func.coalesce(
            CandidateGrade.confirmed_grade_id, CandidateGrade.claimed_grade_id
        )
        rows = (
            await self._session.execute(
                select(
                    specialization_id,
                    grade_id,
                    func.count(),
                    func.count(CandidateGrade.confirmed_grade_id),
                )
                .select_from(CandidateProfile)
                .outerjoin(CandidateGrade, CandidateGrade.user_id == CandidateProfile.user_id)
                .where(
                    CandidateProfile.user_id.in_(_published_user_ids(sandboxes=sandboxes)),
                    specialization_id.is_not(None),
                )
                .group_by(specialization_id, grade_id)
            )
        ).all()
        specializations = {s.id: s for s in await self._session.scalars(select(Specialization))}
        grades = {g.id: g for g in await self._session.scalars(select(Grade))}
        counts = [
            CategoryCount(specializations[spec], grades.get(grade) if grade else None, total, ok)
            for spec, grade, total, ok in rows
        ]
        # Без грейда: в конце своего направления.
        return sorted(
            counts,
            key=lambda c: (c.specialization.title, c.grade.level if c.grade else len(grades)),
        )

    async def add_to_shortlist(
        self, member: CompanyMember, need_id: uuid.UUID, candidate_number: int
    ) -> None:
        need = await self.get_need(member, need_id)
        candidate = await self.find_published(member, candidate_number)
        await self._session.execute(
            insert(ShortlistEntry)
            .values(
                need_id=need.id,
                candidate_user_id=candidate.profile.user_id,
                added_by_id=member.user_id,
            )
            .on_conflict_do_nothing()
        )
        await self._session.commit()

    async def remove_from_shortlist(
        self, member: CompanyMember, need_id: uuid.UUID, candidate_number: int
    ) -> None:
        need = await self.get_need(member, need_id)
        # Скрывший профиль кандидат тоже убирается: ищем по номеру без проверки публикации.
        await self._session.execute(
            delete(ShortlistEntry).where(
                ShortlistEntry.need_id == need.id,
                ShortlistEntry.candidate_user_id
                == select(CandidateProfile.user_id)
                .where(CandidateProfile.candidate_number == candidate_number)
                .scalar_subquery(),
            )
        )
        await self._session.commit()

    async def _pool(self, query: Select[CandidateProfile, CandidateGrade]) -> list[PoolCandidate]:
        rows = (await self._session.execute(query)).unique().all()
        user_ids = [profile.user_id for profile, _ in rows]
        standings = await self._fsp.standings(
            {
                profile.user_id: _specialization_slug(profile, category)
                for profile, category in rows
            }
        )
        results = await self._test_results([category for _, category in rows if category])
        solved = await self._cases.solved_recently(user_ids)
        return [
            PoolCandidate(
                profile,
                category,
                standings.get(profile.user_id, NO_FSP),
                results.get(profile.user_id, ()),
                solved.get(profile.user_id, 0),
            )
            for profile, category in rows
        ]

    async def _ranked(
        self,
        member: CompanyMember,
        need: HiringNeed | None,
        pool: list[PoolCandidate],
        shortlisted: set[uuid.UUID],
    ) -> list[CandidateMatch]:
        if not pool:
            return []
        matches = await self._scoring.rank(
            _need_features(need) if need else None, [_candidate_features(c) for c in pool]
        )
        by_number = {c.profile.candidate_number: c for c in pool}
        user_ids = [c.profile.user_id for c in pool]
        # Песочницы жюри: после остальных при том же порядке внутри групп, иначе клоны
        # демо-кандидата заслоняли бы засеянных и настоящих кандидатов.
        sandbox_ids = set(
            await self._session.scalars(_sandbox_user_ids().where(User.id.in_(user_ids)))
        )
        matches.sort(key=lambda m: by_number[m.key].profile.user_id in sandbox_ids)
        invitations = await self._latest_invitations(member, user_ids)
        revealed = await self._revealed(member, user_ids)
        return [
            CandidateMatch(
                candidate=by_number[m.key],
                match=m,
                total_experience_months=total_experience_months(
                    by_number[m.key].profile.experience
                ),
                invitation=invitations.get(by_number[m.key].profile.user_id),
                contacts_revealed=by_number[m.key].profile.user_id in revealed,
                shortlisted=by_number[m.key].profile.user_id in shortlisted,
            )
            for m in matches[:MAX_RESULTS]
        ]

    async def match(self, need: HiringNeed, candidate: PoolCandidate) -> MatchResult:
        """Совпадение одного кандидата с потребностью: с причинами и пометками навыков."""
        (result,) = await self._scoring.rank(
            _need_features(need), [_candidate_features(candidate)]
        )
        return result

    async def get_candidate(
        self, member: CompanyMember, candidate_number: int, *, need_id: uuid.UUID | None
    ) -> CandidateDetails:
        candidate = await self.find_published(member, candidate_number)
        need = await self.get_need(member, need_id) if need_id else None
        match = await self.match(need, candidate) if need is not None else None
        user_id = candidate.profile.user_id
        contacts = None
        if user_id in await self._revealed(member, [user_id]):
            contacts = await self._session.get(User, user_id)
        invitations = await self._session.scalars(
            select(Invitation)
            .where(
                Invitation.company_id == member.company_id,
                Invitation.candidate_user_id == user_id,
            )
            .order_by(Invitation.created_at.desc())
        )
        return CandidateDetails(
            candidate=candidate,
            total_experience_months=total_experience_months(candidate.profile.experience),
            test_results=list(candidate.test_results),
            fsp=await self._fsp.get_profile(user_id),
            match=match,
            contacts=contacts,
            invitations=list(invitations),
        )

    async def own_details(self, user: User) -> CandidateDetails:
        """Карточка кандидата для него самого: как её видит работодатель после принятия
        приглашения (с ФИО и контактами). Публикация не нужна: это выгрузка своего профиля."""
        candidate = await self._load_candidate(
            _candidates().where(CandidateProfile.user_id == user.id)
        )
        return CandidateDetails(
            candidate=candidate,
            total_experience_months=total_experience_months(candidate.profile.experience),
            test_results=list(candidate.test_results),
            fsp=await self._fsp.get_profile(user.id),
            match=None,
            contacts=user,
            invitations=[],
        )

    async def own_candidate(self, user: User, *, published: bool) -> PoolCandidate:
        """Свой профиль кандидата в виде участника выдачи. published: только если профиль
        опубликован (без этого откликаться нельзя: работодатель не открыл бы карточку)."""
        # Свой профиль кандидат видит всегда, песочница он или нет.
        query = published_candidates(sandboxes=True) if published else _candidates()
        return await self._load_candidate(query.where(CandidateProfile.user_id == user.id))

    async def published_need(self, user: User, need_id: uuid.UUID) -> HiringNeed:
        need = await self._session.scalar(
            self._vacancy_query(sandboxes=user.sees_sandboxes).where(HiringNeed.id == need_id)
        )
        if need is None:
            raise VacancyNotFoundError
        return need

    async def vacancies(self, user: User) -> list[Vacancy]:
        """Лента вакансий направления кандидата (категории, иначе профиля): с совпадением,
        посчитанным тем же скором, что и подборка работодателя."""
        candidate = await self.own_candidate(user, published=False)
        category = candidate.category
        specialization_id = (
            category.specialization_id if category else candidate.profile.specialization_id
        )
        query = (
            self._vacancy_query(sandboxes=user.sees_sandboxes)
            # Вакансии песочниц: после остальных, иначе их копии заслоняли бы настоящие.
            .order_by(
                HiringNeed.company_id.in_(_sandbox_company_ids()), HiringNeed.published_at.desc()
            )
            .limit(MAX_VACANCIES)
        )
        if specialization_id is not None:
            query = query.where(HiringNeed.specialization_id == specialization_id)
        needs = list((await self._session.scalars(query)).unique())
        # ponytail: по вызову scoring на вакансию, параллельно; при длинной ленте: один
        # пакетный запрос «кандидат × вакансии».
        matches = await asyncio.gather(*(self.match(need, candidate) for need in needs))
        return [Vacancy(need, match) for need, match in zip(needs, matches, strict=True)]

    async def find_published(self, member: CompanyMember, candidate_number: int) -> PoolCandidate:
        sandboxes = await self._sees_sandboxes(member)
        return await self._load_candidate(
            published_candidates(sandboxes=sandboxes).where(
                CandidateProfile.candidate_number == candidate_number
            )
        )

    async def _sees_sandboxes(self, member: CompanyMember) -> bool:
        # Пользователь уже в сессии (его загрузила авторизация), get берёт его без запроса.
        return (await self._session.get_one(User, member.user_id)).sees_sandboxes

    async def _load_candidate(
        self, query: Select[CandidateProfile, CandidateGrade]
    ) -> PoolCandidate:
        row = (await self._session.execute(query)).unique().one_or_none()
        if row is None:
            raise CandidateNotFoundError
        profile, category = row
        standings = await self._fsp.standings(
            {profile.user_id: _specialization_slug(profile, category)}
        )
        standing = standings.get(profile.user_id, NO_FSP)
        results = await self._test_results([category] if category else [])
        solved = await self._cases.solved_recently([profile.user_id])
        foreign = 0
        if category is not None and category.confirmed_grade_id is not None:
            foreign = (
                await self._session.scalar(
                    select(AssessmentAttempt.foreign_answers).where(
                        AssessmentAttempt.id.in_(_confirming_attempts([profile.user_id]))
                    )
                )
                or 0
            )
        return PoolCandidate(
            profile,
            category,
            standing,
            results.get(profile.user_id, ()),
            solved.get(profile.user_id, 0),
            foreign,
        )

    async def _test_results(
        self, categories: Sequence[CandidateGrade]
    ) -> dict[uuid.UUID, tuple[CompetencyResult, ...]]:
        """Итоги по компетенциям из последней попытки, подтвердившей текущий грейд:
        одним запросом на весь пул."""
        user_ids = [c.user_id for c in categories if c.confirmed_grade_id is not None]
        if not user_ids:
            return {}
        confirming = _confirming_attempts(user_ids)
        rows = await self._session.execute(
            select(
                AssessmentAttempt.user_id,
                AttemptItem.competency,
                AttemptItem.competency_title,
                func.count().filter(AttemptItem.is_correct.is_(True)),
                func.count(),
            )
            .join(AttemptItem, AttemptItem.attempt_id == AssessmentAttempt.id)
            .where(AssessmentAttempt.id.in_(confirming))
            .group_by(
                AssessmentAttempt.user_id, AttemptItem.competency, AttemptItem.competency_title
            )
            .order_by(func.min(AttemptItem.position))
        )
        results: defaultdict[uuid.UUID, list[CompetencyResult]] = defaultdict(list)
        for user_id, competency, title, correct, total in rows:
            results[user_id].append(CompetencyResult(competency, title, correct, total))
        return {user_id: tuple(items) for user_id, items in results.items()}

    async def _latest_invitations(
        self, member: CompanyMember, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Invitation]:
        # Иначе карточка и выдача показывали бы просроченное приглашение ожидающим.
        await expire_overdue_invitations(self._session)
        result = await self._session.scalars(
            select(Invitation)
            .where(
                Invitation.company_id == member.company_id,
                Invitation.candidate_user_id.in_(user_ids),
            )
            .order_by(Invitation.created_at)
        )
        # По возрастанию даты: в словаре остаётся последнее приглашение.
        return {inv.candidate_user_id: inv for inv in result}

    async def _revealed(
        self, member: CompanyMember, user_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        result = await self._session.scalars(
            select(ContactReveal.candidate_user_id).where(
                ContactReveal.company_id == member.company_id,
                ContactReveal.candidate_user_id.in_(user_ids),
                ContactReveal.revoked_at.is_(None),
            )
        )
        return set(result)


HiringServiceDep = Annotated[HiringService, Depends()]


async def expire_overdue_invitations(session: AsyncSession) -> None:
    """Просроченные ожидающие приглашения → expired. Вызывается перед чтением статусов."""
    # ponytail: истечение считается при обращении, без фоновых задач; один UPDATE по
    # частичному индексу ожидающих. При большом числе приглашений: периодическая задача.
    await session.execute(
        update(Invitation)
        .where(
            Invitation.status.in_(PENDING_STATUSES),
            Invitation.expires_at < datetime.now(UTC),
        )
        .values(status=InvitationStatus.EXPIRED)
    )
    await session.commit()
