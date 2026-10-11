import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.schemas.common import DbInt, validate_optional_phone
from app.schemas.dictionaries import GradeRead, SpecializationRead
from app.services.db.models import ConsentKind, ProfileSection, SkillKind, WorkFormat

if TYPE_CHECKING:
    from app.services.candidates import CandidateProfileOverview
    from app.services.consents import ConsentState
    from app.services.db.models import CandidateProfile, CandidateSkill
    from app.services.resume import ResumeDraft

MAX_TECHNOLOGIES = 50
MAX_SOFT_SKILLS = 20
MAX_EXPERIENCE_ENTRIES = 30
MAX_EDUCATION_ENTRIES = 10
MAX_SALARY_RUB = 10_000_000
MIN_GRADUATION_YEAR = 1950
# Год окончания может быть в будущем: студенты указывают ожидаемый.
MAX_YEARS_TO_GRADUATION = 10

# Сообщения валидации уходят пользователю в ответе 422.
SKILL_INPUT_ERROR = "Укажите skill_id или title"
FUTURE_DATES_ERROR = "Даты работы не могут быть в будущем"
PAST_DATES_ERROR = "Даты работы: не раньше {} года"
PERIOD_ORDER_ERROR = "Окончание работы раньше начала"
TELEGRAM_ERROR = "Ник в Telegram: латиница, цифры и _, от 5 до 32 символов"
GRADUATION_YEAR_ERROR = "Год окончания: от {} до {}"

_TELEGRAM = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_TELEGRAM_PREFIX = re.compile(r"^(?:https?://)?(?:t\.me/|telegram\.me/)|^@", re.IGNORECASE)

CONTACT_PLACEHOLDER = "[контакт скрыт]"
# ponytail: эвристика для обычной записи контактов; «иван собака мейл ру» не поймает,
# список доменов неполный. Домены: только в нижнем регистре, чтобы не задеть ASP.NET.
_CONTACTS = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"  # email
    r"|(?:https?://|www\.)[^\s,;]+"  # ссылка
    r"|\b(?:[\w-]+\.)+(?:ru|рф|su|com|net|org|io|me|dev|pro|app|info|tech|site|by|kz)\b"
    r"(?:/[^\s,;]*)?"  # домен: ivan.dev, t.me/ivan, github.com/ivan
    r"|@\w{2,}"  # @ник
    r"|\b(?i:telegram|tg|телеграмм?|тг|whatsapp|ватсап|skype|скайп)\s*:\s*[^\s,;]+"  # tg: ник
    r"|\+\d[\d \u00a0()-]{8,}\d"  # телефон с кодом страны
    # Российский номер с 8 или 7: вилка «250 000-300 000» и годы «2015-2019» сюда не попадут.
    r"|\b[78][ \u00a0(-]*\d{3}[ \u00a0)-]*\d{3}[ \u00a0-]*\d{2}[ \u00a0-]*\d{2}\b"
    # Мобильный без кода: «916 123-45-67», «(916) 123-45-67», «9161234567».
    r"|(?<!\w)\(?9\d{2}\)?[ \u00a0-]*\d{3}[ \u00a0-]*\d{2}[ \u00a0-]*\d{2}(?!\d)"
)


def mask_contacts(text: str) -> str:
    """Скрывает контакты, вписанные в свободный текст профиля.

    До принятия приглашения работодатель не видит контактов кандидата (ТЗ §2.2), а «о себе»
    и описание опыта иначе позволили бы обойти это правило.
    """
    return _CONTACTS.sub(CONTACT_PLACEHOLDER, text)


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionalName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)]


def _first_of_month(value: date) -> date:
    return value.replace(day=1)


class SkillInput(BaseModel):
    """Навык из справочника (skill_id) или свой тег (title): ровно одно из двух."""

    skill_id: DbInt | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.skill_id is None) == (not self.title):
            raise ValueError(SKILL_INPUT_ERROR)
        return self


class WorkExperienceInput(BaseModel):
    company_name: ShortText
    position: ShortText
    started_on: date
    ended_on: date | None = None
    description: LongText = ""

    @field_validator("started_on", "ended_on")
    @classmethod
    def _month_precision(cls, value: date | None) -> date | None:
        return _first_of_month(value) if value is not None else None

    @model_validator(mode="after")
    def _valid_period(self) -> Self:
        this_month = _first_of_month(datetime.now(UTC).date())
        if self.started_on > this_month or (self.ended_on and self.ended_on > this_month):
            raise ValueError(FUTURE_DATES_ERROR)
        # Иначе «0001-01» давало в карточке стаж в две тысячи лет.
        if self.started_on.year < MIN_GRADUATION_YEAR:
            raise ValueError(PAST_DATES_ERROR.format(MIN_GRADUATION_YEAR))
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise ValueError(PERIOD_ORDER_ERROR)
        return self


class EducationInput(BaseModel):
    institution: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    specialty: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    graduation_year: int | None = None

    @field_validator("graduation_year")
    @classmethod
    def _plausible_year(cls, value: int | None) -> int | None:
        latest = datetime.now(UTC).year + MAX_YEARS_TO_GRADUATION
        if value is not None and not MIN_GRADUATION_YEAR <= value <= latest:
            raise ValueError(GRADUATION_YEAR_ERROR.format(MIN_GRADUATION_YEAR, latest))
        return value


class CandidateProfileInput(BaseModel):
    last_name: Name
    first_name: Name
    middle_name: OptionalName = ""
    phone: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    telegram: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    specialization_id: DbInt | None = None
    work_formats: list[WorkFormat] = []
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    salary_expectation_rub: Annotated[int, Field(gt=0, le=MAX_SALARY_RUB)] | None = None
    about: LongText = ""
    technologies: Annotated[list[SkillInput], Field(max_length=MAX_TECHNOLOGIES)] = []
    soft_skills: Annotated[list[SkillInput], Field(max_length=MAX_SOFT_SKILLS)] = []
    experience: Annotated[list[WorkExperienceInput], Field(max_length=MAX_EXPERIENCE_ENTRIES)] = []
    education: Annotated[list[EducationInput], Field(max_length=MAX_EDUCATION_ENTRIES)] = []

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, value: str) -> str:
        return validate_optional_phone(value)

    @field_validator("telegram")
    @classmethod
    def _normalize_telegram(cls, value: str) -> str:
        # Принимаем «@nick», «nick» и ссылку t.me/nick: храним просто ник.
        nick = _TELEGRAM_PREFIX.sub("", value).strip("/")
        if nick and not _TELEGRAM.match(nick):
            raise ValueError(TELEGRAM_ERROR)
        return nick

    @field_validator("work_formats")
    @classmethod
    def _unique_formats(cls, value: list[WorkFormat]) -> list[WorkFormat]:
        return list(dict.fromkeys(value))


class SkillRead(BaseModel):
    skill_id: int | None
    title: str
    is_custom: bool

    @classmethod
    def from_candidate_skill(cls, item: "CandidateSkill") -> "SkillRead":
        if item.skill is not None:
            return cls(skill_id=item.skill.id, title=item.skill.title, is_custom=False)
        return cls(skill_id=None, title=item.custom_title or "", is_custom=True)


class WorkExperienceRead(BaseModel):
    company_name: str
    position: str
    started_on: date
    ended_on: date | None
    description: str


class EducationRead(BaseModel):
    institution: str
    specialty: str
    graduation_year: int | None


class ConsentStateRead(BaseModel):
    kind: ConsentKind
    is_active: bool
    current_version: str
    granted_version: str | None
    granted_at: datetime | None

    @classmethod
    def from_state(cls, state: "ConsentState") -> "ConsentStateRead":
        granted = state.granted
        return cls(
            kind=state.kind,
            is_active=state.is_active,
            current_version=state.current_version,
            granted_version=granted.document_version if granted else None,
            granted_at=granted.granted_at if granted else None,
        )


def _skills(profile: "CandidateProfile", kind: SkillKind) -> list[SkillRead]:
    return [SkillRead.from_candidate_skill(item) for item in profile.skills if item.kind == kind]


class CandidateProfileRead(BaseModel):
    """Профиль глазами самого кандидата. Пока профиль не сохранён, exists=False,
    а ФИО подставлено из аккаунта."""

    exists: bool
    candidate_number: int | None
    last_name: str
    first_name: str
    middle_name: str
    email: str
    phone: str
    telegram: str
    specialization: SpecializationRead | None
    work_formats: list[WorkFormat]
    city: str
    salary_expectation_rub: int | None
    about: str
    technologies: list[SkillRead]
    soft_skills: list[SkillRead]
    experience: list[WorkExperienceRead]
    education: list[EducationRead]
    total_experience_months: int
    is_published: bool
    hidden_sections: list[ProfileSection]
    consents: list[ConsentStateRead]

    @classmethod
    def from_overview(cls, overview: "CandidateProfileOverview") -> "CandidateProfileRead":
        user, profile = overview.user, overview.profile
        consents = [ConsentStateRead.from_state(state) for state in overview.consents]
        if profile is None:
            return cls(
                exists=False,
                candidate_number=None,
                last_name=user.last_name,
                first_name=user.first_name,
                middle_name="",
                email=user.email,
                phone="",
                telegram="",
                specialization=None,
                work_formats=[],
                city="",
                salary_expectation_rub=None,
                about="",
                technologies=[],
                soft_skills=[],
                experience=[],
                education=[],
                total_experience_months=0,
                is_published=False,
                hidden_sections=[],
                consents=consents,
            )
        return cls(
            exists=True,
            candidate_number=profile.candidate_number,
            last_name=profile.last_name,
            first_name=profile.first_name,
            middle_name=profile.middle_name,
            email=user.email,
            phone=profile.phone,
            telegram=profile.telegram,
            specialization=(
                SpecializationRead.model_validate(profile.specialization)
                if profile.specialization
                else None
            ),
            work_formats=[WorkFormat(value) for value in profile.work_formats],
            city=profile.city,
            salary_expectation_rub=profile.salary_expectation_rub,
            about=profile.about,
            technologies=_skills(profile, SkillKind.TECHNOLOGY),
            soft_skills=_skills(profile, SkillKind.SOFT),
            experience=[
                WorkExperienceRead(
                    company_name=entry.company_name,
                    position=entry.position,
                    started_on=entry.started_on,
                    ended_on=entry.ended_on,
                    description=entry.description,
                )
                for entry in profile.experience
            ],
            education=[
                EducationRead(
                    institution=entry.institution,
                    specialty=entry.specialty,
                    graduation_year=entry.graduation_year,
                )
                for entry in profile.education
            ],
            total_experience_months=overview.total_experience_months,
            is_published=overview.is_published,
            hidden_sections=[ProfileSection(value) for value in profile.hidden_sections],
            consents=consents,
        )


class EmployerExperienceRead(BaseModel):
    """Опыт глазами работодателя. Название компании: только после раскрытия контактов:
    до этого по нему работодатель легко узнал бы человека."""

    company_name: str | None
    position: str
    started_on: date
    ended_on: date | None
    description: str


class CandidateEmployerView(BaseModel):
    """Профиль глазами работодателя.

    Единственная схема, через которую данные кандидата уходят работодателю. Пока кандидат
    не принял приглашение, нет ФИО, контактов и названий компаний (правило видимости из ТЗ),
    контакты, вписанные в свободный текст, скрыты (`mask_contacts`); с раскрытием контактов
    открываются текст, скрытые разделы и названия компаний.
    Нет и ожиданий по зарплате: это скрытый порог, по нему проверяется только совместимость
    вилки приглашения, иначе работодатель подгонял бы вилку под минимум кандидата.
    """

    candidate_number: int
    specialization: SpecializationRead | None
    work_formats: list[WorkFormat]
    city: str
    about: str
    technologies: list[str]
    soft_skills: list[str]
    total_experience_months: int
    experience: list[EmployerExperienceRead]
    education: list[EducationRead]
    # Разделы, которые кандидат скрыл до принятия приглашения: в полях выше они пустые.
    hidden_sections: list[ProfileSection]

    @classmethod
    def from_profile(
        cls,
        profile: "CandidateProfile",
        total_experience_months: int,
        *,
        contacts_revealed: bool = False,
    ) -> "CandidateEmployerView":
        def text(value: str) -> str:
            # Кандидат принял приглашение: контакты открыты, в том числе вписанные в текст.
            return value if contacts_revealed else mask_contacts(value)

        # Скрытые кандидатом разделы открываются вместе с контактами.
        hidden = (
            set() if contacts_revealed else {ProfileSection(v) for v in profile.hidden_sections}
        )

        def titles(kind: SkillKind) -> list[str]:
            # Навыки из справочника контактов не содержат, свои теги: могут.
            return [s.title if not s.is_custom else text(s.title) for s in _skills(profile, kind)]

        return cls(
            candidate_number=profile.candidate_number,
            specialization=(
                SpecializationRead.model_validate(profile.specialization)
                if profile.specialization
                else None
            ),
            work_formats=[WorkFormat(value) for value in profile.work_formats],
            city=text(profile.city),
            about="" if ProfileSection.ABOUT in hidden else text(profile.about),
            technologies=titles(SkillKind.TECHNOLOGY),
            soft_skills=[] if ProfileSection.SOFT_SKILLS in hidden else titles(SkillKind.SOFT),
            total_experience_months=total_experience_months,
            experience=[
                EmployerExperienceRead(
                    company_name=entry.company_name if contacts_revealed else None,
                    position=text(entry.position),
                    started_on=entry.started_on,
                    ended_on=entry.ended_on,
                    description=text(entry.description),
                )
                for entry in profile.experience
                if ProfileSection.EXPERIENCE not in hidden
            ],
            education=[
                EducationRead(
                    institution=text(entry.institution),
                    specialty=text(entry.specialty),
                    graduation_year=entry.graduation_year,
                )
                for entry in profile.education
                if ProfileSection.EDUCATION not in hidden
            ],
            hidden_sections=sorted(hidden),
        )


class ConsentDocumentRead(BaseModel):
    kind: ConsentKind
    version: str
    title: str
    text: str


class ResumeDraftRead(BaseModel):
    """Поля, распознанные в PDF-резюме. Ничего не сохранено: фронт подставляет их в форму,
    кандидат проверяет и сохраняет профиль. ФИО и email берутся из аккаунта, грейд: только
    подсказка: подтверждает его тест."""

    phone: str
    telegram: str
    github: str
    specialization: SpecializationRead | None
    grade: GradeRead | None
    technologies: list[SkillRead]
    soft_skills: list[SkillRead]
    experience: list[WorkExperienceRead]
    total_experience_months: int

    @classmethod
    def from_draft(cls, draft: "ResumeDraft") -> "ResumeDraftRead":
        parsed = draft.parsed
        return cls(
            phone=parsed.phone,
            telegram=parsed.telegram,
            github=parsed.github,
            specialization=(
                SpecializationRead.model_validate(draft.specialization)
                if draft.specialization
                else None
            ),
            grade=GradeRead.model_validate(draft.grade) if draft.grade else None,
            technologies=[
                SkillRead(skill_id=skill.id, title=skill.title, is_custom=False)
                for skill in draft.technologies
            ],
            soft_skills=[
                SkillRead(skill_id=skill.id, title=skill.title, is_custom=False)
                for skill in draft.soft_skills
            ],
            experience=[
                WorkExperienceRead(
                    company_name=entry.company_name,
                    position=entry.position,
                    started_on=entry.started_on,
                    ended_on=entry.ended_on,
                    description="",
                )
                for entry in parsed.experience
            ],
            total_experience_months=parsed.total_experience_months,
        )


class PrivacyInput(BaseModel):
    hidden_sections: list[ProfileSection]
