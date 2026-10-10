from decimal import Decimal

import pytest

from app.services.revenue_audit_rules import (
    find_duplicate_invoices,
    reconcile_amounts,
    test_sales_cutoff as run_cutoff_test,
)


def test_duplicate_invoice_detection_is_case_insensitive():
    rows = [
        {"invoice": "INV-1"},
        {"invoice": "inv-1"},
        {"invoice": "INV-2"},
        {"invoice": ""},
    ]
    findings = find_duplicate_invoices(rows, "invoice")
    assert len(findings) == 2
    assert {item["rule_code"] for item in findings} == {"REV_DUPLICATE_INVOICE"}


def test_reconciliation_detects_amount_mismatch_and_missing_invoice():
    sales = [
        {"invoice": "A", "amount": "100.00"},
        {"invoice": "B", "amount": "50"},
    ]
    ledger = [
        {"invoice": "A", "amount": "90.00"},
        {"invoice": "C", "amount": "20"},
    ]

    findings = reconcile_amounts(
        sales, ledger, "invoice", "invoice", "amount", "amount"
    )
    by_code = {item["rule_code"] for item in findings}

    assert "REV_RECON_AMOUNT_MISMATCH" in by_code
    assert "REV_RECON_SALES_ONLY" in by_code
    assert "REV_RECON_LEDGER_ONLY" in by_code


def test_reconciliation_does_not_treat_missing_amount_as_zero():
    findings = reconcile_amounts(
        [{"invoice": "A", "amount": ""}],
        [{"invoice": "A", "amount": "0"}],
        "invoice", "invoice", "amount", "amount",
    )
    assert findings[0]["rule_code"] == "REV_RECON_MISSING_AMOUNT"
    assert findings[0]["difference"] is None


def test_cutoff_flags_out_of_period_and_missing_dates():
    records = [
        {"invoice": "A", "date": "2026-03-27", "amount": "100"},
        {"invoice": "B", "date": "2026-03-30", "amount": "200"},
        {"invoice": "C", "date": "", "amount": "300"},
    ]

    findings = run_cutoff_test(
        records, "date", "2026-03-28", "2026-04-02", "invoice", "amount"
    )

    assert [item["rule_code"] for item in findings] == [
        "REV_CUTOFF_OUT_OF_PERIOD",
        "REV_CUTOFF_MISSING_DATE",
    ]


def test_invalid_cutoff_period_rejected():
    with pytest.raises(ValueError):
        run_cutoff_test([], "date", "2026-04-02", "2026-03-28")


def test_duplicate_reconciliation_keys_are_not_silently_summed():
    findings = reconcile_amounts(
        [
            {"invoice": "A", "amount": "10"},
            {"invoice": "A", "amount": "20"},
        ],
        [{"invoice": "A", "amount": "30"}],
        "invoice", "invoice", "amount", "amount",
    )
    assert findings[0]["rule_code"] == "REV_RECON_DUPLICATE_KEY"
