"""Разбор PDF-резюме в черновик профиля (ТЗ §2.1: «загрузка PDF с автораспознаванием»).

Без LLM: персональные данные не уходят наружу, демо не зависит от ключа. Разбор выполняет чистая
функция `parse_resume` над текстом, её проверяют `tests/test_resume_parse.py` и бенчмарк
`python -m validation.resume` (отчёт в `docs/validation-resume.md`). Черновик ничего не сохраняет:
кандидат проверяет поля в форме и сохраняет профиль обычной кнопкой.
"""

import asyncio
import io
import multiprocessing
import re
import resource
from collections import Counter
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Annotated

import pdfplumber
from fastapi import Depends
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from app.errors import DomainError
from app.services.candidates import total_experience_months
from app.services.db.models import Grade, Skill, SkillKind, Specialization
from app.services.dictionaries import DictionaryServiceDep

RESUME_MAX_BYTES = 5 * 1024 * 1024
RESUME_MAX_PAGES = 5
# Меньше этого: скан без текстового слоя или пустой файл.
MIN_TEXT_CHARS = 50
PDF_SIGNATURE = b"%PDF"


class ResumeTooLargeError(DomainError):
    status_code = 413
    message = "Файл больше 5 МБ"


class ResumeNotPdfError(DomainError):
    status_code = 415
    message = "Нужен файл PDF"


class ResumeUnreadableError(DomainError):
    status_code = 422
    message = "Не удалось распознать текст, заполните профиль вручную"


@dataclass(frozen=True)
class DictionarySkill:
    id: int
    title: str
    aliases: Sequence[str]


@dataclass(frozen=True)
class ParsedExperience:
    position: str
    company_name: str
    started_on: date
    ended_on: date | None


@dataclass
class ParsedResume:
    email: str = ""
    phone: str = ""
    telegram: str = ""
    github: str = ""
    technology_ids: list[int] = field(default_factory=list)
    soft_skill_ids: list[int] = field(default_factory=list)
    experience: list[ParsedExperience] = field(default_factory=list)
    grade_level: int | None = None
    specialization_slug: str | None = None

    @property
    def total_experience_months(self) -> int:
        return total_experience_months(self.experience)


# --- контакты ---------------------------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Zа-яА-Я]{2,}")
_PHONE = re.compile(
    r"(?:\+7|\b8)[  (-]*\d{3}[  )-]*\d{3}[  -]*\d{2}[  -]*\d{2}\b"
    r"|\+\d{1,3}[  (-]*\d{2,4}[  )-]*\d{3}[  -]*\d{2,4}[  -]*\d{0,4}\b"
)
_TELEGRAM_LINK = re.compile(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{5,32})\b", re.IGNORECASE)
# «Telegram: @nick», «tg: nick». Просто «@nick» без подписи не берём: это может быть что угодно.
_TELEGRAM_LABELED = re.compile(
    # \b вокруг подписи: иначе «Pos|tg|reSQL» в списке навыков давало ник «reSQL».
    r"\b(?:telegram|телеграмм?|tg|тг)\b\s*[:\-—–]?\s*@?([A-Za-z0-9_]{5,32})\b",
    re.IGNORECASE,
)
_GITHUB = re.compile(r"github\.com/([A-Za-z0-9-]{1,39})\b", re.IGNORECASE)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":  # noqa: PLR2004 (длина российского номера)
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:]}"
    return "+" + digits


# --- навыки -----------------------------------------------------------------------------------

# Короткие названия («C», «R», «Go») ищем с учётом регистра: иначе «go» в любой фразе стал бы
# навыком.
_SHORT_NAME = 2


def _skill_pattern(name: str) -> re.Pattern[str]:
    # Границы слова свои: «C++», «C#» и «.NET» не состоят только из букв, а «C» внутри «C++»
    # не отдельный навык.
    flags = 0 if len(name) <= _SHORT_NAME else re.IGNORECASE
    return re.compile(rf"(?<![\w+#.]){re.escape(name)}(?![\w+#]|\.\w)", flags)


def find_skills(text: str, dictionary: Iterable[DictionarySkill]) -> list[int]:
    """Навыки справочника, упомянутые в тексте по названию или синониму."""
    return [
        skill.id
        for skill in dictionary
        if any(_skill_pattern(name).search(text) for name in (skill.title, *skill.aliases))
    ]


# --- опыт -------------------------------------------------------------------------------------

_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8,
    "сен": 9, "окт": 10, "ноя": 11, "дек": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_WORD = r"(?:янв|фев|мар|апр|ма[йя]|июн|июл|авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[а-яa-z]*\.?"  # noqa: E501
_POINT = rf"(?:{_MONTH_WORD}\s+\d{{4}}|\d{{1,2}}[./]\d{{4}}|\d{{4}})"
_NOW = r"(?:по\s+)?(?:н\.\s*в\.?|наст(?:оящее|\.)?\s*(?:время|вр\.?)|сейчас|present|now|current)"
_PERIOD = re.compile(
    rf"(?P<start>{_POINT})\s*(?:[-–—]|по|to)\s*(?P<end>{_POINT}|{_NOW})", re.IGNORECASE
)
# Начало периода с тире в конце строки или перед текстом соседней ячейки, а окончание
# в начале следующей строки: так узкая колонка дат переносится в таблицах и сайдбарах.
_DANGLING_START = re.compile(rf"(?P<start>{_POINT})\s*[-–—]\s*(?P<rest>.*)$", re.IGNORECASE)
_LEADING_END = re.compile(rf"^(?P<end>{_POINT}|{_NOW})\b\s*(?P<rest>.*)$", re.IGNORECASE)
_MAX_WRAPPED_WORDS = 2
# «2 года 3 месяца», «1 year 2 months» рядом с периодом: шум для должности и компании.
_DURATION = re.compile(
    r"\(?\s*\d+\s*(?:год|года|лет|year|years|мес|месяц|месяца|месяцев|month|months)\.?"
    r"(?:\s*\d+\s*(?:мес|месяц|месяца|месяцев|month|months)\.?)?\s*\)?",
    re.IGNORECASE,
)
_SEPARATORS = re.compile(r"\s*[|·•,]\s*|\s+[—–-]\s+")

_ROLE_WORDS = re.compile(
    r"разработчик|программист|инженер|developer|engineer|аналитик|analyst|тестировщик|"
    r"\bqa\b|тимлид|team\s*lead|\blead\b|руководитель|архитектор|architect|стажёр|стажер|"
    r"intern|scientist|devops|\bsre\b|специалист|дизайнер|designer|administrator|администратор",
    re.IGNORECASE,
)
_COMPANY_MARKS = re.compile(
    r"\b(?:ООО|АО|ПАО|ЗАО|ОАО|ИП|ФГУП|LLC|Inc|Ltd|GmbH|Group|Банк|Bank)\b|[«\"]", re.IGNORECASE
)
_SECTION_HEADERS = re.compile(
    r"^(?:опыт работы|опыт|experience|work experience|образование|education|навыки|skills|"
    r"о себе|about|контакты|contacts|ключевые навыки|проекты|projects)\s*:?$",
    re.IGNORECASE,
)
# Строка-кандидат в должность или компанию: не длиннее этого, иначе это описание.
_MAX_HEADING_CHARS = 80


def _parse_point(raw: str, *, is_end: bool) -> date | None:
    raw = raw.strip().casefold()
    if re.fullmatch(_NOW, raw, re.IGNORECASE):
        return None
    year_match = re.search(r"\d{4}", raw)
    if year_match is None:
        return None
    year = int(year_match.group())
    if numeric := re.match(r"(\d{1,2})[./]", raw):
        month = int(numeric.group(1))
    elif raw[:3] in _MONTHS:
        month = _MONTHS[raw[:3]]
    else:
        # Только год: начало в январе, окончание в декабре (как читает человек «2019 — 2021»).
        month = 12 if is_end else 1
    if not 1 <= month <= 12:  # noqa: PLR2004
        return None
    return date(year, month, 1)


def _clean_heading(line: str) -> str:
    return _DURATION.sub("", line).strip(" \t|·•,—–-:")


def _candidate_lines(lines: Sequence[str], index: int, rest: str) -> list[str]:
    """Строки рядом с периодом, где обычно пишут должность и компанию."""
    found = [part for part in _SEPARATORS.split(_clean_heading(rest)) if part]
    for neighbour in (index - 1, index - 2, index + 1, index + 2):
        if 0 <= neighbour < len(lines):
            line = _clean_heading(lines[neighbour])
            if (
                line
                and len(line) <= _MAX_HEADING_CHARS
                and not _SECTION_HEADERS.match(line)
                and not _PERIOD.search(lines[neighbour])
            ):
                # «ООО «Яндекс», Frontend-разработчик»: компания и должность в одной строке.
                # Целиком она ушла бы в должность, а компания нашлась бы у соседнего места работы.
                found.extend(part for part in _SEPARATORS.split(line) if part)
    return found


def _position_and_company(candidates: list[str]) -> tuple[str, str]:
    position = next((line for line in candidates if _ROLE_WORDS.search(line)), "")
    company = next(
        (line for line in candidates if line != position and _COMPANY_MARKS.search(line)), ""
    )
    if not company:
        company = next((line for line in candidates if line != position), "")
    return position, company


def _join_wrapped_periods(lines: list[str]) -> list[str]:
    """«Июль 2023 — Junior-разработчик» + «настоящее время Ozon» →
    «Июль 2023 — настоящее время | Junior-разработчик | Ozon» и пустая строка вместо второй.

    Перенос бывает и внутри окончания («Январь» / «2025», «по наст.» / «время»), поэтому
    к началу следующей строки пробуем приставить одно-два первых слова после тире.
    """
    joined = list(lines)
    for index in range(len(joined) - 1):
        start = None if _PERIOD.search(joined[index]) else _DANGLING_START.search(joined[index])
        if start is None:
            continue
        words = start.group("rest").split()
        for taken in range(min(_MAX_WRAPPED_WORDS, len(words)), -1, -1):
            end = _LEADING_END.match(" ".join([*words[:taken], joined[index + 1]]))
            if end is not None:
                break
        if end is None:
            continue
        before = joined[index][: start.start()]
        joined[index] = (
            f"{before} {start.group('start')} — {end.group('end')}"
            f" | {' '.join(words[taken:])} | {end.group('rest')}"
        )
        joined[index + 1] = ""
    return joined


def find_experience(text: str, today: date) -> list[ParsedExperience]:
    """Места работы по периодам «март 2019 — настоящее время», «01.2020 – 03.2022», «2018 — 2020».

    ponytail: эвристика по соседним строкам; резюме, где период стоит далеко от должности,
    разбирается без должности, её дозаполнит кандидат.
    """
    lines = _join_wrapped_periods([line.strip() for line in text.splitlines()])
    entries: list[ParsedExperience] = []
    for index, line in enumerate(lines):
        match = _PERIOD.search(line)
        if match is None:
            continue
        started_on = _parse_point(match.group("start"), is_end=False)
        ended_on = _parse_point(match.group("end"), is_end=True)
        if started_on is None or started_on > today:
            continue
        if ended_on is not None and ended_on > today:
            ended_on = None  # окончание в будущем: опечатка или «работаю до…», считаем текущей
        if ended_on is not None and ended_on < started_on:
            continue
        rest = line[: match.start()] + " " + line[match.end() :]
        position, company = _position_and_company(_candidate_lines(lines, index, rest))
        entries.append(ParsedExperience(position, company, started_on, ended_on))
    return entries


# --- грейд и специализация --------------------------------------------------------------------

_GRADE_WORDS: list[tuple[int, re.Pattern[str]]] = [
    (4, re.compile(r"\b(?:team\s*lead|tech\s*lead|тимлид|техлид|lead)\b", re.IGNORECASE)),
    (3, re.compile(r"\b(?:senior|сеньор|синьор|старший|ведущий)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(?:middle|мидл)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(?:junior|джун|джуниор|младший)\b", re.IGNORECASE)),
    (0, re.compile(r"\b(?:стажёр|стажер|intern|trainee)\b", re.IGNORECASE)),
]

_SPECIALIZATION_WORDS: dict[str, re.Pattern[str]] = {
    "backend": re.compile(
        r"backend|бэкенд|бекенд|back-end|серверн|(?:python|java|go|golang|php|c#|\.net|kotlin)"
        r"-разработчик",
        re.IGNORECASE,
    ),
    "frontend": re.compile(
        r"frontend|фронтенд|front-end|верстальщик|(?:react|vue|angular|веб|web)-разработчик",
        re.IGNORECASE,
    ),
    "fullstack": re.compile(r"full-?stack|фулстек|фуллстек", re.IGNORECASE),
    "mobile": re.compile(r"\bios\b|android|mobile|мобильн|flutter", re.IGNORECASE),
    "devops": re.compile(r"devops|\bsre\b|site reliability", re.IGNORECASE),
    "data-science": re.compile(
        r"data scien|machine learning|\bml\b|ml-|машинн\w+ обучени|deep learning|аналитик данных",
        re.IGNORECASE,
    ),
    "data-engineering": re.compile(
        r"data engineer|дата-инженер|инженер данных|etl", re.IGNORECASE
    ),
    "qa": re.compile(r"\bqa\b|тестировщик|тестирован|quality assurance|\bsdet\b", re.IGNORECASE),
    "analytics": re.compile(r"аналитик(?! данных)|(?<!data )analyst", re.IGNORECASE),
    "gamedev": re.compile(r"gamedev|game developer|unity|unreal|игр", re.IGNORECASE),
    "security": re.compile(r"безопасност|security|pentest|пентест", re.IGNORECASE),
    "embedded": re.compile(r"embedded|встраиваем|микроконтроллер|stm32", re.IGNORECASE),
}


def find_grade(experience: Sequence[ParsedExperience], text: str) -> int | None:
    """Грейд из последней должности, иначе из заголовка резюме (первые строки)."""
    latest = sorted(experience, key=lambda entry: entry.started_on, reverse=True)
    sources = [entry.position for entry in latest[:1]] + ["\n".join(text.splitlines()[:5])]
    for source in sources:
        for level, pattern in _GRADE_WORDS:
            if pattern.search(source):
                return level
    return None


def find_specialization(experience: Sequence[ParsedExperience], text: str) -> str | None:
    """Направление по должностям; если по ним не понять, по всему тексту."""
    for source in ("\n".join(entry.position for entry in experience), text):
        counts = Counter(
            {slug: len(pattern.findall(source)) for slug, pattern in _SPECIALIZATION_WORDS.items()}
        )
        slug, hits = counts.most_common(1)[0]
        if hits:
            return slug
    return None


def parse_resume(
    text: str,
    technologies: Sequence[DictionarySkill],
    soft_skills: Sequence[DictionarySkill],
    today: date | None = None,
) -> ParsedResume:
    today = today or datetime.now(UTC).date()
    result = ParsedResume()
    if email := _EMAIL.search(text):
        result.email = email.group()
    if phone := _PHONE.search(text):
        result.phone = _normalize_phone(phone.group())
    if telegram := _TELEGRAM_LINK.search(text) or _TELEGRAM_LABELED.search(text):
        result.telegram = telegram.group(1)
    if github := _GITHUB.search(text):
        result.github = github.group(1)
    result.technology_ids = find_skills(text, technologies)
    result.soft_skill_ids = find_skills(text, soft_skills)
    result.experience = find_experience(text, today)
    result.grade_level = find_grade(result.experience, text)
    result.specialization_slug = find_specialization(result.experience, text)
    return result


# --- PDF --------------------------------------------------------------------------------------


def extract_text(content: bytes) -> str:
    """Текст первых страниц PDF. Двухколоночная вёрстка читается по колонкам: pdfplumber
    группирует слова по строкам, поэтому колонки разделяем по самому широкому вертикальному
    просвету."""
    if len(content) > RESUME_MAX_BYTES:
        raise ResumeTooLargeError
    if not content.startswith(PDF_SIGNATURE):
        raise ResumeNotPdfError
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(_page_text(page) for page in pdf.pages[:RESUME_MAX_PAGES])
    except (PdfminerException, PDFSyntaxError) as error:
        raise ResumeUnreadableError from error
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ResumeUnreadableError
    return text


# Чужой PDF разбирается в отдельном процессе с пределом памяти и времени: файл в сотни байт
# (поток-«бомба» или страница шириной 10^8) иначе занимал гигабайты памяти всего бэкенда.
PARSE_TIMEOUT_SECONDS = 20
PARSE_MEMORY_BYTES = 1024 * 1024 * 1024


async def extract_text_isolated(content: bytes) -> str:
    """extract_text в отдельном процессе; всё, что он не осилил, считается
    нераспознанным резюме."""
    if len(content) > RESUME_MAX_BYTES:
        raise ResumeTooLargeError
    if not content.startswith(PDF_SIGNATURE):
        raise ResumeNotPdfError
    pool = ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"), initializer=_limit_memory
    )
    try:
        text = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(pool, _extract_or_none, content),
            PARSE_TIMEOUT_SECONDS,
        )
    except (TimeoutError, BrokenProcessPool) as error:
        raise ResumeUnreadableError from error
    finally:
        # Зависший разбор не дожидаемся: процесс убиваем, иначе он держал бы CPU и память.
        for process in list((pool._processes or {}).values()):  # noqa: SLF001 (нет публичного API)
            process.kill()
        pool.shutdown(wait=False, cancel_futures=True)
    if text is None:
        raise ResumeUnreadableError
    return text


def _limit_memory() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (PARSE_MEMORY_BYTES, PARSE_MEMORY_BYTES))


def _extract_or_none(content: bytes) -> str | None:
    # Исключения из процесса не возвращаем: DomainError не переживает pickle. Любой сбой
    # стороннего разборщика на чужом файле (MemoryError, TypeError без MediaBox) означает
    # «не распознано».
    try:
        return extract_text(content)
    except Exception:
        return None


# Колонка есть, если просвет шире этой доли страницы и по обе стороны много слов.
_GUTTER_SHARE = 0.04
_MAX_PAGE_WIDTH = 2000
_MIN_COLUMN_SHARE = 0.2


def _page_text(page: pdfplumber.page.Page) -> str:
    words = page.extract_words()
    gutter = _find_gutter(words, float(page.width))
    if gutter is None:
        return page.extract_text() or ""
    left = page.crop((0, 0, gutter, page.height)).extract_text() or ""
    right = page.crop((gutter, 0, page.width, page.height)).extract_text() or ""
    return left + "\n" + right


def _find_gutter(words: Sequence[dict[str, object]], width: float) -> float | None:
    """Середина вертикального просвета, который не пересекает ни одно слово."""
    # Ширина берётся из файла: на странице шире 2000 pt (A4: 595) колонки не ищем, иначе
    # массив ниже растёт с подставленным в MediaBox числом.
    if not words or width > _MAX_PAGE_WIDTH:
        return None
    covered = [False] * int(width + 1)
    for word in words:
        x0, x1 = float(str(word["x0"])), float(str(word["x1"]))
        for x in range(int(x0), min(int(x1) + 1, len(covered))):
            covered[x] = True
    best_start, best_length, start = 0, 0, None
    margin = int(width * 0.15)  # просветы у полей страницы не колонки
    for x in range(margin, len(covered) - margin):
        if not covered[x] and start is None:
            start = x
        elif covered[x] and start is not None:
            if x - start > best_length:
                best_start, best_length = start, x - start
            start = None
    if best_length < width * _GUTTER_SHARE:
        return None
    gutter = best_start + best_length / 2
    left = sum(1 for word in words if float(str(word["x1"])) <= gutter)
    if not _MIN_COLUMN_SHARE <= left / len(words) <= 1 - _MIN_COLUMN_SHARE:
        return None
    return gutter


# --- сервис -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeDraft:
    parsed: ParsedResume
    technologies: list[Skill]
    soft_skills: list[Skill]
    grade: Grade | None
    specialization: Specialization | None


def _dictionary(skills: Sequence[Skill]) -> list[DictionarySkill]:
    return [DictionarySkill(skill.id, skill.title, skill.aliases) for skill in skills]


class ResumeService:
    def __init__(self, dictionaries: DictionaryServiceDep) -> None:
        self._dictionaries = dictionaries

    async def parse(self, content: bytes) -> ResumeDraft:
        text = await extract_text_isolated(content)
        technologies = await self._dictionaries.list_skills(SkillKind.TECHNOLOGY)
        soft_skills = await self._dictionaries.list_skills(SkillKind.SOFT)
        parsed = parse_resume(text, _dictionary(technologies), _dictionary(soft_skills))
        grades = {grade.level: grade for grade in await self._dictionaries.list_grades()}
        specializations = {
            item.slug: item for item in await self._dictionaries.list_specializations()
        }
        by_id = {skill.id: skill for skill in (*technologies, *soft_skills)}
        return ResumeDraft(
            parsed=parsed,
            technologies=[by_id[skill_id] for skill_id in parsed.technology_ids],
            soft_skills=[by_id[skill_id] for skill_id in parsed.soft_skill_ids],
            grade=grades.get(parsed.grade_level) if parsed.grade_level is not None else None,
            specialization=(
                specializations.get(parsed.specialization_slug)
                if parsed.specialization_slug
                else None
            ),
        )


ResumeServiceDep = Annotated[ResumeService, Depends()]
