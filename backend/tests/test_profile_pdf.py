import io
from datetime import UTC, date, datetime

import pdfplumber

from app.api.profile_pdf import render_candidate_pdf
from app.schemas.candidates import CandidateEmployerView, EmployerExperienceRead, mask_contacts
from app.schemas.dictionaries import GradeRead, SpecializationRead
from app.schemas.fsp import FspRankRead, FspResultRead
from app.schemas.hiring import (
    CandidateCategoryRead,
    CandidateContactsRead,
    CompetencyResultRead,
    EmployerCandidateRead,
)
from app.services.db.models import FspAward, FspDiscipline, FspSportRank, WorkFormat

ABOUT = "Пишите на ivan@example.ru или +7 912 345-67-89"
CONTACTS = CandidateContactsRead(
    last_name="Иванов",
    first_name="Иван",
    middle_name="",
    email="ivan@example.ru",
    phone="+7 912 345-67-89",
    telegram="ivan_dev",
)


def _card(*, revealed: bool) -> EmployerCandidateRead:
    return EmployerCandidateRead(
        profile=CandidateEmployerView(
            candidate_number=42,
            specialization=SpecializationRead(id=1, slug="backend", title="Backend-разработка"),
            work_formats=[WorkFormat.REMOTE],
            city="Казань",
            about=ABOUT if revealed else mask_contacts(ABOUT),
            technologies=["Python", "PostgreSQL"],
            soft_skills=["Работа в команде"],
            total_experience_months=30,
            experience=[
                EmployerExperienceRead(
                    company_name="ООО «Ромашка»" if revealed else None,
                    position="Python-разработчик",
                    started_on=date(2024, 4, 1),
                    ended_on=None,
                    description="Сервисы <на> Python & SQL",
                )
            ],
            education=[],
            hidden_sections=[],
        ),
        category=CandidateCategoryRead(
            specialization=SpecializationRead(id=1, slug="backend", title="Backend-разработка"),
            grade=GradeRead(id=3, slug="middle", title="Middle", level=2),
            confirmed=True,
            confirmed_at=datetime(2026, 10, 1, tzinfo=UTC),
        ),
        test_results=[CompetencyResultRead(title="SQL", correct=3, total=4)],
        fsp_linked=True,
        fsp_results=[
            FspResultRead(
                event_title="Кубок России",
                discipline=FspDiscipline.PRODUCT,
                starts_on=date(2025, 5, 1),
                ekp_number="1101770002000101",
                award=FspAward.PRIZE,
                place=2,
                team_name="Бинарные котики" if revealed else None,
            )
        ],
        fsp_sport_rank=FspRankRead(rank=FspSportRank.CMS, assigned_on=date(2025, 12, 1)),
        recent_cases=2,
        foreign_answers=0,
        match=None,
        contacts=CONTACTS if revealed else None,
        invitations=[],
    )


def _text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_pdf_before_acceptance_has_no_personal_data() -> None:
    text = _text(render_candidate_pdf(_card(revealed=False)))
    assert "Кандидат №42" in text
    for secret in (
        "Иванов",
        "ivan@example.ru",
        "345-67-89",
        "ivan_dev",
        "Бинарные котики",
        "Ромашка",
    ):
        assert secret not in text
    assert "Middle" in text
    assert "Кубок России" in text
    assert "кандидат в мастера спорта" in text
    # Разметка reportlab экранирована: «<на>» и «&» из текста пользователя не ломают PDF.
    assert "Сервисы <на> Python & SQL" in text


def test_pdf_after_acceptance_shows_contacts_and_team() -> None:
    text = _text(render_candidate_pdf(_card(revealed=True)))
    for shown in ("Иванов Иван", "ivan@example.ru", "@ivan_dev", "Бинарные котики", "Ромашка"):
        assert shown in text
