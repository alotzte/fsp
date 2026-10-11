from pydantic import BaseModel, Field

from app.services.matching import SkillStatus


class NeedSkillInput(BaseModel):
    id: int
    title: str
    must_have: bool


class NeedInput(BaseModel):
    grade_level: int | None = None
    skills: list[NeedSkillInput] = Field(default_factory=list)
    work_formats: list[str] = Field(default_factory=list)
    city: str = ""
    salary_to: int | None = None


class CandidateInput(BaseModel):
    key: int
    grade_level: int | None
    grade_title: str | None
    confirmed: bool
    theta: float | None = None
    theta_se: float | None = None
    skills: list[int] = Field(default_factory=list)
    work_formats: list[str] = Field(default_factory=list)
    city: str = ""
    fsp_score: float = Field(default=0.0, ge=0, le=1)
    fsp_achievements: int = Field(default=0, ge=0)
    fsp_relevant: int = Field(default=0, ge=0)
    salary_expectation: int | None = None
    verified_skills: list[int] = Field(default_factory=list)
    recent_cases: int = Field(default=0, ge=0)


class RankRequest(BaseModel):
    # None: поиск по банку без потребности: ранжирование по силе профиля.
    need: NeedInput | None = None
    candidates: list[CandidateInput]


class ContributionRead(BaseModel):
    key: str
    title: str
    value: float
    weight: float


class SkillCheckRead(BaseModel):
    title: str
    must_have: bool
    status: SkillStatus


class MatchRead(BaseModel):
    key: int
    score: float
    salary_compatible: bool
    format_compatible: bool
    contributions: list[ContributionRead]
    reasons: list[str]
    skills: list[SkillCheckRead]
