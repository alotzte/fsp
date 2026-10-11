from typing import Any, ClassVar

from sqladmin import ModelView

from app.services.db.models import (
    AssessmentAttempt,
    CandidateGrade,
    CandidateProfile,
    Company,
    CompanyMember,
    CompanyReport,
    FspAthleteRank,
    FspEvent,
    FspLink,
    FspResult,
    Grade,
    HiringNeed,
    Industry,
    Invitation,
    Skill,
    Specialization,
    User,
)


class SpecializationAdmin(ModelView, model=Specialization):
    name = "Специализация"
    name_plural = "Специализации"
    column_list: ClassVar[list[Any]] = [
        Specialization.id,
        Specialization.slug,
        Specialization.title,
    ]
    column_searchable_list: ClassVar[list[Any]] = [
        Specialization.title,
        Specialization.slug,
    ]


class GradeAdmin(ModelView, model=Grade):
    name = "Грейд"
    name_plural = "Грейды"
    column_list: ClassVar[list[Any]] = [Grade.id, Grade.slug, Grade.title, Grade.level]
    column_default_sort = "level"


class UserAdmin(ModelView, model=User):
    # Учётки создаёт Keycloak при регистрации; здесь только просмотр.
    name = "Пользователь"
    name_plural = "Пользователи"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [User.email, User.role, User.created_at]
    column_searchable_list: ClassVar[list[Any]] = [User.email]
    column_default_sort = ("created_at", True)


class CompanyAdmin(ModelView, model=Company):
    name = "Компания"
    name_plural = "Компании"
    can_create = False
    column_list: ClassVar[list[Any]] = [
        Company.name,
        Company.trust_level,
        Company.verified_domain,
        Company.frozen_at,
        Company.created_at,
    ]
    column_searchable_list: ClassVar[list[Any]] = [Company.name]
    # Разбор жалоб: снять заморозку (очистить frozen_at), поднять доверие (trust_level 1).
    form_columns: ClassVar[list[Any]] = [
        Company.name,
        Company.description,
        Company.trust_level,
        Company.frozen_at,
    ]


class CompanyReportAdmin(ModelView, model=CompanyReport):
    # Жалобы подают кандидаты из карточки приглашения, здесь их разбирают.
    name = "Жалоба на компанию"
    name_plural = "Жалобы на компании"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        CompanyReport.company,
        CompanyReport.reason,
        CompanyReport.created_at,
    ]
    column_default_sort = ("created_at", True)


class CompanyMemberAdmin(ModelView, model=CompanyMember):
    name = "Участник компании"
    name_plural = "Участники компаний"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        CompanyMember.company,
        CompanyMember.user,
        CompanyMember.role,
        CompanyMember.joined_at,
    ]


class SkillAdmin(ModelView, model=Skill):
    name = "Навык"
    name_plural = "Навыки"
    column_list: ClassVar[list[Any]] = [Skill.kind, Skill.title, Skill.aliases]
    column_searchable_list: ClassVar[list[Any]] = [Skill.title]
    column_default_sort = "title"
    form_columns: ClassVar[list[Any]] = [Skill.kind, Skill.slug, Skill.title, Skill.aliases]


class IndustryAdmin(ModelView, model=Industry):
    name = "Отрасль"
    name_plural = "Отрасли"
    column_list: ClassVar[list[Any]] = [Industry.slug, Industry.title]
    column_default_sort = "title"


class CandidateProfileAdmin(ModelView, model=CandidateProfile):
    # Персональные данные: только просмотр, правит их сам кандидат.
    name = "Профиль кандидата"
    name_plural = "Профили кандидатов"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        CandidateProfile.candidate_number,
        CandidateProfile.last_name,
        CandidateProfile.first_name,
        CandidateProfile.city,
        CandidateProfile.updated_at,
    ]
    column_searchable_list: ClassVar[list[Any]] = [CandidateProfile.last_name]


class HiringNeedAdmin(ModelView, model=HiringNeed):
    # Потребности ведёт работодатель в кабинете; здесь только просмотр.
    name = "Потребность"
    name_plural = "Потребности"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        HiringNeed.title,
        HiringNeed.specialization,
        HiringNeed.grade,
        HiringNeed.salary_from_rub,
        HiringNeed.salary_to_rub,
        HiringNeed.published_at,
        HiringNeed.created_at,
    ]
    column_searchable_list: ClassVar[list[Any]] = [HiringNeed.title]
    column_default_sort = ("created_at", True)


class InvitationAdmin(ModelView, model=Invitation):
    # Статусы меняют только стороны приглашения: правка здесь обошла бы правила переходов.
    name = "Приглашение или отклик"
    name_plural = "Приглашения и отклики"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        Invitation.company,
        Invitation.direction,
        Invitation.title,
        Invitation.salary_from_rub,
        Invitation.salary_to_rub,
        Invitation.status,
        Invitation.created_at,
    ]
    column_default_sort = ("created_at", True)


class FspEventAdmin(ModelView, model=FspEvent):
    # Имитация реестра ФСП: синтетические данные, правятся здесь.
    name = "Соревнование ФСП"
    name_plural = "Реестр ФСП: соревнования"
    column_list: ClassVar[list[Any]] = [
        FspEvent.id,
        FspEvent.title,
        FspEvent.discipline,
        FspEvent.starts_on,
        FspEvent.ekp_number,
    ]
    column_labels: ClassVar[dict[Any, str]] = {FspEvent.ekp_number: "№ ЕКП"}
    column_searchable_list: ClassVar[list[Any]] = [FspEvent.title]
    column_default_sort = ("starts_on", True)


class FspResultAdmin(ModelView, model=FspResult):
    name = "Результат ФСП"
    name_plural = "Реестр ФСП: результаты"
    column_list: ClassVar[list[Any]] = [
        FspResult.fsp_id,
        FspResult.event,
        FspResult.award,
        FspResult.place,
        FspResult.team_name,
    ]
    column_searchable_list: ClassVar[list[Any]] = [FspResult.fsp_id]
    form_columns: ClassVar[list[Any]] = [
        FspResult.event,
        FspResult.fsp_id,
        FspResult.award,
        FspResult.place,
        FspResult.team_name,
    ]


class FspAthleteRankAdmin(ModelView, model=FspAthleteRank):
    name = "Разряд ФСП"
    name_plural = "Реестр ФСП: разряды и звания"
    column_list: ClassVar[list[Any]] = [
        FspAthleteRank.fsp_id,
        FspAthleteRank.rank,
        FspAthleteRank.assigned_on,
    ]
    column_searchable_list: ClassVar[list[Any]] = [FspAthleteRank.fsp_id]


class FspLinkAdmin(ModelView, model=FspLink):
    # Привязку делает кандидат через вход в ФСП ID; здесь только просмотр.
    name = "Привязка ФСП ID"
    name_plural = "Привязки ФСП ID"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [FspLink.fsp_id, FspLink.linked_at]
    column_searchable_list: ClassVar[list[Any]] = [FspLink.fsp_id]
    column_default_sort = ("linked_at", True)


class CandidateGradeAdmin(ModelView, model=CandidateGrade):
    # Категорию выставляет тест; ручная правка обошла бы правила смены грейда.
    name = "Категория кандидата"
    name_plural = "Тесты: категории кандидатов"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        CandidateGrade.specialization,
        CandidateGrade.claimed_grade,
        CandidateGrade.confirmed_grade,
        CandidateGrade.confirmed_at,
        CandidateGrade.theta,
    ]
    column_default_sort = ("updated_at", True)


class AssessmentAttemptAdmin(ModelView, model=AssessmentAttempt):
    name = "Попытка теста"
    name_plural = "Тесты: попытки"
    can_create = False
    can_edit = False
    column_list: ClassVar[list[Any]] = [
        AssessmentAttempt.specialization,
        AssessmentAttempt.grade,
        AssessmentAttempt.is_express,
        AssessmentAttempt.started_at,
        AssessmentAttempt.finished_at,
        AssessmentAttempt.passed,
        AssessmentAttempt.theta,
        AssessmentAttempt.foreign_answers,
    ]
    column_labels: ClassVar[dict[Any, str]] = {
        AssessmentAttempt.foreign_answers: "Ответы от чужого варианта",
    }
    column_default_sort = ("started_at", True)


ADMIN_VIEWS: list[type[ModelView]] = [
    UserAdmin,
    CompanyAdmin,
    CompanyMemberAdmin,
    CandidateProfileAdmin,
    HiringNeedAdmin,
    InvitationAdmin,
    CompanyReportAdmin,
    CandidateGradeAdmin,
    AssessmentAttemptAdmin,
    FspEventAdmin,
    FspResultAdmin,
    FspAthleteRankAdmin,
    FspLinkAdmin,
    SkillAdmin,
    IndustryAdmin,
    SpecializationAdmin,
    GradeAdmin,
]
