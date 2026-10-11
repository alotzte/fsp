import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.errors import error_responses
from app.schemas.assessment import (
    AnswerInput,
    AssessmentOverviewRead,
    AttemptRead,
    StartAttemptInput,
)
from app.schemas.common import DbInt
from app.services.assessment import (
    AssessmentServiceDep,
    AssessmentUnavailableError,
    AttemptFinishedError,
    AttemptInProgressError,
    AttemptItemNotFoundError,
    AttemptNotFoundError,
    ExpressNotAllowedError,
    GradeTestNotAllowedError,
    UnknownGradeError,
    UnknownOptionError,
)
from app.services.auth.dependencies import ROLE_ERRORS, CandidateUserDep
from app.services.consents import ConsentRequiredError
from app.services.scoring import ScoringUnavailableError

router = APIRouter(prefix="/candidate/assessment", tags=["assessment"])


@router.get("", responses=error_responses(*ROLE_ERRORS, ScoringUnavailableError))
async def get_my_assessment(
    user: CandidateUserDep, assessment: AssessmentServiceDep
) -> AssessmentOverviewRead:
    """Категория, доступные тесты, что и когда можно пройти, история попыток."""
    return AssessmentOverviewRead.from_overview(await assessment.get_overview(user))


@router.post(
    "/attempts",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        *ROLE_ERRORS,
        AssessmentUnavailableError,
        UnknownGradeError,
        ExpressNotAllowedError,
        AttemptInProgressError,
        ConsentRequiredError,
        GradeTestNotAllowedError,
        ScoringUnavailableError,
    ),
)
async def start_assessment_attempt(
    payload: StartAttemptInput, user: CandidateUserDep, assessment: AssessmentServiceDep
) -> AttemptRead:
    """Начинает тест на заявленный грейд: задания собираются под кандидата и не меняются."""
    attempt = await assessment.start(
        user, payload.specialization_id, payload.grade_id, express=payload.express
    )
    return AttemptRead.from_attempt(attempt, await assessment.grades_by_level())


@router.get(
    "/attempts/{attempt_id}",
    responses=error_responses(*ROLE_ERRORS, AttemptNotFoundError, ScoringUnavailableError),
)
async def get_assessment_attempt(
    attempt_id: uuid.UUID, user: CandidateUserDep, assessment: AssessmentServiceDep
) -> AttemptRead:
    """Попытка с заданиями (без эталонов). Просроченная попытка завершается при чтении."""
    attempt = await assessment.get_attempt(user, attempt_id)
    return AttemptRead.from_attempt(attempt, await assessment.grades_by_level())


@router.put(
    "/attempts/{attempt_id}/items/{position}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *ROLE_ERRORS,
        UnknownOptionError,
        AttemptItemNotFoundError,
        AttemptNotFoundError,
        AttemptFinishedError,
    ),
)
async def save_assessment_answer(
    attempt_id: uuid.UUID,
    position: DbInt,
    payload: AnswerInput,
    user: CandidateUserDep,
    assessment: AssessmentServiceDep,
) -> None:
    """Сохраняет ответ на задание (автосохранение при каждом изменении)."""
    await assessment.save_answer(user, attempt_id, position, payload.response)


@router.post(
    "/attempts/{attempt_id}/finish",
    responses=error_responses(
        *ROLE_ERRORS, AttemptNotFoundError, AttemptFinishedError, ScoringUnavailableError
    ),
)
async def finish_assessment_attempt(
    attempt_id: uuid.UUID,
    user: CandidateUserDep,
    assessment: AssessmentServiceDep,
    seen_items: Annotated[
        DbInt | None,
        Query(description="Сколько заданий видел кандидат: если их уже больше, попытку продлили"),
    ] = None,
) -> AttemptRead:
    """Завершить тест. Если результат у самой границы грейда, попытка продлевается: ответ
    без `result`, с новыми заданиями и новым `deadline_at`."""
    attempt = await assessment.finish(user, attempt_id, seen_items=seen_items)
    return AttemptRead.from_attempt(attempt, await assessment.grades_by_level())
