import uuid

from pydantic import BaseModel

from app.services.db.models import CompanyRole, UserRole
from app.services.users import UserOverview


class MyCompanyRead(BaseModel):
    id: uuid.UUID
    name: str
    my_role: CompanyRole


class MeRead(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole | None
    company: MyCompanyRead | None
    # Песочница жюри: доступен экспресс-тест, данные удаляются через сутки.
    is_demo: bool

    @classmethod
    def from_overview(cls, overview: UserOverview) -> "MeRead":
        membership = overview.membership
        company = (
            MyCompanyRead(
                id=membership.company.id,
                name=membership.company.name,
                my_role=membership.role,
            )
            if membership is not None
            else None
        )
        user = overview.user
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            company=company,
            is_demo=user.is_jury_demo,
        )


class RoleChoice(BaseModel):
    role: UserRole
