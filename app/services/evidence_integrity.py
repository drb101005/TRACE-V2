"""Deterministic integrity checks for audit evidence documents."""

import hashlib
import hmac
from pathlib import Path
from typing import BinaryIO


def sha256_bytes(content: bytes) -> str:
    """Return the SHA-256 digest of file contents."""
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash a file incrementally to avoid loading large files into memory."""
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_stream(stream: BinaryIO) -> str:
    """Hash a binary stream from its current position."""
    digest = hashlib.sha256()

    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)

    return digest.hexdigest()


def verify_sha256(actual: str, expected: str) -> bool:
    """Compare SHA-256 values without ordinary string comparison."""
    if not actual or not expected:
        return False

    actual = actual.strip().lower()
    expected = expected.strip().lower()

    if len(actual) != 64 or len(expected) != 64:
        return False

    try:
        bytes.fromhex(actual)
        bytes.fromhex(expected)
    except ValueError:
        return False

    return hmac.compare_digest(actual, expected)
