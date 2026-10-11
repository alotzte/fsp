from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, select

from app.errors import ConflictError
from app.services.db.models import (
    AssessmentAttempt,
    CandidateGrade,
    CandidateProfile,
    Consent,
    ConsentKind,
    ContactReveal,
    FspLink,
    Invitation,
    ShortlistEntry,
    User,
    WeeklyCase,
)
from app.services.db.session import SessionDep


@dataclass(frozen=True)
class ConsentDocument:
    kind: ConsentKind
    version: str
    title: str
    text: str


# Тексты: рабочие черновики для MVP, перед запуском их должен вычитать юрист.
# При изменении текста поднимайте version: у принявших старую версию согласие станет неактуальным.
CONSENT_DOCUMENTS: dict[ConsentKind, ConsentDocument] = {
    ConsentKind.DATA_PROCESSING: ConsentDocument(
        kind=ConsentKind.DATA_PROCESSING,
        version="2026-10-05",
        title="Согласие на обработку персональных данных",
        text=(
            "Я даю согласие оператору платформы «ФСП Карьера» на обработку моих персональных "
            "данных: ФИО, контактных данных (email, телефон, Telegram), сведений об опыте работы, "
            "образовании, навыках, результатах тестирования и достижениях в соревнованиях "
            "Федерации спортивного программирования.\n\n"
            "Цель обработки: ведение профиля соискателя, определение его категории и подбор "
            "предложений о работе. Обработка включает сбор, запись, систематизацию, хранение, "
            "уточнение, использование и удаление данных.\n\n"
            "Согласие действует до его отзыва. Отозвать согласие можно в настройках профиля; "
            "после отзыва профиль и связанные с ним данные удаляются."
        ),
    ),
    ConsentKind.PROFILE_PUBLICATION: ConsentDocument(
        kind=ConsentKind.PROFILE_PUBLICATION,
        version="2026-10-06",
        title="Согласие на показ профиля работодателям",
        text=(
            "Я разрешаю показывать мой профиль зарегистрированным работодателям платформы "
            "«ФСП Карьера» в поиске и подборках кандидатов.\n\n"
            "До того как я приму приглашение работодателя, ему видны только обезличенные "
            "сведения: специализация, грейд и результаты тестирования, навыки, опыт без "
            "названий компаний, образование и достижения ФСП. ФИО и контакты раскрываются "
            "конкретному работодателю только после того, как я приму его приглашение.\n\n"
            "Мои ожидания по зарплате работодателю не показываются: по ним платформа только "
            "проверяет, что вилка в приглашении им соответствует.\n\n"
            "Согласие можно отозвать в любой момент: профиль сразу пропадёт из поиска."
        ),
    ),
    ConsentKind.FSP_DATA: ConsentDocument(
        kind=ConsentKind.FSP_DATA,
        version="2026-10-08",
        title="Согласие на получение данных из реестра ФСП",
        text=(
            "Я разрешаю платформе «ФСП Карьера» получать по моему ФСП ID сведения из реестра "
            "Федерации спортивного программирования: соревнования, дисциплины, занятые места, "
            "награды и названия команд.\n\n"
            "Цель: показывать подтверждённые достижения в моём профиле и учитывать их при "
            "ранжировании внутри категории. На грейд они не влияют. Названия команд работодатель "
            "видит только после того, как я приму его приглашение.\n\n"
            "Согласие можно отозвать в любой момент: ФСП ID отвяжется, а достижения перестанут "
            "показываться и учитываться."
        ),
    ),
}

# Согласия, которые имеют смысл только при действующем согласии на обработку данных.
DEPENDENT_CONSENTS = (ConsentKind.PROFILE_PUBLICATION, ConsentKind.FSP_DATA)


class ConsentRequiredError(ConflictError):
    message = "Сначала дайте согласие на обработку персональных данных"


@dataclass(frozen=True)
class ConsentState:
    kind: ConsentKind
    current_version: str
    granted: Consent | None

    @property
    def is_active(self) -> bool:
        # Согласие на старую версию документа не считается действующим.
        return self.granted is not None and self.granted.document_version == self.current_version


class ConsentService:
    def __init__(self, session: SessionDep) -> None:
        self._session = session

    async def get_states(self, user: User) -> list[ConsentState]:
        active = await self._session.scalars(
            select(Consent).where(Consent.user_id == user.id, Consent.revoked_at.is_(None))
        )
        by_kind = {consent.kind: consent for consent in active}
        return [
            ConsentState(kind=kind, current_version=document.version, granted=by_kind.get(kind))
            for kind, document in CONSENT_DOCUMENTS.items()
        ]

    async def is_active(self, user: User, kind: ConsentKind) -> bool:
        states = await self.get_states(user)
        return any(state.kind == kind and state.is_active for state in states)

    async def grant(self, user: User, kind: ConsentKind) -> list[ConsentState]:
        if kind in DEPENDENT_CONSENTS and not await self.is_active(
            user, ConsentKind.DATA_PROCESSING
        ):
            raise ConsentRequiredError
        document = CONSENT_DOCUMENTS[kind]
        await self._revoke_active(user, kind)
        self._session.add(Consent(user_id=user.id, kind=kind, document_version=document.version))
        await self._session.commit()
        return await self.get_states(user)

    async def revoke(self, user: User, kind: ConsentKind) -> list[ConsentState]:
        await self._revoke_active(user, kind)
        if kind == ConsentKind.DATA_PROCESSING:
            # Без согласия на обработку данные хранить нельзя (152-ФЗ): удаляем профиль
            # и снимаем зависящие от него согласия (показ работодателям, данные ФСП).
            for dependent in DEPENDENT_CONSENTS:
                await self._revoke_active(user, dependent)
            await self._session.execute(
                delete(CandidateProfile).where(CandidateProfile.user_id == user.id)
            )
            # «Профиль и связанные с ним данные удаляются» (текст согласия): раскрытия контактов,
            # приглашения с перепиской и решениями кейсов, шортлисты, тесты и кейсы недели. Иначе
            # компания увидела бы ФИО и контакты нового профиля без нового принятия приглашения.
            for model, column in (
                (ContactReveal, ContactReveal.candidate_user_id),
                (Invitation, Invitation.candidate_user_id),
                (ShortlistEntry, ShortlistEntry.candidate_user_id),
                (CandidateGrade, CandidateGrade.user_id),
                (AssessmentAttempt, AssessmentAttempt.user_id),
                (WeeklyCase, WeeklyCase.user_id),
            ):
                await self._session.execute(delete(model).where(column == user.id))
        if kind in {ConsentKind.DATA_PROCESSING, ConsentKind.FSP_DATA}:
            # Без согласия на данные ФСП привязка ФСП ID не хранится.
            await self._session.execute(delete(FspLink).where(FspLink.user_id == user.id))
        await self._session.commit()
        return await self.get_states(user)

    async def _revoke_active(self, user: User, kind: ConsentKind) -> None:
        active = await self._session.scalars(
            select(Consent).where(
                Consent.user_id == user.id, Consent.kind == kind, Consent.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        for consent in active:
            consent.revoked_at = now


ConsentServiceDep = Annotated[ConsentService, Depends()]
