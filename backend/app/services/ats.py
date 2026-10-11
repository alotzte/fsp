"""Интеграция с ATS: pull-лента событий компании по API-токену (docs/architecture.md §9.1).

ATS (Хантфлоу, Talantix, своя) раз в несколько минут забирает `GET /api/v1/ats/events?since=...`
и получает новые отклики, ответы кандидатов на приглашения, ответы компании на отклики и
сообщения переписки. Без фоновых задач и отдельной таблицы событий: события собираются из тех же
записей, что видит кабинет. Контакты кандидата: только при активном раскрытии, как в кабинете.
Push-вебхуки через outbox: следующий шаг (концепция).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import and_, select, update

from app.errors import NotFoundError, UnauthorizedError
from app.services.companies import CompanyServiceDep, NotCompanyOwnerError
from app.services.db.models import (
    CandidateProfile,
    CompanyApiToken,
    CompanyMember,
    CompanyRole,
    ContactReveal,
    Invitation,
    InvitationDirection,
    InvitationMessage,
    InvitationStatus,
    User,
)
from app.services.db.session import SessionDep
from app.services.tokens import generate_token, hash_token

# Сколько событий за запрос: ATS догоняет историю несколькими запросами по курсору.
EVENTS_LIMIT = 200
# Префикс, по которому токен легко узнать в логах и секретах ATS.
TOKEN_PREFIX = "fspats_"


class AtsTokenInvalidError(UnauthorizedError):
    message = "Неверный или отозванный токен ATS"


class AtsTokenNotFoundError(NotFoundError):
    message = "Токен не найден"


@dataclass(frozen=True)
class AtsCandidate:
    last_name: str
    first_name: str
    email: str
    phone: str
    telegram: str


@dataclass(frozen=True)
class AtsEvent:
    # Устойчивый id: ATS отбрасывает повторы при перекрытии курсоров.
    id: str
    type: str
    occurred_at: datetime
    invitation_id: uuid.UUID
    need_id: uuid.UUID | None
    title: str
    candidate_number: int
    status: InvitationStatus
    decline_reason: str | None
    message: str | None
    # Только при активном раскрытии контактов компании.
    candidate: AtsCandidate | None


@dataclass(frozen=True)
class IssuedAtsToken:
    record: CompanyApiToken
    token: str


class AtsService:
    def __init__(self, session: SessionDep, companies: CompanyServiceDep) -> None:
        self._session = session
        self._companies = companies

    # --- Токены (владелец компании) ---

    async def issue_token(self, user: User, title: str) -> IssuedAtsToken:
        membership = await self._require_owner(user)
        token = f"{TOKEN_PREFIX}{generate_token()}"
        record = CompanyApiToken(
            company_id=membership.company_id,
            token_hash=hash_token(token),
            title=title,
            created_by_id=user.id,
        )
        self._session.add(record)
        await self._session.commit()
        return IssuedAtsToken(record, token)

    async def list_tokens(self, user: User) -> Sequence[CompanyApiToken]:
        membership = await self._require_owner(user)
        result = await self._session.scalars(
            select(CompanyApiToken)
            .where(
                CompanyApiToken.company_id == membership.company_id,
                CompanyApiToken.revoked_at.is_(None),
            )
            .order_by(CompanyApiToken.created_at.desc())
        )
        return result.all()

    async def revoke_token(self, user: User, token_id: uuid.UUID) -> None:
        membership = await self._require_owner(user)
        result = await self._session.execute(
            update(CompanyApiToken)
            .where(
                CompanyApiToken.id == token_id,
                CompanyApiToken.company_id == membership.company_id,
                CompanyApiToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise AtsTokenNotFoundError
        await self._session.commit()

    async def _require_owner(self, user: User) -> CompanyMember:
        membership = await self._companies.require_membership(user)
        if membership.role != CompanyRole.OWNER:
            raise NotCompanyOwnerError
        return membership

    # --- Лента (ATS по токену) ---

    async def company_by_token(self, token: str) -> uuid.UUID:
        record = await self._session.scalar(
            select(CompanyApiToken).where(
                CompanyApiToken.token_hash == hash_token(token),
                CompanyApiToken.revoked_at.is_(None),
            )
        )
        if record is None:
            raise AtsTokenInvalidError
        record.last_used_at = datetime.now(UTC)
        await self._session.commit()
        return record.company_id

    async def events(self, company_id: uuid.UUID, since: datetime | None) -> list[AtsEvent]:
        """События начиная с since (включительно), не больше EVENTS_LIMIT. Курсор следующего
        запроса: occurred_at последнего события; события с той же меткой придут повторно, ATS
        отбрасывает их по id. Строгое «>» теряло события с одинаковой меткой на границе (отклики
        одной транзакции). ponytail: курсор по времени; при большом потоке: таблица событий с
        монотонным id (она же outbox для вебхуков)."""
        since = since or datetime.min.replace(tzinfo=UTC)
        revealed = and_(
            ContactReveal.company_id == Invitation.company_id,
            ContactReveal.candidate_user_id == Invitation.candidate_user_id,
            ContactReveal.revoked_at.is_(None),
        )
        base = (
            select(Invitation, CandidateProfile, User, ContactReveal.company_id)
            .join(CandidateProfile, CandidateProfile.user_id == Invitation.candidate_user_id)
            .join(User, User.id == Invitation.candidate_user_id)
            .outerjoin(ContactReveal, revealed)
            .where(Invitation.company_id == company_id)
        )
        events: list[AtsEvent] = []
        # Новые отклики кандидатов.
        rows = await self._session.execute(
            base.where(
                Invitation.direction == InvitationDirection.CANDIDATE,
                Invitation.created_at >= since,
            )
        )
        for invitation, profile, user, shared in rows:
            events.append(
                _event(
                    "application.created", invitation.created_at, invitation, profile, user, shared
                )
            )
        # Ответы: кандидата на приглашение и компании на отклик.
        rows = await self._session.execute(
            base.where(
                Invitation.status.in_((InvitationStatus.ACCEPTED, InvitationStatus.DECLINED)),
                Invitation.answered_at >= since,
            )
        )
        for invitation, profile, user, shared in rows:
            kind = (
                "application"
                if invitation.direction == InvitationDirection.CANDIDATE
                else "invitation"
            )
            assert invitation.answered_at is not None
            events.append(
                _event(
                    f"{kind}.{invitation.status.value}",
                    invitation.answered_at,
                    invitation,
                    profile,
                    user,
                    shared,
                )
            )
        # Сообщения переписки.
        rows_messages = await self._session.execute(
            select(InvitationMessage, Invitation, CandidateProfile, User, ContactReveal.company_id)
            .join(Invitation, Invitation.id == InvitationMessage.invitation_id)
            .join(CandidateProfile, CandidateProfile.user_id == Invitation.candidate_user_id)
            .join(User, User.id == Invitation.candidate_user_id)
            .outerjoin(ContactReveal, revealed)
            .where(Invitation.company_id == company_id, InvitationMessage.created_at >= since)
        )
        for message, invitation, profile, user, shared in rows_messages:
            author = (
                "candidate" if message.author_id == invitation.candidate_user_id else "company"
            )
            events.append(
                _event(
                    "message.created",
                    message.created_at,
                    invitation,
                    profile,
                    user,
                    shared,
                    event_id=f"message:{message.id}",
                    message=f"[{author}] {message.body}",
                )
            )
        events.sort(key=lambda event: (event.occurred_at, event.id))
        return events[:EVENTS_LIMIT]


def _event(
    kind: str,
    occurred_at: datetime,
    invitation: Invitation,
    profile: CandidateProfile,
    user: User,
    shared: uuid.UUID | None,
    *,
    event_id: str | None = None,
    message: str | None = None,
) -> AtsEvent:
    return AtsEvent(
        id=event_id or f"{kind}:{invitation.id}",
        type=kind,
        occurred_at=occurred_at,
        invitation_id=invitation.id,
        need_id=invitation.need_id,
        title=invitation.title,
        candidate_number=profile.candidate_number,
        status=invitation.status,
        decline_reason=invitation.decline_reason.value if invitation.decline_reason else None,
        message=message,
        candidate=(
            AtsCandidate(
                last_name=profile.last_name,
                first_name=profile.first_name,
                email=user.email,
                phone=profile.phone,
                telegram=profile.telegram,
            )
            if shared is not None
            else None
        ),
    )


AtsServiceDep = Annotated[AtsService, Depends()]
