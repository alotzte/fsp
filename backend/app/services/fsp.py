"""ФСП ID и достижения кандидата.

Привязка: кандидат входит в ФСП ID (OIDC, Authorization Code + PKCE), бэк проверяет ID-токен
и сохраняет номер участника из claim fsp_id, а если ФСП ID его не передаёт (по сути это
почта и пароль): sub его аккаунта. Привязка подтверждает, что ФСП ID принадлежит кандидату:
автопривязки по совпадению email нет (известная уязвимость брокеринга).

Достижения влияют только на ранжирование внутри категории, не на грейд. По разъяснениям
организаторов учитываются результаты, а не участие, и все соревнования весят одинаково.
"""

import math
import secrets
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import SettingsDep
from app.errors import ConflictError, UnauthorizedError
from app.services.auth.keycloak import FspIdClientDep
from app.services.auth.login_flow import LoginFlow, LoginFlowSigner
from app.services.consents import ConsentServiceDep
from app.services.db.models import (
    JURY_DEMO_PREFIX,
    ConsentKind,
    FspAthleteRank,
    FspAward,
    FspDiscipline,
    FspLink,
    FspResult,
    User,
)
from app.services.db.session import SessionDep

# Должен совпадать с redirectUris клиента в infra/keycloak/realm-fsp-id.json.
FSP_CALLBACK_PATH = "/api/v1/candidate/fsp/callback"
FSP_ID_CLAIM = "fsp_id"

# Вес результата: участие не засчитывается, иначе профиль набивали бы онлайн-отборами.
AWARD_WEIGHTS = {
    FspAward.WINNER: 1.0,
    FspAward.PRIZE: 1.0,
    FspAward.FINALIST: 0.5,
    FspAward.PARTICIPANT: 0.0,
}
# Результат двухлетней давности весит в e раз меньше свежего.
DECAY_DAYS = 730
# Подтверждённое достижение: призовое место или выход в финал.
ACHIEVEMENT_AWARDS = (FspAward.WINNER, FspAward.PRIZE, FspAward.FINALIST)
_SOFTWARE = frozenset(
    {
        "backend",
        "frontend",
        "fullstack",
        "mobile",
        "devops",
        "data-science",
        "data-engineering",
        "qa",
        "analytics",
        "gamedev",
    }
)
# Дисциплины ФСП, профильные для направления (slug специализации). Эксперты: специалисту по ИБ
# соревнования по ИБ релевантнее робототехники. Влияет только на объяснение: веса у всех
# соревнований по-прежнему равны.
DISCIPLINE_SPECIALIZATIONS: dict[FspDiscipline, frozenset[str]] = {
    FspDiscipline.ALGORITHMIC: frozenset(
        {"backend", "fullstack", "data-science", "data-engineering", "gamedev", "embedded"}
    ),
    FspDiscipline.PRODUCT: _SOFTWARE,
    FspDiscipline.INFOSEC: frozenset({"security"}),
    FspDiscipline.ROBOTICS: frozenset({"embedded"}),
    FspDiscipline.UAS: frozenset({"embedded"}),
}


class FspIdAlreadyLinkedError(ConflictError):
    message = "Этот ФСП ID уже привязан к другому профилю"


class FspIdClaimMissingError(UnauthorizedError):
    message = "ФСП ID не передал идентификатор участника"


class FspConsentRequiredError(ConflictError):
    message = "Сначала дайте согласие на получение данных из реестра ФСП"


class FspLinkStateMismatchError(UnauthorizedError):
    message = "Ответ ФСП ID не относится к начатой привязке"


@dataclass(frozen=True)
class FspStanding:
    """Сводка для ранжирования: нормированный бонус и число подтверждённых достижений."""

    score: float
    achievements: int
    # Из них: в дисциплине, профильной для направления кандидата.
    relevant: int = 0


def fsp_standing(
    results: Iterable[FspResult], today: date, specialization: str | None = None
) -> FspStanding:
    """Бонус 0..1: 1 − exp(−Σ вес·затухание). Одна свежая победа ≈ 0.63, две ≈ 0.86.
    specialization: slug направления кандидата, по нему считаются профильные достижения."""
    points = 0.0
    achievements = relevant = 0
    for result in results:
        weight = AWARD_WEIGHTS[result.award]
        age_days = max(0, (today - result.event.starts_on).days)
        points += weight * math.exp(-age_days / DECAY_DAYS)
        if result.award in ACHIEVEMENT_AWARDS:
            achievements += 1
            relevant += specialization in DISCIPLINE_SPECIALIZATIONS[result.event.discipline]
    return FspStanding(score=1 - math.exp(-points), achievements=achievements, relevant=relevant)


# Кандидат без истории ФСП: бонус 0, без штрафа (обязательный случай ТЗ).
NO_FSP = FspStanding(score=0.0, achievements=0)


async def registry_results(
    session: AsyncSession, fsp_ids: Sequence[str]
) -> dict[str, list[FspResult]]:
    """Результаты из реестра ФСП, от новых к старым. Для реального реестра меняется только это."""
    rows = await session.scalars(
        select(FspResult).options(joinedload(FspResult.event)).where(FspResult.fsp_id.in_(fsp_ids))
    )
    by_id: dict[str, list[FspResult]] = defaultdict(list)
    for result in rows:
        by_id[result.fsp_id].append(result)
    for results in by_id.values():
        results.sort(key=lambda r: r.event.starts_on, reverse=True)
    return by_id


async def registry_rank(session: AsyncSession, fsp_id: str) -> FspAthleteRank | None:
    """Спортивный разряд или звание по реестру ФСП. Для реального реестра меняется только это."""
    return await session.get(FspAthleteRank, fsp_id)


async def user_registry_results(session: AsyncSession, user_id: uuid.UUID) -> list[FspResult]:
    """Результаты по привязанному ФСП ID; пусто: не привязан или истории нет."""
    fsp_id = await session.scalar(select(FspLink.fsp_id).where(FspLink.user_id == user_id))
    if fsp_id is None:
        return []
    return (await registry_results(session, [fsp_id])).get(fsp_id, [])


@dataclass(frozen=True)
class FspProfile:
    link: FspLink | None
    results: list[FspResult]
    rank: FspAthleteRank | None = None


class FspService:
    def __init__(
        self,
        session: SessionDep,
        fsp_id: FspIdClientDep,
        settings: SettingsDep,
        consents: ConsentServiceDep,
    ) -> None:
        self._session = session
        self._consents = consents
        self._fsp_id = fsp_id
        self._settings = settings
        self._flow_signer = LoginFlowSigner(settings.secret_key.get_secret_value())
        self._callback_url = f"{settings.public_url}{FSP_CALLBACK_PATH}"

    async def get_profile(self, user_id: uuid.UUID) -> FspProfile:
        link = await self._session.get(FspLink, user_id)
        if link is None:
            return FspProfile(None, [])
        results = (await self.results_for([link.fsp_id])).get(link.fsp_id, [])
        return FspProfile(link, results, await registry_rank(self._session, link.fsp_id))

    async def results_for(self, fsp_ids: Sequence[str]) -> dict[str, list[FspResult]]:
        return await registry_results(self._session, fsp_ids)

    async def standings(
        self, specializations: Mapping[uuid.UUID, str | None]
    ) -> dict[uuid.UUID, FspStanding]:
        """specializations: slug направления каждого кандидата (для профильных достижений)."""
        links = list(
            await self._session.scalars(
                select(FspLink).where(FspLink.user_id.in_(specializations.keys()))
            )
        )
        results = await self.results_for([link.fsp_id for link in links])
        today = datetime.now(UTC).date()
        return {
            link.user_id: fsp_standing(
                results.get(link.fsp_id, []), today, specializations[link.user_id]
            )
            for link in links
        }

    async def begin_link(self, user: User, next_path: str) -> tuple[str, str]:
        """Адрес входа в ФСП ID и подписанная cookie с секретами этого входа."""
        await self._require_consent(user)
        flow = LoginFlow.start(next_path)
        url = self._fsp_id.authorization_url(
            redirect_uri=self._callback_url,
            state=flow.state,
            nonce=flow.nonce,
            code_challenge=flow.code_challenge,
            register=False,
            # Без повторного входа открытая сессия ФСП ID в общем браузере
            # молча привязала бы чужой номер участника.
            force_login=True,
        )
        return url, self._flow_signer.dump(flow)

    async def complete_link(self, user: User, *, code: str, state: str, flow_cookie: str) -> str:
        """Завершает привязку и возвращает адрес фронта, куда вернуть кандидата."""
        # Согласие могли отозвать, пока кандидат входил в ФСП ID.
        await self._require_consent(user)
        flow = self._flow_signer.load(flow_cookie)
        if not secrets.compare_digest(state, flow.state):
            raise FspLinkStateMismatchError
        id_token = await self._fsp_id.exchange_code(
            code=code, code_verifier=flow.code_verifier, redirect_uri=self._callback_url
        )
        claims = await self._fsp_id.decode_id_token(id_token, nonce=flow.nonce)
        fsp_id = claims.get(FSP_ID_CLAIM) or claims.get("sub")
        if not isinstance(fsp_id, str) or not fsp_id:
            raise FspIdClaimMissingError
        await self._session.execute(delete(FspLink).where(FspLink.user_id == user.id))
        # Тестовых спортсменов mock ФСП ID четыре, а песочница жюри живёт сутки: её привязка
        # уходит следующему, иначе второй проверяющий упёрся бы в «уже привязан».
        await self._session.execute(
            delete(FspLink).where(
                FspLink.fsp_id == fsp_id,
                FspLink.user_id.in_(
                    select(User.id).where(User.keycloak_sub.startswith(JURY_DEMO_PREFIX))
                ),
            )
        )
        self._session.add(FspLink(user_id=user.id, fsp_id=fsp_id))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            raise FspIdAlreadyLinkedError from exc
        return f"{self._settings.effective_frontend_url}{flow.next_path}"

    async def _require_consent(self, user: User) -> None:
        if not await self._consents.is_active(user, ConsentKind.FSP_DATA):
            raise FspConsentRequiredError

    async def unlink(self, user: User) -> None:
        await self._session.execute(delete(FspLink).where(FspLink.user_id == user.id))
        await self._session.commit()


FspServiceDep = Annotated[FspService, Depends()]
