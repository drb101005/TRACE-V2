"""Read-only verification of stored audit evidence documents."""

from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.evidence_integrity import sha256_file, verify_sha256


@dataclass(frozen=True)
class DocumentVerification:
    status: str
    expected_sha256: str | None
    actual_sha256: str | None
    message: str


def verify_document(
    path: str | Path,
    expected_sha256: str | None,
) -> DocumentVerification:
    """
    Verify file content without changing it.

    A missing expected digest is NOT treated as successful verification.
    """
    if not expected_sha256:
        return DocumentVerification(
            "UNVERIFIABLE", None, None,
            "No expected document hash is recorded.",
        )

    document = Path(path)

    if not document.is_file():
        return DocumentVerification(
            "MISSING", expected_sha256, None,
            "Stored evidence document is unavailable.",
        )

    try:
        actual = sha256_file(document)
    except OSError:
        return DocumentVerification(
            "UNVERIFIABLE", expected_sha256, None,
            "Stored evidence document could not be read.",
        )

    if not verify_sha256(actual, expected_sha256):
        return DocumentVerification(
            "TAMPERED", expected_sha256, actual,
            "Document content does not match the recorded hash.",
        )

    return DocumentVerification(
        "VERIFIED", expected_sha256, actual,
        "Document content matches the recorded hash.",
    )


def verification_dict(result: DocumentVerification) -> dict:
    """Convert a verification result to a JSON-compatible dictionary."""
    return asdict(result)
