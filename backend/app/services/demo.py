"""Песочницы для жюри: вход без регистрации, чтобы за минуты пройти сквозной сценарий ТЗ.

Каждый вход создаёт отдельного пользователя, поэтому члены жюри не мешают друг другу.
- Демо-кандидат: заполненный профиль с согласиями, показ работодателям включён, теста ещё нет:
  его жюри проходит само (полный или экспресс). Если демо-сид создал компанию с историей
  приглашений, от неё сразу приходит приглашение: видны «почему вам», кейс и репутация.
- Демо-работодатель: компания и готовая потребность, сразу видна подборка.
Работает только при DEMO_MODE=true. Песочницы старше суток удаляются при следующем входе.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, func, select

from app.config import SettingsDep
from app.errors import DomainError, NotFoundError
from app.schemas.invitations import InvitationInput
from app.services.auth.service import AuthServiceDep
from app.services.consents import CONSENT_DOCUMENTS
from app.services.db.models import (
    JURY_DEMO_PREFIX,
    SEED_DEMO_PREFIX,
    CandidateGrade,
    CandidateProfile,
    CandidateSkill,
    Company,
    CompanyMember,
    CompanyRole,
    Consent,
    ConsentKind,
    Grade,
    HiringNeed,
    HiringNeedSkill,
    Skill,
    SkillKind,
    Specialization,
    User,
    UserRole,
)
from app.services.db.session import SessionDep
from app.services.invitations import InvitationServiceDep

logger = logging.getLogger(__name__)

SANDBOX_TTL = timedelta(days=1)
# Владелец демо-компании с историей приглашений (создаёт app.demo_seed).
DEMO_EMPLOYER_SUB = "demo:employer"
DEMO_CASE = "Как бы вы повторяли платёж, если банк не ответил за 30 секунд? Опишите подход."

DEMO_SPECIALIZATION = "backend"
DEMO_GRADE = "middle"
CANDIDATE_SKILLS = ["python", "postgresql", "fastapi", "docker", "git", "redis"]
NEED_SKILLS = {"python": True, "postgresql": True, "kafka": False}
# Сколько откликов демо-кандидатов получает вакансия работодателя-песочницы.
DEMO_APPLICATIONS = 2


class DemoModeDisabledError(NotFoundError):
    message = "Демо-режим выключен"


class DemoService:
    def __init__(
        self,
        session: SessionDep,
        auth: AuthServiceDep,
        settings: SettingsDep,
        invitations: InvitationServiceDep,
    ) -> None:
        self._session = session
        self._auth = auth
        self._settings = settings
        self._invitations = invitations

    @property
    def enabled(self) -> bool:
        return self._settings.demo_mode

    @property
    def session_lifetime(self) -> timedelta:
        return self._auth.session_lifetime

    async def login(self, role: UserRole) -> str:
        """Создаёт песочницу и открывает в ней сессию. Возвращает токен для cookie."""
        if not self.enabled:
            raise DemoModeDisabledError
        await self._remove_expired()
        suffix = uuid.uuid4().hex[:8]
        user = User(
            keycloak_sub=f"{JURY_DEMO_PREFIX}{suffix}",
            email=f"jury-{suffix}@demo.fsp.invalid",
            first_name="Жюри",
            last_name="Демо",
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        if role == UserRole.CANDIDATE:
            await self._fill_candidate(user)
            await self._invite_from_demo_company(user)
        else:
            await self._fill_employer(user, suffix)
        return await self._auth.open_session(user, id_token="")

    async def _fill_candidate(self, user: User) -> None:
        for kind in (ConsentKind.DATA_PROCESSING, ConsentKind.PROFILE_PUBLICATION):
            self._session.add(
                Consent(
                    user_id=user.id, kind=kind, document_version=CONSENT_DOCUMENTS[kind].version
                )
            )
        skills = await self._skills(CANDIDATE_SKILLS)
        self._session.add(
            CandidateProfile(
                user_id=user.id,
                last_name="Демо",
                first_name="Кандидат",
                middle_name="",
                phone="+7 900 000-00-00",
                telegram="",
                specialization_id=await self._specialization_id(),
                work_formats=["remote", "hybrid"],
                city="Москва",
                salary_expectation_rub=200_000,
                about="Демо-профиль для проверки платформы. Бэкенд на Python, PostgreSQL.",
                skills=[
                    CandidateSkill(kind=SkillKind.TECHNOLOGY, skill_id=skill.id)
                    for skill in skills.values()
                ],
            )
        )

    async def _fill_employer(self, user: User, suffix: str) -> None:
        company = Company(
            name=f"Демо-работодатель {suffix[:4].upper()}",
            description="Компания-песочница для проверки платформы.",
            contact_email=user.email,
            # Уровень доверия как у подтвердившей домен: квота приглашений не мешает проверке.
            trust_level=1,
        )
        self._session.add(company)
        await self._session.flush()
        self._session.add(
            CompanyMember(user_id=user.id, company_id=company.id, role=CompanyRole.OWNER)
        )
        grade_id = await self._session.scalar(select(Grade.id).where(Grade.slug == DEMO_GRADE))
        skills = await self._skills(list(NEED_SKILLS))
        need = HiringNeed(
            company_id=company.id,
            created_by_id=user.id,
            title="Python-разработчик в команду платежей",
            description=(
                "Платёжный шлюз под высокой нагрузкой: PostgreSQL, очереди, мониторинг. "
                "Ищем инженера, который доводит задачи до продакшена."
            ),
            specialization_id=await self._specialization_id(),
            grade_id=grade_id,
            work_formats=["remote", "hybrid"],
            city="Москва",
            salary_from_rub=200_000,
            salary_to_rub=320_000,
            skills=[
                HiringNeedSkill(skill_id=skill.id, must_have=NEED_SKILLS[slug])
                for slug, skill in skills.items()
            ],
            # Опубликована как вакансия: на неё уже откликнулись демо-кандидаты, и другая
            # песочница-кандидат тоже может откликнуться.
            published_at=datetime.now(UTC),
        )
        self._session.add(need)
        await self._session.flush()
        await self._applications_from_demo_candidates(need)

    async def _applications_from_demo_candidates(self, need: HiringNeed) -> None:
        """Отклики засеянных кандидатов с подтверждённым грейдом рядом с грейдом вакансии:
        тем же путём, что у настоящих кандидатов (правила и раскрытие контактов)."""
        levels = select(Grade.id).where(Grade.level.between(1, 3))
        applicants = await self._session.scalars(
            select(User)
            .join(CandidateGrade, CandidateGrade.user_id == User.id)
            .where(
                User.keycloak_sub.startswith(SEED_DEMO_PREFIX),
                CandidateGrade.specialization_id == need.specialization_id,
                CandidateGrade.confirmed_grade_id.in_(levels),
            )
            .order_by(func.random())
            .limit(DEMO_APPLICATIONS)
        )
        for applicant in applicants.all():
            try:
                await self._invitations.apply(applicant, need.id)
            except DomainError:
                # Демо-сид не запускали или scoring недоступен: песочница работает и без откликов.
                logger.warning("Демо-отклик не создан", exc_info=True)

    async def _invite_from_demo_company(self, user: User) -> None:
        """Приглашение от демо-компании с историей: тем же путём, что у настоящих компаний."""
        member = await self._session.scalar(
            select(CompanyMember)
            .join(User, User.id == CompanyMember.user_id)
            .where(User.keycloak_sub == DEMO_EMPLOYER_SUB)
        )
        if member is None:
            return  # демо-сид не запускали
        need = await self._session.scalar(
            select(HiringNeed).where(HiringNeed.company_id == member.company_id).limit(1)
        )
        await self._session.flush()
        number = await self._session.scalar(
            select(CandidateProfile.candidate_number).where(CandidateProfile.user_id == user.id)
        )
        if need is None or number is None:
            return
        try:
            await self._invitations.create(
                member,
                InvitationInput(
                    candidate_number=number,
                    need_id=need.id,
                    title=need.title,
                    description=need.description,
                    salary_from_rub=need.salary_from_rub,
                    salary_to_rub=need.salary_to_rub,
                    contact="hr@primer.demo.fsp.invalid",
                    case_task=DEMO_CASE,
                ),
            )
        except DomainError:
            # Например, scoring недоступен: песочница работает и без этого приглашения.
            # Квота ожидающих приглашений на общую демо-компанию не действует (is_shared_demo).
            logger.warning("Демо-приглашение не создано", exc_info=True)

    async def _specialization_id(self) -> int | None:
        return await self._session.scalar(
            select(Specialization.id).where(Specialization.slug == DEMO_SPECIALIZATION)
        )

    async def _skills(self, slugs: list[str]) -> dict[str, Skill]:
        result = await self._session.scalars(select(Skill).where(Skill.slug.in_(slugs)))
        return {skill.slug: skill for skill in result}

    async def _remove_expired(self) -> None:
        expired = select(User.id).where(
            User.keycloak_sub.startswith(JURY_DEMO_PREFIX),
            User.created_at < datetime.now(UTC) - SANDBOX_TTL,
        )
        # Компании песочниц не привязаны к пользователю каскадом: удаляем их явно.
        await self._session.execute(
            delete(Company).where(
                Company.id.in_(
                    select(CompanyMember.company_id).where(CompanyMember.user_id.in_(expired))
                )
            )
        )
        await self._session.execute(delete(User).where(User.id.in_(expired)))


DemoServiceDep = Annotated[DemoService, Depends()]
