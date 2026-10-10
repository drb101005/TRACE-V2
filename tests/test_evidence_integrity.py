import hashlib

from app.services.evidence_integrity import (
    sha256_bytes,
    sha256_file,
    sha256_stream,
    verify_sha256,
)


def test_bytes_hash_is_deterministic():
    content = b"TRACE-V2 evidence"
    expected = hashlib.sha256(content).hexdigest()

    assert sha256_bytes(content) == expected
    assert sha256_bytes(content) == sha256_bytes(content)


def test_file_hash_reads_large_files_incrementally(tmp_path):
    path = tmp_path / "invoice.pdf"
    content = b"invoice-data-" * 200_000
    path.write_bytes(content)

    assert sha256_file(path) == hashlib.sha256(content).hexdigest()


def test_stream_hash():
    from io import BytesIO

    content = b"evidence stream"
    assert sha256_stream(BytesIO(content)) == hashlib.sha256(content).hexdigest()


def test_original_document_hash_verifies():
    digest = sha256_bytes(b"original invoice")
    assert verify_sha256(digest, digest.upper())


def test_modified_document_is_detected():
    original = sha256_bytes(b"original invoice")
    modified = sha256_bytes(b"modified invoice")

    assert not verify_sha256(modified, original)


def test_invalid_or_missing_hash_is_rejected():
    valid = sha256_bytes(b"invoice")

    assert not verify_sha256("", valid)
    assert not verify_sha256(valid, "")
    assert not verify_sha256("not-a-hash", valid)
    assert not verify_sha256("z" * 64, valid)
