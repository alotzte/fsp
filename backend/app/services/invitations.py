"""Приглашения работодателя кандидату: выход на контакт по инициативе работодателя.

Правила (ТЗ + архитектура §5):
- вилка «от-до» обязательна, кандидат видит её сразу, до начала общения;
- верх вилки не ниже скрытых ожиданий кандидата, иначе приглашение не отправляется;
- контакты кандидата раскрываются компании только после того, как он принял приглашение;
- у компании ограничено число приглашений, ждущих ответа (по уровню доверия, `pending_quota`):
  любой ответ освобождает место, поэтому выгодно приглашать точно, а не рассылать всем подряд;
- замороженная жалобами компания приглашать не может;
- после отказа компания не может снова пригласить того же кандидата DECLINE_COOLDOWN.

Отклик кандидата на вакансию: та же запись с direction=candidate: отвечает работодатель,
а контакты раскрываются сразу (ТЗ §2.2: «или откликнулся сам»). Правила отклика:
`application_block`.
"""

import statistics
import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.config import SettingsDep
from app.errors import ConflictError, NotFoundError
from app.services.db.models import (
    PENDING_STATUSES,
    CandidateProfile,
    Company,
    CompanyMember,
    CompanyRole,
    ContactReveal,
    DeclineReason,
    Invitation,
    InvitationDirection,
    InvitationMessage,
    InvitationStatus,
    User,
    UserRole,
)
from app.services.db.session import SessionDep
from app.services.hiring import (
    CandidateNotFoundError,
    HiringServiceDep,
    PoolCandidate,
    Vacancy,
    VacancyNotFoundError,
    expire_overdue_invitations,
)
from app.services.mailer import MailerDep
from app.services.scoring import MatchResult
from app.services.trust import CompanyFrozenError, is_shared_demo, pending_quota

if TYPE_CHECKING:
    from app.schemas.invitations import InvitationInput

# Сколько ждёт ответа приглашение.
INVITATION_TTL = timedelta(days=7)
# Сколько после отказа кандидата компания не может пригласить его снова: иначе отказ
# ничего не значит, и приглашения превращаются в спам.
DECLINE_COOLDOWN = timedelta(days=30)
MESSAGES_LIMIT = 200
# Вкладка кабинета кандидата со списком приглашений (frontend/src/pages/candidate).
CANDIDATE_INVITATIONS_FRONTEND_PATH = "/candidate?tab=invitations"
# Откликов без подтверждённого грейда в неделю. Тест это способ выделиться, а не барьер, но
# массовые отклики «на всё» обесценили бы ленту для работодателя.
APPLICATIONS_PER_WEEK = 3
APPLICATIONS_WINDOW = timedelta(days=7)
# С подтверждённым грейдом: на вакансии своего грейда и соседних.
APPLICATION_GRADE_SPREAD = 1
# Приглашения в кабинете работодателя (frontend/src/app/router.tsx).
EMPLOYER_INVITATIONS_FRONTEND_PATH = "/employer/invitations"
# Репутацию показываем, когда у компании столько завершённых приглашений: одна неудача не
# должна обнулять новую компанию.
REPUTATION_MIN_INVITATIONS = 5
# «Написала после принятия»: если первое сообщение компании пришло в этот срок.
REPLY_WINDOW = timedelta(days=3)
DECLINE_REASON_TITLES = {
    DeclineReason.SALARY: "не устраивает зарплата",
    DeclineReason.STACK: "не тот стек",
    DeclineReason.FORMAT: "не подходит формат работы",
    DeclineReason.NOT_LOOKING: "сейчас не ищет работу",
    DeclineReason.OTHER: "другое",
}


class InvitationNotFoundError(NotFoundError):
    message = "Приглашение не найдено"


class SalaryBelowExpectationError(ConflictError):
    message = "Верх вилки ниже ожиданий кандидата: приглашение не будет отправлено"


class InvitationAlreadyPendingError(ConflictError):
    message = "Этому кандидату уже отправлено приглашение, ждём его ответа"


class PendingQuotaExceededError(ConflictError):
    message = (
        "Слишком много приглашений ждут ответа. Место освободится, когда кандидаты ответят "
        "или приглашения истекут"
    )


class DeclineCooldownError(ConflictError):
    message = (
        "Кандидат недавно отклонил приглашение вашей компании. "
        f"Пригласить его снова можно через {DECLINE_COOLDOWN.days} дней после отказа"
    )


class ApplicationGradeMismatchError(ConflictError):
    message = "Откликаться можно на вакансии своего подтверждённого грейда и соседних"


class ApplicationWeeklyLimitError(ConflictError):
    message = (
        f"Без подтверждённого грейда: не больше {APPLICATIONS_PER_WEEK} откликов в неделю. "
        "Пройдите тест, чтобы откликаться без ограничения"
    )


class AlreadyAppliedError(ConflictError):
    message = "Вы уже откликнулись на эту вакансию"


class ApplicationAlreadyPendingError(ConflictError):
    message = "У вас с этой компанией уже есть приглашение или отклик, ждущий ответа"


class ProfileNotPublishedError(ConflictError):
    message = "Чтобы откликаться, опубликуйте профиль: работодатель откроет его по отклику"


class CounterWithinRangeError(ConflictError):
    message = "Эта сумма уже входит в вилку приглашения: его можно просто принять"


class CounterAlreadySentError(ConflictError):
    message = "Встречное предложение по этому приглашению уже отправлено"


class NoCounterOfferError(ConflictError):
    message = "Кандидат не присылал встречного предложения"


class InvitationNotPendingError(ConflictError):
    message = "Приглашение уже не ждёт ответа"


class ChatNotAvailableError(ConflictError):
    message = "Переписка доступна после того, как кандидат принял приглашение"


class ChatClosedError(ConflictError):
    message = "Кандидат закрыл компании доступ к контактам: переписка только для чтения"


def application_block(
    *, confirmed_level: int | None, vacancy_level: int, applied_this_week: int
) -> type[ConflictError] | None:
    """Почему откликнуться нельзя (класс ошибки) или None. С подтверждённым грейдом: только
    вакансии грейда ±1; без подтверждения: не больше APPLICATIONS_PER_WEEK в неделю."""
    if confirmed_level is not None:
        if abs(confirmed_level - vacancy_level) > APPLICATION_GRADE_SPREAD:
            return ApplicationGradeMismatchError
        return None
    if applied_this_week >= APPLICATIONS_PER_WEEK:
        return ApplicationWeeklyLimitError
    return None


def counter_block(
    *, salary_to_rub: int, counter_rub: int, already_sent: bool
) -> type[ConflictError] | None:
    """Встречное предложение «готов при вилке от X» имеет смысл, только если X выше верха вилки,
    и отправляется один раз: торг по кругу превратил бы приглашение в переписку без контактов."""
    if already_sent:
        return CounterAlreadySentError
    if counter_rub <= salary_to_rub:
        return CounterWithinRangeError
    return None


def confirmed_level(candidate: PoolCandidate) -> int | None:
    grade = candidate.category.confirmed_grade if candidate.category else None
    return grade.level if grade else None


@dataclass(frozen=True)
class CompanyReputation:
    """Как компания ведёт себя с кандидатами: по её же завершённым приглашениям."""

    invitations: int
    # Доля принятых приглашений, по которым компания написала в течение REPLY_WINDOW.
    replied_share: float | None
    # Медиана времени от принятия до первого сообщения компании.
    median_reply: timedelta | None
    withdrawn_share: float


def company_reputation(
    finished: int,
    withdrawn: int,
    accepted: Sequence[tuple[datetime, datetime | None]],
    now: datetime,
) -> CompanyReputation | None:
    """finished: приглашений, которые уже не ждут ответа; accepted: пары (когда принято,
    когда компания впервые написала или None). Метрики из поведения, а не из документов:
    кандидат видит, отвечает ли компания после принятия и отзывает ли приглашения."""
    if finished < REPUTATION_MIN_INVITATIONS:
        return None
    # Недавно принятые без ответа ещё в окне: считать их «без ответа» рано.
    settled = [
        (at, reply) for at, reply in accepted if reply is not None or at + REPLY_WINDOW <= now
    ]
    in_time = sum(1 for at, reply in settled if reply is not None and reply - at <= REPLY_WINDOW)
    delays = [(reply - at).total_seconds() for at, reply in accepted if reply is not None]
    return CompanyReputation(
        invitations=finished,
        replied_share=in_time / len(settled) if settled else None,
        median_reply=timedelta(seconds=statistics.median(delays)) if delays else None,
        withdrawn_share=withdrawn / finished,
    )


@dataclass(frozen=True)
class VacancyItem:
    vacancy: Vacancy
    application_status: InvitationStatus | None
    apply_block: type[ConflictError] | None


@dataclass(frozen=True)
class EmployerInvitation:
    invitation: Invitation
    candidate_number: int
    # Видит ли компания сейчас контакты кандидата (и может ли ему писать).
    contacts_shared: bool


@dataclass(frozen=True)
class Chat:
    """Переписка по принятому приглашению глазами одной из сторон."""

    invitation: Invitation
    candidate_number: int
    # ФИО кандидата: только компании и только пока открыты контакты.
    candidate_name: str | None
    contacts_shared: bool
    last_message: InvitationMessage | None
    unread: int


@dataclass(frozen=True)
class Notifications:
    unread_messages: int
    # Ждут ответа этой стороны: кандидату: приглашения, компании: отклики и встречные
    # предложения.
    invitations_to_answer: int
    # Компании: кандидат принял, а в переписке ещё никто не написал: первой пишет компания.
    chats_to_start: int


def from_my_side(
    author_id: uuid.UUID | None, candidate_user_id: uuid.UUID, *, viewer_is_candidate: bool
) -> bool:
    """Сообщение своей стороны. Сторон две: кандидат и компания (любой её сотрудник), поэтому
    сообщение коллеги: тоже «своё», а не кандидата."""
    return (author_id == candidate_user_id) == viewer_is_candidate


class InvitationService:
    def __init__(
        self,
        session: SessionDep,
        hiring: HiringServiceDep,
        mailer: MailerDep,
        settings: SettingsDep,
    ) -> None:
        self._session = session
        self._hiring = hiring
        self._mailer = mailer
        self._settings = settings

    # --- Работодатель ---

    async def create(self, member: CompanyMember, data: "InvitationInput") -> EmployerInvitation:
        await self._expire_overdue()
        # FOR UPDATE: параллельные отправки одной компании считают квоту по очереди, иначе
        # каждая видит старое число ожидающих и квота превышается.
        company = await self._session.get_one(Company, member.company_id, with_for_update=True)
        if company.frozen_at is not None:
            raise CompanyFrozenError
        candidate = await self._hiring.find_published(member, data.candidate_number)
        profile = candidate.profile
        if await self._sandbox_reaches_real_user(member.user_id, profile.user_id):
            raise CandidateNotFoundError
        # Потребность: только своей компании.
        need = await self._hiring.get_need(member, data.need_id) if data.need_id else None
        expectation = profile.salary_expectation_rub
        if expectation is not None and data.salary_to_rub < expectation:
            raise SalaryBelowExpectationError
        pending = await self._session.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(
                Invitation.company_id == member.company_id,
                Invitation.direction == InvitationDirection.EMPLOYER,
                Invitation.status.in_(PENDING_STATUSES),
            )
        )
        over_quota = (pending or 0) >= pending_quota(company.trust_level)
        if over_quota and not await is_shared_demo(self._session, company.id):
            raise PendingQuotaExceededError
        recently_declined = await self._session.scalar(
            select(Invitation.id)
            .where(
                Invitation.company_id == member.company_id,
                Invitation.candidate_user_id == profile.user_id,
                Invitation.direction == InvitationDirection.EMPLOYER,
                Invitation.status == InvitationStatus.DECLINED,
                Invitation.answered_at > datetime.now(UTC) - DECLINE_COOLDOWN,
            )
            .limit(1)
        )
        if recently_declined is not None:
            raise DeclineCooldownError

        snapshot = (
            _match_snapshot(candidate, await self._hiring.match(need, candidate)) if need else None
        )
        invitation = Invitation(
            company_id=member.company_id,
            candidate_user_id=profile.user_id,
            sent_by_id=member.user_id,
            need_id=data.need_id,
            title=data.title,
            description=data.description,
            salary_from_rub=data.salary_from_rub,
            salary_to_rub=data.salary_to_rub,
            contact=data.contact,
            match_snapshot=snapshot,
            case_task=data.case_task or None,
            status=InvitationStatus.SENT,
            expires_at=datetime.now(UTC) + INVITATION_TTL,
        )
        self._session.add(invitation)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Уникальный индекс: у компании уже есть ожидающее приглашение этому кандидату.
            raise InvitationAlreadyPendingError from exc
        # После коммита: сбой почты не отменяет уже отправленное приглашение.
        await self._notify_candidate(invitation)
        return EmployerInvitation(
            invitation,
            profile.candidate_number,
            await self._contacts_shared(member.company_id, profile.user_id),
        )

    async def list_for_company(self, member: CompanyMember) -> list[EmployerInvitation]:
        """Приглашения и отклики компании. Открыв список, компания просмотрела новые отклики."""
        await self._expire_overdue()
        await self._session.execute(
            update(Invitation)
            .where(
                Invitation.company_id == member.company_id,
                Invitation.direction == InvitationDirection.CANDIDATE,
                Invitation.status == InvitationStatus.SENT,
            )
            .values(status=InvitationStatus.VIEWED, viewed_at=datetime.now(UTC))
        )
        await self._session.commit()
        rows = await self._session.execute(
            select(
                Invitation,
                CandidateProfile.candidate_number,
                and_(ContactReveal.granted_at.is_not(None), ContactReveal.revoked_at.is_(None)),
            )
            .join(CandidateProfile, CandidateProfile.user_id == Invitation.candidate_user_id)
            .outerjoin(
                ContactReveal,
                and_(
                    ContactReveal.company_id == Invitation.company_id,
                    ContactReveal.candidate_user_id == Invitation.candidate_user_id,
                ),
            )
            .where(Invitation.company_id == member.company_id)
            .order_by(Invitation.created_at.desc())
        )
        return [
            EmployerInvitation(invitation, number, shared) for invitation, number, shared in rows
        ]

    async def withdraw(self, member: CompanyMember, invitation_id: uuid.UUID) -> None:
        await self._expire_overdue()
        # FOR UPDATE: одновременные отзыв и принятие выполнятся по очереди, и второй увидит
        # уже не ожидающее приглашение (иначе отзыв затёр бы принятие с раскрытыми контактами).
        invitation = await self._session.scalar(
            select(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.company_id == member.company_id,
                Invitation.direction == InvitationDirection.EMPLOYER,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.status not in PENDING_STATUSES:
            raise InvitationNotPendingError
        invitation.status = InvitationStatus.WITHDRAWN
        invitation.answered_at = datetime.now(UTC)
        await self._session.commit()

    async def answer_application(
        self,
        member: CompanyMember,
        invitation_id: uuid.UUID,
        *,
        accept: bool,
        reason: DeclineReason | None = None,
    ) -> None:
        """Ответ компании на отклик: пригласить к разговору (открывается переписка) или отказ."""
        await self._expire_overdue()
        invitation = await self._session.scalar(
            select(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.company_id == member.company_id,
                Invitation.direction == InvitationDirection.CANDIDATE,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.status not in PENDING_STATUSES:
            raise InvitationNotPendingError
        invitation.status = InvitationStatus.ACCEPTED if accept else InvitationStatus.DECLINED
        invitation.decline_reason = None if accept else (reason or DeclineReason.OTHER)
        invitation.answered_at = datetime.now(UTC)
        invitation.sent_by_id = member.user_id
        await self._session.commit()
        await self._notify_applicant(invitation, accepted=accept)

    # --- Кандидат ---

    async def apply(self, user: User, need_id: uuid.UUID) -> Invitation:
        """Отклик на вакансию. Контакты раскрываются компании сразу: кандидат сам вышел
        на контакт (ТЗ §2.2)."""
        await self._expire_overdue()
        try:
            candidate = await self._hiring.own_candidate(user, published=True)
        except CandidateNotFoundError as exc:
            raise ProfileNotPublishedError from exc
        need = await self._hiring.published_need(user, need_id)
        owner_id = await self._session.scalar(
            select(CompanyMember.user_id).where(
                CompanyMember.company_id == need.company_id,
                CompanyMember.role == CompanyRole.OWNER,
            )
        )
        if await self._sandbox_reaches_real_user(user.id, owner_id):
            raise VacancyNotFoundError
        now = datetime.now(UTC)
        block = application_block(
            confirmed_level=confirmed_level(candidate),
            vacancy_level=need.grade.level,
            applied_this_week=await self.applied_this_week(user),
        )
        if block is not None:
            raise block
        already = await self._session.scalar(
            select(Invitation.id)
            .where(
                Invitation.candidate_user_id == user.id,
                Invitation.need_id == need.id,
                Invitation.direction == InvitationDirection.CANDIDATE,
                Invitation.status.not_in((InvitationStatus.WITHDRAWN, InvitationStatus.EXPIRED)),
            )
            .limit(1)
        )
        if already is not None:
            raise AlreadyAppliedError

        company = need.company
        invitation = Invitation(
            direction=InvitationDirection.CANDIDATE,
            company_id=need.company_id,
            candidate_user_id=user.id,
            need_id=need.id,
            title=need.title,
            description=need.description or need.title,
            salary_from_rub=need.salary_from_rub,
            salary_to_rub=need.salary_to_rub,
            contact=company.contact_email or company.contact_phone or "переписка на платформе",
            match_snapshot=_match_snapshot(candidate, await self._hiring.match(need, candidate)),
            status=InvitationStatus.SENT,
            expires_at=now + INVITATION_TTL,
        )
        self._session.add(invitation)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # Уникальный индекс: с этой компанией уже есть ожидающее приглашение или отклик.
            raise ApplicationAlreadyPendingError from exc
        await self._grant_reveal(invitation, now)
        await self._session.commit()
        await self._notify_need_owner(invitation, need.created_by_id)
        return invitation

    async def withdraw_application(self, user: User, invitation_id: uuid.UUID) -> None:
        await self._expire_overdue()
        invitation = await self._session.scalar(
            select(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.CANDIDATE,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.status not in PENDING_STATUSES:
            raise InvitationNotPendingError
        invitation.status = InvitationStatus.WITHDRAWN
        invitation.answered_at = datetime.now(UTC)
        # Контакты открыл сам отклик: отзывая его, кандидат закрывает и их. Доступ, открытый
        # позже принятым приглашением этой компании, указывает на другое приглашение и остаётся.
        reveal = await self._session.get(ContactReveal, (invitation.company_id, user.id))
        if reveal is not None and reveal.invitation_id == invitation.id:
            reveal.revoked_at = reveal.revoked_at or invitation.answered_at
        await self._session.commit()

    async def application_statuses(
        self, user: User, need_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, InvitationStatus]:
        """Статус последнего отклика кандидата по каждой вакансии: для ленты."""
        await self._expire_overdue()
        rows = await self._session.execute(
            select(Invitation.need_id, Invitation.status)
            .where(
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.CANDIDATE,
                Invitation.need_id.in_(need_ids),
            )
            .order_by(Invitation.created_at)
        )
        return {need_id: status for need_id, status in rows if need_id is not None}

    async def vacancy_feed(self, user: User) -> list[VacancyItem]:
        """Лента вакансий с совпадением, статусом отклика и причиной, если откликнуться нельзя
        (то же правило, что проверяет `apply`)."""
        vacancies = await self._hiring.vacancies(user)
        statuses = await self.application_statuses(user, [v.need.id for v in vacancies])
        level = confirmed_level(await self._hiring.own_candidate(user, published=False))
        applied = await self.applied_this_week(user)
        return [
            VacancyItem(
                vacancy,
                statuses.get(vacancy.need.id),
                application_block(
                    confirmed_level=level,
                    vacancy_level=vacancy.need.grade.level,
                    applied_this_week=applied,
                ),
            )
            for vacancy in vacancies
        ]

    async def applied_this_week(self, user: User) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.CANDIDATE,
                Invitation.created_at > datetime.now(UTC) - APPLICATIONS_WINDOW,
            )
        )
        return count or 0

    async def list_for_candidate(self, user: User) -> Sequence[Invitation]:
        """Входящие приглашения. Открыв список, кандидат их просмотрел: SENT → VIEWED."""
        await self._expire_overdue()
        now = datetime.now(UTC)
        await self._session.execute(
            update(Invitation)
            .where(
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.EMPLOYER,
                Invitation.status == InvitationStatus.SENT,
            )
            .values(status=InvitationStatus.VIEWED, viewed_at=now)
        )
        await self._session.commit()
        result = await self._session.scalars(
            select(Invitation)
            .options(joinedload(Invitation.company))
            .where(Invitation.candidate_user_id == user.id)
            .order_by(Invitation.created_at.desc())
        )
        return result.all()

    async def accept(self, user: User, invitation_id: uuid.UUID, case_answer: str = "") -> None:
        """Принять приглашение; решение кейса, если он есть, приходит вместе с принятием."""
        invitation = await self._pending_for_candidate(user, invitation_id)
        now = datetime.now(UTC)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.answered_at = now
        if invitation.case_task and case_answer:
            invitation.case_answer = case_answer
        await self._grant_reveal(invitation, now)
        await self._session.commit()
        await self._notify_employer(
            invitation,
            "принял приглашение",
            "Его контакты и переписка открыты в кабинете."
            + (" Он приложил решение кейса." if invitation.case_answer else ""),
        )

    async def decline(self, user: User, invitation_id: uuid.UUID, reason: DeclineReason) -> None:
        invitation = await self._pending_for_candidate(user, invitation_id)
        invitation.status = InvitationStatus.DECLINED
        invitation.decline_reason = reason
        invitation.answered_at = datetime.now(UTC)
        await self._session.commit()
        await self._notify_employer(
            invitation,
            "отклонил приглашение",
            f"Причина: {DECLINE_REASON_TITLES[reason]}. Пригласить его снова можно "
            f"через {DECLINE_COOLDOWN.days} дней.",
        )

    async def counter(self, user: User, invitation_id: uuid.UUID, salary_rub: int) -> None:
        """Встречное предложение вместо отказа: «готов при вилке от X». Контакты не раскрываются,
        приглашение остаётся ждать ответа; компания может поднять вилку."""
        invitation = await self._pending_for_candidate(user, invitation_id)
        block = counter_block(
            salary_to_rub=invitation.salary_to_rub,
            counter_rub=salary_rub,
            already_sent=invitation.counter_salary_rub is not None,
        )
        if block is not None:
            raise block
        invitation.counter_salary_rub = salary_rub
        await self._session.commit()
        await self._notify_employer(
            invitation,
            "готов рассмотреть",
            f"Он готов при вилке от {_format_rub(salary_rub)} до НДФЛ. Поднимите вилку "
            "в кабинете (приглашение вернётся кандидату) или отзовите его.",
        )

    async def raise_to_counter(self, member: CompanyMember, invitation_id: uuid.UUID) -> None:
        """Компания принимает встречное предложение: вилка поднимается до суммы кандидата,
        приглашение снова ждёт его ответа и действует ещё INVITATION_TTL."""
        await self._expire_overdue()
        invitation = await self._session.scalar(
            select(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.company_id == member.company_id,
                Invitation.direction == InvitationDirection.EMPLOYER,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.status not in PENDING_STATUSES:
            raise InvitationNotPendingError
        # Поднятая вилка: то же новое приглашение с письмом кандидату, замороженной нельзя.
        company = await self._session.get_one(Company, member.company_id)
        if company.frozen_at is not None:
            raise CompanyFrozenError
        counter = invitation.counter_salary_rub
        if counter is None:
            raise NoCounterOfferError
        invitation.salary_from_rub = max(invitation.salary_from_rub, counter)
        invitation.salary_to_rub = max(invitation.salary_to_rub, counter)
        invitation.counter_salary_rub = None
        invitation.status = InvitationStatus.SENT
        invitation.expires_at = datetime.now(UTC) + INVITATION_TTL
        await self._session.commit()
        await self._notify_candidate(invitation)

    async def revoke_contacts(self, user: User, company_id: uuid.UUID) -> None:
        """Кандидат забирает у компании доступ к своим контактам."""
        reveal = await self._session.get(ContactReveal, (company_id, user.id))
        if reveal is not None and reveal.revoked_at is None:
            reveal.revoked_at = datetime.now(UTC)
            await self._session.commit()

    async def reputations(
        self, company_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, CompanyReputation]:
        """Репутация компаний по их приглашениям: двумя запросами на весь список."""
        if not company_ids:
            return {}
        counts = await self._session.execute(
            select(
                Invitation.company_id,
                func.count(),
                func.count().filter(Invitation.status == InvitationStatus.WITHDRAWN),
            )
            .where(
                Invitation.company_id.in_(company_ids),
                # Репутация: по приглашениям компании; отклики отзывает кандидат, а не она.
                Invitation.direction == InvitationDirection.EMPLOYER,
                Invitation.status.not_in(PENDING_STATUSES),
            )
            .group_by(Invitation.company_id)
        )
        # Первое сообщение компании: в переписке пишут только кандидат и сотрудники компании.
        first_reply = (
            select(func.min(InvitationMessage.created_at))
            .where(
                InvitationMessage.invitation_id == Invitation.id,
                InvitationMessage.author_id != Invitation.candidate_user_id,
            )
            .scalar_subquery()
        )
        accepted = await self._session.execute(
            select(Invitation.company_id, Invitation.answered_at, first_reply).where(
                Invitation.company_id.in_(company_ids),
                Invitation.direction == InvitationDirection.EMPLOYER,
                Invitation.status == InvitationStatus.ACCEPTED,
                Invitation.answered_at.is_not(None),
            )
        )
        replies: defaultdict[uuid.UUID, list[tuple[datetime, datetime | None]]] = defaultdict(list)
        for company_id, answered_at, reply in accepted:
            if answered_at is not None:
                replies[company_id].append((answered_at, reply))
        now = datetime.now(UTC)
        result = {}
        for company_id, finished, withdrawn in counts:
            reputation = company_reputation(finished, withdrawn, replies[company_id], now)
            if reputation is not None:
                result[company_id] = reputation
        return result

    async def revealed_company_ids(self, user: User) -> set[uuid.UUID]:
        result = await self._session.scalars(
            select(ContactReveal.company_id).where(
                ContactReveal.candidate_user_id == user.id, ContactReveal.revoked_at.is_(None)
            )
        )
        return set(result)

    async def _pending_for_candidate(self, user: User, invitation_id: uuid.UUID) -> Invitation:
        await self._expire_overdue()
        invitation = await self._session.scalar(
            select(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.candidate_user_id == user.id,
                # На свой отклик кандидат не отвечает: его можно только отозвать.
                Invitation.direction == InvitationDirection.EMPLOYER,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.status not in PENDING_STATUSES:
            raise InvitationNotPendingError
        return invitation

    async def _grant_reveal(self, invitation: Invitation, now: datetime) -> None:
        """Открыть компании контакты кандидата (или вернуть доступ после отзыва)."""
        reveal = await self._session.get(
            ContactReveal,
            (invitation.company_id, invitation.candidate_user_id),
            with_for_update=True,
        )
        if reveal is None:
            self._session.add(
                ContactReveal(
                    company_id=invitation.company_id,
                    candidate_user_id=invitation.candidate_user_id,
                    invitation_id=invitation.id,
                    granted_at=now,
                )
            )
        else:
            reveal.invitation_id = invitation.id
            reveal.granted_at = now
            reveal.revoked_at = None

    # --- Переписка (обе стороны) ---

    async def list_messages(
        self, user: User, invitation_id: uuid.UUID
    ) -> tuple[Invitation, Sequence[InvitationMessage]]:
        """Переписка (последние MESSAGES_LIMIT). Открыв её, сторона прочитала всё."""
        invitation = await self._chat_invitation(user, invitation_id)
        result = await self._session.scalars(
            select(InvitationMessage)
            .where(InvitationMessage.invitation_id == invitation.id)
            .order_by(InvitationMessage.id.desc())
            .limit(MESSAGES_LIMIT)
        )
        messages = list(reversed(result.all()))
        if messages:
            self._mark_read(invitation, user, messages[-1].id)
            await self._session.commit()
        return invitation, messages

    async def post_message(self, user: User, invitation_id: uuid.UUID, body: str) -> None:
        invitation = await self._chat_invitation(user, invitation_id)
        # Переписка тоже способ связи: после отзыва контактов писать нельзя обеим сторонам,
        # история остаётся. Снова откроет её только принятие нового приглашения компании.
        if not await self._contacts_shared(invitation.company_id, invitation.candidate_user_id):
            raise ChatClosedError
        message = InvitationMessage(invitation_id=invitation.id, author_id=user.id, body=body)
        self._session.add(message)
        await self._session.flush()
        # Отвечая, сторона прочитала всё, что было до её сообщения.
        self._mark_read(invitation, user, message.id)
        await self._session.commit()

    @staticmethod
    def _mark_read(invitation: Invitation, user: User, message_id: int) -> None:
        if user.role == UserRole.CANDIDATE:
            invitation.candidate_read_message_id = max(
                invitation.candidate_read_message_id or 0, message_id
            )
        else:
            invitation.company_read_message_id = max(
                invitation.company_read_message_id or 0, message_id
            )

    async def chats(self, user: User) -> list[Chat]:
        """Переписки стороны пользователя, сначала свежие. Два запроса на весь список."""
        is_candidate = user.role == UserRole.CANDIDATE
        if is_candidate:
            scope = Invitation.candidate_user_id == user.id
            read_mark = Invitation.candidate_read_message_id
            from_other_side = InvitationMessage.author_id.is_distinct_from(
                Invitation.candidate_user_id
            )
        else:
            company_id = await self._company_id(user)
            if company_id is None:
                return []
            scope = Invitation.company_id == company_id
            read_mark = Invitation.company_read_message_id
            from_other_side = InvitationMessage.author_id == Invitation.candidate_user_id
        last_id = (
            select(func.max(InvitationMessage.id))
            .where(InvitationMessage.invitation_id == Invitation.id)
            .scalar_subquery()
        )
        unread = (
            select(func.count())
            .where(
                InvitationMessage.invitation_id == Invitation.id,
                InvitationMessage.id > func.coalesce(read_mark, 0),
                from_other_side,
            )
            .scalar_subquery()
        )
        rows = (
            await self._session.execute(
                select(
                    Invitation,
                    CandidateProfile.candidate_number,
                    CandidateProfile.last_name,
                    CandidateProfile.first_name,
                    and_(
                        ContactReveal.granted_at.is_not(None), ContactReveal.revoked_at.is_(None)
                    ),
                    last_id,
                    unread,
                )
                .options(joinedload(Invitation.company))
                .join(CandidateProfile, CandidateProfile.user_id == Invitation.candidate_user_id)
                .outerjoin(
                    ContactReveal,
                    and_(
                        ContactReveal.company_id == Invitation.company_id,
                        ContactReveal.candidate_user_id == Invitation.candidate_user_id,
                    ),
                )
                .where(scope, Invitation.status == InvitationStatus.ACCEPTED)
            )
        ).all()
        message_ids = [row[5] for row in rows if row[5] is not None]
        last_messages = {
            m.id: m
            for m in await self._session.scalars(
                select(InvitationMessage).where(InvitationMessage.id.in_(message_ids))
            )
        }
        chats = [
            Chat(
                invitation=invitation,
                candidate_number=number,
                candidate_name=(
                    f"{last_name} {first_name}" if shared and not is_candidate else None
                ),
                contacts_shared=bool(shared),
                last_message=last_messages.get(last) if last is not None else None,
                unread=count,
            )
            for invitation, number, last_name, first_name, shared, last, count in rows
        ]
        return sorted(chats, key=_chat_activity, reverse=True)

    async def notifications(self, user: User) -> Notifications:
        """Счётчики для шапки: то, что ждёт действия пользователя. Только чтение: опрашивается
        часто, поэтому просроченные приглашения отсекаются условием, а не UPDATE."""
        chats = await self.chats(user)
        waiting = and_(
            Invitation.status.in_(PENDING_STATUSES), Invitation.expires_at > datetime.now(UTC)
        )
        if user.role == UserRole.CANDIDATE:
            to_answer = and_(
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.EMPLOYER,
                # Встречное предложение отправлено: ход за компанией.
                Invitation.counter_salary_rub.is_(None),
            )
        else:
            company_id = await self._company_id(user)
            to_answer = and_(
                Invitation.company_id == company_id,
                (Invitation.direction == InvitationDirection.CANDIDATE)
                | Invitation.counter_salary_rub.is_not(None),
            )
        count = await self._session.scalar(
            select(func.count()).select_from(Invitation).where(waiting, to_answer)
        )
        return Notifications(
            unread_messages=sum(chat.unread for chat in chats),
            invitations_to_answer=count or 0,
            chats_to_start=(
                0
                if user.role == UserRole.CANDIDATE
                else sum(1 for c in chats if c.last_message is None and c.contacts_shared)
            ),
        )

    async def _company_id(self, user: User) -> uuid.UUID | None:
        return await self._session.scalar(
            select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
        )

    async def _chat_invitation(self, user: User, invitation_id: uuid.UUID) -> Invitation:
        """Переписка открыта кандидату и сотрудникам пригласившей компании после принятия."""
        invitation = await self._session.get(Invitation, invitation_id)
        if invitation is None:
            raise InvitationNotFoundError
        if user.role == UserRole.CANDIDATE:
            participant = invitation.candidate_user_id == user.id
        else:
            participant = await self._company_id(user) == invitation.company_id
        if not participant:
            # Чужое приглашение неотличимо от несуществующего.
            raise InvitationNotFoundError
        if invitation.status != InvitationStatus.ACCEPTED:
            raise ChatNotAvailableError
        return invitation

    async def _sandbox_reaches_real_user(
        self, sender_id: uuid.UUID, recipient_id: uuid.UUID | None
    ) -> bool:
        """Песочница жюри видит настоящих пользователей, но писать им не должна: она для них
        невидима, а новая песочница в один клик обходила бы квоты и паузы антиспама."""
        sender = await self._session.get_one(User, sender_id)
        if not sender.is_jury_demo or recipient_id is None:
            return False
        recipient = await self._session.get_one(User, recipient_id)
        return not recipient.sees_sandboxes

    async def _contacts_shared(self, company_id: uuid.UUID, candidate_user_id: uuid.UUID) -> bool:
        reveal = await self._session.get(ContactReveal, (company_id, candidate_user_id))
        return reveal is not None and reveal.revoked_at is None

    async def _notify_candidate(self, invitation: Invitation) -> None:
        candidate = await self._session.get_one(User, invitation.candidate_user_id)
        company = await self._session.get_one(Company, invitation.company_id)
        link = f"{self._settings.effective_frontend_url}{CANDIDATE_INVITATIONS_FRONTEND_PATH}"
        why = _why_you(invitation.match_snapshot)
        case = (
            "К приглашению приложен короткий кейс: ответить можно при принятии.\n"
            if invitation.case_task
            else ""
        )
        await self._mailer.send(
            to=candidate.email,
            subject=f"Приглашение от {company.name}: {invitation.title}",
            body=(
                f"Компания «{company.name}» приглашает вас на позицию «{invitation.title}».\n"
                f"Зарплата: от {_format_rub(invitation.salary_from_rub)} "
                f"до {_format_rub(invitation.salary_to_rub)} в месяц до вычета НДФЛ.\n"
                + (f"Почему вам: {why}.\n" if why else "")
                + case
                + f"\nПосмотреть приглашение и ответить: {link}\n"
                f"Приглашение действует до {invitation.expires_at:%d.%m.%Y}.\n\n"
                "Ваши контакты компания увидит, только если вы примете приглашение."
            ),
        )

    async def _notify_employer(self, invitation: Invitation, answer: str, details: str) -> None:
        """Письмо пригласившему сотруднику об ответе кандидата: иначе он узнал бы об ответе,
        только зайдя в кабинет. Контактов в письме нет: кандидат может закрыть к ним доступ,
        а копия в почте осталась бы."""
        if invitation.sent_by_id is None:
            return  # сотрудник удалён: ответ всё равно виден в кабинете компании
        sender = await self._session.get_one(User, invitation.sent_by_id)
        number = await self._session.scalar(
            select(CandidateProfile.candidate_number).where(
                CandidateProfile.user_id == invitation.candidate_user_id
            )
        )
        link = f"{self._settings.effective_frontend_url}{EMPLOYER_INVITATIONS_FRONTEND_PATH}"
        await self._mailer.send(
            to=sender.email,
            subject=f"Кандидат №{number} {answer} «{invitation.title}»",
            body=(
                f"Кандидат №{number} {answer} «{invitation.title}».\n{details}\n\n"
                f"Приглашения компании: {link}"
            ),
        )

    async def _notify_need_owner(self, invitation: Invitation, owner_id: uuid.UUID | None) -> None:
        """Письмо автору вакансии о новом отклике. Контактов в письме нет: они в кабинете."""
        if owner_id is None:
            return
        owner = await self._session.get_one(User, owner_id)
        number = await self._session.scalar(
            select(CandidateProfile.candidate_number).where(
                CandidateProfile.user_id == invitation.candidate_user_id
            )
        )
        link = f"{self._settings.effective_frontend_url}{EMPLOYER_INVITATIONS_FRONTEND_PATH}"
        await self._mailer.send(
            to=owner.email,
            subject=f"Кандидат №{number} откликнулся на «{invitation.title}»",
            body=(
                f"Кандидат №{number} откликнулся на вакансию «{invitation.title}». Его профиль "
                "и контакты уже открыты вам. Пригласите к разговору или откажите: ответ "
                f"ждём до {invitation.expires_at:%d.%m.%Y}.\n\nОтклики компании: {link}"
            ),
        )

    async def _notify_applicant(self, invitation: Invitation, *, accepted: bool) -> None:
        candidate = await self._session.get_one(User, invitation.candidate_user_id)
        company = await self._session.get_one(Company, invitation.company_id)
        link = f"{self._settings.effective_frontend_url}{CANDIDATE_INVITATIONS_FRONTEND_PATH}"
        if accepted:
            text = "приглашает вас к разговору: переписка открыта в кабинете"
        else:
            reason = DECLINE_REASON_TITLES[invitation.decline_reason or DeclineReason.OTHER]
            text = f"отклонила отклик. Причина: {reason}"
        await self._mailer.send(
            to=candidate.email,
            subject=f"Ответ на отклик «{invitation.title}»",
            body=f"Компания «{company.name}» {text}.\n\nВаши отклики: {link}",
        )

    async def _expire_overdue(self) -> None:
        await expire_overdue_invitations(self._session)


def _chat_activity(chat: Chat) -> datetime:
    """Свежесть переписки: последнее сообщение, а без сообщений момент принятия приглашения."""
    if chat.last_message is not None:
        return chat.last_message.created_at
    return chat.invitation.answered_at or chat.invitation.created_at


def _match_snapshot(candidate: PoolCandidate, match: MatchResult) -> dict[str, Any]:
    """Почему пригласили: без скрытого от кандидата и работодателя: ни ожиданий по зарплате,
    ни внутренних вкладов скора."""
    grade = candidate.grade
    return {
        "score": round(match.score, 3),
        "grade": grade.title if grade else None,
        "grade_confirmed": candidate.confirmed,
        "fsp_achievements": candidate.fsp.achievements,
        "skills": [skill.model_dump() for skill in match.skills],
    }


def _why_you(snapshot: dict[str, Any] | None) -> str:
    """«Почему вам» одной строкой для письма."""
    if not snapshot:
        return ""
    parts = [f"совпадение с потребностью {round(100 * snapshot['score'])}%"]
    verified = [s["title"] for s in snapshot["skills"] if s["status"] == "verified"]
    if verified:
        parts.append("подтверждены тестом: " + ", ".join(verified))
    if snapshot["grade"]:
        state = "подтверждён тестом" if snapshot["grade_confirmed"] else "заявлен"
        parts.append(f"грейд {snapshot['grade']} {state}")
    if snapshot["fsp_achievements"]:
        parts.append(f"достижения ФСП: {snapshot['fsp_achievements']}")
    return "; ".join(parts)


def _format_rub(amount: int) -> str:
    return f"{amount:,}".replace(",", "\u00a0") + "\u00a0₽"


InvitationServiceDep = Annotated[InvitationService, Depends()]
