from dataclasses import replace

from fastapi import APIRouter, Response, UploadFile

from app.api.profile_pdf import pdf_response, render_candidate_pdf
from app.errors import error_responses
from app.schemas.candidates import (
    CandidateProfileInput,
    CandidateProfileRead,
    ConsentStateRead,
    PrivacyInput,
    ResumeDraftRead,
)
from app.schemas.hiring import EmployerCandidateRead
from app.services.auth.dependencies import ROLE_ERRORS, CandidateUserDep
from app.services.candidates import CandidateProfileNotFoundError, CandidateProfileServiceDep
from app.services.consents import ConsentRequiredError, ConsentServiceDep
from app.services.db.models import ConsentKind
from app.services.dictionaries import UnknownSkillError, UnknownSpecializationError
from app.services.hiring import CandidateNotFoundError, HiringServiceDep
from app.services.resume import (
    RESUME_MAX_BYTES,
    ResumeNotPdfError,
    ResumeServiceDep,
    ResumeTooLargeError,
    ResumeUnreadableError,
)

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.get("/profile", responses=error_responses(*ROLE_ERRORS))
async def get_my_candidate_profile(
    user: CandidateUserDep, profiles: CandidateProfileServiceDep
) -> CandidateProfileRead:
    return CandidateProfileRead.from_overview(await profiles.get_overview(user))


@router.put(
    "/profile",
    responses=error_responses(
        *ROLE_ERRORS, UnknownSkillError, UnknownSpecializationError, ConsentRequiredError
    ),
)
async def save_my_candidate_profile(
    payload: CandidateProfileInput, user: CandidateUserDep, profiles: CandidateProfileServiceDep
) -> CandidateProfileRead:
    """Сохраняет профиль целиком. Требует действующего согласия на обработку данных."""
    return CandidateProfileRead.from_overview(await profiles.save(user, payload))


@router.put(
    "/profile/privacy", responses=error_responses(*ROLE_ERRORS, CandidateProfileNotFoundError)
)
async def save_my_profile_privacy(
    payload: PrivacyInput, user: CandidateUserDep, profiles: CandidateProfileServiceDep
) -> CandidateProfileRead:
    """Разделы, скрытые от работодателя до принятия приглашения. Город, форматы и навыки скрыть
    нельзя: по ним считается совместимость в подборе."""
    return CandidateProfileRead.from_overview(
        await profiles.set_hidden_sections(user, payload.hidden_sections)
    )


@router.get(
    "/profile/employer-view",
    responses=error_responses(*ROLE_ERRORS, CandidateNotFoundError),
)
async def get_my_employer_view(
    user: CandidateUserDep, hiring: HiringServiceDep
) -> EmployerCandidateRead:
    """Предпросмотр: карточка в том виде, в каком её видит работодатель до принятия приглашения:
    та же, что у него, но без контактов (категория, итоги теста и ФСП тоже видны ему сразу)."""
    details = await hiring.own_details(user)
    return EmployerCandidateRead.from_details(replace(details, contacts=None))


@router.get(
    "/profile/pdf",
    response_class=Response,
    responses={
        **error_responses(*ROLE_ERRORS, CandidateNotFoundError),
        200: {"content": {"application/pdf": {}}},
    },
)
async def download_my_profile_pdf(user: CandidateUserDep, hiring: HiringServiceDep) -> Response:
    """Стандартизированный PDF-профиль: категория, итоги теста, навыки, ФСП, опыт, с ФИО и
    контактами, как его видит работодатель после принятия приглашения."""
    card = EmployerCandidateRead.from_details(await hiring.own_details(user))
    return pdf_response(
        render_candidate_pdf(card), f"candidate-{card.profile.candidate_number}.pdf"
    )


@router.post(
    "/profile/resume",
    responses=error_responses(
        *ROLE_ERRORS, ResumeTooLargeError, ResumeNotPdfError, ResumeUnreadableError
    ),
)
async def parse_my_resume(
    file: UploadFile, _user: CandidateUserDep, resumes: ResumeServiceDep
) -> ResumeDraftRead:
    """Распознаёт PDF-резюме (до 5 МБ, первые 5 страниц) и возвращает черновик полей профиля.

    Ничего не сохраняет. Скан без текстового слоя: 422, не PDF: 415, больше 5 МБ: 413.
    """
    # На байт больше лимита: отличаем слишком большой файл, не читая его целиком.
    content = await file.read(RESUME_MAX_BYTES + 1)
    return ResumeDraftRead.from_draft(await resumes.parse(content))


@router.post("/consents/{kind}", responses=error_responses(*ROLE_ERRORS, ConsentRequiredError))
async def grant_consent(
    kind: ConsentKind, user: CandidateUserDep, consents: ConsentServiceDep
) -> list[ConsentStateRead]:
    return [ConsentStateRead.from_state(state) for state in await consents.grant(user, kind)]


@router.delete("/consents/{kind}", responses=error_responses(*ROLE_ERRORS))
async def revoke_consent(
    kind: ConsentKind, user: CandidateUserDep, consents: ConsentServiceDep
) -> list[ConsentStateRead]:
    """Отзыв согласия. Отзыв согласия на обработку данных удаляет профиль кандидата."""
    return [ConsentStateRead.from_state(state) for state in await consents.revoke(user, kind)]
