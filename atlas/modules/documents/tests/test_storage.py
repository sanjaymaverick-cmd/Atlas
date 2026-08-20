"""Security and integrity tests for local append-only document storage."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from atlas.modules.documents.storage import (
    InvalidObjectKeyError,
    LocalDocumentStorage,
    ObjectAlreadyExistsError,
    ObjectIntegrityError,
    StorageError,
)

pytestmark = pytest.mark.unit


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_write_and_read_verify_the_immutable_checksum(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    content = b"synthetic document bytes"
    stored = storage.put(
        key="project/document/revision-a.pdf", content=content, expected_sha256=digest(content)
    )
    assert stored.size_bytes == len(content)
    assert storage.read(key=stored.key, expected_sha256=stored.checksum_sha256) == content


def test_existing_object_is_never_overwritten(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    original = b"synthetic original"
    storage.put(key="project/revision", content=original, expected_sha256=digest(original))
    with pytest.raises(ObjectAlreadyExistsError):
        storage.put(key="project/revision", content=original, expected_sha256=digest(original))
    assert storage.read(key="project/revision", expected_sha256=digest(original)) == original


@pytest.mark.parametrize(
    "key",
    ["../outside", "/absolute", "https://example.invalid/object", "folder\\object"],
)
def test_paths_urls_and_traversal_are_rejected(tmp_path: Path, key: str) -> None:
    storage = LocalDocumentStorage(tmp_path)
    with pytest.raises(InvalidObjectKeyError):
        storage.put(key=key, content=b"x", expected_sha256=digest(b"x"))


def test_checksum_mismatch_and_size_limit_are_rejected(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path, max_bytes=2)
    with pytest.raises(ObjectIntegrityError):
        storage.put(key="object", content=b"x", expected_sha256="0" * 64)
    with pytest.raises(StorageError, match="size limit"):
        storage.put(key="large", content=b"xxx", expected_sha256=digest(b"xxx"))


def test_read_detects_out_of_band_tampering(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    content = b"synthetic original"
    checksum = digest(content)
    storage.put(key="project/object", content=content, expected_sha256=checksum)
    (tmp_path / "project" / "object").write_bytes(b"tampered")
    with pytest.raises(ObjectIntegrityError):
        storage.read(key="project/object", expected_sha256=checksum)
