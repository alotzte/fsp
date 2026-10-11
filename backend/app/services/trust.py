"""Защита от фиктивных работодателей без модерации (ТЗ: работодателей не проверяем в MVP).

Работают три вещи: квота ожидающих приглашений по уровню доверия (новая компания не разошлёт
спам), подтверждение домена письмом (уровень 1) и жалобы кандидатов, которым компания писала:
после FREEZE_AFTER_REPORTS жалоб от разных кандидатов компания замораживается до разбора
в админке. Проверка ИНН и юрлица: концепция (docs/architecture.md §9).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SettingsDep
from app.errors import ConflictError, NotFoundError
from app.services.companies import CompanyServiceDep, NotCompanyOwnerError, website_domain
from app.services.db.models import (
    SEED_DEMO_PREFIX,
    Company,
    CompanyMember,
    CompanyReport,
    CompanyRole,
    Invitation,
    InvitationDirection,
    ReportReason,
    User,
)
from app.services.db.session import SessionDep
from app.services.mailer import MailerDep

# Сколько приглашений компании могут одновременно ждать ответа, по уровню доверия.
PENDING_QUOTAS = {0: 5, 1: 20}
FREEZE_AFTER_REPORTS = 3
DOMAIN_TOKEN_MAX_AGE = timedelta(days=1)
DOMAIN_CONFIRM_PATH = "/api/v1/companies/domain/confirm"
# Кабинет компании (frontend/src/app/router.tsx).
COMPANY_FRONTEND_PATH = "/employer/company"
_DOMAIN_SALT = "company-domain"
# Почтовые сервисы: ящик на них заводит кто угодно, поэтому их домен ничего не подтверждает
# («сайт yandex.ru» + свой ящик @yandex.ru выдавали бы бейдж «домен подтверждён»).
PUBLIC_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yandex.ru",
        "ya.ru",
        "yandex.com",
        "mail.ru",
        "bk.ru",
        "inbox.ru",
        "list.ru",
        "internet.ru",
        "rambler.ru",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "me.com",
        "yahoo.com",
        "proton.me",
        "protonmail.com",
    }
)


class WebsiteRequiredError(ConflictError):
    message = "Сначала укажите сайт компании: подтверждается адрес в его домене"


class PublicMailDomainError(ConflictError):
    message = "Домен почтового сервиса не подтверждает компанию: укажите сайт компании"


class EmailDomainMismatchError(ConflictError):
    message = "Адрес должен быть в домене сайта компании"


class ReportTargetNotFoundError(NotFoundError):
    message = "Приглашение не найдено"


class AlreadyReportedError(ConflictError):
    message = "Вы уже пожаловались на эту компанию"


class CompanyFrozenError(ConflictError):
    message = (
        "Компания временно не может приглашать: на неё пожаловались несколько кандидатов. "
        "Напишите в поддержку платформы"
    )


def pending_quota(trust_level: int) -> int:
    return PENDING_QUOTAS.get(trust_level, max(PENDING_QUOTAS.values()))


def should_freeze(distinct_reporters: int) -> bool:
    return distinct_reporters >= FREEZE_AFTER_REPORTS


async def is_shared_demo(session: AsyncSession, company_id: uuid.UUID) -> bool:
    """Общая демо-компания стенда (владелец из сида). Её не замораживают жалобы и не ограничивает
    квота приглашений: она приглашает каждую песочницу жюри, и иначе жюри сломало бы демо всем
    следующим проверяющим. Жалобы на неё всё равно записываются."""
    demo_member = await session.scalar(
        select(CompanyMember.user_id)
        .join(User, User.id == CompanyMember.user_id)
        .where(
            CompanyMember.company_id == company_id,
            User.keycloak_sub.startswith(SEED_DEMO_PREFIX),
        )
        .limit(1)
    )
    return demo_member is not None


def email_matches_website(email: str, website: str) -> bool:
    """Адрес в домене сайта или его поддомене: hr@acme.ru и hr@mail.acme.ru для acme.ru."""
    domain = website_domain(website)
    email_domain = email.rsplit("@", 1)[-1].lower()
    return domain is not None and (email_domain == domain or email_domain.endswith(f".{domain}"))


class TrustService:
    def __init__(
        self,
        session: SessionDep,
        companies: CompanyServiceDep,
        mailer: MailerDep,
        settings: SettingsDep,
    ) -> None:
        self._session = session
        self._companies = companies
        self._mailer = mailer
        self._settings = settings
        self._serializer = URLSafeTimedSerializer(
            settings.secret_key.get_secret_value(), salt=_DOMAIN_SALT
        )

    async def request_domain_check(self, user: User, email: str) -> None:
        """Письмо со ссылкой подтверждения на адрес в домене сайта компании."""
        membership = await self._companies.require_membership(user)
        if membership.role != CompanyRole.OWNER:
            raise NotCompanyOwnerError
        company = membership.company
        domain = website_domain(company.website)
        if not domain:
            raise WebsiteRequiredError
        if domain in PUBLIC_MAIL_DOMAINS:
            raise PublicMailDomainError
        if not email_matches_website(email, company.website):
            raise EmailDomainMismatchError
        token = self._serializer.dumps({"company": str(company.id), "email": email})
        link = f"{self._settings.public_url}{DOMAIN_CONFIRM_PATH}?token={token}"
        await self._mailer.send(
            to=email,
            subject=f"Подтверждение домена компании «{company.name}»",
            body=(
                f"Чтобы подтвердить, что «{company.name}» владеет доменом {email.split('@')[1]}, "
                f"откройте ссылку в течение суток:\n{link}\n\n"
                "Если вы не запрашивали подтверждение, просто удалите письмо."
            ),
        )

    async def confirm_domain(self, token: str) -> str:
        """Подтверждает домен по ссылке из письма и возвращает адрес кабинета для редиректа.
        Вход не нужен: ссылку мог открыть только владелец почтового ящика."""
        target = f"{self._settings.effective_frontend_url}{COMPANY_FRONTEND_PATH}"
        try:
            data = self._serializer.loads(token, max_age=int(DOMAIN_TOKEN_MAX_AGE.total_seconds()))
            company = await self._session.get(Company, uuid.UUID(data["company"]))
        except (BadSignature, KeyError, ValueError, TypeError):
            return f"{target}?domain=failed"
        if (
            company is None
            or not email_matches_website(data["email"], company.website)
            or website_domain(company.website) in PUBLIC_MAIL_DOMAINS
        ):
            # Сайт сменили после запроса: домен уже не тот.
            return f"{target}?domain=failed"
        company.verified_domain = str(data["email"]).rsplit("@", 1)[1].lower()
        company.trust_level = max(company.trust_level, 1)
        await self._session.commit()
        return f"{target}?domain=ok"

    async def report(self, user: User, invitation_id: uuid.UUID, reason: ReportReason) -> None:
        """Жалоба кандидата на компанию, которая ему писала."""
        invitation = await self._session.scalar(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.candidate_user_id == user.id,
                Invitation.direction == InvitationDirection.EMPLOYER,
            )
        )
        if invitation is None:
            raise ReportTargetNotFoundError
        # Строку компании блокируем до вставки жалобы: внешний ключ жалобы берёт на неё KEY SHARE,
        # и две одновременные жалобы, ждущие FOR UPDATE после вставки, давали deadlock. Заодно
        # жалобщики считаются по очереди, и третья жалоба не пропустит заморозку.
        company = await self._session.get_one(Company, invitation.company_id, with_for_update=True)
        self._session.add(
            CompanyReport(
                company_id=invitation.company_id,
                candidate_user_id=user.id,
                invitation_id=invitation.id,
                reason=reason,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise AlreadyReportedError from exc
        reporters = await self._session.scalar(
            select(func.count(func.distinct(CompanyReport.candidate_user_id))).where(
                CompanyReport.company_id == invitation.company_id
            )
        )
        if (
            should_freeze(reporters or 0)
            and company.frozen_at is None
            and not await is_shared_demo(self._session, company.id)
        ):
            company.frozen_at = datetime.now(UTC)
        await self._session.commit()

    async def reported_company_ids(self, user: User) -> set[uuid.UUID]:
        result = await self._session.scalars(
            select(CompanyReport.company_id).where(CompanyReport.candidate_user_id == user.id)
        )
        return set(result)


TrustServiceDep = Annotated[TrustService, Depends()]
