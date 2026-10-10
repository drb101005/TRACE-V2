import hashlib

from app.services.document_verification import verify_document


def test_valid_document_is_verified(tmp_path):
    path = tmp_path / "invoice.pdf"
    content = b"sample invoice content"
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()

    result = verify_document(path, expected)

    assert result.status == "VERIFIED"
    assert result.actual_sha256 == expected


def test_modified_document_is_flagged(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"modified content")
    expected = hashlib.sha256(b"original content").hexdigest()

    result = verify_document(path, expected)

    assert result.status == "TAMPERED"
    assert result.actual_sha256 != expected


def test_missing_document_is_flagged(tmp_path):
    expected = hashlib.sha256(b"original").hexdigest()

    result = verify_document(tmp_path / "missing.pdf", expected)

    assert result.status == "MISSING"
    assert result.actual_sha256 is None


def test_missing_expected_hash_is_not_verified(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"invoice")

    result = verify_document(path, None)

    assert result.status == "UNVERIFIABLE"
    assert result.actual_sha256 is None


def test_invalid_expected_hash_fails_verification(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"invoice")

    result = verify_document(path, "invalid")

    assert result.status == "TAMPERED"


def test_empty_file_can_be_verified(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    expected = hashlib.sha256(b"").hexdigest()

    assert verify_document(path, expected).status == "VERIFIED"
