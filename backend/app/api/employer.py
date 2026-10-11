import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.profile_pdf import pdf_response, render_candidate_pdf
from app.errors import error_responses
from app.schemas.common import DbInt
from app.schemas.hiring import (
    CandidateSearchRead,
    CategoryCountRead,
    EmployerCandidateRead,
    HiringNeedInput,
    HiringNeedRead,
)
from app.schemas.invitations import (
    ApplicationAnswerInput,
    EmployerInvitationRead,
    InvitationInput,
)
from app.services.assessment import UnknownGradeError
from app.services.companies import COMPANY_MEMBER_ERRORS, CompanyMemberDep
from app.services.db.models import WorkFormat
from app.services.dictionaries import UnknownSkillError, UnknownSpecializationError
from app.services.hiring import (
    CandidateNotFoundError,
    HiringNeedNotFoundError,
    HiringServiceDep,
    SearchFilters,
)
from app.services.invitations import (
    DeclineCooldownError,
    InvitationAlreadyPendingError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InvitationServiceDep,
    NoCounterOfferError,
    PendingQuotaExceededError,
    SalaryBelowExpectationError,
)
from app.services.scoring import ScoringUnavailableError
from app.services.trust import CompanyFrozenError

router = APIRouter(prefix="/employer", tags=["employer"])


@router.get("/needs", responses=error_responses(*COMPANY_MEMBER_ERRORS))
async def list_hiring_needs(
    member: CompanyMemberDep, hiring: HiringServiceDep
) -> list[HiringNeedRead]:
    return [HiringNeedRead.from_need(need) for need in await hiring.list_needs(member)]


@router.post(
    "/needs",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS, UnknownGradeError, UnknownSkillError, UnknownSpecializationError
    ),
)
async def create_hiring_need(
    payload: HiringNeedInput, member: CompanyMemberDep, hiring: HiringServiceDep
) -> HiringNeedRead:
    """Описание потребности: кого ищем. По нему строится подборка кандидатов."""
    return HiringNeedRead.from_need(await hiring.create_need(member, payload))


@router.get(
    "/needs/{need_id}", responses=error_responses(*COMPANY_MEMBER_ERRORS, HiringNeedNotFoundError)
)
async def get_hiring_need(
    need_id: uuid.UUID, member: CompanyMemberDep, hiring: HiringServiceDep
) -> HiringNeedRead:
    return HiringNeedRead.from_need(await hiring.get_need(member, need_id))


@router.put(
    "/needs/{need_id}",
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS,
        UnknownGradeError,
        UnknownSkillError,
        UnknownSpecializationError,
        HiringNeedNotFoundError,
    ),
)
async def update_hiring_need(
    need_id: uuid.UUID,
    payload: HiringNeedInput,
    member: CompanyMemberDep,
    hiring: HiringServiceDep,
) -> HiringNeedRead:
    return HiringNeedRead.from_need(await hiring.update_need(member, need_id, payload))


@router.delete(
    "/needs/{need_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*COMPANY_MEMBER_ERRORS, HiringNeedNotFoundError),
)
async def delete_hiring_need(
    need_id: uuid.UUID, member: CompanyMemberDep, hiring: HiringServiceDep
) -> None:
    await hiring.delete_need(member, need_id)


@router.get("/categories", responses=error_responses(*COMPANY_MEMBER_ERRORS))
async def list_candidate_categories(
    member: CompanyMemberDep, hiring: HiringServiceDep
) -> list[CategoryCountRead]:
    """Обзор банка: категории «направление × грейд» с числом кандидатов и подтверждённых."""
    return [CategoryCountRead.from_count(c) for c in await hiring.categories(member)]


@router.get(
    "/candidates",
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS, UnknownGradeError, HiringNeedNotFoundError, ScoringUnavailableError
    ),
)
async def search_candidates(
    member: CompanyMemberDep,
    hiring: HiringServiceDep,
    need_id: uuid.UUID | None = None,
    specialization_id: DbInt | None = None,
    grade_id: DbInt | None = None,
    skill_ids: Annotated[list[DbInt], Query()] = [],  # noqa: B006  # FastAPI копирует значение
    confirmed_only: bool = False,
    work_format: WorkFormat | None = None,
    has_fsp: bool = False,
) -> CandidateSearchRead:
    """Подборка под потребность (need_id) или поиск по банку кандидатов.

    Выдача строится по категориям из тестирования и ранжируется по соответствию потребности
    и силе подтверждённого профиля; у каждого кандидата есть объяснение позиции. Фильтры сужают
    подборку, не меняя её порядка.
    """
    result = await hiring.search(
        member,
        need_id=need_id,
        filters=SearchFilters(
            specialization_id=specialization_id,
            grade_id=grade_id,
            skill_ids=frozenset(skill_ids),
            confirmed_only=confirmed_only,
            work_format=work_format.value if work_format else None,
            has_fsp=has_fsp,
        ),
    )
    return CandidateSearchRead.from_result(result)


@router.put(
    "/needs/{need_id}/shortlist/{candidate_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS, CandidateNotFoundError, HiringNeedNotFoundError
    ),
)
async def add_to_shortlist(
    need_id: uuid.UUID, candidate_number: DbInt, member: CompanyMemberDep, hiring: HiringServiceDep
) -> None:
    """Отобрать кандидата в потребность: он останется в шортлисте при любых фильтрах."""
    await hiring.add_to_shortlist(member, need_id, candidate_number)


@router.delete(
    "/needs/{need_id}/shortlist/{candidate_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*COMPANY_MEMBER_ERRORS, HiringNeedNotFoundError),
)
async def remove_from_shortlist(
    need_id: uuid.UUID, candidate_number: DbInt, member: CompanyMemberDep, hiring: HiringServiceDep
) -> None:
    await hiring.remove_from_shortlist(member, need_id, candidate_number)


@router.get(
    "/candidates/{candidate_number}/pdf",
    response_class=Response,
    responses={
        **error_responses(*COMPANY_MEMBER_ERRORS, CandidateNotFoundError),
        200: {"content": {"application/pdf": {}}},
    },
)
async def download_employer_candidate_pdf(
    candidate_number: DbInt,
    member: CompanyMemberDep,
    hiring: HiringServiceDep,
) -> Response:
    """PDF-профиль кандидата, как и карточка: до принятия приглашения обезличенно,
    после него с ФИО, контактами и командами ФСП."""
    card = EmployerCandidateRead.from_details(
        await hiring.get_candidate(member, candidate_number, need_id=None)
    )
    return pdf_response(render_candidate_pdf(card), f"candidate-{candidate_number}.pdf")


@router.get(
    "/candidates/{candidate_number}",
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS,
        CandidateNotFoundError,
        HiringNeedNotFoundError,
        ScoringUnavailableError,
    ),
)
async def get_employer_candidate(
    candidate_number: DbInt,
    member: CompanyMemberDep,
    hiring: HiringServiceDep,
    need_id: uuid.UUID | None = None,
) -> EmployerCandidateRead:
    """Карточка кандидата. Контакты: только если кандидат принял приглашение компании."""
    return EmployerCandidateRead.from_details(
        await hiring.get_candidate(member, candidate_number, need_id=need_id)
    )


@router.post(
    "/invitations",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS,
        CandidateNotFoundError,
        HiringNeedNotFoundError,
        CompanyFrozenError,
        DeclineCooldownError,
        InvitationAlreadyPendingError,
        PendingQuotaExceededError,
        SalaryBelowExpectationError,
        ScoringUnavailableError,
    ),
)
async def send_invitation(
    payload: InvitationInput, member: CompanyMemberDep, invitations: InvitationServiceDep
) -> EmployerInvitationRead:
    """Приглашение конкретному кандидату с вилкой. Привязка к потребности не обязательна."""
    return EmployerInvitationRead.from_employer(await invitations.create(member, payload))


@router.get("/invitations", responses=error_responses(*COMPANY_MEMBER_ERRORS))
async def list_sent_invitations(
    member: CompanyMemberDep, invitations: InvitationServiceDep
) -> list[EmployerInvitationRead]:
    return [
        EmployerInvitationRead.from_employer(i) for i in await invitations.list_for_company(member)
    ]


@router.post(
    "/invitations/{invitation_id}/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS, InvitationNotFoundError, InvitationNotPendingError
    ),
)
async def withdraw_invitation(
    invitation_id: uuid.UUID, member: CompanyMemberDep, invitations: InvitationServiceDep
) -> None:
    await invitations.withdraw(member, invitation_id)


@router.post(
    "/invitations/{invitation_id}/answer",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS, InvitationNotFoundError, InvitationNotPendingError
    ),
)
async def answer_application(
    invitation_id: uuid.UUID,
    payload: ApplicationAnswerInput,
    member: CompanyMemberDep,
    invitations: InvitationServiceDep,
) -> None:
    """Ответ на отклик кандидата: пригласить к разговору (открывается переписка) или отказать."""
    await invitations.answer_application(
        member, invitation_id, accept=payload.accept, reason=payload.reason
    )


@router.post(
    "/invitations/{invitation_id}/raise",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *COMPANY_MEMBER_ERRORS,
        InvitationNotFoundError,
        InvitationNotPendingError,
        NoCounterOfferError,
        CompanyFrozenError,
    ),
)
async def raise_to_counter_offer(
    invitation_id: uuid.UUID, member: CompanyMemberDep, invitations: InvitationServiceDep
) -> None:
    """Принять встречное предложение кандидата: вилка поднимается до его суммы, приглашение
    снова ждёт ответа ещё 7 дней."""
    await invitations.raise_to_counter(member, invitation_id)
