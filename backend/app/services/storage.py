import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import Depends, Request


class FileStorage(Protocol):
    """Хранилище содержимого файлов. Метаданные: в таблице stored_files.

    Интерфейс нужен, чтобы локальный диск можно было заменить на S3-совместимое хранилище
    без правок в сервисах.
    """

    async def save(self, content: bytes) -> str: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class LocalFileStorage:
    """Файлы на диске (в Docker: volume). Ключ случайный, имя от пользователя не используется."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, content: bytes) -> str:
        name = uuid.uuid4().hex
        # Подкаталог по первым символам, чтобы не держать все файлы в одной папке.
        key = f"{name[:2]}/{name}"
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return key

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    def _path(self, key: str) -> Path:
        return self._base_dir / key


def get_file_storage(request: Request) -> FileStorage:
    storage: FileStorage = request.app.state.file_storage
    return storage


FileStorageDep = Annotated[FileStorage, Depends(get_file_storage)]
