"""Стандартизированный PDF-профиль кандидата (ТЗ §2.1).

Рендер живёт в слое API и строится только из схемы ответа `EmployerCandidateRead`: в PDF попадает
ровно то, что видно в карточке. До принятия приглашения это обезличенный профиль с маской
контактов, после принятия с ФИО, контактами и командами ФСП. Своему владельцу профиль выгружается
в виде «после принятия» (`HiringService.own_details`).
"""

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.hiring import EmployerCandidateRead
from app.services.db.models import FspAward, FspDiscipline, FspSportRank, WorkFormat

# ponytail: DejaVu из пакета fonts-dejavu-core (кириллица); фирменный JetBrains Mono заменён
# DejaVu Sans Mono: отдельный TTF в репозиторий, если брендбук потребует точного шрифта.
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONTS = {
    "Body": "DejaVuSans.ttf",
    "Body-Bold": "DejaVuSans-Bold.ttf",
    "Heading": "DejaVuSansMono-Bold.ttf",
}
FSP_BLUE = colors.HexColor("#402FFF")
MUTED = colors.HexColor("#5C5D66")
LIGHT = colors.HexColor("#EDEDED")

WORK_FORMAT_LABELS = {
    WorkFormat.OFFICE: "офис",
    WorkFormat.HYBRID: "гибрид",
    WorkFormat.REMOTE: "удалёнка",
}
AWARD_LABELS = {
    FspAward.WINNER: "победитель",
    FspAward.PRIZE: "призёр",
    FspAward.FINALIST: "финалист",
    FspAward.PARTICIPANT: "участник",
}
DISCIPLINE_LABELS = {
    FspDiscipline.ALGORITHMIC: "алгоритмическое программирование",
    FspDiscipline.PRODUCT: "продуктовое программирование",
    FspDiscipline.INFOSEC: "программирование систем ИБ",
    FspDiscipline.ROBOTICS: "программирование робототехники",
    FspDiscipline.UAS: "программирование БАС",
}
SPORT_RANK_LABELS = {
    FspSportRank.THIRD: "III спортивный разряд",
    FspSportRank.SECOND: "II спортивный разряд",
    FspSportRank.FIRST: "I спортивный разряд",
    FspSportRank.CMS: "кандидат в мастера спорта",
    FspSportRank.MS: "мастер спорта",
}
MONTHS_IN_YEAR = 12

_registered = False


def _register_fonts() -> None:
    global _registered  # noqa: PLW0603  # регистрация шрифтов reportlab глобальна и нужна один раз
    if not _registered:
        for name, file in FONTS.items():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
        _registered = True


BODY = ParagraphStyle("body", fontName="Body", fontSize=9.5, leading=13)
MUTED_TEXT = ParagraphStyle("muted", parent=BODY, textColor=MUTED, fontSize=8.5, leading=11)
TITLE = ParagraphStyle("title", fontName="Heading", fontSize=18, leading=22, textColor=FSP_BLUE)
HEADING = ParagraphStyle(
    "heading", fontName="Heading", fontSize=11, leading=15, spaceBefore=10, spaceAfter=4
)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="Body-Bold")


def _p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    # Текст профиля пишет пользователь: экранируем, иначе «<» сломает разметку reportlab.
    return Paragraph(escape(text), style)


def _years(months: int) -> str:
    years, rest = divmod(months, MONTHS_IN_YEAR)
    parts = [f"{years} г." if years else "", f"{rest} мес." if rest else ""]
    return " ".join(part for part in parts if part) or "нет"


def _header(card: EmployerCandidateRead) -> list[Flowable]:
    if card.contacts is None:
        return [
            _p(f"Кандидат №{card.profile.candidate_number}", TITLE),
            _p("ФИО и контакты откроются, когда кандидат примет приглашение.", MUTED_TEXT),
        ]
    c = card.contacts
    name = " ".join(part for part in (c.last_name, c.first_name, c.middle_name) if part)
    contacts = [c.email, c.phone, f"Telegram: @{c.telegram}" if c.telegram else ""]
    return [_p(name, TITLE), _p(" · ".join(item for item in contacts if item), MUTED_TEXT)]


def _category(card: EmployerCandidateRead) -> list[Flowable]:
    profile, category = card.profile, card.category
    specialization = category.specialization.title if category.specialization else "не выбрано"
    grade = category.grade.title if category.grade else "грейд не выбран"
    if category.confirmed and category.confirmed_at:
        status = f"подтверждён тестом {category.confirmed_at:%d.%m.%Y}"
    else:
        status = "не подтверждён тестом"
    formats = ", ".join(WORK_FORMAT_LABELS[f] for f in profile.work_formats)
    facts = [
        f"Стаж: {_years(profile.total_experience_months)}",
        f"Город: {profile.city}" if profile.city else "",
        f"Формат: {formats}" if formats else "",
    ]
    return [
        _p("Категория", HEADING),
        _p(f"{specialization} · {grade}: {status}", BOLD),
        _p(" · ".join(fact for fact in facts if fact)),
    ]


def _tests_and_skills(card: EmployerCandidateRead) -> list[Flowable]:
    story: list[Flowable] = []
    if card.test_results:
        rows = [[_p(r.title), _p(f"{r.correct} из {r.total}")] for r in card.test_results]
        story += [_p("Итоги теста по компетенциям", HEADING), _table(rows, [130 * mm, 40 * mm])]
    profile = card.profile
    if profile.technologies or profile.soft_skills:
        story.append(_p("Навыки", HEADING))
    if profile.technologies:
        story.append(_p(", ".join(profile.technologies)))
    if profile.soft_skills:
        story.append(_p("Софт-скиллы: " + ", ".join(profile.soft_skills), MUTED_TEXT))
    return story


def _fsp(card: EmployerCandidateRead) -> list[Flowable]:
    # Нет истории ФСП, нет и раздела: без штрафа и без упоминания (ТЗ, docs/architecture.md §4).
    story: list[Flowable] = []
    if card.fsp_results or card.fsp_sport_rank:
        story.append(_p("Достижения ФСП (реестр ФСП)", HEADING))
    if rank := card.fsp_sport_rank:
        label = SPORT_RANK_LABELS[rank.rank]
        story.append(_p(f"Спортивное программирование: {label}, с {rank.assigned_on:%m.%Y}"))
    if card.fsp_results:
        rows = []
        for r in card.fsp_results:
            place = f", {r.place} место" if r.place else ""
            team = f", команда «{r.team_name}»" if r.team_name else ""
            ekp = f", № ЕКП {r.ekp_number}" if r.ekp_number else ""
            event = f"{r.event_title}: {DISCIPLINE_LABELS[r.discipline]}{team}{ekp}"
            rows.append(
                [_p(f"{r.starts_on:%m.%Y}"), _p(event), _p(f"{AWARD_LABELS[r.award]}{place}")]
            )
        story.append(_table(rows, [20 * mm, 110 * mm, 40 * mm]))
    if card.recent_cases:
        story.append(_p(f"Кейсы недели: {card.recent_cases} решено за 30 дней", MUTED_TEXT))
    return story


def _experience_and_about(card: EmployerCandidateRead) -> list[Flowable]:
    profile = card.profile
    story: list[Flowable] = []
    if profile.experience:
        story.append(_p("Опыт работы", HEADING))
    for job in profile.experience:
        end = f"{job.ended_on:%m.%Y}" if job.ended_on else "н. в."
        company = f", {job.company_name}" if job.company_name else ""
        story.append(_p(f"{job.position}{company} · {job.started_on:%m.%Y} - {end}", BOLD))
        if job.description:
            story.append(_p(job.description))
        story.append(Spacer(1, 4))
    if profile.education:
        story.append(_p("Образование", HEADING))
    for entry in profile.education:
        parts = [entry.institution, entry.specialty, str(entry.graduation_year or "")]
        story.append(_p(", ".join(part for part in parts if part)))
    if profile.about:
        story += [_p("О себе", HEADING), _p(profile.about)]
    return story


def render_candidate_pdf(card: EmployerCandidateRead) -> bytes:
    _register_fonts()
    story = [
        *_header(card),
        *_category(card),
        *_tests_and_skills(card),
        *_fsp(card),
        *_experience_and_about(card),
        Spacer(1, 12),
        _p(
            f"Профиль платформы ФСП, выгружен {datetime.now(UTC):%d.%m.%Y}. Категория и итоги "
            "теста взяты из теста платформы, достижения из реестра ФСП.",
            MUTED_TEXT,
        ),
    ]
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Кандидат №{card.profile.candidate_number}",
    ).build(story)
    return buffer.getvalue()


def _table(rows: Sequence[list[Paragraph]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
