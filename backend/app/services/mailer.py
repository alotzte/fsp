import logging
from email.message import EmailMessage
from typing import Annotated

import aiosmtplib
from fastapi import Depends

from app.config import SettingsDep

logger = logging.getLogger(__name__)


class Mailer:
    """Отправка писем по SMTP. В Docker это Mailpit: письма видны на /mail и никуда не уходят."""

    def __init__(self, settings: SettingsDep) -> None:
        self._settings = settings

    async def send(self, *, to: str, subject: str, body: str) -> bool:
        """Отправляет письмо. Не бросает исключений: письмо это уведомление, и его сбой
        не должен отменять действие, о котором оно сообщает. Возвращает успех отправки."""
        message = EmailMessage()
        message["From"] = self._settings.mail_from
        message["To"] = to
        # Тема собирается из названий компании и должности: перевод строки в них сделал бы
        # заголовок недопустимым (ValueError уже после коммита действия).
        message["Subject"] = " ".join(subject.split())
        message.set_content(body)
        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                timeout=self._settings.smtp_timeout_seconds,
            )
        except (aiosmtplib.SMTPException, OSError):
            logger.warning("Не удалось отправить письмо на %s", to, exc_info=True)
            return False
        return True


MailerDep = Annotated[Mailer, Depends()]
