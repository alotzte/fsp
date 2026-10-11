"""seed dictionaries

Revision ID: e072abcaad0d
Revises: 38736fc5ecf9
Create Date: 2026-10-05 17:49:45.139432

Начальные справочники. Дальше их правят в админке, поэтому вставка не трогает
уже существующие slug (ON CONFLICT DO NOTHING), а downgrade удаляет только свои slug.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e072abcaad0d"
down_revision: str | None = "38736fc5ecf9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPECIALIZATIONS = [
    ("backend", "Backend-разработка"),
    ("frontend", "Frontend-разработка"),
    ("fullstack", "Fullstack-разработка"),
    ("mobile", "Мобильная разработка"),
    ("devops", "DevOps / SRE"),
    ("data-science", "Data Science / ML"),
    ("data-engineering", "Data Engineering"),
    ("qa", "Тестирование (QA)"),
    ("analytics", "Системный и бизнес-анализ"),
    ("gamedev", "Разработка игр"),
    ("security", "Информационная безопасность"),
    ("embedded", "Embedded-разработка"),
]

GRADES = [
    ("intern", "Стажёр", 0),
    ("junior", "Junior", 1),
    ("middle", "Middle", 2),
    ("senior", "Senior", 3),
    ("lead", "Lead", 4),
]

# (slug, название, синонимы в нижнем регистре)
TECHNOLOGIES = [
    ("python", "Python", ["py", "python3"]),
    ("java", "Java", []),
    ("kotlin", "Kotlin", []),
    ("go", "Go", ["golang"]),
    ("rust", "Rust", []),
    ("cpp", "C++", ["c plus plus", "cpp"]),
    ("c", "C", []),
    ("csharp", "C#", ["c sharp", "csharp", ".net c#"]),
    ("dotnet", ".NET", ["dotnet", "asp.net", "asp.net core"]),
    ("javascript", "JavaScript", ["js", "ecmascript", "es6"]),
    ("typescript", "TypeScript", ["ts"]),
    ("php", "PHP", []),
    ("ruby", "Ruby", []),
    ("swift", "Swift", []),
    ("dart", "Dart", []),
    ("scala", "Scala", []),
    ("sql", "SQL", []),
    ("react", "React", ["reactjs", "react.js"]),
    ("vue", "Vue", ["vuejs", "vue.js"]),
    ("angular", "Angular", ["angularjs"]),
    ("svelte", "Svelte", []),
    ("nextjs", "Next.js", ["next", "nextjs"]),
    ("nodejs", "Node.js", ["node", "nodejs"]),
    ("django", "Django", []),
    ("fastapi", "FastAPI", []),
    ("flask", "Flask", []),
    ("spring", "Spring", ["spring boot", "springboot"]),
    ("laravel", "Laravel", []),
    ("flutter", "Flutter", []),
    ("react-native", "React Native", ["rn"]),
    ("android", "Android", []),
    ("ios", "iOS", []),
    ("postgresql", "PostgreSQL", ["postgres", "pg"]),
    ("mysql", "MySQL", []),
    ("mongodb", "MongoDB", ["mongo"]),
    ("redis", "Redis", []),
    ("clickhouse", "ClickHouse", []),
    ("elasticsearch", "Elasticsearch", ["elastic", "es"]),
    ("kafka", "Kafka", ["apache kafka"]),
    ("rabbitmq", "RabbitMQ", ["rabbit"]),
    ("docker", "Docker", []),
    ("kubernetes", "Kubernetes", ["k8s"]),
    ("terraform", "Terraform", []),
    ("ansible", "Ansible", []),
    ("linux", "Linux", []),
    ("git", "Git", []),
    ("ci-cd", "CI/CD", ["ci", "cicd", "gitlab ci", "github actions"]),
    ("aws", "AWS", ["amazon web services"]),
    ("pandas", "pandas", []),
    ("numpy", "NumPy", []),
    ("pytorch", "PyTorch", ["torch"]),
    ("tensorflow", "TensorFlow", ["tf"]),
    ("scikit-learn", "scikit-learn", ["sklearn"]),
    ("spark", "Apache Spark", ["spark", "pyspark"]),
    ("airflow", "Apache Airflow", ["airflow"]),
    ("unity", "Unity", []),
    ("unreal", "Unreal Engine", ["ue", "ue5", "unreal"]),
    ("graphql", "GraphQL", []),
    ("grpc", "gRPC", []),
    ("selenium", "Selenium", []),
    ("playwright", "Playwright", []),
    ("algorithms", "Алгоритмы и структуры данных", ["алгоритмы", "algorithms", "dsa"]),
]

SOFT_SKILLS = [
    ("teamwork", "Работа в команде", ["командная работа"]),
    ("communication", "Коммуникация", []),
    ("mentoring", "Наставничество", ["менторство"]),
    ("leadership", "Лидерство", []),
    ("time-management", "Тайм-менеджмент", []),
    ("problem-solving", "Решение задач", []),
    ("critical-thinking", "Критическое мышление", []),
    ("self-learning", "Самообучение", ["обучаемость"]),
    ("presentation", "Публичные выступления", ["презентации"]),
    ("stress-resistance", "Стрессоустойчивость", []),
    ("responsibility", "Ответственность", []),
    ("english", "Английский язык", ["english"]),
]

INDUSTRIES = [
    ("fintech", "Финтех и банки"),
    ("ecommerce", "E-commerce и ритейл"),
    ("edtech", "Образование (EdTech)"),
    ("gamedev", "Игры"),
    ("healthtech", "Медицина (HealthTech)"),
    ("govtech", "Госсектор"),
    ("telecom", "Телеком"),
    ("industry", "Промышленность"),
    ("logistics", "Логистика и транспорт"),
    ("media", "Медиа и развлечения"),
    ("security", "Информационная безопасность"),
    ("b2b-saas", "B2B SaaS"),
    ("it-outsourcing", "ИТ-аутсорсинг и консалтинг"),
    ("other", "Другое"),
]


def _insert_ignoring_existing(table: str, rows: list[dict[str, object]]) -> None:
    columns = list(rows[0])
    statement = sa.text(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + column for column in columns)}) "
        "ON CONFLICT (slug) DO NOTHING"
    )
    op.get_bind().execute(statement, rows)


def upgrade() -> None:
    _insert_ignoring_existing(
        "specializations", [{"slug": slug, "title": title} for slug, title in SPECIALIZATIONS]
    )
    # level уникален: если в БД уже есть грейды с другими slug на тех же уровнях, пропускаем.
    op.get_bind().execute(
        sa.text(
            "INSERT INTO grades (slug, title, level) VALUES (:slug, :title, :level) "
            "ON CONFLICT DO NOTHING"
        ),
        [{"slug": slug, "title": title, "level": level} for slug, title, level in GRADES],
    )
    _insert_ignoring_existing(
        "skills",
        [
            {"kind": kind, "slug": slug, "title": title, "aliases": aliases}
            for kind, items in (("technology", TECHNOLOGIES), ("soft", SOFT_SKILLS))
            for slug, title, aliases in items
        ],
    )
    _insert_ignoring_existing(
        "industries", [{"slug": slug, "title": title} for slug, title in INDUSTRIES]
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table, slugs in (
        ("industries", [slug for slug, _ in INDUSTRIES]),
        ("skills", [slug for slug, _, _ in TECHNOLOGIES + SOFT_SKILLS]),
        ("grades", [slug for slug, _, _ in GRADES]),
        ("specializations", [slug for slug, _ in SPECIALIZATIONS]),
    ):
        bind.execute(sa.text(f"DELETE FROM {table} WHERE slug = ANY(:slugs)"), {"slugs": slugs})
