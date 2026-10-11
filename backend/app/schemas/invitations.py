import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.candidates import MAX_SALARY_RUB, ShortText, mask_contacts
from app.schemas.common import DbInt, SkillCheckRead
from app.schemas.companies import company_logo_url
from app.services.db.models import (
    DeclineReason,
    InvitationDirection,
    InvitationStatus,
    ReportReason,
)
from app.services.invitations import from_my_side

if TYPE_CHECKING:
    from app.services.db.models import Invitation, InvitationMessage
    from app.services.invitations import (
        Chat,
        CompanyReputation,
        EmployerInvitation,
        Notifications,
    )

SALARY_RANGE_ERROR = "Верх вилки не может быть меньше нижней границы"

Salary = Annotated[int, Field(gt=0, le=MAX_SALARY_RUB, description="Рублей в месяц")]
# Кейс: вопрос о подходе, а не бесплатная работа: короткое условие и ответ.
MAX_CASE_TASK = 1500
MAX_CASE_ANSWER = 3000


class SalaryRangeInput(BaseModel):
    salary_from_rub: Salary
    salary_to_rub: Salary

    @model_validator(mode="after")
    def _valid_range(self) -> Self:
        if self.salary_to_rub < self.salary_from_rub:
            raise ValueError(SALARY_RANGE_ERROR)
        return self


class InvitationInput(SalaryRangeInput):
    candidate_number: DbInt
    # Потребность, по которой нашли кандидата. Не обязательна: приглашают и без неё.
    need_id: uuid.UUID | None = None
    title: ShortText
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)
    ]
    # Как связаться: телефон, почта, Telegram рекрутера, кандидат видит сразу.
    contact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    # Необязательный короткий кейс: кандидат ответит на него вместе с принятием.
    case_task: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=MAX_CASE_TASK)
    ] = ""


class EmployerInvitationRead(BaseModel):
    id: uuid.UUID
    # employer: приглашение компании, candidate: отклик кандидата на вакансию.
    direction: InvitationDirection
    candidate_number: int
    need_id: uuid.UUID | None
    title: str
    salary_from_rub: int
    salary_to_rub: int
    status: InvitationStatus
    decline_reason: DeclineReason | None
    created_at: datetime
    viewed_at: datetime | None
    answered_at: datetime | None
    expires_at: datetime
    # Видит ли компания сейчас контакты кандидата; если нет: переписка только для чтения.
    contacts_shared: bool
    case_task: str | None
    # Решение кейса приходит вместе с принятием: значит, уже вместе с контактами.
    case_answer: str | None
    # Встречное предложение кандидата: готов при вилке от этой суммы.
    counter_salary_rub: int | None

    @classmethod
    def from_invitation(
        cls, invitation: "Invitation", candidate_number: int, *, contacts_shared: bool
    ) -> "EmployerInvitationRead":
        return cls(
            id=invitation.id,
            direction=invitation.direction,
            candidate_number=candidate_number,
            need_id=invitation.need_id,
            title=invitation.title,
            salary_from_rub=invitation.salary_from_rub,
            salary_to_rub=invitation.salary_to_rub,
            status=invitation.status,
            decline_reason=invitation.decline_reason,
            created_at=invitation.created_at,
            viewed_at=invitation.viewed_at,
            answered_at=invitation.answered_at,
            expires_at=invitation.expires_at,
            contacts_shared=contacts_shared,
            case_task=invitation.case_task,
            # Решение кейса уходит вместе с контактами; без активного раскрытия идёт с маской.
            case_answer=(
                invitation.case_answer
                if contacts_shared or invitation.case_answer is None
                else mask_contacts(invitation.case_answer)
            ),
            counter_salary_rub=invitation.counter_salary_rub,
        )

    @classmethod
    def from_employer(cls, item: "EmployerInvitation") -> "EmployerInvitationRead":
        return cls.from_invitation(
            item.invitation, item.candidate_number, contacts_shared=item.contacts_shared
        )


class CompanyReputationRead(BaseModel):
    """Как компания ведёт себя с кандидатами: по её завершённым приглашениям."""

    invitations: int
    # Доля принятых приглашений, по которым компания написала в течение 3 дней.
    replied_share: float | None
    # Медиана часов от принятия до первого сообщения компании.
    median_reply_hours: float | None
    withdrawn_share: float

    @classmethod
    def from_reputation(cls, reputation: "CompanyReputation") -> "CompanyReputationRead":
        median = reputation.median_reply
        return cls(
            invitations=reputation.invitations,
            replied_share=reputation.replied_share,
            median_reply_hours=median.total_seconds() / 3600 if median is not None else None,
            withdrawn_share=reputation.withdrawn_share,
        )


class InvitingCompanyRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    website: str
    logo_url: str | None
    # Нет: у компании пока мало завершённых приглашений.
    reputation: CompanyReputationRead | None
    # Подтверждённый письмом домен сайта; пусто: не подтверждён.
    verified_domain: str


class InvitationMatchRead(BaseModel):
    """Почему пригласили: совпадение с потребностью на момент отправки приглашения."""

    score: float
    grade: str | None
    grade_confirmed: bool
    # Победы, призовые места и финалы ФСП; 0 значит не упоминаем (нет истории, нет и строки).
    fsp_achievements: int
    skills: list[SkillCheckRead]


class CandidateInvitationRead(BaseModel):
    """Приглашение глазами кандидата: компания, суть предложения, вилка и способ связи.
    Отклик кандидата (direction=candidate) лежит в том же списке, на него отвечает компания."""

    id: uuid.UUID
    direction: InvitationDirection
    company: InvitingCompanyRead
    title: str
    description: str
    salary_from_rub: int
    salary_to_rub: int
    contact: str
    status: InvitationStatus
    decline_reason: DeclineReason | None
    created_at: datetime
    expires_at: datetime
    # Видит ли компания сейчас контакты кандидата.
    contacts_shared: bool
    # Почему выбрали именно вас; нет: приглашение отправлено без потребности.
    match: InvitationMatchRead | None
    case_task: str | None
    case_answer: str | None
    counter_salary_rub: int | None
    # Кандидат уже пожаловался на эту компанию.
    reported: bool

    @classmethod
    def from_invitation(
        cls,
        invitation: "Invitation",
        contacts_shared: bool,
        reputation: "CompanyReputation | None",
        *,
        reported: bool = False,
    ) -> "CandidateInvitationRead":
        company = invitation.company
        return cls(
            id=invitation.id,
            direction=invitation.direction,
            company=InvitingCompanyRead(
                id=company.id,
                name=company.name,
                description=company.description,
                website=company.website,
                logo_url=company_logo_url(company.id, company.logo_file_id),
                reputation=(
                    CompanyReputationRead.from_reputation(reputation) if reputation else None
                ),
                verified_domain=company.verified_domain,
            ),
            title=invitation.title,
            description=invitation.description,
            salary_from_rub=invitation.salary_from_rub,
            salary_to_rub=invitation.salary_to_rub,
            contact=invitation.contact,
            status=invitation.status,
            decline_reason=invitation.decline_reason,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            contacts_shared=contacts_shared,
            match=(
                InvitationMatchRead.model_validate(invitation.match_snapshot)
                if invitation.match_snapshot
                else None
            ),
            case_task=invitation.case_task,
            case_answer=invitation.case_answer,
            counter_salary_rub=invitation.counter_salary_rub,
            reported=reported,
        )


class CounterInput(BaseModel):
    # «Готов при вилке от»: выше верха вилки приглашения.
    salary_rub: Salary


class ReportInput(BaseModel):
    reason: ReportReason


class AcceptInput(BaseModel):
    # Решение кейса из приглашения, если он есть. Необязательно.
    case_answer: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=MAX_CASE_ANSWER)
    ] = ""


class DeclineInput(BaseModel):
    reason: DeclineReason


class MessageInput(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class MessageRead(BaseModel):
    id: int
    mine: bool
    body: str
    created_at: datetime

    @classmethod
    def from_message(cls, message: "InvitationMessage", *, mine: bool) -> "MessageRead":
        return cls(id=message.id, mine=mine, body=message.body, created_at=message.created_at)


class ChatCompanyRead(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None


class ChatRead(BaseModel):
    """Переписка в списке «Сообщения»: с кем, последнее сообщение, сколько непрочитанных."""

    invitation_id: uuid.UUID
    direction: InvitationDirection
    title: str
    company: ChatCompanyRead
    candidate_number: int
    # ФИО кандидата: только компании и только пока кандидат не закрыл контакты.
    candidate_name: str | None
    # Нет: кандидат закрыл контакты, переписка только для чтения.
    contacts_shared: bool
    last_message: MessageRead | None
    unread: int

    @classmethod
    def from_chat(cls, chat: "Chat", *, viewer_is_candidate: bool) -> "ChatRead":
        invitation = chat.invitation
        company = invitation.company
        last = chat.last_message
        return cls(
            invitation_id=invitation.id,
            direction=invitation.direction,
            title=invitation.title,
            company=ChatCompanyRead(
                id=company.id,
                name=company.name,
                logo_url=company_logo_url(company.id, company.logo_file_id),
            ),
            candidate_number=chat.candidate_number,
            candidate_name=chat.candidate_name,
            contacts_shared=chat.contacts_shared,
            last_message=(
                MessageRead.from_message(
                    last,
                    mine=from_my_side(
                        last.author_id,
                        invitation.candidate_user_id,
                        viewer_is_candidate=viewer_is_candidate,
                    ),
                )
                if last
                else None
            ),
            unread=chat.unread,
        )


class NotificationsRead(BaseModel):
    """Что ждёт действия пользователя: счётчики в шапке, опрашиваются фронтом."""

    unread_messages: int
    invitations_to_answer: int
    chats_to_start: int

    @classmethod
    def from_notifications(cls, notifications: "Notifications") -> "NotificationsRead":
        return cls(
            unread_messages=notifications.unread_messages,
            invitations_to_answer=notifications.invitations_to_answer,
            chats_to_start=notifications.chats_to_start,
        )


class ApplicationAnswerInput(BaseModel):
    """Ответ компании на отклик: пригласить к разговору или отказать с причиной."""

    accept: bool
    reason: DeclineReason | None = None
