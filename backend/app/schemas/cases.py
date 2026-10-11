from datetime import date, timedelta
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, StringConstraints

from app.services.db.models import ItemKind

if TYPE_CHECKING:
    from app.services.db.models import WeeklyCase

MAX_CASE_RESPONSE = 500


class WeeklyCaseRead(BaseModel):
    """Кейс недели без эталона: правильный ответ не отдаётся ни до, ни после ответа."""

    week: date
    # Когда появится следующий кейс (понедельник).
    next_case_on: date
    competency_title: str
    kind: ItemKind
    prompt: str
    code: str | None
    options: list[str]
    response: str | None
    is_correct: bool | None
    # Верно решённых кейсов за 30 дней: столько видит работодатель.
    solved_recently: int

    @classmethod
    def from_case(cls, case: "WeeklyCase", solved_recently: int) -> "WeeklyCaseRead":
        return cls(
            week=case.week,
            next_case_on=case.week + timedelta(days=7),
            competency_title=case.competency_title,
            kind=case.kind,
            prompt=case.prompt,
            code=case.code,
            options=case.options,
            response=case.response,
            is_correct=case.is_correct,
            solved_recently=solved_recently,
        )


class CaseAnswerInput(BaseModel):
    # strip до проверки длины: ответ из пробелов сжигал бы единственную попытку недели.
    response: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CASE_RESPONSE)
    ]
