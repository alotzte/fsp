"""Демо-кандидаты для стенда: `python -m app.demo_seed [количество]`.

Кандидаты проходят тест через настоящий механизм (сборка в scoring, сервис попыток, оценка),
а ответы моделируются по 2PL от «истинного» уровня θ. Поэтому их грейды, θ и итоги по
компетенциям получены так же, как у живых людей, и выдача работодателю правдоподобна.

Демо-пользователи помечены keycloak_sub = "demo:<n>" и войти не могут. Повторный запуск
удаляет прежних демо-кандидатов и создаёт заново (детерминированно, seed 2026).

Ещё создаётся компания «Пример Технологии» с историей приглашений этим кандидатам: на ней видна
репутация работодателя, и от неё демо-кандидат жюри сразу получает приглашение.
Требует запущенный scoring (SCORING_URL).
"""

import asyncio
import math
import sys
from datetime import UTC, date, datetime, time, timedelta
from random import Random

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.assessment import AssessmentService
from app.services.cases import CaseService, week_start
from app.services.consents import CONSENT_DOCUMENTS, ConsentService
from app.services.db.models import (
    SEED_DEMO_PREFIX,
    CandidateProfile,
    CandidateSkill,
    Company,
    CompanyMember,
    CompanyRole,
    Consent,
    ConsentKind,
    ContactReveal,
    DeclineReason,
    Education,
    FspAthleteRank,
    FspAward,
    FspDiscipline,
    FspEvent,
    FspLink,
    FspResult,
    FspSportRank,
    Grade,
    HiringNeed,
    HiringNeedSkill,
    Invitation,
    InvitationMessage,
    InvitationStatus,
    Skill,
    SkillKind,
    Specialization,
    User,
    UserRole,
    WorkExperience,
    WorkFormat,
)
from app.services.db.session import build_engine, build_session_maker
from app.services.demo import DEMO_EMPLOYER_SUB
from app.services.scoring import ScoringClient

DEMO_PREFIX = SEED_DEMO_PREFIX
DEFAULT_COUNT = 90
# Доля демо-кандидатов с привязанным ФСП ID.
FSP_LINKED_SHARE = 0.45
FSP_AWARD_WEIGHTS = {
    FspAward.WINNER: 1,
    FspAward.PRIZE: 3,
    FspAward.FINALIST: 3,
    FspAward.PARTICIPANT: 4,
}
FSP_EVENTS = [
    (
        "Чемпионат России по спортивному программированию",
        FspDiscipline.PRODUCT,
        date(2025, 11, 20),
    ),
    (
        "Чемпионат России по спортивному программированию",
        FspDiscipline.ALGORITHMIC,
        date(2025, 11, 22),
    ),
    ("Кубок России по спортивному программированию", FspDiscipline.PRODUCT, date(2025, 4, 18)),
    ("Кубок России по спортивному программированию", FspDiscipline.INFOSEC, date(2025, 4, 19)),
    # Сам хакатон ЛЦТ: соревнование ФСП по продуктовому программированию (календарь ФСП).
    (
        "Международные соревнования «Лидеры цифровой трансформации»",
        FspDiscipline.PRODUCT,
        date(2025, 10, 17),
    ),
    ("Первенство Центрального федерального округа", FspDiscipline.ALGORITHMIC, date(2026, 3, 14)),
    ("Первенство Приволжского федерального округа", FspDiscipline.PRODUCT, date(2026, 2, 21)),
    (
        "Кубок Федерации спортивного программирования, отборочный этап",
        FspDiscipline.ALGORITHMIC,
        date(2024, 12, 7),
    ),
    ("Чемпионат Сибирского федерального округа", FspDiscipline.ROBOTICS, date(2025, 9, 12)),
    ("Чемпионат Северо-Западного федерального округа", FspDiscipline.UAS, date(2026, 5, 30)),
]
EKP_DEMO_BASE = 1101770002000101
TEAMS = ["404 Not Found", "Синтаксический сахар", "Бинарные котики", "Null Pointer", "Стек и ко"]
# Тестовые спортсмены mock-реалма fsp-id (infra/keycloak/realm-fsp-id.json, пароль fsp-demo):
# индекс события, результат, место.
ATHLETES: dict[str, list[tuple[int, FspAward, int | None]]] = {
    "FSP-100001": [(0, FspAward.WINNER, 1), (1, FspAward.PRIZE, 3), (4, FspAward.FINALIST, 7)],
    "FSP-100002": [(3, FspAward.FINALIST, 9), (5, FspAward.PARTICIPANT, None)],
    # Только участие: в подборках не засчитывается, так советуют организаторы.
    "FSP-100003": [(7, FspAward.PARTICIPANT, None), (6, FspAward.PARTICIPANT, None)],
    # FSP-100004 без истории ФСП: обязательный случай ТЗ.
}
# Разряды и звания тестовых спортсменов (присваиваются приказами по результатам).
ATHLETE_RANKS = {
    "FSP-100001": (FspSportRank.CMS, date(2025, 12, 15)),
    "FSP-100002": (FspSportRank.FIRST, date(2025, 6, 2)),
}
# Разряд засеянного кандидата: по его лучшему результату; участие разряда не даёт.
BEST_AWARD_RANK = {
    FspAward.WINNER: FspSportRank.CMS,
    FspAward.PRIZE: FspSportRank.FIRST,
    FspAward.FINALIST: FspSportRank.SECOND,
}
# Доля кандидатов, прошедших тест; остальные видны с пометкой «грейд не подтверждён».
TESTED_SHARE = 0.8
# Доля тех, кто заявляет грейд на ступень выше истинного.
OVERCLAIM_SHARE = 0.2
# Доля прошедших тест, кто решает кейсы недели (1-3 за последний месяц).
CASE_ACTIVE_SHARE = 0.4

# История приглашений демо-компании: (статус, через сколько часов после принятия компания
# написала кандидату или причина отказа). Даёт репутацию «пишет за 3 дня в 83%, обычно через
# 8 ч, отзывает 10%».
DEMO_HISTORY: list[tuple[InvitationStatus, int | DeclineReason | None]] = [
    (InvitationStatus.ACCEPTED, 4),
    (InvitationStatus.ACCEPTED, 20),
    (InvitationStatus.ACCEPTED, 2),
    (InvitationStatus.ACCEPTED, 30),
    (InvitationStatus.ACCEPTED, 8),
    (InvitationStatus.ACCEPTED, None),
    (InvitationStatus.DECLINED, DeclineReason.SALARY),
    (InvitationStatus.DECLINED, DeclineReason.FORMAT),
    (InvitationStatus.WITHDRAWN, None),
    (InvitationStatus.EXPIRED, None),
]

# Диапазоны истинного θ по уровню грейда: те же, что в scoring/validation.
THETA_BANDS = {0: (-2.5, -1.0), 1: (-1.0, 0.0), 2: (0.0, 1.0), 3: (1.0, 1.8), 4: (1.8, 2.8)}
GRADE_WEIGHTS = {0: 1, 1: 3, 2: 4, 3: 3, 4: 1}
EXPERIENCE_YEARS = {0: (0, 0), 1: (0, 1), 2: (2, 4), 3: (4, 8), 4: (7, 12)}
SALARY_K = {0: (50, 80), 1: (90, 150), 2: (170, 280), 3: (290, 450), 4: (400, 600)}

STACKS = {
    "backend": {
        "core": ["python", "sql", "git", "docker", "linux"],
        "extra": [
            "go",
            "java",
            "postgresql",
            "redis",
            "kafka",
            "kubernetes",
            "fastapi",
            "django",
            "spring",
            "rabbitmq",
            "grpc",
            "clickhouse",
            "ci-cd",
        ],
        "positions": ["Backend-разработчик", "Python-разработчик", "Разработчик серверной части"],
    },
    "frontend": {
        "core": ["javascript", "typescript", "react", "git"],
        "extra": [
            "vue",
            "angular",
            "nextjs",
            "nodejs",
            "graphql",
            "playwright",
            "svelte",
            "docker",
            "ci-cd",
        ],
        "positions": ["Frontend-разработчик", "React-разработчик", "Веб-разработчик"],
    },
    "data-science": {
        "core": ["python", "pandas", "numpy", "sql"],
        "extra": [
            "scikit-learn",
            "pytorch",
            "tensorflow",
            "spark",
            "airflow",
            "clickhouse",
            "postgresql",
            "docker",
        ],
        "positions": ["Data Scientist", "ML-инженер", "Аналитик данных"],
    },
}
FIRST_NAMES = [
    "Алексей",
    "Мария",
    "Иван",
    "Анна",
    "Дмитрий",
    "Екатерина",
    "Сергей",
    "Ольга",
    "Никита",
    "Дарья",
    "Артём",
    "Полина",
    "Михаил",
    "Софья",
    "Егор",
    "Алина",
]
LAST_NAMES = [
    "Смирнов",
    "Иванова",
    "Кузнецов",
    "Попова",
    "Соколов",
    "Лебедева",
    "Козлов",
    "Новикова",
    "Морозов",
    "Волкова",
    "Павлов",
    "Фёдорова",
    "Орлов",
    "Зайцева",
]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород"]
UNIVERSITIES = ["МГТУ им. Н. Э. Баумана", "ИТМО", "МФТИ", "НИУ ВШЭ", "УрФУ", "НГУ", "КФУ"]
ABOUT = {
    0: "Учусь и делаю пет-проекты, участвую в хакатонах.",
    1: "Пишу продакшен-код под присмотром наставника, быстро разбираюсь в новом.",
    2: "Самостоятельно веду задачи от постановки до релиза, ревьюю код коллег.",
    3: "Проектирую сервисы под нагрузку, отвечаю за надёжность и качество.",
    4: "Руковожу командой разработки, выстраиваю процессы и архитектуру.",
}


async def _seed_registry(session: AsyncSession) -> list[FspEvent]:
    """Mock реестра ФСП целиком демо-данные: пересоздаётся при каждом запуске."""
    await session.execute(delete(FspResult))
    await session.execute(delete(FspEvent))
    await session.execute(delete(FspAthleteRank))
    # ponytail: демо-номера в формате ЕКП (16 цифр), не настоящие, реестр целиком mock.
    events = [
        FspEvent(
            title=t, discipline=d, starts_on=day, ekp_number=f"{EKP_DEMO_BASE + index * 137:016d}"
        )
        for index, (t, d, day) in enumerate(FSP_EVENTS)
    ]
    session.add_all(events)
    await session.flush()
    rng = Random(7)
    for fsp_id, results in ATHLETES.items():
        for index, award, place in results:
            result = _result(events[index], fsp_id, award, rng)
            result.place = place
            session.add(result)
    for fsp_id, (rank, assigned_on) in ATHLETE_RANKS.items():
        session.add(FspAthleteRank(fsp_id=fsp_id, rank=rank, assigned_on=assigned_on))
    return events


def _result(event: FspEvent, fsp_id: str, award: FspAward, rng: Random) -> FspResult:
    places = {FspAward.WINNER: (1, 1), FspAward.PRIZE: (2, 3), FspAward.FINALIST: (4, 15)}
    team = rng.choice(TEAMS) if event.discipline == FspDiscipline.PRODUCT else None
    return FspResult(
        event_id=event.id,
        fsp_id=fsp_id,
        award=award,
        place=rng.randint(*places[award]) if award in places else None,
        team_name=team,
    )


def _probability(theta: float, a: float, b: float) -> float:
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


async def _seed_demo_company(
    session: AsyncSession,
    candidates: list[User],
    specialization: Specialization,
    grade: Grade,
    skills: dict[str, Skill],
) -> None:
    """Компания с историей приглашений: у неё есть репутация, и она приглашает жюри."""
    owner = User(
        keycloak_sub=DEMO_EMPLOYER_SUB,
        email="hr@primer.demo.fsp.invalid",
        first_name="Ольга",
        last_name="Кадрова",
        role=UserRole.EMPLOYER,
    )
    company = Company(
        name="Пример Технологии",
        description="Финтех-продукт: платежи и выплаты для малого бизнеса. Демо-компания стенда.",
        contact_email=owner.email,
        trust_level=1,
    )
    session.add_all([owner, company])
    await session.flush()
    session.add(CompanyMember(user_id=owner.id, company_id=company.id, role=CompanyRole.OWNER))
    need = HiringNeed(
        company_id=company.id,
        created_by_id=owner.id,
        title="Python-разработчик в платёжную команду",
        description=(
            "Платёжный шлюз под нагрузкой: PostgreSQL, очереди, идемпотентность. Ищем инженера, "
            "который сам доводит задачи до продакшена."
        ),
        specialization_id=specialization.id,
        grade_id=grade.id,
        work_formats=["remote", "hybrid"],
        city="Москва",
        salary_from_rub=220_000,
        salary_to_rub=320_000,
        skills=[
            HiringNeedSkill(skill_id=skills[slug].id, must_have=must)
            for slug, must in (("python", True), ("postgresql", True), ("kafka", False))
            if slug in skills
        ],
    )
    session.add(need)
    await session.flush()
    now = datetime.now(UTC)
    for n, (candidate, (status, outcome)) in enumerate(
        zip(candidates, DEMO_HISTORY, strict=False)
    ):
        sent = now - timedelta(days=40 - 3 * n)
        answered = sent + timedelta(days=1) if status != InvitationStatus.EXPIRED else None
        invitation = Invitation(
            company_id=company.id,
            candidate_user_id=candidate.id,
            sent_by_id=owner.id,
            need_id=need.id,
            title=need.title,
            description=need.description,
            salary_from_rub=need.salary_from_rub,
            salary_to_rub=need.salary_to_rub,
            contact=owner.email,
            status=status,
            decline_reason=outcome if isinstance(outcome, DeclineReason) else None,
            created_at=sent,
            viewed_at=sent + timedelta(hours=6),
            answered_at=answered,
            expires_at=sent + timedelta(days=7),
        )
        session.add(invitation)
        await session.flush()
        if status == InvitationStatus.ACCEPTED and answered is not None:
            session.add(
                ContactReveal(
                    company_id=company.id,
                    candidate_user_id=candidate.id,
                    invitation_id=invitation.id,
                    granted_at=answered,
                )
            )
            if isinstance(outcome, int):
                replied = answered + timedelta(hours=outcome)
                session.add_all(
                    [
                        InvitationMessage(
                            invitation_id=invitation.id,
                            author_id=owner.id,
                            body="Здравствуйте! Спасибо, что откликнулись. Удобно созвониться?",
                            created_at=replied,
                        ),
                        InvitationMessage(
                            invitation_id=invitation.id,
                            author_id=candidate.id,
                            body="Добрый день! Да, давайте завтра после обеда.",
                            created_at=replied + timedelta(hours=1),
                        ),
                    ]
                )
    await session.commit()


# Опубликованные вакансии второй демо-компании: на них откликается демо-кандидат жюри.
# (направление, уровень грейда, должность, вилка в тыс. ₽, навыки: slug → обязательный)
DEMO_VACANCIES = [
    ("backend", 1, "Junior Python-разработчик", (120, 170), {"python": True, "sql": True}),
    ("backend", 2, "Go-разработчик в команду биллинга", (230, 330), {"go": True, "kafka": False}),
    ("backend", 3, "Senior backend-инженер", (350, 480), {"python": True, "kubernetes": True}),
    (
        "frontend",
        2,
        "Frontend-разработчик (React)",
        (200, 290),
        {"react": True, "typescript": True},
    ),
    ("data-science", 2, "Data Scientist в кредитный скоринг", (220, 320), {"pandas": True}),
]


async def _seed_vacancies(
    session: AsyncSession,
    specializations: dict[str, Specialization],
    grades: dict[int, Grade],
    skills: dict[str, Skill],
) -> None:
    owner = User(
        keycloak_sub=f"{DEMO_EMPLOYER_SUB}-2",
        email="jobs@sever.demo.fsp.invalid",
        first_name="Илья",
        last_name="Северов",
        role=UserRole.EMPLOYER,
    )
    company = Company(
        name="Северный Код",
        description="Продуктовая разработка для логистики и финансов. Демо-компания стенда.",
        contact_email=owner.email,
        trust_level=1,
    )
    session.add_all([owner, company])
    await session.flush()
    session.add(CompanyMember(user_id=owner.id, company_id=company.id, role=CompanyRole.OWNER))
    now = datetime.now(UTC)
    for n, (slug, level, title, (low, high), need_skills) in enumerate(DEMO_VACANCIES):
        session.add(
            HiringNeed(
                company_id=company.id,
                created_by_id=owner.id,
                title=title,
                description=f"{title}: продуктовая команда, код-ревью, релизы каждую неделю.",
                specialization_id=specializations[slug].id,
                grade_id=grades[level].id,
                work_formats=["remote", "hybrid"],
                city="Санкт-Петербург",
                salary_from_rub=low * 1000,
                salary_to_rub=high * 1000,
                published_at=now - timedelta(days=n),
                skills=[
                    HiringNeedSkill(skill_id=skills[s].id, must_have=must)
                    for s, must in need_skills.items()
                    if s in skills
                ],
            )
        )
    await session.commit()


async def seed(count: int) -> None:
    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    session_maker = build_session_maker(engine)
    rng = Random(2026)
    async with (
        httpx.AsyncClient(base_url=settings.scoring_url, timeout=30) as http,
        session_maker() as session,
    ):
        scoring = ScoringClient(http)
        demo_users = select(User.id).where(User.keycloak_sub.startswith(DEMO_PREFIX))
        # Компания не удаляется каскадом вместе с владельцем: удаляем явно.
        await session.execute(
            delete(Company).where(
                Company.id.in_(
                    select(CompanyMember.company_id).where(CompanyMember.user_id.in_(demo_users))
                )
            )
        )
        await session.execute(delete(User).where(User.keycloak_sub.startswith(DEMO_PREFIX)))
        events = await _seed_registry(session)
        await session.commit()

        specializations = {
            s.slug: s
            for s in await session.scalars(
                select(Specialization).where(Specialization.slug.in_(list(STACKS)))
            )
        }
        grades = {g.level: g for g in await session.scalars(select(Grade))}
        skills = {
            s.slug: s
            for s in await session.scalars(select(Skill).where(Skill.kind == SkillKind.TECHNOLOGY))
        }
        soft = list(await session.scalars(select(Skill).where(Skill.kind == SkillKind.SOFT)))
        levels = [lvl for lvl, w in GRADE_WEIGHTS.items() for _ in range(w)]
        backend_candidates: list[User] = []

        for n in range(1, count + 1):
            slug = list(STACKS)[n % len(STACKS)]
            stack = STACKS[slug]
            level = rng.choice(levels)
            theta = rng.uniform(*THETA_BANDS[level])
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            if first.endswith(("а", "я")) and not last.endswith("а"):
                last += "а"
            user = User(
                keycloak_sub=f"{DEMO_PREFIX}{n}",
                email=f"demo{n}@demo.fsp.invalid",
                first_name=first,
                last_name=last,
                role=UserRole.CANDIDATE,
            )
            session.add(user)
            await session.flush()
            for kind in (ConsentKind.DATA_PROCESSING, ConsentKind.PROFILE_PUBLICATION):
                session.add(
                    Consent(
                        user_id=user.id,
                        kind=kind,
                        document_version=CONSENT_DOCUMENTS[kind].version,
                    )
                )

            low, high = EXPERIENCE_YEARS[level]
            years = rng.randint(low, high)
            today = date(2026, 10, 1)
            started = date(today.year - years, rng.randint(1, 12), 1)
            chosen = stack["core"][: rng.randint(2, len(stack["core"]))] + rng.sample(
                stack["extra"], rng.randint(1, 3 + level)
            )
            profile = CandidateProfile(
                user_id=user.id,
                last_name=last,
                first_name=first,
                middle_name="",
                phone=f"+7 9{rng.randint(10, 99)} {rng.randint(1_000_000, 9_999_999)}",
                telegram=f"demo_{n:04d}",
                specialization_id=specializations[slug].id,
                work_formats=rng.sample([f.value for f in WorkFormat], rng.randint(1, 3)),
                city=rng.choice(CITIES),
                salary_expectation_rub=rng.randint(*SALARY_K[level]) * 1000,
                about=ABOUT[level],
                skills=[
                    CandidateSkill(kind=SkillKind.TECHNOLOGY, skill_id=skills[s].id)
                    for s in dict.fromkeys(chosen)
                    if s in skills
                ]
                + [
                    CandidateSkill(kind=SkillKind.SOFT, skill_id=s.id)
                    for s in rng.sample(soft, min(2, len(soft)))
                ],
                experience=(
                    [
                        WorkExperience(
                            company_name="Демо-компания",
                            position=rng.choice(stack["positions"]),
                            started_on=started,
                            ended_on=None,
                            description="",
                        )
                    ]
                    if years
                    else []
                ),
                education=[
                    Education(
                        institution=rng.choice(UNIVERSITIES),
                        specialty="Прикладная информатика",
                        graduation_year=today.year - years + rng.choice([0, 1]),
                    )
                ],
            )
            session.add(profile)
            if rng.random() < FSP_LINKED_SHARE:
                fsp_id = f"FSP-2{n:05d}"
                # Привязка ФСП ID требует согласия на получение данных реестра.
                session.add(
                    Consent(
                        user_id=user.id,
                        kind=ConsentKind.FSP_DATA,
                        document_version=CONSENT_DOCUMENTS[ConsentKind.FSP_DATA].version,
                    )
                )
                session.add(FspLink(user_id=user.id, fsp_id=fsp_id))
                awards: dict[FspAward, date] = {}
                for event in rng.sample(events, rng.randint(1, 3)):
                    award = rng.choices(list(FSP_AWARD_WEIGHTS), list(FSP_AWARD_WEIGHTS.values()))[
                        0
                    ]
                    awards[award] = max(awards.get(award, event.starts_on), event.starts_on)
                    session.add(_result(event, fsp_id, award, rng))
                best = next((a for a in BEST_AWARD_RANK if a in awards), None)
                if best is not None:
                    rank = BEST_AWARD_RANK[best]
                    session.add(FspAthleteRank(fsp_id=fsp_id, rank=rank, assigned_on=awards[best]))
            await session.commit()

            if rng.random() < TESTED_SHARE:
                await _take_test(
                    session, scoring, user, specializations[slug].id, grades, level, theta, rng
                )
                if rng.random() < CASE_ACTIVE_SHARE:
                    await _solve_cases(session, scoring, user, theta, rng)
            if slug == "backend":
                backend_candidates.append(user)
            sys.stderr.write(f"{n}/{count}: {slug}, истинный уровень {level}\n")
        await _seed_demo_company(
            session, backend_candidates, specializations["backend"], grades[2], skills
        )
        await _seed_vacancies(session, specializations, grades, skills)
    await engine.dispose()


async def _take_test(
    session: AsyncSession,
    scoring: ScoringClient,
    user: User,
    specialization_id: int,
    grades: dict[int, Grade],
    level: int,
    theta: float,
    rng: Random,
) -> None:
    """Тест через сервис попыток. Заявляют свой уровень, иногда на ступень выше."""
    claimed = min(level + (1 if rng.random() < OVERCLAIM_SHARE else 0), max(grades))
    service = AssessmentService(session, ConsentService(session), scoring)
    attempt = await service.start(user, specialization_id, grades[claimed].id)
    answered: set[int] = set()
    # Решение у порога продлевает попытку новыми заданиями: отвечаем и на них.
    while attempt.finished_at is None:
        for item in attempt.items:
            if item.position in answered:
                continue
            correct = rng.random() < _probability(theta, item.a, item.b)
            response = item.answer if correct else None
            await service.save_answer(user, attempt.id, item.position, response)
            answered.add(item.position)
        attempt = await service.finish(user, attempt.id)


async def _solve_cases(
    session: AsyncSession, scoring: ScoringClient, user: User, theta: float, rng: Random
) -> None:
    """Кейсы недели за прошлые недели через настоящий сервис; ответ: по 2PL, как в тесте."""
    service = CaseService(session, scoring)
    this_week = week_start(datetime.now(UTC).date())
    for weeks_ago in sorted(rng.sample(range(1, 5), rng.randint(1, 3))):
        week = this_week - timedelta(weeks=weeks_ago)
        case = await service.create(user, week)
        correct = rng.random() < _probability(theta, case.a, case.b)
        case.response = case.answer if correct else None
        case.is_correct = correct
        case.answered_at = datetime.combine(week, time(12), UTC) + timedelta(days=2)
    await session.commit()


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_COUNT
    asyncio.run(seed(count))


if __name__ == "__main__":
    main()
