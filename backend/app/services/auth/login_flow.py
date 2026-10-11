import base64
import hashlib
import secrets
from dataclasses import asdict, dataclass

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.errors import UnauthorizedError

# Сколько живёт незавершённый вход: от редиректа в Keycloak до возврата в callback.
LOGIN_FLOW_MAX_AGE_SECONDS = 10 * 60
_SERIALIZER_SALT = "oidc-login-flow"


class LoginFlowExpiredError(UnauthorizedError):
    message = "Вход устарел или был начат в другом браузере"


@dataclass(frozen=True)
class LoginFlow:
    """Одноразовые секреты одного входа. Живут в подписанной cookie до callback."""

    state: str
    nonce: str
    code_verifier: str
    next_path: str

    @classmethod
    def start(cls, next_path: str) -> "LoginFlow":
        return cls(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            next_path=safe_next_path(next_path),
        )

    @property
    def code_challenge(self) -> str:
        digest = hashlib.sha256(self.code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class LoginFlowSigner:
    def __init__(self, secret_key: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt=_SERIALIZER_SALT)

    def dump(self, flow: LoginFlow) -> str:
        return self._serializer.dumps(asdict(flow))

    def load(self, value: str) -> LoginFlow:
        try:
            raw = self._serializer.loads(value, max_age=LOGIN_FLOW_MAX_AGE_SECONDS)
            return LoginFlow(**raw)
        except (BadSignature, TypeError) as exc:
            raise LoginFlowExpiredError from exc


def safe_next_path(next_path: str) -> str:
    """Пускает только относительные пути внутри сайта, иначе вход станет открытым редиректом."""
    if not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:
        return "/"
    return next_path
