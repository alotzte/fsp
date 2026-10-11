# ruff: noqa: E501 (шаблон отчёта в Markdown с широкой таблицей)
"""Бенчмарк разбора PDF-резюме: `uv run python -m validation.resume` (из backend/).

Синтетические резюме (стеки и должности как в `app.demo_seed`, навыки из сид-миграции
справочника) рисуются reportlab в трёх вёрстках: одна колонка, две колонки (сайдбар с контактами
и навыками), таблица опыта. Затем прогоняются через продовый `extract_text` + `parse_resume`,
и поля сравниваются с истиной. Результат: `docs/validation-resume.md`.

Чтобы цифры не были завышены по построению, навыки пишутся то названием, то синонимом, в разном
регистре, а 20% навыков вне справочника (их разбор и не должен находить). Это проверка
извлечения, а не понимания текста: живые резюме разнообразнее, см. ограничения в отчёте.
"""

import importlib.util
import io
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from random import Random

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    FrameBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
)

from app.demo_seed import FIRST_NAMES, LAST_NAMES, STACKS
from app.services.candidates import total_experience_months
from app.services.resume import DictionarySkill, ParsedExperience, extract_text, parse_resume

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "validation-resume.md"
SEED_MIGRATION = (
    ROOT / "backend" / "migrations" / "versions" / "20261005_e072abcaad0d_seed_dictionaries.py"
)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
PROFILES = 100
MONTHS_IN_YEAR = 12
SOFT_ID_OFFSET = 1000  # у софт-скиллов в бенчмарке отдельный диапазон id
OUT_OF_DICTIONARY_SKILLS = ["Bitrix24", "1С-Битрикс", "Камунда", "Jira", "Confluence"]
GRADE_TITLES = {0: "Стажёр", 1: "Junior", 2: "Middle", 3: "Senior", 4: "Lead"}
COMPANIES = [
    "ООО «Ромашка»",
    "АО «Технопарк»",
    "ПАО «Северсталь»",
    "Яндекс",
    "Тинькофф",
    "Студия Пикс",
    "ООО «Цифровые решения»",
    "Ozon",
]
MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]  # fmt: skip


def _load_dictionary() -> tuple[list[DictionarySkill], list[DictionarySkill], dict[str, int]]:
    spec = importlib.util.spec_from_file_location("seed", SEED_MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ids: dict[str, int] = {}

    def build(items: list[tuple[str, str, list[str]]], offset: int) -> list[DictionarySkill]:
        skills = []
        for index, (slug, title, aliases) in enumerate(items):
            ids[slug] = offset + index
            skills.append(DictionarySkill(offset + index, title, aliases))
        return skills

    return build(module.TECHNOLOGIES, 1), build(module.SOFT_SKILLS, SOFT_ID_OFFSET), ids


@dataclass
class Truth:
    name: str
    email: str
    phone: str
    telegram: str
    specialization: str
    grade: int
    skill_ids: set[int]
    skill_texts: list[str]
    soft_texts: list[str]
    experience: list[ParsedExperience]
    period_texts: list[str]


def _period_text(rng: Random, start: date, end: date | None) -> tuple[str, date, date | None]:
    """Период в одном из форматов; «только год» сдвигает истину к январю и декабрю."""
    style = rng.randrange(4)
    if style == 0:
        tail = "настоящее время" if end is None else f"{MONTHS_RU[end.month - 1]} {end.year}"
        return f"{MONTHS_RU[start.month - 1]} {start.year} — {tail}", start, end
    if style == 1:
        tail = "н.в." if end is None else f"{end.month:02d}.{end.year}"
        return f"{start.month:02d}.{start.year} – {tail}", start, end
    if style == 2:  # noqa: PLR2004
        short = MONTHS_RU[start.month - 1][:3].lower() + "."
        tail = (
            "по наст. время"
            if end is None
            else f"{MONTHS_RU[end.month - 1][:3].lower()}. {end.year}"
        )
        return f"{short} {start.year} - {tail}", start, end
    start = date(start.year, 1, 1)
    end = None if end is None else date(end.year, 12, 1)
    return f"{start.year} — {'н.в.' if end is None else end.year}", start, end


def _make_truth(
    n: int, rng: Random, tech: dict[str, DictionarySkill], soft: list[DictionarySkill]
) -> Truth:
    slug = list(STACKS)[n % len(STACKS)]
    stack = STACKS[slug]
    level = rng.choice([0, 1, 1, 2, 2, 2, 3, 3, 4])
    name = f"{rng.choice(LAST_NAMES)} {rng.choice(FIRST_NAMES)}"
    chosen = stack["core"][: rng.randint(2, len(stack["core"]))] + rng.sample(
        stack["extra"], rng.randint(1, 4)
    )
    skills = [tech[s] for s in dict.fromkeys(chosen) if s in tech]

    def spelled(skill: DictionarySkill) -> str:
        name = rng.choice([skill.title, *skill.aliases]) if skill.aliases else skill.title
        return name.lower() if rng.random() < 0.3 and len(name) > 2 else name  # noqa: PLR2004

    soft_chosen = rng.sample(soft, 2)
    today = datetime.now(UTC).date().replace(day=1)
    jobs = rng.randint(1, 3)
    experience: list[ParsedExperience] = []
    periods: list[str] = []
    cursor: date | None = None  # конец следующей (более старой) работы
    for index in range(jobs):
        months = rng.randint(8, 40)
        end = cursor
        end_point = end or today
        total = end_point.year * 12 + end_point.month - 1 - months
        start = date(total // 12, total % 12 + 1, 1)
        text, start, end = _period_text(rng, start, end)
        prefix = GRADE_TITLES[level] if index == 0 and level else ""
        position = f"{prefix} {rng.choice(stack['positions'])}".strip()
        if index == 0 and level == 0:
            position = f"Стажёр-{rng.choice(stack['positions']).lower()}"
        experience.append(ParsedExperience(position, rng.choice(COMPANIES), start, end))
        periods.append(text)
        back = start.year * 12 + start.month - 1 - rng.randint(0, 6)
        cursor = date(back // 12, back % 12 + 1, 1)
    return Truth(
        name=name,
        email=f"user{n}@example.ru",
        phone=f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}",
        telegram=f"dev_user_{n:03d}",
        specialization=slug,
        grade=level,
        skill_ids={s.id for s in skills} | {s.id for s in soft_chosen},
        skill_texts=[spelled(s) for s in skills] + rng.sample(OUT_OF_DICTIONARY_SKILLS, 1),
        soft_texts=[s.title for s in soft_chosen],
        experience=experience,
        period_texts=periods,
    )


# --- вёрстки ----------------------------------------------------------------------------------

STYLE = ParagraphStyle("body", fontName="DejaVu", fontSize=10, leading=13)
TITLE = ParagraphStyle("title", parent=STYLE, fontSize=16, leading=20)
HEADING = ParagraphStyle("heading", parent=STYLE, fontSize=12, leading=16, spaceBefore=8)
DESCRIPTION = "Разработка и поддержка сервисов, участие в код-ревью, работа с командой продукта."


def _contacts(t: Truth) -> list[Flowable]:
    return [
        Paragraph(t.phone, STYLE),
        Paragraph(t.email, STYLE),
        Paragraph(f"Telegram: @{t.telegram}", STYLE),
    ]


def _skills(t: Truth) -> list[Flowable]:
    return [
        Paragraph("Навыки", HEADING),
        Paragraph(", ".join(t.skill_texts), STYLE),
        Paragraph("Софт-скиллы", HEADING),
        Paragraph(", ".join(t.soft_texts), STYLE),
    ]


def _jobs(t: Truth) -> list[Flowable]:
    story: list[Flowable] = [Paragraph("Опыт работы", HEADING)]
    for job, period in zip(t.experience, t.period_texts, strict=True):
        story += [
            Paragraph(job.position, STYLE),
            Paragraph(job.company_name, STYLE),
            Paragraph(period, STYLE),
            Paragraph(DESCRIPTION, STYLE),
            Spacer(1, 6),
        ]
    return story


def _header(t: Truth) -> list[Flowable]:
    return [Paragraph(t.name, TITLE), Paragraph(t.experience[0].position, STYLE)]


def one_column(t: Truth) -> bytes:
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4).build(_header(t) + _contacts(t) + _jobs(t) + _skills(t))
    return buffer.getvalue()


def two_columns(t: Truth) -> bytes:
    buffer = io.BytesIO()
    width, height = A4
    margin, sidebar = 15 * mm, 60 * mm
    frames = [
        Frame(margin, margin, sidebar, height - 2 * margin, id="side"),
        Frame(margin + sidebar + 12 * mm, margin, width - sidebar - 2 * margin - 12 * mm,
              height - 2 * margin, id="main"),
    ]  # fmt: skip
    document = BaseDocTemplate(buffer, pagesize=A4)
    document.addPageTemplates([PageTemplate(id="two", frames=frames)])
    document.build(_contacts(t) + _skills(t) + [FrameBreak()] + _header(t) + _jobs(t))
    return buffer.getvalue()


def table(t: Truth) -> bytes:
    buffer = io.BytesIO()
    rows = [
        [Paragraph(period, STYLE), Paragraph(f"{job.position}<br/>{job.company_name}", STYLE)]
        for job, period in zip(t.experience, t.period_texts, strict=True)
    ]
    story = [*_header(t), *_contacts(t), Paragraph("Опыт работы", HEADING)]
    story += [Table(rows, colWidths=[50 * mm, 110 * mm]), *_skills(t)]
    SimpleDocTemplate(buffer, pagesize=A4).build(story)
    return buffer.getvalue()


MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _hh_period(job: ParsedExperience, english: bool) -> str:
    """Период как в выгрузке hh.ru: с длительностью; иногда по-английски."""
    end = job.ended_on or datetime.now(UTC).date().replace(day=1)
    months = (end.year - job.started_on.year) * 12 + end.month - job.started_on.month + 1
    duration = (
        f"{months // 12} лет {months % 12} месяцев"
        if months >= MONTHS_IN_YEAR
        else f"{months} месяцев"
    )
    if english:
        tail = "Present" if job.ended_on is None else f"{MONTHS_EN[end.month - 1]} {end.year}"
        return f"{MONTHS_EN[job.started_on.month - 1]} {job.started_on.year} – {tail} {duration}"
    tail = (
        "по настоящее время" if job.ended_on is None else f"{MONTHS_RU[end.month - 1]} {end.year}"
    )
    return f"{MONTHS_RU[job.started_on.month - 1]} {job.started_on.year} — {tail} {duration}"


def hh_export(t: Truth) -> bytes:
    """Порядок «период → компания → должность → описание», как в выгрузке hh.ru.

    Здесь периоды пишутся из истинных дат напрямую (формат «только год» не используется), поэтому
    истина задана точными месяцами. Разбор под эту вёрстку не подгонялся: это контрольная вёрстка.
    """
    buffer = io.BytesIO()
    story: list[Flowable] = [*_header(t), *_contacts(t), Paragraph("Опыт работы", HEADING)]
    for index, job in enumerate(t.experience):
        story += [
            Paragraph(_hh_period(job, english=index % 2 == 1), STYLE),
            Paragraph(job.company_name, STYLE),
            Paragraph(job.position, STYLE),
            Paragraph(DESCRIPTION, STYLE),
            Spacer(1, 6),
        ]
    SimpleDocTemplate(buffer, pagesize=A4).build([*story, *_skills(t)])
    return buffer.getvalue()


LAYOUTS: dict[str, Callable[[Truth], bytes]] = {
    "одна колонка": one_column,
    "две колонки": two_columns,
    "таблица опыта": table,
    "как выгрузка hh.ru (контрольная)": hh_export,
}


# --- метрики ----------------------------------------------------------------------------------


@dataclass
class Score:
    phone: int = 0
    email: int = 0
    telegram: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    jobs_count: int = 0
    periods: int = 0
    positions: int = 0
    companies: int = 0
    jobs_total: int = 0
    grade: int = 0
    specialization: int = 0
    months_error: list[int] | None = None


def evaluate(
    truths: list[Truth],
    render: Callable[[Truth], bytes],
    tech: list[DictionarySkill],
    soft: list[DictionarySkill],
) -> Score:
    score = Score(months_error=[])
    for t in truths:
        parsed = parse_resume(extract_text(render(t)), tech, soft)
        score.phone += parsed.phone == t.phone
        score.email += parsed.email == t.email
        score.telegram += parsed.telegram == t.telegram
        found = set(parsed.technology_ids) | set(parsed.soft_skill_ids)
        score.tp += len(found & t.skill_ids)
        score.fp += len(found - t.skill_ids)
        score.fn += len(t.skill_ids - found)
        score.jobs_count += len(parsed.experience) == len(t.experience)
        score.jobs_total += len(t.experience)
        for truth_job, parsed_job in zip(t.experience, parsed.experience, strict=False):
            score.periods += (parsed_job.started_on, parsed_job.ended_on) == (
                truth_job.started_on,
                truth_job.ended_on,
            )
            score.positions += parsed_job.position == truth_job.position
            score.companies += parsed_job.company_name == truth_job.company_name
        assert score.months_error is not None
        score.months_error.append(
            abs(parsed.total_experience_months - total_experience_months(t.experience))
        )
        score.grade += parsed.grade_level == t.grade
        score.specialization += parsed.specialization_slug == t.specialization
    return score


def _pct(value: float) -> str:
    return f"{100 * value:.0f}%"


def main() -> None:
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT)))
    tech, soft, ids = _load_dictionary()
    by_slug = {
        slug: next(s for s in tech if s.id == skill_id)
        for slug, skill_id in ids.items()
        if skill_id < SOFT_ID_OFFSET
    }
    rng = Random(2026)
    truths = [_make_truth(n, rng, by_slug, soft) for n in range(PROFILES)]
    rows = []
    for layout, render in LAYOUTS.items():
        s = evaluate(truths, render, tech, soft)
        assert s.months_error is not None
        precision = s.tp / (s.tp + s.fp) if s.tp + s.fp else 0.0
        recall = s.tp / (s.tp + s.fn) if s.tp + s.fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            f"| {layout} | {_pct(s.phone / PROFILES)} | {_pct(s.email / PROFILES)} "
            f"| {_pct(s.telegram / PROFILES)} | {precision:.2f} / {recall:.2f} / {f1:.2f} "
            f"| {_pct(s.jobs_count / PROFILES)} | {_pct(s.periods / s.jobs_total)} "
            f"| {_pct(s.positions / s.jobs_total)} | {_pct(s.companies / s.jobs_total)} "
            f"| {statistics.mean(s.months_error):.1f} / {statistics.median(s.months_error):.0f} "
            f"| {_pct(s.grade / PROFILES)} | {_pct(s.specialization / PROFILES)} |"
        )
        print(rows[-1], file=sys.stderr)  # noqa: T201
    REPORT.write_text(_report(rows), encoding="utf-8")


def _report(rows: list[str]) -> str:
    return f"""# Валидация разбора PDF-резюме

Сгенерировано `uv run python -m validation.resume` (из `backend/`): {PROFILES} синтетических резюме
× 4 вёрстки, seed 2026. Разбирают рабочие функции `extract_text` и `parse_resume`
(`backend/app/services/resume.py`), без LLM.

Как построены резюме. Направления, должности и стеки те же, что в `app.demo_seed` (backend,
frontend, data science). Навыки из справочника записаны то названием, то синонимом («golang»,
«k8s»), иногда строчными буквами. В каждом резюме есть навык вне справочника, который разбор
находить не должен. Опыт: 1-3 места работы, периоды в четырёх форматах («Март 2021 — настоящее
время», «03.2021 – н.в.», «мар. 2021 - по наст. время», «2019 — 2021»). Грейд указан приставкой к
последней должности (Junior/Middle/Senior/Lead, «Стажёр-…»).

| Вёрстка | Телефон | Email | Telegram | Навыки P / R / F1 | Число мест | Период | Должность | Компания | Ошибка стажа, мес. (ср. / мед.) | Грейд | Направление |
|---|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

Для всех полей, кроме навыков и стажа, считается точное совпадение. Навыки усредняются по всем
резюме (микро-усреднение), для стажа считается абсолютная ошибка суммарного стажа. «Период»,
«Должность» и «Компания» показывают долю мест работы, где поле совпало полностью.

Как читать. Первые три вёрстки использовались при отладке разбора (на них нашлись перенос периода
в узкой колонке и склейка ячеек таблицы), поэтому их цифры являются верхней границей. Четвёртая
вёрстка повторяет выгрузку hh.ru (период с длительностью, затем компания, затем должность, часть
дат по-английски) и под разбор не подгонялась, это контрольная оценка. Её слабое место: компанию
без «ООО» и кавычек разбор путает со строкой описания предыдущего места работы.

Ограничения:
- Синтетика проверяет извлечение из вёрстки и форматы дат, но не разнообразие живых резюме: свои
  формулировки должностей, опыт без дат, резюме на английском. Поэтому в интерфейсе черновик только
  подставляется в форму, а кандидат проверяет его перед сохранением.
- Скан без текстового слоя не распознаётся (OCR не подключён): ручка отвечает 422, и кандидат
  заполняет профиль вручную.
"""


if __name__ == "__main__":
    main()
