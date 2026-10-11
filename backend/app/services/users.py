from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.errors import ConflictError
from app.services.db.models import CompanyMember, User, UserRole
from app.services.db.session import SessionDep


class RoleAlreadyChosenError(ConflictError):
    message = "Роль уже выбрана"


@dataclass(frozen=True)
class UserOverview:
    user: User
    membership: CompanyMember | None


class UserService:
    def __init__(self, session: SessionDep) -> None:
        self._session = session

    async def get_overview(self, user: User) -> UserOverview:
        membership = await self._session.scalar(
            select(CompanyMember)
            .options(joinedload(CompanyMember.company))
            .where(CompanyMember.user_id == user.id)
        )
        return UserOverview(user=user, membership=membership)

    async def choose_role(self, user: User, role: UserRole) -> UserOverview:
        # Роль выбирается один раз: от неё зависят права и все связанные данные.
        if user.role is not None:
            raise RoleAlreadyChosenError
        user.role = role
        await self._session.commit()
        return await self.get_overview(user)


UserServiceDep = Annotated[UserService, Depends()]
