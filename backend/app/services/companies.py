import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import SettingsDep
from app.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.services.auth.dependencies import ROLE_ERRORS, EmployerUserDep
from app.services.db.models import (
    Company,
    CompanyInvite,
    CompanyMember,
    CompanyRole,
    StoredFile,
    User,
    UserRole,
)
from app.services.db.session import SessionDep
from app.services.dictionaries import DictionaryServiceDep
from app.services.storage import FileStorageDep
from app.services.tokens import generate_token, hash_token

# Маршрут фронта, который принимает приглашение (frontend/src/app/router.tsx).
INVITE_FRONTEND_PATH = "/join"

LOGO_MAX_BYTES = 2 * 1024 * 1024
# Тип логотипа определяем по сигнатуре файла, а не по заголовку от клиента.
# SVG не принимаем: в нём может быть скрипт.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_WEBP_RIFF, _WEBP_MARK, _WEBP_MARK_OFFSET = b"RIFF", b"WEBP", 8


def detect_image_type(content: bytes) -> str | None:
    for signature, content_type in _IMAGE_SIGNATURES:
        if content.startswith(signature):
            return content_type
    mark_end = _WEBP_MARK_OFFSET + len(_WEBP_MARK)
    if content.startswith(_WEBP_RIFF) and content[_WEBP_MARK_OFFSET:mark_end] == _WEBP_MARK:
        return "image/webp"
    return None


class AlreadyInCompanyError(ConflictError):
    message = "Вы уже состоите в компании"


class NotInCompanyError(NotFoundError):
    message = "Вы ещё не состоите в компании"


class NotCompanyOwnerError(PermissionDeniedError):
    message = "Это может сделать только владелец компании"


class InviteNotFoundError(NotFoundError):
    message = "Ссылка-приглашение недействительна"


class InviteAlreadyUsedError(ConflictError):
    message = "Ссылка-приглашение уже использована"


class InviteExpiredError(ConflictError):
    message = "Срок действия ссылки-приглашения истёк"


class LogoTooLargeError(DomainError):
    message = "Логотип больше 2 МБ"


class UnsupportedLogoFormatError(DomainError):
    message = "Логотип должен быть в формате PNG, JPEG или WebP"


class CompanyLogoNotFoundError(NotFoundError):
    message = "У компании нет логотипа"


@dataclass(frozen=True)
class CompanyUpdate:
    name: str
    description: str
    industry_id: int | None
    website: str
    contact_email: str
    contact_phone: str


class CandidateCannotJoinCompanyError(ConflictError):
    message = "Аккаунт кандидата не может вступить в компанию"


class SandboxCompanyInviteError(ConflictError):
    message = "Это приглашение в демо-компанию жюри: она удалится через сутки вместе с участниками"


@dataclass(frozen=True)
class CompanyDetails:
    company: Company
    my_role: CompanyRole
    members: Sequence[CompanyMember]


@dataclass(frozen=True)
class IssuedInvite:
    url: str
    expires_at: datetime


class CompanyService:
    def __init__(
        self,
        session: SessionDep,
        settings: SettingsDep,
        dictionaries: DictionaryServiceDep,
        storage: FileStorageDep,
    ) -> None:
        self._session = session
        self._settings = settings
        self._dictionaries = dictionaries
        self._storage = storage

    async def create_company(self, owner: User, *, name: str, description: str) -> CompanyDetails:
        if await self._find_membership(owner.id) is not None:
            raise AlreadyInCompanyError
        company = Company(name=name, description=description)
        self._session.add(company)
        await self._session.flush()
        self._session.add(
            CompanyMember(user_id=owner.id, company_id=company.id, role=CompanyRole.OWNER)
        )
        await self._session.commit()
        return await self.get_details(owner)

    async def get_details(self, user: User) -> CompanyDetails:
        membership = await self.require_membership(user)
        members = await self._session.scalars(
            select(CompanyMember)
            .options(joinedload(CompanyMember.user))
            .where(CompanyMember.company_id == membership.company_id)
            .order_by(CompanyMember.joined_at)
        )
        return CompanyDetails(
            company=membership.company, my_role=membership.role, members=members.all()
        )

    async def update_company(self, user: User, update: CompanyUpdate) -> CompanyDetails:
        membership = await self._require_owner(user)
        if update.industry_id is not None:
            await self._dictionaries.require_industry(update.industry_id)
        company = membership.company
        company.name = update.name
        company.description = update.description
        company.industry_id = update.industry_id
        if company.verified_domain and website_domain(update.website) != website_domain(
            company.website
        ):
            # Подтверждали прежний сайт: к новому подтверждение и доверие не относятся.
            company.verified_domain = ""
            company.trust_level = 0
        company.website = update.website
        company.contact_email = update.contact_email
        company.contact_phone = update.contact_phone
        await self._session.commit()
        return await self._reload_details(user, company)

    async def set_logo(self, user: User, content: bytes) -> CompanyDetails:
        membership = await self._require_owner(user)
        if len(content) > LOGO_MAX_BYTES:
            raise LogoTooLargeError
        content_type = detect_image_type(content)
        if content_type is None:
            raise UnsupportedLogoFormatError

        company = membership.company
        previous_logo = (
            await self._session.get(StoredFile, company.logo_file_id)
            if company.logo_file_id
            else None
        )
        storage_key = await self._storage.save(content)
        logo = StoredFile(
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            uploaded_by_id=user.id,
        )
        self._session.add(logo)
        await self._session.flush()
        company.logo_file_id = logo.id
        if previous_logo is not None:
            await self._session.delete(previous_logo)
        await self._session.commit()
        # Старый файл удаляем после commit: при откате транзакции ссылка на него осталась бы.
        if previous_logo is not None:
            await self._storage.delete(previous_logo.storage_key)
        return await self._reload_details(user, company)

    async def get_logo(self, company_id: uuid.UUID) -> tuple[StoredFile, bytes]:
        company = await self._session.get(Company, company_id)
        if company is None or company.logo_file_id is None:
            raise CompanyLogoNotFoundError
        logo = await self._session.get(StoredFile, company.logo_file_id)
        if logo is None:
            raise CompanyLogoNotFoundError
        return logo, await self._storage.read(logo.storage_key)

    async def issue_invite(self, user: User) -> IssuedInvite:
        membership = await self._require_owner(user)
        token = generate_token()
        expires_at = datetime.now(UTC) + timedelta(
            hours=self._settings.company_invite_lifetime_hours
        )
        self._session.add(
            CompanyInvite(
                company_id=membership.company_id,
                token_hash=hash_token(token),
                created_by_id=user.id,
                expires_at=expires_at,
            )
        )
        await self._session.commit()
        url = f"{self._settings.effective_frontend_url}{INVITE_FRONTEND_PATH}/{token}"
        return IssuedInvite(url=url, expires_at=expires_at)

    async def accept_invite(self, user: User, token: str) -> CompanyDetails:
        # FOR UPDATE: две одновременные попытки по одной ссылке выполнятся по очереди,
        # и вторая увидит used_at.
        invite = await self._session.scalar(
            select(CompanyInvite)
            .where(CompanyInvite.token_hash == hash_token(token))
            .with_for_update()
        )
        if invite is None:
            raise InviteNotFoundError
        if invite.used_at is not None:
            raise InviteAlreadyUsedError
        now = datetime.now(UTC)
        if invite.expires_at <= now:
            raise InviteExpiredError
        if user.role == UserRole.CANDIDATE:
            raise CandidateCannotJoinCompanyError
        if await self._find_membership(user.id) is not None:
            raise AlreadyInCompanyError
        # Песочницу жюри удаляют через сутки вместе с компанией: настоящий пользователь остался бы
        # работодателем без компании.
        inviter = await self._session.get(User, invite.created_by_id)
        if inviter is not None and inviter.is_jury_demo and not user.is_jury_demo:
            raise SandboxCompanyInviteError

        # Пришедший по ссылке без роли становится рекрутером, экран выбора роли ему не нужен.
        if user.role is None:
            user.role = UserRole.EMPLOYER
        self._session.add(
            CompanyMember(
                user_id=user.id,
                company_id=invite.company_id,
                role=CompanyRole.RECRUITER,
            )
        )
        invite.used_at = now
        invite.used_by_id = user.id
        await self._session.commit()
        return await self.get_details(user)

    async def _find_membership(self, user_id: uuid.UUID) -> CompanyMember | None:
        return await self._session.scalar(
            select(CompanyMember)
            .options(joinedload(CompanyMember.company).joinedload(Company.industry))
            .where(CompanyMember.user_id == user_id)
        )

    async def _require_owner(self, user: User) -> CompanyMember:
        membership = await self.require_membership(user)
        if membership.role != CompanyRole.OWNER:
            raise NotCompanyOwnerError
        return membership

    async def _reload_details(self, user: User, company: Company) -> CompanyDetails:
        # После смены industry_id загруженное отношение industry устарело: помечаем компанию
        # устаревшей, и запрос в get_details перечитает её вместе с отраслью.
        self._session.expire(company)
        return await self.get_details(user)

    async def require_membership(self, user: User) -> CompanyMember:
        membership = await self._find_membership(user.id)
        if membership is None:
            raise NotInCompanyError
        return membership


CompanyServiceDep = Annotated[CompanyService, Depends()]


async def get_company_membership(
    user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyMember:
    """Работодатель в компании: от её имени ищут кандидатов и отправляют приглашения."""
    return await companies.require_membership(user)


CompanyMemberDep = Annotated[CompanyMember, Depends(get_company_membership)]
# Ошибки CompanyMemberDep для OpenAPI.
COMPANY_MEMBER_ERRORS = (*ROLE_ERRORS, NotInCompanyError)


def website_domain(website: str) -> str | None:
    host = (urlsplit(website).hostname or "").lower().removeprefix("www.")
    return host or None
