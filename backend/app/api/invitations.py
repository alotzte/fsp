import uuid

from fastapi import APIRouter, status

from app.errors import error_responses
from app.schemas.hiring import VacancyRead
from app.schemas.invitations import (
    AcceptInput,
    CandidateInvitationRead,
    ChatRead,
    CounterInput,
    DeclineInput,
    MessageInput,
    MessageRead,
    NotificationsRead,
    ReportInput,
)
from app.services.auth.dependencies import (
    CURRENT_USER_ERRORS,
    ROLE_ERRORS,
    CandidateUserDep,
    CurrentUserDep,
)
from app.services.db.models import UserRole
from app.services.hiring import CandidateNotFoundError, VacancyNotFoundError
from app.services.invitations import (
    AlreadyAppliedError,
    ApplicationAlreadyPendingError,
    ApplicationGradeMismatchError,
    ApplicationWeeklyLimitError,
    ChatClosedError,
    ChatNotAvailableError,
    CounterAlreadySentError,
    CounterWithinRangeError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InvitationServiceDep,
    ProfileNotPublishedError,
    from_my_side,
)
from app.services.scoring import ScoringUnavailableError
from app.services.trust import AlreadyReportedError, ReportTargetNotFoundError, TrustServiceDep

candidate_router = APIRouter(prefix="/candidate/invitations", tags=["invitations"])
chat_router = APIRouter(prefix="/invitations", tags=["invitations"])


@candidate_router.get("", responses=error_responses(*ROLE_ERRORS))
async def list_my_invitations(
    user: CandidateUserDep, invitations: InvitationServiceDep, trust: TrustServiceDep
) -> list[CandidateInvitationRead]:
    """Входящие приглашения. Открытие списка отмечает новые приглашения просмотренными."""
    items = await invitations.list_for_candidate(user)
    shared = await invitations.revealed_company_ids(user)
    reputations = await invitations.reputations({i.company_id for i in items})
    reported = await trust.reported_company_ids(user)
    return [
        CandidateInvitationRead.from_invitation(
            i,
            i.company_id in shared,
            reputations.get(i.company_id),
            reported=i.company_id in reported,
        )
        for i in items
    ]


@candidate_router.post(
    "/{invitation_id}/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*ROLE_ERRORS, InvitationNotFoundError, InvitationNotPendingError),
)
async def accept_invitation(
    invitation_id: uuid.UUID,
    user: CandidateUserDep,
    invitations: InvitationServiceDep,
    payload: AcceptInput | None = None,
) -> None:
    """Принять приглашение: компания получает ФИО и контакты, открывается переписка.
    Если к приглашению приложен кейс, решение можно отправить здесь же."""
    await invitations.accept(user, invitation_id, payload.case_answer if payload else "")


@candidate_router.post(
    "/{invitation_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*ROLE_ERRORS, InvitationNotFoundError, InvitationNotPendingError),
)
async def decline_invitation(
    invitation_id: uuid.UUID,
    payload: DeclineInput,
    user: CandidateUserDep,
    invitations: InvitationServiceDep,
) -> None:
    await invitations.decline(user, invitation_id, payload.reason)


@candidate_router.post(
    "/{invitation_id}/counter",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *ROLE_ERRORS,
        InvitationNotFoundError,
        InvitationNotPendingError,
        CounterAlreadySentError,
        CounterWithinRangeError,
    ),
)
async def counter_invitation(
    invitation_id: uuid.UUID,
    payload: CounterInput,
    user: CandidateUserDep,
    invitations: InvitationServiceDep,
) -> None:
    """Встречное предложение вместо отказа: «готов при вилке от X» (один раз, выше верха вилки).
    Контакты не раскрываются; компания может поднять вилку, и приглашение вернётся."""
    await invitations.counter(user, invitation_id, payload.salary_rub)


@candidate_router.post(
    "/{invitation_id}/report",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*ROLE_ERRORS, ReportTargetNotFoundError, AlreadyReportedError),
)
async def report_company(
    invitation_id: uuid.UUID, payload: ReportInput, user: CandidateUserDep, trust: TrustServiceDep
) -> None:
    """Пожаловаться на компанию, которая прислала приглашение. После жалоб нескольких
    кандидатов компания замораживается до разбора."""
    await trust.report(user, invitation_id, payload.reason)


@candidate_router.post(
    "/{invitation_id}/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*ROLE_ERRORS, InvitationNotFoundError, InvitationNotPendingError),
)
async def withdraw_application(
    invitation_id: uuid.UUID, user: CandidateUserDep, invitations: InvitationServiceDep
) -> None:
    """Отозвать свой отклик, пока компания не ответила."""
    await invitations.withdraw_application(user, invitation_id)


@candidate_router.post(
    "/companies/{company_id}/revoke-contacts",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*ROLE_ERRORS),
)
async def revoke_contact_access(
    company_id: uuid.UUID, user: CandidateUserDep, invitations: InvitationServiceDep
) -> None:
    """Закрыть компании доступ к своим контактам."""
    await invitations.revoke_contacts(user, company_id)


@chat_router.get(
    "/{invitation_id}/messages",
    responses=error_responses(
        *CURRENT_USER_ERRORS, InvitationNotFoundError, ChatNotAvailableError
    ),
)
async def list_invitation_messages(
    invitation_id: uuid.UUID, user: CurrentUserDep, invitations: InvitationServiceDep
) -> list[MessageRead]:
    """Переписка по принятому приглашению: для кандидата и сотрудников компании."""
    invitation, messages = await invitations.list_messages(user, invitation_id)
    is_candidate = user.role == UserRole.CANDIDATE
    return [
        MessageRead.from_message(
            m,
            mine=from_my_side(
                m.author_id, invitation.candidate_user_id, viewer_is_candidate=is_candidate
            ),
        )
        for m in messages
    ]


@chat_router.post(
    "/{invitation_id}/messages",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *CURRENT_USER_ERRORS, InvitationNotFoundError, ChatNotAvailableError, ChatClosedError
    ),
)
async def post_invitation_message(
    invitation_id: uuid.UUID,
    payload: MessageInput,
    user: CurrentUserDep,
    invitations: InvitationServiceDep,
) -> None:
    await invitations.post_message(user, invitation_id, payload.body)


inbox_router = APIRouter(tags=["chats"])


@inbox_router.get("/chats", responses=error_responses(*CURRENT_USER_ERRORS))
async def list_my_chats(user: CurrentUserDep, invitations: InvitationServiceDep) -> list[ChatRead]:
    """Переписки по принятым приглашениям и откликам, сначала свежие, с непрочитанными."""
    is_candidate = user.role == UserRole.CANDIDATE
    return [
        ChatRead.from_chat(chat, viewer_is_candidate=is_candidate)
        for chat in await invitations.chats(user)
    ]


@inbox_router.get("/notifications", responses=error_responses(*CURRENT_USER_ERRORS))
async def get_my_notifications(
    user: CurrentUserDep, invitations: InvitationServiceDep
) -> NotificationsRead:
    """Счётчики того, что ждёт действия: непрочитанные сообщения, приглашения и отклики без
    ответа. Фронт опрашивает их и по изменению обновляет списки."""
    return NotificationsRead.from_notifications(await invitations.notifications(user))


vacancy_router = APIRouter(prefix="/candidate/vacancies", tags=["vacancies"])


@vacancy_router.get(
    "", responses=error_responses(*ROLE_ERRORS, CandidateNotFoundError, ScoringUnavailableError)
)
async def list_vacancies(
    user: CandidateUserDep, invitations: InvitationServiceDep
) -> list[VacancyRead]:
    """Вакансии направления кандидата с его совпадением; почему нельзя откликнуться: в
    apply_block (то же правило, что проверяет отклик)."""
    return [VacancyRead.from_item(item) for item in await invitations.vacancy_feed(user)]


@vacancy_router.post(
    "/{need_id}/apply",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        *ROLE_ERRORS,
        ProfileNotPublishedError,
        VacancyNotFoundError,
        AlreadyAppliedError,
        ApplicationAlreadyPendingError,
        ApplicationGradeMismatchError,
        ApplicationWeeklyLimitError,
        ScoringUnavailableError,
    ),
)
async def apply_to_vacancy(
    need_id: uuid.UUID, user: CandidateUserDep, invitations: InvitationServiceDep
) -> None:
    """Откликнуться: компания сразу видит профиль с ФИО и контактами и отвечает в течение 7 дней.
    Нужен опубликованный профиль; без подтверждённого грейда: не больше 3 откликов в неделю."""
    await invitations.apply(user, need_id)
