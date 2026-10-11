from datetime import date

from app.schemas.candidates import CandidateEmployerView
from app.services.db.models import (
    CandidateProfile,
    CandidateSkill,
    Education,
    ProfileSection,
    Skill,
    SkillKind,
    WorkExperience,
)


def _profile(hidden: list[ProfileSection]) -> CandidateProfile:
    python = Skill(id=1, kind=SkillKind.TECHNOLOGY, title="Python", aliases=[])
    team = Skill(id=2, kind=SkillKind.SOFT, title="Работа в команде", aliases=[])
    return CandidateProfile(
        candidate_number=1001,
        specialization=None,
        work_formats=["remote"],
        city="Казань",
        about="Люблю распределённые системы",
        hidden_sections=[section.value for section in hidden],
        skills=[
            CandidateSkill(kind=SkillKind.TECHNOLOGY, skill=python),
            CandidateSkill(kind=SkillKind.SOFT, skill=team),
        ],
        experience=[
            WorkExperience(
                company_name="ООО «Ромашка»",
                position="Python-разработчик",
                started_on=date(2022, 1, 1),
                ended_on=None,
                description="",
            )
        ],
        education=[Education(institution="КФУ", specialty="", graduation_year=2021)],
    )


ALL = list(ProfileSection)


def test_hidden_sections_are_empty_before_reveal() -> None:
    view = CandidateEmployerView.from_profile(_profile(ALL), 30)
    assert (view.about, view.soft_skills, view.experience, view.education) == ("", [], [], [])
    assert set(view.hidden_sections) == set(ALL)
    # Навыки, город и форматы скрыть нельзя: по ним считается совместимость.
    assert view.technologies == ["Python"]
    assert view.city == "Казань"
    assert view.total_experience_months == 30


def test_hidden_sections_open_with_contacts() -> None:
    view = CandidateEmployerView.from_profile(_profile(ALL), 30, contacts_revealed=True)
    assert view.about == "Люблю распределённые системы"
    assert view.soft_skills == ["Работа в команде"]
    assert len(view.experience) == len(view.education) == 1
    assert view.hidden_sections == []


def test_nothing_hidden_by_default() -> None:
    view = CandidateEmployerView.from_profile(_profile([]), 30)
    assert view.about
    assert view.hidden_sections == []


def test_company_names_only_with_contacts() -> None:
    # До принятия по компании работодатель узнал бы человека; после: видит резюме целиком.
    hidden = CandidateEmployerView.from_profile(_profile([]), 30)
    revealed = CandidateEmployerView.from_profile(_profile([]), 30, contacts_revealed=True)
    assert hidden.experience[0].company_name is None
    assert revealed.experience[0].company_name == "ООО «Ромашка»"
