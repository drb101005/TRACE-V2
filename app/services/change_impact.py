"""Deterministic dataset-version comparison for audit reassessment."""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence


class ChangeType(str, Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"


@dataclass(frozen=True)
class DatasetChange:
    change_type: ChangeType
    record_key: str
    previous_hash: str | None
    current_hash: str | None


def canonical_hash(value: Any) -> str:
    """Stable hash for JSON-compatible audit data."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare_datasets(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    key_field: str,
) -> list[DatasetChange]:
    """
    Compare records by a stable business key.

    Duplicate or missing keys are rejected rather than silently overwritten.
    """
    def index_records(records, label):
        indexed = {}
        for record in records:
            key = record.get(key_field)
            if key is None or not str(key).strip():
                raise ValueError(f"{label} record has a missing key: {key_field}")

            key = str(key).strip()
            if key in indexed:
                raise ValueError(f"{label} dataset contains duplicate key: {key}")

            indexed[key] = canonical_hash(record)
        return indexed

    old = index_records(previous, "Previous")
    new = index_records(current, "Current")
    changes = []

    for key in sorted(old.keys() | new.keys()):
        before = old.get(key)
        after = new.get(key)

        if before is None:
            kind = ChangeType.ADDED
        elif after is None:
            kind = ChangeType.REMOVED
        elif before == after:
            kind = ChangeType.UNCHANGED
        else:
            kind = ChangeType.MODIFIED

        changes.append(DatasetChange(kind, key, before, after))

    return changes


def impacted_audit_procedures(
    changes: Sequence[DatasetChange],
    dependency_map: Mapping[str, Sequence[str]],
    changed_fields: Sequence[str] | None = None,
) -> list[str]:
    """
    Return procedures affected by changes to their declared dependencies.

    dependency_map maps field names to procedure names. If changed_fields is
    omitted, every changed record conservatively impacts all declared fields.
    """
    changed_types = {
        ChangeType.ADDED,
        ChangeType.REMOVED,
        ChangeType.MODIFIED,
    }
    if not any(change.change_type in changed_types for change in changes):
        return []

    fields = set(changed_fields or dependency_map.keys())
    impacted = {
        procedure
        for field in fields
        for procedure in dependency_map.get(field, ())
    }
    return sorted(impacted)
