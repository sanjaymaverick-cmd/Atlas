"""Append-only binary storage boundary for document revisions."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol


class StorageError(Exception):
    """Base class for safe document-storage failures."""


class InvalidObjectKeyError(StorageError):
    """The supplied key is not an opaque relative object key."""


class ObjectIntegrityError(StorageError):
    """Stored bytes do not match their immutable SHA-256 identity."""


class ObjectAlreadyExistsError(StorageError):
    """Append-only storage refuses to replace an existing revision object."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    checksum_sha256: str
    size_bytes: int


class DocumentStorage(Protocol):
    def put(self, *, key: str, content: bytes, expected_sha256: str) -> StoredObject: ...

    def read(self, *, key: str, expected_sha256: str) -> bytes: ...


class LocalDocumentStorage:
    """Development-only append-only storage rooted in an explicit directory."""

    def __init__(self, root: Path, *, max_bytes: int = 25 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if root.exists() and root.is_symlink():
            raise InvalidObjectKeyError("storage root must not be a symbolic link")
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve(strict=True)
        self._max_bytes = max_bytes

    @staticmethod
    def _parts(key: str) -> tuple[str, ...]:
        if "\\" in key or "://" in key:
            raise InvalidObjectKeyError("object key must not be a path or URL")
        parsed = PurePosixPath(key)
        if (
            parsed.is_absolute()
            or not parsed.parts
            or any(part in {"", ".", ".."} for part in parsed.parts)
        ):
            raise InvalidObjectKeyError("object key must be a safe relative key")
        return parsed.parts

    def _target(self, key: str) -> Path:
        parts = self._parts(key)
        target = self._root.joinpath(*parts)
        current = self._root
        for part in parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise InvalidObjectKeyError("object key traverses a symbolic link")
        return target

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def put(self, *, key: str, content: bytes, expected_sha256: str) -> StoredObject:
        if len(content) > self._max_bytes:
            raise StorageError("document exceeds the configured local size limit")
        actual = self._checksum(content)
        if not hmac.compare_digest(actual, expected_sha256):
            raise ObjectIntegrityError("document checksum does not match")
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as destination:
                destination.write(content)
        except FileExistsError as exc:
            raise ObjectAlreadyExistsError("document object already exists") from exc
        return StoredObject(key=key, checksum_sha256=actual, size_bytes=len(content))

    def read(self, *, key: str, expected_sha256: str) -> bytes:
        target = self._target(key)
        try:
            content = target.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("document object does not exist") from exc
        actual = self._checksum(content)
        if not hmac.compare_digest(actual, expected_sha256):
            raise ObjectIntegrityError("stored document failed its integrity check")
        return content
