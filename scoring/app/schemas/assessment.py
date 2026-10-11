from pydantic import BaseModel, Field

from app.services.assessment.bank import ItemKind
from app.services.assessment.irt import MAX_LEVEL

# Совпадает с лимитом выборки чужих эталонов в backend (app/services/assessment.py).
MAX_FOREIGN_ANSWERS = 200

Level = Field(ge=0, le=MAX_LEVEL, description="Уровень грейда: grades.level в backend")


class CompetencyQuotaRead(BaseModel):
    slug: str
    title: str
    count: int


class BlueprintRead(BaseModel):
    specialization: str
    items_count: int
    time_limit_minutes: int
    competencies: list[CompetencyQuotaRead]


class AssembleRequest(BaseModel):
    specialization: str
    level: int = Level
    seed: int = Field(
        ge=0, description="Детерминирует выбор и содержимое заданий попытки"
    )
    recent_families: list[str] = Field(
        default_factory=list,
        description="Семейства недавних попыток: по возможности не повторять",
    )
    # Экспресс-тест: столько заданий в тех же пропорциях компетенций (демо для жюри).
    length: int | None = Field(default=None, ge=3)


class CaseRequest(BaseModel):
    specialization: str
    level: int = Level
    seed: int = Field(ge=0, description="Детерминирует выбор семейства и экземпляр")


class ExtendRequest(BaseModel):
    specialization: str
    # У стажёра порога нет, продлевать нечего.
    level: int = Field(ge=1, le=MAX_LEVEL)
    seed: int = Field(ge=0)
    count: int = Field(ge=1, le=10)
    attempt_families: list[str] = Field(
        description="Семейства, уже показанные в этой попытке: не повторяются"
    )
    recent_families: list[str] = Field(
        default_factory=list,
        description="Семейства недавних попыток: только если свежих не хватило",
    )


class AssembledItemRead(BaseModel):
    """Экземпляр задания вместе с эталоном. Эталон хранит backend и не отдаёт кандидату."""

    family_id: str
    competency: str
    competency_title: str
    a: float
    b: float
    kind: ItemKind
    prompt: str
    code: str | None
    options: list[str]
    answer: str


class ScoreItemInput(BaseModel):
    a: float
    b: float
    answer: str
    response: str | None
    # Эталоны других экземпляров того же семейства (детектор утечки), только текстовые задания.
    foreign_answers: list[str] = Field(
        default_factory=list, max_length=MAX_FOREIGN_ANSWERS
    )


class ScoreRequest(BaseModel):
    level: int = Level
    items: list[ScoreItemInput] = Field(min_length=1)
    # Сколько раз попытку уже продлевали и экспресс ли это: от них зависит, продлевать ли ещё.
    extensions: int = Field(default=0, ge=0)
    express: bool = False


class ScoreRead(BaseModel):
    theta: float
    se: float
    passed: bool
    strong: bool
    estimated_level: int
    # Сколько заданий у порога добавить перед решением; 0 значит, что решение окончательное.
    extend_items: int
    # Вероятность, что повторная попытка на этот грейд даст то же решение.
    retest_agreement: float
    correct: list[bool]
    # Неверный ответ совпал с эталоном чужого экземпляра: признак утечки, на грейд не влияет.
    foreign_matches: list[bool]
