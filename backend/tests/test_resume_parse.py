from datetime import date

from app.services.resume import DictionarySkill, find_skills, parse_resume

TODAY = date(2026, 10, 7)

TECH = [
    DictionarySkill(1, "Python", ["py", "python3"]),
    DictionarySkill(2, "Go", ["golang"]),
    DictionarySkill(3, "C", []),
    DictionarySkill(4, "C++", ["cpp"]),
    DictionarySkill(5, "PostgreSQL", ["postgres"]),
    DictionarySkill(6, "Kubernetes", ["k8s"]),
    DictionarySkill(7, "Node.js", ["nodejs"]),
    DictionarySkill(8, "React", ["react.js"]),
]
SOFT = [
    DictionarySkill(101, "Работа в команде", ["командная работа"]),
    DictionarySkill(102, "Наставничество", ["менторство"]),
]

HH_STYLE = """Иванов Иван Иванович
Senior Python-разработчик
+7 (912) 345-67-89
ivan.ivanov@example.ru
Telegram: @ivan_dev
github.com/ivanov

Опыт работы
Senior Python-разработчик
ООО «Ромашка»
Март 2021 — настоящее время (5 лет 8 месяцев)
Разрабатывал сервисы на Python и golang, PostgreSQL, деплой в k8s.
Менторство двух стажёров.

Python-разработчик
АО «Лютик»
Январь 2018 — Февраль 2021
Бэкенд на Python 3, командная работа.

Навыки
Python, Go, PostgreSQL, Kubernetes
"""

ONE_LINE_PERIODS = """Петрова Анна
Frontend-разработчик (Middle)
anna@mail.ru, 8 916 123 45 67
t.me/anna_front

Опыт
01.2022 – н.в. | Frontend-разработчик | Яндекс
06.2019 – 12.2021 | Junior frontend developer | Студия Пикс
Стек: React, Node.js, C++ в университете
"""

YEARS_ONLY = """Data Scientist
Опыт работы
2019 — 2021
Data Scientist
Сбер
Machine learning, Python
"""


def test_hh_style_resume() -> None:
    parsed = parse_resume(HH_STYLE, TECH, SOFT, TODAY)
    assert parsed.phone == "+7 912 345-67-89"
    assert parsed.email == "ivan.ivanov@example.ru"
    assert parsed.telegram == "ivan_dev"
    assert parsed.github == "ivanov"
    assert parsed.technology_ids == [1, 2, 5, 6]
    assert parsed.soft_skill_ids == [101, 102]
    assert [(e.position, e.company_name) for e in parsed.experience] == [
        ("Senior Python-разработчик", "ООО «Ромашка»"),
        ("Python-разработчик", "АО «Лютик»"),
    ]
    assert parsed.experience[0].started_on == date(2021, 3, 1)
    assert parsed.experience[0].ended_on is None
    assert parsed.experience[1].ended_on == date(2021, 2, 1)
    # Январь 2018 — октябрь 2026 без пересечений: 8 лет 10 месяцев.
    assert parsed.total_experience_months == 106
    assert parsed.grade_level == 3
    assert parsed.specialization_slug == "backend"


def test_periods_on_one_line_with_separators() -> None:
    parsed = parse_resume(ONE_LINE_PERIODS, TECH, SOFT, TODAY)
    assert parsed.phone == "+7 916 123-45-67"
    assert parsed.telegram == "anna_front"
    assert [(e.position, e.company_name) for e in parsed.experience] == [
        ("Frontend-разработчик", "Яндекс"),
        ("Junior frontend developer", "Студия Пикс"),
    ]
    assert parsed.experience[1].started_on == date(2019, 6, 1)
    # Грейд берётся по последней должности, а она без пометки; тогда по заголовку резюме.
    assert parsed.grade_level == 2
    assert parsed.specialization_slug == "frontend"
    assert set(parsed.technology_ids) == {4, 7, 8}


def test_year_only_period_counts_whole_years() -> None:
    parsed = parse_resume(YEARS_ONLY, TECH, SOFT, TODAY)
    assert len(parsed.experience) == 1
    entry = parsed.experience[0]
    assert (entry.started_on, entry.ended_on) == (date(2019, 1, 1), date(2021, 12, 1))
    assert entry.position == "Data Scientist"
    assert entry.company_name == "Сбер"
    assert parsed.total_experience_months == 36
    assert parsed.specialization_slug == "data-science"


def test_salary_and_years_are_not_phones_or_periods() -> None:
    text = "Ожидания: 250 000-300 000 ₽. Окончил вуз в 2015-2019 годах? Нет: 2015 — диплом."
    parsed = parse_resume(text, TECH, SOFT, TODAY)
    assert parsed.phone == ""
    # «2015-2019» похоже на период; должности рядом нет, но период честно распознан.
    assert all(entry.position == "" for entry in parsed.experience)


def test_short_skill_names_need_exact_case() -> None:
    # «go» в обычной фразе и «C» внутри «C++» не навыки Go и C.
    assert find_skills("Let's go! Писал на C++ и cpp.", TECH) == [4]
    assert find_skills("Языки: C, Go.", TECH) == [2, 3]


def test_no_resume_data_gives_empty_draft() -> None:
    parsed = parse_resume("Просто текст без резюме, " * 5, TECH, SOFT, TODAY)
    assert parsed.experience == []
    assert parsed.grade_level is None
    assert parsed.specialization_slug is None
    assert parsed.technology_ids == []


COMPANY_AND_POSITION_ON_ONE_LINE = """Опыт работы
ООО «Яндекс», Frontend-разработчик
Март 2021 — по настоящее время
Разработка интерфейсов личного кабинета, React + TypeScript.

ООО «Тинькофф», Junior Frontend-разработчик
Сентябрь 2019 — Февраль 2021
Вёрстка и поддержка внутренних сервисов.
"""


def test_company_and_position_on_one_line() -> None:
    # Компания не должна браться у соседнего места работы, а описание не должно
    # становиться компанией.
    parsed = parse_resume(COMPANY_AND_POSITION_ON_ONE_LINE, TECH, SOFT, TODAY)
    assert [(e.position, e.company_name) for e in parsed.experience] == [
        ("Frontend-разработчик", "ООО «Яндекс»"),
        ("Junior Frontend-разработчик", "ООО «Тинькофф»"),
    ]


def test_postgresql_is_not_a_telegram_nick() -> None:
    parsed = parse_resume("Навыки: Python, Django, PostgreSQL, Docker", TECH, SOFT, TODAY)
    assert parsed.telegram == ""
    assert parse_resume("tg: ivan_dev", TECH, SOFT, TODAY).telegram == "ivan_dev"
