import uuid

from fastapi import APIRouter, Response, UploadFile, status
from fastapi.responses import RedirectResponse

from app.api.auth import BROWSER_REDIRECT_TAG
from app.errors import error_responses
from app.schemas.companies import (
    CompanyCreate,
    CompanyDetailsRead,
    CompanyInviteRead,
    CompanyUpdateInput,
    DomainCheckInput,
)
from app.services.auth.dependencies import (
    CURRENT_USER_ERRORS,
    ROLE_ERRORS,
    CurrentUserDep,
    EmployerUserDep,
)
from app.services.companies import (
    LOGO_MAX_BYTES,
    AlreadyInCompanyError,
    CandidateCannotJoinCompanyError,
    CompanyLogoNotFoundError,
    CompanyServiceDep,
    InviteAlreadyUsedError,
    InviteExpiredError,
    InviteNotFoundError,
    LogoTooLargeError,
    NotCompanyOwnerError,
    NotInCompanyError,
    SandboxCompanyInviteError,
    UnsupportedLogoFormatError,
)
from app.services.dictionaries import UnknownIndustryError
from app.services.trust import (
    EmailDomainMismatchError,
    PublicMailDomainError,
    TrustServiceDep,
    WebsiteRequiredError,
)

# Логотип адресуется с ?v=<id файла>, поэтому один адрес: всегда один и тот же файл.
LOGO_CACHE_SECONDS = 24 * 60 * 60

router = APIRouter(tags=["companies"])


@router.post(
    "/companies",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(*ROLE_ERRORS, AlreadyInCompanyError),
)
async def create_company(
    payload: CompanyCreate, user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyDetailsRead:
    details = await companies.create_company(
        user, name=payload.name, description=payload.description
    )
    return CompanyDetailsRead.from_details(details)


@router.get("/companies/my", responses=error_responses(*ROLE_ERRORS, NotInCompanyError))
async def get_my_company(
    user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyDetailsRead:
    return CompanyDetailsRead.from_details(await companies.get_details(user))


@router.put(
    "/companies/my",
    responses=error_responses(
        *ROLE_ERRORS, NotInCompanyError, NotCompanyOwnerError, UnknownIndustryError
    ),
)
async def update_my_company(
    payload: CompanyUpdateInput, user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyDetailsRead:
    """Профиль компании. Менять его может только владелец."""
    return CompanyDetailsRead.from_details(
        await companies.update_company(user, payload.to_update())
    )


@router.put(
    "/companies/my/logo",
    responses=error_responses(
        *ROLE_ERRORS,
        NotInCompanyError,
        NotCompanyOwnerError,
        LogoTooLargeError,
        UnsupportedLogoFormatError,
    ),
)
async def upload_my_company_logo(
    file: UploadFile, user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyDetailsRead:
    """PNG, JPEG или WebP до 2 МБ. Формат проверяется по содержимому файла."""
    # Читаем на байт больше лимита: этого хватает, чтобы отличить слишком большой файл,
    # не загружая его в память целиком.
    content = await file.read(LOGO_MAX_BYTES + 1)
    return CompanyDetailsRead.from_details(await companies.set_logo(user, content))


@router.get(
    "/companies/{company_id}/logo",
    response_class=Response,
    responses={
        **error_responses(*CURRENT_USER_ERRORS, CompanyLogoNotFoundError),
        200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}},
    },
)
async def get_company_logo(
    company_id: uuid.UUID, _user: CurrentUserDep, companies: CompanyServiceDep
) -> Response:
    logo, content = await companies.get_logo(company_id)
    return Response(
        content=content,
        media_type=logo.content_type,
        headers={
            "Cache-Control": f"private, max-age={LOGO_CACHE_SECONDS}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/companies/my/invites",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(*ROLE_ERRORS, NotInCompanyError, NotCompanyOwnerError),
)
async def create_company_invite(
    user: EmployerUserDep, companies: CompanyServiceDep
) -> CompanyInviteRead:
    return CompanyInviteRead.from_issued(await companies.issue_invite(user))


@router.post(
    "/company-invites/{token}/accept",
    responses=error_responses(
        *CURRENT_USER_ERRORS,
        InviteNotFoundError,
        InviteExpiredError,
        InviteAlreadyUsedError,
        AlreadyInCompanyError,
        CandidateCannotJoinCompanyError,
        SandboxCompanyInviteError,
    ),
)
async def accept_company_invite(
    token: str, user: CurrentUserDep, companies: CompanyServiceDep
) -> CompanyDetailsRead:
    # CurrentUserDep, а не EmployerUserDep: по ссылке приходят и пользователи без роли.
    return CompanyDetailsRead.from_details(await companies.accept_invite(user, token))


@router.post(
    "/companies/my/domain",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        *ROLE_ERRORS,
        NotInCompanyError,
        NotCompanyOwnerError,
        WebsiteRequiredError,
        EmailDomainMismatchError,
        PublicMailDomainError,
    ),
)
async def request_domain_check(
    payload: DomainCheckInput, user: EmployerUserDep, trust: TrustServiceDep
) -> None:
    """Письмо со ссылкой подтверждения на адрес в домене сайта компании (только владелец).
    Подтверждённый домен поднимает уровень доверия и квоту приглашений."""
    await trust.request_domain_check(user, payload.email)


@router.get(
    "/companies/domain/confirm",
    response_class=RedirectResponse,
    status_code=307,
    tags=[BROWSER_REDIRECT_TAG],
)
async def confirm_domain(token: str, trust: TrustServiceDep) -> RedirectResponse:
    """Ссылка из письма: подтверждает домен и возвращает в кабинет компании."""
    return RedirectResponse(await trust.confirm_domain(token))
