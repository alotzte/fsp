import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, StringConstraints

from app.services.db.models import InvitationStatus

if TYPE_CHECKING:
    from app.services.ats import AtsEvent, IssuedAtsToken
    from app.services.db.models import CompanyApiToken


class AtsTokenInput(BaseModel):
    # Для какой системы токен: «Хантфлоу», «Talantix».
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AtsTokenRead(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    last_used_at: datetime | None

    @classmethod
    def from_token(cls, record: "CompanyApiToken") -> "AtsTokenRead":
        return cls(
            id=record.id,
            title=record.title,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
        )


class AtsTokenIssuedRead(AtsTokenRead):
    # Показывается один раз: в БД только хеш.
    token: str

    @classmethod
    def from_issued(cls, issued: "IssuedAtsToken") -> "AtsTokenIssuedRead":
        return cls(**AtsTokenRead.from_token(issued.record).model_dump(), token=issued.token)


class AtsCandidateRead(BaseModel):
    last_name: str
    first_name: str
    email: str
    phone: str
    telegram: str


class AtsEventRead(BaseModel):
    id: str
    # application.created, application.accepted / declined, invitation.accepted / declined,
    # message.created.
    type: str
    occurred_at: datetime
    invitation_id: uuid.UUID
    need_id: uuid.UUID | None
    title: str
    candidate_number: int
    status: InvitationStatus
    decline_reason: str | None
    message: str | None
    # Только пока кандидат не закрыл компании доступ к контактам.
    candidate: AtsCandidateRead | None

    @classmethod
    def from_event(cls, event: "AtsEvent") -> "AtsEventRead":
        candidate = event.candidate
        return cls(
            id=event.id,
            type=event.type,
            occurred_at=event.occurred_at,
            invitation_id=event.invitation_id,
            need_id=event.need_id,
            title=event.title,
            candidate_number=event.candidate_number,
            status=event.status,
            decline_reason=event.decline_reason,
            message=event.message,
            candidate=AtsCandidateRead(**vars(candidate)) if candidate else None,
        )


class AtsEventsRead(BaseModel):
    events: list[AtsEventRead]
    # Передать в since следующего запроса; null: событий пока нет, повторить с тем же since.
    next_since: datetime | None
