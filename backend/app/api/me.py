from fastapi import APIRouter

from app.errors import error_responses
from app.schemas.users import MeRead, RoleChoice
from app.services.auth.dependencies import CURRENT_USER_ERRORS, CurrentUserDep
from app.services.users import RoleAlreadyChosenError, UserServiceDep

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", responses=error_responses(*CURRENT_USER_ERRORS))
async def get_me(user: CurrentUserDep, users: UserServiceDep) -> MeRead:
    return MeRead.from_overview(await users.get_overview(user))


@router.put("/role", responses=error_responses(*CURRENT_USER_ERRORS, RoleAlreadyChosenError))
async def choose_my_role(
    payload: RoleChoice, user: CurrentUserDep, users: UserServiceDep
) -> MeRead:
    return MeRead.from_overview(await users.choose_role(user, payload.role))
