"""Тестирование кандидата: попытки, присвоение категории, ограничения частоты.

Психометрика (сборка теста, оценка уровня, решение о грейде) живёт в сервисе scoring,
здесь данные и правила во времени: кто, когда и какой тест может пройти.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.services.consents import ConsentRequiredError, ConsentServiceDep
from app.services.db.models import (
    AssessmentAttempt,
    AttemptItem,
    CandidateGrade,
    ConsentKind,
    FspAward,
    FspResult,
    Grade,
    ItemKind,
    Specialization,
    User,
)
from app.services.db.session import SessionDep
from app.services.fsp import user_registry_results
from app.services.scoring import AssembledItem, Blueprint, ScoreItem, ScoringClientDep

# Смена подтверждённого грейда (вверх, вниз или в другое направление): не чаще раза в 90 дней.
GRADE_CHANGE_COOLDOWN = timedelta(days=90)
# Повтор неудачной попытки на тот же грейд: через 30 дней.
SAME_GRADE_RETRY = timedelta(days=30)
# Сколько действует предложение системы пройти тест на соседний грейд без ожидания.
OFFER_TTL = timedelta(days=7)
# Запас на сетевую задержку при отправке ответа в последние секунды.
DEADLINE_GRACE = timedelta(seconds=30)
# Семейства заданий из стольких последних попыток не повторяются (по возможности).
RECENT_ATTEMPTS = 2
HISTORY_LIMIT = 20
MAX_RESPONSE_LENGTH = 500
# Экспресс-тест для жюри: заданий и минут (по минуте на задание).
EXPRESS_ITEMS = 6
# Чужих эталонов на семейство для детектора утечки; совпадает с лимитом scoring.
MAX_FOREIGN_ANSWERS = 200


class AssessmentUnavailableError(DomainError):
    message = "Для этого направления тест пока не готов"


class UnknownGradeError(DomainError):
    message = "Грейд не найден в справочнике"


class GradeTestNotAllowedError(ConflictError):
    message = "Тест на этот грейд сейчас недоступен: проверьте, с какой даты его можно пройти"


class AttemptInProgressError(ConflictError):
    message = "Сначала завершите начатый тест"


class AttemptNotFoundError(NotFoundError):
    message = "Попытка не найдена"


class AttemptItemNotFoundError(NotFoundError):
    message = "Задание не найдено"


class AttemptFinishedError(ConflictError):
    message = "Тест уже завершён"


class UnknownOptionError(DomainError):
    message = "Такого варианта ответа нет"


class ExpressNotAllowedError(PermissionDeniedError):
    message = "Экспресс-тест доступен только в демо-режиме для жюри"


class OptionStatus(StrEnum):
    AVAILABLE = "available"
    # Система предложила этот шаг по итогам попытки: можно пройти сразу.
    OFFERED = "offered"
    # Уже подтверждён в этом направлении.
    CONFIRMED = "confirmed"
    COOLDOWN = "cooldown"


def evaluate_option(
    *,
    now: datetime,
    specialization_id: int,
    grade_id: int,
    category: CandidateGrade | None,
    last_failure_at: datetime | None,
) -> tuple[OptionStatus, datetime | None]:
    """Можно ли сейчас начать тест на грейд и, если нет, с какого момента.

    Правила (ТЗ + разъяснения организаторов):
    - грейд не понижается принудительно, а смена подтверждённого: не чаще GRADE_CHANGE_COOLDOWN;
    - после неудачи на грейд G тест на G−1 предлагается сразу, без ожидания;
    - после уверенного прохождения G сразу предлагается тест на G+1;
    - повтор неудачной попытки на тот же грейд: через SAME_GRADE_RETRY.
    """
    if (
        category is not None
        and category.offered_grade_id == grade_id
        and category.specialization_id == specialization_id
        and category.offer_expires_at is not None
        and category.offer_expires_at > now
        # Предложение снимает паузу смены грейда, но не паузу после провала на нём же:
        # иначе цепочка «провал → предложение G−1 → провал → ...» гоняла бы один грейд подряд.
        and (last_failure_at is None or last_failure_at + SAME_GRADE_RETRY <= now)
    ):
        return OptionStatus.OFFERED, None

    waits = []
    if last_failure_at is not None:
        waits.append(last_failure_at + SAME_GRADE_RETRY)
    if category is not None and category.confirmed_at is not None:
        if (
            category.confirmed_grade_id == grade_id
            and category.specialization_id == specialization_id
        ):
            return OptionStatus.CONFIRMED, None
        waits.append(category.confirmed_at + GRADE_CHANGE_COOLDOWN)
    available_from = max(waits, default=None)
    if available_from is not None and available_from > now:
        return OptionStatus.COOLDOWN, available_from
    return OptionStatus.AVAILABLE, None


# Подсказка грейда по ФСП учитывает результаты за этот срок: старая победа о текущем уровне
# говорит мало.
FSP_HINT_WINDOW = timedelta(days=730)
JUNIOR_LEVEL, MIDDLE_LEVEL, SENIOR_LEVEL = 1, 2, 3


def updates_category_theta(
    *, passed: bool, same_specialization: bool, has_confirmed: bool
) -> bool:
    """Заменяет ли оценка уровня из попытки θ категории (по ней ранжируется сила кандидата).

    Пройденная: да, θ сопоставима между попытками, храним свежую. Проваленная: только если
    грейд направления ещё не подтверждён: иначе попытка на грейд выше, которую система сама
    предлагает, опускала бы подтверждённого кандидата в выдаче (провал не должен понижать).
    """
    return passed or (same_specialization and not has_confirmed)


def suggest_grade(results: Iterable[FspResult], today: date) -> int | None:
    """Уровень грейда, который подсказываем по достижениям ФСП. Выбирает кандидат сам.

    Организаторы: подсказка по ФСП допустима, выбор за кандидатом; на подтверждение грейда
    она не влияет. Правило: эвристика до калибровки на реальных данных:
    победа и ещё одна победа или призовое место за 2 года → Senior; одна победа или призовое
    место → Middle; только финалы → Junior; иначе (в том числе нет истории ФСП) подсказки нет.
    """
    recent = [r.award for r in results if today - r.event.starts_on <= FSP_HINT_WINDOW]
    wins = recent.count(FspAward.WINNER)
    podiums = wins + recent.count(FspAward.PRIZE)
    if wins and podiums >= 2:  # noqa: PLR2004  # «победа и ещё одно призовое»
        return SENIOR_LEVEL
    if podiums:
        return MIDDLE_LEVEL
    if FspAward.FINALIST in recent:
        return JUNIOR_LEVEL
    return None


@dataclass(frozen=True)
class AvailableTest:
    specialization: Specialization
    blueprint: Blueprint


@dataclass(frozen=True)
class GradeOption:
    specialization_id: int
    grade_id: int
    status: OptionStatus
    available_from: datetime | None


@dataclass(frozen=True)
class AssessmentOverview:
    category: CandidateGrade | None
    tests: list[AvailableTest]
    options: list[GradeOption]
    active_attempt_id: uuid.UUID | None
    history: list[AssessmentAttempt]
    grades_by_level: dict[int, Grade]
    # Подсказка по достижениям ФСП; None: подсказки нет (и ФСП не упоминаем).
    suggested_grade_id: int | None

    @property
    def next_change_at(self) -> datetime | None:
        if self.category is None or self.category.confirmed_at is None:
            return None
        return self.category.confirmed_at + GRADE_CHANGE_COOLDOWN


class AssessmentService:
    def __init__(
        self, session: SessionDep, consents: ConsentServiceDep, scoring: ScoringClientDep
    ) -> None:
        self._session = session
        self._consents = consents
        self._scoring = scoring

    async def get_overview(self, user: User) -> AssessmentOverview:
        active = await self._active_attempt(user)
        if active is not None and await self._finish_if_expired(user, active):
            active = None
        category = await self._load_category(user)
        grades = await self._grades()
        tests = await self._available_tests()
        failures = await self._last_failures(user)
        now = datetime.now(UTC)
        options = []
        for test in tests:
            for grade in grades:
                status, available_from = evaluate_option(
                    now=now,
                    specialization_id=test.specialization.id,
                    grade_id=grade.id,
                    category=category,
                    last_failure_at=failures.get((test.specialization.id, grade.id)),
                )
                options.append(
                    GradeOption(test.specialization.id, grade.id, status, available_from)
                )
        history = await self._session.scalars(
            select(AssessmentAttempt)
            .options(
                joinedload(AssessmentAttempt.specialization),
                joinedload(AssessmentAttempt.grade),
            )
            .where(
                AssessmentAttempt.user_id == user.id, AssessmentAttempt.finished_at.is_not(None)
            )
            .order_by(AssessmentAttempt.finished_at.desc())
            .limit(HISTORY_LIMIT)
        )
        return AssessmentOverview(
            category=category,
            tests=tests,
            options=options,
            active_attempt_id=active.id if active else None,
            history=list(history),
            grades_by_level={grade.level: grade for grade in grades},
            suggested_grade_id=await self._suggested_grade_id(user, grades),
        )

    async def _suggested_grade_id(self, user: User, grades: Sequence[Grade]) -> int | None:
        results = await user_registry_results(self._session, user.id)
        level = suggest_grade(results, datetime.now(UTC).date())
        return next((grade.id for grade in grades if grade.level == level), None)

    async def start(
        self, user: User, specialization_id: int, grade_id: int, *, express: bool = False
    ) -> AssessmentAttempt:
        if not await self._consents.is_active(user, ConsentKind.DATA_PROCESSING):
            raise ConsentRequiredError
        # Короткий тест точнее подтверждать не может, поэтому настоящим кандидатам он закрыт.
        if express and not user.is_jury_demo:
            raise ExpressNotAllowedError
        active = await self._active_attempt(user)
        if active is not None and not await self._finish_if_expired(user, active):
            raise AttemptInProgressError
        grade = await self._session.get(Grade, grade_id)
        if grade is None:
            raise UnknownGradeError
        test = next(
            (t for t in await self._available_tests() if t.specialization.id == specialization_id),
            None,
        )
        if test is None:
            raise AssessmentUnavailableError

        now = datetime.now(UTC)
        category = await self._load_category(user)
        failures = await self._last_failures(user)
        status, _ = evaluate_option(
            now=now,
            specialization_id=specialization_id,
            grade_id=grade_id,
            category=category,
            last_failure_at=failures.get((specialization_id, grade_id)),
        )
        if status not in (OptionStatus.AVAILABLE, OptionStatus.OFFERED):
            raise GradeTestNotAllowedError

        # До _prepare_category: её новая строка иначе ушла бы в БД автофлашем этого запроса, вне
        # try ниже, и параллельный старт падал бы 500 на дубле ключа вместо 409.
        recent_families = await self._recent_families(user, specialization_id)
        category = self._prepare_category(user, category, specialization_id, grade_id)
        if status == OptionStatus.OFFERED:
            _clear_offer(category)

        attempt = AssessmentAttempt(
            id=uuid.uuid4(),
            user_id=user.id,
            specialization_id=specialization_id,
            grade_id=grade_id,
            started_at=now,
            deadline_at=now
            + timedelta(minutes=EXPRESS_ITEMS if express else test.blueprint.time_limit_minutes),
            is_express=express,
        )
        items = await self._scoring.assemble(
            specialization=test.specialization.slug,
            level=grade.level,
            seed=_seed(attempt),
            recent_families=recent_families,
            length=EXPRESS_ITEMS if express else None,
        )
        attempt.items = _attempt_items(items, first_position=1)
        self._session.add(attempt)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Уникальный индекс «одна незавершённая попытка»: параллельный старт из второй вкладки.
            raise AttemptInProgressError from exc
        return await self.get_attempt(user, attempt.id)

    def _prepare_category(
        self,
        user: User,
        category: CandidateGrade | None,
        specialization_id: int,
        grade_id: int,
    ) -> CandidateGrade:
        """Категория при старте попытки: создаётся при первом тесте, а пока грейд не
        подтверждён: следует за последним выбором кандидата."""
        if category is None:
            category = CandidateGrade(
                user_id=user.id, specialization_id=specialization_id, claimed_grade_id=grade_id
            )
            self._session.add(category)
        elif category.confirmed_grade_id is None:
            if category.specialization_id != specialization_id:
                _clear_offer(category)
            category.specialization_id = specialization_id
            category.claimed_grade_id = grade_id
        return category

    async def get_attempt(self, user: User, attempt_id: uuid.UUID) -> AssessmentAttempt:
        attempt = await self._load_attempt(user, attempt_id)
        if await self._finish_if_expired(user, attempt):
            attempt = await self._load_attempt(user, attempt_id)
        return attempt

    async def save_answer(
        self, user: User, attempt_id: uuid.UUID, position: int, response: str | None
    ) -> None:
        attempt = await self._load_attempt(user, attempt_id, for_update=True)
        if attempt.finished_at is not None or _is_expired(attempt):
            raise AttemptFinishedError
        item = next((i for i in attempt.items if i.position == position), None)
        if item is None:
            raise AttemptItemNotFoundError
        if response is not None and item.kind == ItemKind.CHOICE and response not in item.options:
            raise UnknownOptionError
        item.response = response
        await self._session.commit()

    async def finish(
        self, user: User, attempt_id: uuid.UUID, *, seen_items: int | None = None
    ) -> AssessmentAttempt:
        """Завершает попытку. Если решение у порога неуверенное, попытка вместо этого
        продлевается: возвращается незавершённой, с новыми заданиями и временем на них.

        seen_items: сколько заданий видел кандидат. Если их уже больше, попытку только что
        продлил параллельный запрос (вторая вкладка, повтор при сбое сети): оценивать её с
        неотвеченными новыми заданиями нельзя: возвращаем как есть."""
        attempt = await self._load_attempt(user, attempt_id, for_update=True)
        if attempt.finished_at is not None:
            raise AttemptFinishedError
        if seen_items is not None and seen_items < len(attempt.items) and not _is_expired(attempt):
            return attempt
        # Время вышло: решаем по тому, что есть, продлевать некому.
        await self._score(user, attempt, may_extend=not _is_expired(attempt))
        return await self._load_attempt(user, attempt_id)

    async def _score(
        self, user: User, attempt: AssessmentAttempt, *, may_extend: bool = False
    ) -> None:
        """Оценивает попытку и обновляет категорию кандидата (или продлевает попытку, если
        решение у порога неуверенное и `may_extend`). Коммитит транзакцию."""
        foreign = await self._foreign_answers(user, attempt)
        result = await self._scoring.score(
            level=attempt.grade.level,
            items=[
                ScoreItem(
                    a=item.a,
                    b=item.b,
                    answer=item.answer,
                    response=item.response,
                    foreign_answers=foreign.get(item.family_id, []),
                )
                for item in attempt.items
            ],
            extensions=attempt.extensions,
            express=attempt.is_express,
        )
        # Продлевать ли, решает scoring (правило остановки теста: часть психометрии).
        if (
            may_extend
            and result.extend_items
            and await self._extend(user, attempt, result.extend_items)
        ):
            return
        now = datetime.now(UTC)
        for item, correct in zip(attempt.items, result.correct, strict=True):
            item.is_correct = correct
        attempt.finished_at = now
        attempt.theta = result.theta
        attempt.theta_se = result.se
        attempt.passed = result.passed
        attempt.estimated_level = result.estimated_level
        attempt.retest_agreement = result.retest_agreement
        attempt.foreign_answers = sum(result.foreign_matches)

        category = await self._load_category(user, for_update=True)
        # Категория создаётся при старте попытки, поэтому здесь она уже есть.
        assert category is not None
        grades = await self.grades_by_level()
        level = attempt.grade.level
        _clear_offer(category)
        if updates_category_theta(
            passed=result.passed,
            same_specialization=category.specialization_id == attempt.specialization_id,
            has_confirmed=category.confirmed_grade_id is not None,
        ):
            category.theta = result.theta
            category.theta_se = result.se
        if result.passed:
            if (
                category.confirmed_grade_id != attempt.grade_id
                or category.specialization_id != attempt.specialization_id
            ):
                category.confirmed_at = now
            category.specialization_id = attempt.specialization_id
            category.claimed_grade_id = attempt.grade_id
            category.confirmed_grade_id = attempt.grade_id
            if result.strong and level + 1 in grades:
                _set_offer(category, grades[level + 1], now)
        elif category.specialization_id == attempt.specialization_id and level - 1 in grades:
            confirmed_level = (
                category.confirmed_grade.level if category.confirmed_grade is not None else -1
            )
            # Грейд ниже предлагаем, только если он выше уже подтверждённого.
            if confirmed_level < level - 1:
                _set_offer(category, grades[level - 1], now)
        await self._session.commit()

    async def _foreign_answers(
        self, user: User, attempt: AssessmentAttempt
    ) -> dict[str, list[str]]:
        """Эталоны чужих экземпляров тех же семейств (текстовые задания) из попыток других
        кандидатов: детектор утечки сверяет с ними неверные ответы."""
        families = {item.family_id for item in attempt.items if item.kind == ItemKind.TEXT}
        if not families:
            return {}
        rows = await self._session.execute(
            select(AttemptItem.family_id, AttemptItem.answer)
            .distinct()
            .join(AssessmentAttempt, AssessmentAttempt.id == AttemptItem.attempt_id)
            .where(
                AttemptItem.family_id.in_(families),
                AttemptItem.kind == ItemKind.TEXT,
                AssessmentAttempt.user_id != user.id,
            )
        )
        # ponytail: все различные эталоны читаются целиком и режутся здесь; при тысячах
        # попыток: оконная функция с лимитом на семейство в самом запросе.
        foreign: defaultdict[str, list[str]] = defaultdict(list)
        for family_id, answer in rows:
            if len(foreign[family_id]) < MAX_FOREIGN_ANSWERS:
                foreign[family_id].append(answer)
        return foreign

    async def _extend(self, user: User, attempt: AssessmentAttempt, count: int) -> bool:
        """Добавляет к попытке задания у порога грейда и время на них. Коммитит транзакцию.
        False: заданий не нашлось (банк исчерпан), решать по тому, что есть."""
        items = await self._scoring.extend(
            specialization=attempt.specialization.slug,
            level=attempt.grade.level,
            seed=_seed(attempt),
            count=count,
            attempt_families=[item.family_id for item in attempt.items],
            recent_families=await self._recent_families(user, attempt.specialization_id),
        )
        if not items:
            return False
        if attempt.is_express:
            per_item = timedelta(minutes=1)
        else:
            # В темпе основного теста: столько же минут на задание.
            test = next(
                t
                for t in await self._available_tests()
                if t.specialization.id == attempt.specialization_id
            )
            per_item = timedelta(minutes=test.blueprint.time_limit_minutes) / (
                test.blueprint.items_count
            )
        attempt.items.extend(_attempt_items(items, first_position=len(attempt.items) + 1))
        attempt.extensions += 1
        # Время только добавляется: кто завершил досрочно, сохраняет и остаток прежнего.
        attempt.deadline_at = max(attempt.deadline_at, datetime.now(UTC)) + per_item * len(items)
        await self._session.commit()
        return True

    async def _finish_if_expired(self, user: User, attempt: AssessmentAttempt) -> bool:
        if attempt.finished_at is not None or not _is_expired(attempt):
            return False
        await self._score(user, await self._load_attempt(user, attempt.id, for_update=True))
        return True

    async def grades_by_level(self) -> dict[int, Grade]:
        return {grade.level: grade for grade in await self._grades()}

    async def _available_tests(self) -> list[AvailableTest]:
        blueprints = {bp.specialization: bp for bp in await self._scoring.list_blueprints()}
        specializations = await self._session.scalars(
            select(Specialization)
            .where(Specialization.slug.in_(list(blueprints)))
            .order_by(Specialization.title)
        )
        return [AvailableTest(spec, blueprints[spec.slug]) for spec in specializations]

    async def _grades(self) -> Sequence[Grade]:
        result = await self._session.scalars(select(Grade).order_by(Grade.level))
        return result.all()

    async def _load_category(
        self, user: User, *, for_update: bool = False
    ) -> CandidateGrade | None:
        query = (
            select(CandidateGrade)
            .options(
                joinedload(CandidateGrade.specialization),
                joinedload(CandidateGrade.claimed_grade),
                joinedload(CandidateGrade.confirmed_grade),
                joinedload(CandidateGrade.offered_grade),
            )
            .where(CandidateGrade.user_id == user.id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update(of=CandidateGrade)
        return await self._session.scalar(query)

    async def _load_attempt(
        self, user: User, attempt_id: uuid.UUID, *, for_update: bool = False
    ) -> AssessmentAttempt:
        query = (
            select(AssessmentAttempt)
            .options(
                joinedload(AssessmentAttempt.specialization),
                joinedload(AssessmentAttempt.grade),
                selectinload(AssessmentAttempt.items),
            )
            # Чужая попытка неотличима от несуществующей.
            .where(AssessmentAttempt.id == attempt_id, AssessmentAttempt.user_id == user.id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update(of=AssessmentAttempt)
        attempt = await self._session.scalar(query)
        if attempt is None:
            raise AttemptNotFoundError
        return attempt

    async def _active_attempt(self, user: User) -> AssessmentAttempt | None:
        return await self._session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.user_id == user.id, AssessmentAttempt.finished_at.is_(None)
            )
        )

    async def _last_failures(self, user: User) -> dict[tuple[int, int], datetime]:
        """Время последней неудачной попытки по каждой паре (направление, грейд)."""
        rows = await self._session.execute(
            select(
                AssessmentAttempt.specialization_id,
                AssessmentAttempt.grade_id,
                func.max(AssessmentAttempt.finished_at),
            )
            .where(AssessmentAttempt.user_id == user.id, AssessmentAttempt.passed.is_(False))
            .group_by(AssessmentAttempt.specialization_id, AssessmentAttempt.grade_id)
        )
        return {(spec, grade): last for spec, grade, last in rows if last is not None}

    async def _recent_families(self, user: User, specialization_id: int) -> list[str]:
        recent = (
            select(AssessmentAttempt.id)
            .where(
                AssessmentAttempt.user_id == user.id,
                AssessmentAttempt.specialization_id == specialization_id,
                AssessmentAttempt.finished_at.is_not(None),
            )
            .order_by(AssessmentAttempt.finished_at.desc())
            .limit(RECENT_ATTEMPTS)
        )
        result = await self._session.scalars(
            select(AttemptItem.family_id).where(AttemptItem.attempt_id.in_(recent)).distinct()
        )
        return list(result)


def _seed(attempt: AssessmentAttempt) -> int:
    """Seed сборки: по нему scoring детерминированно строит экземпляры заданий попытки."""
    return attempt.id.int % 2**63


def _attempt_items(items: Sequence[AssembledItem], *, first_position: int) -> list[AttemptItem]:
    return [
        AttemptItem(
            position=position,
            family_id=item.family_id,
            competency=item.competency,
            competency_title=item.competency_title,
            a=item.a,
            b=item.b,
            kind=item.kind,
            prompt=item.prompt,
            code=item.code,
            options=item.options,
            answer=item.answer,
        )
        for position, item in enumerate(items, first_position)
    ]


def _is_expired(attempt: AssessmentAttempt) -> bool:
    return datetime.now(UTC) > attempt.deadline_at + DEADLINE_GRACE


def _set_offer(category: CandidateGrade, grade: Grade, now: datetime) -> None:
    category.offered_grade_id = grade.id
    category.offer_expires_at = now + OFFER_TTL


def _clear_offer(category: CandidateGrade) -> None:
    category.offered_grade_id = None
    category.offer_expires_at = None


AssessmentServiceDep = Annotated[AssessmentService, Depends()]
