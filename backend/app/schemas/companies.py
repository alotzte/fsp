import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.schemas.common import (
    DbInt,
    validate_optional_email,
    validate_optional_phone,
    validate_optional_url,
)
from app.schemas.dictionaries import IndustryRead
from app.services.companies import CompanyDetails, CompanyUpdate, IssuedInvite
from app.services.db.models import CompanyRole
from app.services.trust import pending_quota

CompanyName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)
]
CompanyDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class CompanyCreate(BaseModel):
    name: CompanyName
    description: CompanyDescription = ""


class CompanyUpdateInput(BaseModel):
    name: CompanyName
    description: CompanyDescription = ""
    industry_id: DbInt | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    contact_email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)] = ""
    contact_phone: Annotated[str, StringConstraints(strip_whitespace=True)] = ""

    @field_validator("website")
    @classmethod
    def _valid_website(cls, value: str) -> str:
        return validate_optional_url(value)

    @field_validator("contact_email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        return validate_optional_email(value)

    @field_validator("contact_phone")
    @classmethod
    def _valid_phone(cls, value: str) -> str:
        return validate_optional_phone(value)

    def to_update(self) -> CompanyUpdate:
        return CompanyUpdate(**self.model_dump())


class CompanyMemberRead(BaseModel):
    user_id: uuid.UUID
    email: str
    role: CompanyRole
    joined_at: datetime


class CompanyDetailsRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    industry: IndustryRead | None
    website: str
    contact_email: str
    contact_phone: str
    # Адрес меняется при замене логотипа (параметр v), поэтому его можно кэшировать.
    logo_url: str | None
    my_role: CompanyRole
    members: list[CompanyMemberRead]
    # 0: новая компания, 1: подтверждён домен; от уровня зависит квота приглашений.
    trust_level: int
    verified_domain: str
    pending_quota: int
    # Заморожена жалобами кандидатов до разбора: приглашать и публиковать вакансии нельзя.
    frozen: bool

    @classmethod
    def from_details(cls, details: CompanyDetails) -> "CompanyDetailsRead":
        company = details.company
        return cls(
            id=company.id,
            name=company.name,
            description=company.description,
            industry=IndustryRead.model_validate(company.industry) if company.industry else None,
            website=company.website,
            contact_email=company.contact_email,
            contact_phone=company.contact_phone,
            logo_url=company_logo_url(company.id, company.logo_file_id),
            my_role=details.my_role,
            trust_level=company.trust_level,
            verified_domain=company.verified_domain,
            pending_quota=pending_quota(company.trust_level),
            frozen=company.frozen_at is not None,
            members=[
                CompanyMemberRead(
                    user_id=member.user_id,
                    email=member.user.email,
                    role=member.role,
                    joined_at=member.joined_at,
                )
                for member in details.members
            ],
        )


def company_logo_url(company_id: uuid.UUID, logo_file_id: uuid.UUID | None) -> str | None:
    if logo_file_id is None:
        return None
    return f"/api/v1/companies/{company_id}/logo?v={logo_file_id}"


class CompanyInviteRead(BaseModel):
    url: str
    expires_at: datetime

    @classmethod
    def from_issued(cls, invite: IssuedInvite) -> "CompanyInviteRead":
        return cls(url=invite.url, expires_at=invite.expires_at)


class DomainCheckInput(BaseModel):
    # Адрес в домене сайта компании: на него придёт ссылка подтверждения.
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        return validate_optional_email(value)
