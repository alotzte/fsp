from fastapi import APIRouter

from app.errors import error_responses
from app.schemas.cases import CaseAnswerInput, WeeklyCaseRead
from app.services.auth.dependencies import ROLE_ERRORS, CandidateUserDep
from app.services.cases import (
    CaseAlreadyAnsweredError,
    CaseServiceDep,
    CaseUnavailableError,
    NoSpecializationError,
    UnknownCaseOptionError,
)
from app.services.scoring import ScoringUnavailableError

router = APIRouter(prefix="/candidate/cases", tags=["cases"])


@router.get(
    "/current",
    responses=error_responses(
        *ROLE_ERRORS, CaseUnavailableError, NoSpecializationError, ScoringUnavailableError
    ),
)
async def get_weekly_case(user: CandidateUserDep, cases: CaseServiceDep) -> WeeklyCaseRead:
    """Кейс этой недели: при первом обращении на неделе подбирается из банка по направлению."""
    case = await cases.current(user)
    solved = await cases.solved_recently([user.id])
    return WeeklyCaseRead.from_case(case, solved.get(user.id, 0))


@router.post(
    "/current/answer",
    responses=error_responses(
        *ROLE_ERRORS,
        UnknownCaseOptionError,
        CaseAlreadyAnsweredError,
        CaseUnavailableError,
        NoSpecializationError,
        ScoringUnavailableError,
    ),
)
async def answer_weekly_case(
    payload: CaseAnswerInput, user: CandidateUserDep, cases: CaseServiceDep
) -> WeeklyCaseRead:
    """Ответить на кейс недели: один раз. Результат «верно / неверно» на грейд не влияет."""
    case = await cases.answer(user, payload.response.strip())
    solved = await cases.solved_recently([user.id])
    return WeeklyCaseRead.from_case(case, solved.get(user.id, 0))
