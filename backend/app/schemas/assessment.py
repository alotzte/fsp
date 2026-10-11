import uuid
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import DbInt
from app.schemas.dictionaries import GradeRead, SpecializationRead
from app.services.assessment import MAX_RESPONSE_LENGTH, OptionStatus
from app.services.db.models import ItemKind

if TYPE_CHECKING:
    from app.services.assessment import AssessmentOverview, AvailableTest, GradeOption
    from app.services.db.models import AssessmentAttempt, CandidateGrade, Grade


class CategoryRead(BaseModel):
    """Категория кандидата: направление × грейд, по ней его находит работодатель."""

    specialization: SpecializationRead
    claimed_grade: GradeRead
    confirmed_grade: GradeRead | None
    confirmed_at: datetime | None
    # Когда можно сменить подтверждённый грейд.
    next_change_at: datetime | None
    # Шаг, который система предложила пройти без ожидания.
    offered_grade: GradeRead | None
    offer_expires_at: datetime | None

    @classmethod
    def from_model(
        cls, category: "CandidateGrade", next_change_at: datetime | None
    ) -> "CategoryRead":
        return cls(
            specialization=SpecializationRead.model_validate(category.specialization),
            claimed_grade=GradeRead.model_validate(category.claimed_grade),
            confirmed_grade=_grade(category.confirmed_grade),
            confirmed_at=category.confirmed_at,
            next_change_at=next_change_at,
            offered_grade=_grade(category.offered_grade),
            offer_expires_at=category.offer_expires_at,
        )


class CompetencyQuotaRead(BaseModel):
    title: str
    count: int


class AssessmentTestRead(BaseModel):
    specialization: SpecializationRead
    items_count: int
    time_limit_minutes: int
    competencies: list[CompetencyQuotaRead]

    @classmethod
    def from_test(cls, test: "AvailableTest") -> "AssessmentTestRead":
        return cls(
            specialization=SpecializationRead.model_validate(test.specialization),
            items_count=test.blueprint.items_count,
            time_limit_minutes=test.blueprint.time_limit_minutes,
            competencies=[
                CompetencyQuotaRead(title=quota.title, count=quota.count)
                for quota in test.blueprint.competencies
            ],
        )


class GradeOptionRead(BaseModel):
    specialization_id: int
    grade_id: int
    status: OptionStatus
    available_from: datetime | None

    @classmethod
    def from_option(cls, option: "GradeOption") -> "GradeOptionRead":
        return cls(
            specialization_id=option.specialization_id,
            grade_id=option.grade_id,
            status=option.status,
            available_from=option.available_from,
        )


class AttemptSummaryRead(BaseModel):
    id: uuid.UUID
    specialization: SpecializationRead
    grade: GradeRead
    started_at: datetime
    finished_at: datetime | None
    is_express: bool
    passed: bool | None
    estimated_grade: GradeRead | None
    # Вероятность, что повтор даст то же решение; None: попытки до появления оценки.
    retest_agreement: float | None

    @classmethod
    def from_attempt(
        cls, attempt: "AssessmentAttempt", grades_by_level: dict[int, "Grade"]
    ) -> "AttemptSummaryRead":
        return cls(
            id=attempt.id,
            specialization=SpecializationRead.model_validate(attempt.specialization),
            grade=GradeRead.model_validate(attempt.grade),
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            is_express=attempt.is_express,
            passed=attempt.passed,
            estimated_grade=(
                _grade(grades_by_level.get(attempt.estimated_level))
                if attempt.estimated_level is not None
                else None
            ),
            retest_agreement=attempt.retest_agreement,
        )


class AssessmentOverviewRead(BaseModel):
    category: CategoryRead | None
    tests: list[AssessmentTestRead]
    options: list[GradeOptionRead]
    active_attempt_id: uuid.UUID | None
    history: list[AttemptSummaryRead]
    # Подсказка грейда по достижениям ФСП (выбирает кандидат сам); null: подсказки нет.
    suggested_grade_id: int | None

    @classmethod
    def from_overview(cls, overview: "AssessmentOverview") -> "AssessmentOverviewRead":
        return cls(
            category=(
                CategoryRead.from_model(overview.category, overview.next_change_at)
                if overview.category
                else None
            ),
            tests=[AssessmentTestRead.from_test(test) for test in overview.tests],
            options=[GradeOptionRead.from_option(option) for option in overview.options],
            active_attempt_id=overview.active_attempt_id,
            history=[
                AttemptSummaryRead.from_attempt(attempt, overview.grades_by_level)
                for attempt in overview.history
            ],
            suggested_grade_id=overview.suggested_grade_id,
        )


class StartAttemptInput(BaseModel):
    specialization_id: DbInt
    grade_id: DbInt
    # Экспресс-тест из нескольких заданий: только для песочниц жюри.
    express: bool = False


class AnswerInput(BaseModel):
    # None: снять ответ.
    response: str | None = Field(default=None, max_length=MAX_RESPONSE_LENGTH)


class AttemptItemRead(BaseModel):
    """Задание без эталона: правильный ответ кандидату не отдаётся ни до, ни после теста."""

    position: int
    competency_title: str
    kind: ItemKind
    prompt: str
    code: str | None
    options: list[str]
    response: str | None


class CompetencyResultRead(BaseModel):
    title: str
    correct: int
    total: int


class AttemptResultRead(BaseModel):
    passed: bool
    estimated_grade: GradeRead | None
    theta: float
    theta_se: float
    # Вероятность, что повторная попытка на этот грейд даст то же решение.
    retest_agreement: float | None
    correct: int
    total: int
    competencies: list[CompetencyResultRead]


class AttemptRead(BaseModel):
    id: uuid.UUID
    specialization: SpecializationRead
    grade: GradeRead
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None
    is_express: bool
    # Сколько раз попытку продлевали заданиями у порога грейда.
    extensions: int
    items: list[AttemptItemRead]
    result: AttemptResultRead | None

    @classmethod
    def from_attempt(
        cls, attempt: "AssessmentAttempt", grades_by_level: dict[int, "Grade"]
    ) -> "AttemptRead":
        return cls(
            id=attempt.id,
            specialization=SpecializationRead.model_validate(attempt.specialization),
            grade=GradeRead.model_validate(attempt.grade),
            started_at=attempt.started_at,
            deadline_at=attempt.deadline_at,
            finished_at=attempt.finished_at,
            is_express=attempt.is_express,
            extensions=attempt.extensions,
            items=[
                AttemptItemRead(
                    position=item.position,
                    competency_title=item.competency_title,
                    kind=item.kind,
                    prompt=item.prompt,
                    code=item.code,
                    options=item.options,
                    response=item.response,
                )
                for item in attempt.items
            ],
            result=_result(attempt, grades_by_level),
        )


def _grade(grade: "Grade | None") -> GradeRead | None:
    return GradeRead.model_validate(grade) if grade is not None else None


def _result(
    attempt: "AssessmentAttempt", grades_by_level: dict[int, "Grade"]
) -> AttemptResultRead | None:
    if attempt.passed is None or attempt.theta is None or attempt.theta_se is None:
        return None
    total = Counter(item.competency_title for item in attempt.items)
    correct = Counter(item.competency_title for item in attempt.items if item.is_correct)
    return AttemptResultRead(
        passed=attempt.passed,
        estimated_grade=(
            _grade(grades_by_level.get(attempt.estimated_level))
            if attempt.estimated_level is not None
            else None
        ),
        theta=attempt.theta,
        theta_se=attempt.theta_se,
        retest_agreement=attempt.retest_agreement,
        correct=sum(correct.values()),
        total=len(attempt.items),
        competencies=[
            CompetencyResultRead(title=title, correct=correct[title], total=count)
            for title, count in total.items()
        ],
    )
