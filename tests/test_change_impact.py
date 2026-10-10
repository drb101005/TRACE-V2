import pytest

from app.services.change_impact import (
    ChangeType,
    canonical_hash,
    compare_datasets,
    impacted_audit_procedures,
)


def test_record_order_does_not_change_hash():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_detects_added_modified_removed_and_unchanged_records():
    old = [
        {"invoice": "A", "amount": "100"},
        {"invoice": "B", "amount": "200"},
        {"invoice": "C", "amount": "300"},
    ]
    new = [
        {"invoice": "A", "amount": "100"},
        {"invoice": "B", "amount": "250"},
        {"invoice": "D", "amount": "400"},
    ]

    changes = compare_datasets(old, new, "invoice")
    actual = {change.record_key: change.change_type for change in changes}

    assert actual == {
        "A": ChangeType.UNCHANGED,
        "B": ChangeType.MODIFIED,
        "C": ChangeType.REMOVED,
        "D": ChangeType.ADDED,
    }


def test_missing_keys_are_rejected():
    with pytest.raises(ValueError, match="missing key"):
        compare_datasets([{"amount": "10"}], [], "invoice")


def test_duplicate_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate key"):
        compare_datasets(
            [{"invoice": "A"}, {"invoice": "A"}],
            [],
            "invoice",
        )


def test_unchanged_data_does_not_trigger_rerun():
    changes = compare_datasets(
        [{"invoice": "A", "amount": "10"}],
        [{"invoice": "A", "amount": "10"}],
        "invoice",
    )

    assert impacted_audit_procedures(
        changes,
        {"amount": ["SALES_RECONCILIATION", "TAX_TEST"]},
        ["amount"],
    ) == []


def test_changed_fields_select_only_dependent_procedures():
    changes = compare_datasets(
        [{"invoice": "A", "amount": "10", "date": "2026-01-01"}],
        [{"invoice": "A", "amount": "20", "date": "2026-01-01"}],
        "invoice",
    )

    result = impacted_audit_procedures(
        changes,
        {
            "amount": ["SALES_RECONCILIATION", "TAX_TEST"],
            "date": ["CUTOFF_TEST"],
        },
        ["amount"],
    )

    assert result == ["SALES_RECONCILIATION", "TAX_TEST"]


def test_unknown_changed_fields_do_not_invent_procedures():
    changes = compare_datasets(
        [{"invoice": "A", "amount": "10"}],
        [{"invoice": "A", "amount": "20"}],
        "invoice",
    )

    assert impacted_audit_procedures(
        changes, {"amount": ["TAX_TEST"]}, ["unmapped_field"]
    ) == []
