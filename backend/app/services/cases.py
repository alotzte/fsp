"""Кейс недели: раз в неделю кандидат получает короткое задание своего направления из банка.

ТЗ просит регулярные короткие задания, которые держат профиль актуальным и дают работодателю
свежий сигнал. Задания с известным ответом проверяет система (так договорились с
организаторами), поэтому кейс это экземпляр семейства из банка: эталон вычисляется, у каждого
кандидата и недели свой экземпляр. Кейс создаётся при первом обращении на неделе, без фоновых
задач. На грейд не влияет: грейд меняет только тест.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.errors import ConflictError, DomainError
from app.services.db.models import (
    CandidateGrade,
    CandidateProfile,
    ItemKind,
    Specialization,
    User,
    WeeklyCase,
)
from app.services.db.session import SessionDep
from app.services.scoring import ScoreItem, ScoringClientDep

# Решённые за этот срок кейсы видны работодателю и попадают в объяснение подбора.
ACTIVITY_WINDOW = timedelta(days=30)
# Без подтверждённого и заявленного грейда кейс уровня Junior.
DEFAULT_LEVEL = 1


class NoSpecializationError(ConflictError):
    message = (
        "Укажите направление в профиле или пройдите опрос перед тестом: кейс подбирается по нему"
    )


class CaseUnavailableError(ConflictError):
    message = "Для вашего направления кейсов пока нет"


class CaseAlreadyAnsweredError(ConflictError):
    message = "На кейс этой недели вы уже ответили: следующий появится в понедельник"


class UnknownCaseOptionError(DomainError):
    message = "Такого варианта ответа нет"


def week_start(day: date) -> date:
    """Понедельник недели: кейс меняется раз в неделю."""
    return day - timedelta(days=day.weekday())


class CaseService:
    def __init__(self, session: SessionDep, scoring: ScoringClientDep) -> None:
        self._session = session
        self._scoring = scoring

    async def current(self, user: User) -> WeeklyCase:
        """Кейс этой недели; при первом обращении на неделе подбирается из банка."""
        week = week_start(datetime.now(UTC).date())
        return await self._find(user, week) or await self.create(user, week)

    async def create(self, user: User, week: date) -> WeeklyCase:
        specialization, level = await self._target(user)
        if specialization.slug not in {
            bp.specialization for bp in await self._scoring.list_blueprints()
        }:
            raise CaseUnavailableError
        item = await self._scoring.case(
            specialization=specialization.slug,
            level=level,
            # Свой экземпляр у каждого кандидата и недели, стабильный при повторных запросах.
            seed=(user.id.int + week.toordinal()) % 2**63,
        )
        case = WeeklyCase(
            user_id=user.id,
            week=week,
            specialization_id=specialization.id,
            family_id=item.family_id,
            competency_title=item.competency_title,
            a=item.a,
            b=item.b,
            kind=item.kind,
            prompt=item.prompt,
            code=item.code,
            options=item.options,
            answer=item.answer,
        )
        self._session.add(case)
        try:
            await self._session.commit()
        except IntegrityError:
            # Параллельный запрос уже создал кейс этой недели (уникальность в БД).
            await self._session.rollback()
            existing = await self._find(user, week)
            assert existing is not None
            return existing
        return case

    async def answer(self, user: User, response: str) -> WeeklyCase:
        """Один ответ на кейс недели; проверяет scoring, эталон кандидату не уходит."""
        await self.current(user)
        case = await self._find(user, week_start(datetime.now(UTC).date()), for_update=True)
        assert case is not None
        if case.answered_at is not None:
            raise CaseAlreadyAnsweredError
        if case.kind == ItemKind.CHOICE and response not in case.options:
            raise UnknownCaseOptionError
        result = await self._scoring.score(
            level=0,
            items=[ScoreItem(a=case.a, b=case.b, answer=case.answer, response=response)],
            extensions=0,
            express=False,
        )
        case.response = response
        case.is_correct = result.correct[0]
        case.answered_at = datetime.now(UTC)
        await self._session.commit()
        return case

    async def solved_recently(self, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Верно решённых кейсов за ACTIVITY_WINDOW: одним запросом на весь пул."""
        if not user_ids:
            return {}
        rows = await self._session.execute(
            select(WeeklyCase.user_id, func.count())
            .where(
                WeeklyCase.user_id.in_(user_ids),
                WeeklyCase.is_correct.is_(True),
                WeeklyCase.answered_at > datetime.now(UTC) - ACTIVITY_WINDOW,
            )
            .group_by(WeeklyCase.user_id)
        )
        return dict(rows.tuples().all())

    async def _find(
        self, user: User, week: date, *, for_update: bool = False
    ) -> WeeklyCase | None:
        query = select(WeeklyCase).where(WeeklyCase.user_id == user.id, WeeklyCase.week == week)
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def _target(self, user: User) -> tuple[Specialization, int]:
        """Направление и уровень кейса: из категории (подтверждённый, иначе заявленный грейд),
        иначе направление из профиля и Junior."""
        category = await self._session.scalar(
            select(CandidateGrade)
            .options(
                joinedload(CandidateGrade.specialization),
                joinedload(CandidateGrade.confirmed_grade),
                joinedload(CandidateGrade.claimed_grade),
            )
            .where(CandidateGrade.user_id == user.id)
        )
        if category is not None:
            grade = category.confirmed_grade or category.claimed_grade
            return category.specialization, grade.level
        specialization = await self._session.scalar(
            select(Specialization)
            .join(CandidateProfile, CandidateProfile.specialization_id == Specialization.id)
            .where(CandidateProfile.user_id == user.id)
        )
        if specialization is None:
            raise NoSpecializationError
        return specialization, DEFAULT_LEVEL


CaseServiceDep = Annotated[CaseService, Depends()]
