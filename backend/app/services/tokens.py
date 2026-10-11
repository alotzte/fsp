import hashlib
import secrets

TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    # В БД только хеш: утечка таблицы не даёт рабочих сессий и ссылок-приглашений.
    return hashlib.sha256(token.encode()).hexdigest()
