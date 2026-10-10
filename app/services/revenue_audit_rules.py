"""Deterministic revenue audit rules. No LLM-based financial calculations."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def _amount(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        amount = Decimal(str(value).replace(",", "").strip())
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def find_duplicate_invoices(
    records: Sequence[Mapping[str, Any]],
    invoice_column: str,
) -> list[dict]:
    """Flag every row belonging to a repeated non-empty invoice number."""
    groups = defaultdict(list)

    for index, record in enumerate(records, start=1):
        value = record.get(invoice_column)
        if value is not None and str(value).strip():
            groups[str(value).strip().casefold()].append((index, str(value).strip()))

    findings = []
    for normalized, entries in sorted(groups.items()):
        if len(entries) < 2:
            continue
        for row_number, original in entries:
            findings.append({
                "rule_code": "REV_DUPLICATE_INVOICE",
                "severity": "HIGH",
                "source_row_number": row_number,
                "invoice_number": original,
                "duplicate_count": len(entries),
                "explanation": "Invoice number occurs multiple times; investigate before concluding misstatement.",
                "amount_under_review": None,
            })
    return findings


def reconcile_amounts(
    sales: Sequence[Mapping[str, Any]],
    ledger: Sequence[Mapping[str, Any]],
    sales_invoice_column: str,
    ledger_invoice_column: str,
    sales_amount_column: str,
    ledger_amount_column: str,
) -> list[dict]:
    """Compare invoice-level amounts, preserving missing and duplicate states."""
    def group(records, invoice_col, amount_col):
        result = defaultdict(list)
        for row in records:
            invoice = row.get(invoice_col)
            if invoice is None or not str(invoice).strip():
                continue
            result[str(invoice).strip().casefold()].append(_amount(row.get(amount_col)))
        return result

    sales_groups = group(sales, sales_invoice_column, sales_amount_column)
    ledger_groups = group(ledger, ledger_invoice_column, ledger_amount_column)
    findings = []

    for invoice in sorted(sales_groups.keys() | ledger_groups.keys()):
        sale_values = sales_groups.get(invoice, [])
        ledger_values = ledger_groups.get(invoice, [])
        code = None
        difference = None

        if len(sale_values) > 1 or len(ledger_values) > 1:
            code = "REV_RECON_DUPLICATE_KEY"
        elif not sale_values:
            code = "REV_RECON_LEDGER_ONLY"
        elif not ledger_values:
            code = "REV_RECON_SALES_ONLY"
        elif sale_values[0] is None or ledger_values[0] is None:
            code = "REV_RECON_MISSING_AMOUNT"
        else:
            difference = sale_values[0] - ledger_values[0]
            if difference != 0:
                code = "REV_RECON_AMOUNT_MISMATCH"

        if code:
            findings.append({
                "rule_code": code,
                "severity": "HIGH" if code != "REV_RECON_MISSING_AMOUNT" else "MEDIUM",
                "invoice_number": invoice,
                "difference": str(difference) if difference is not None else None,
                "explanation": "Investigate this reconciliation exception; it is not automatically a confirmed misstatement.",
            })

    return findings


def test_sales_cutoff(
    records: Sequence[Mapping[str, Any]],
    date_column: str,
    period_start: str,
    period_end: str,
    invoice_column: str | None = None,
    amount_column: str | None = None,
) -> list[dict]:
    """Flag records outside the inclusive audit period; unknown dates remain explicit."""
    start = _date(period_start)
    end = _date(period_end)

    if start is None or end is None or start > end:
        raise ValueError("Invalid audit period")

    findings = []
    for row_number, record in enumerate(records, start=1):
        transaction_date = _date(record.get(date_column))
        if transaction_date is None:
            code = "REV_CUTOFF_MISSING_DATE"
        elif transaction_date < start or transaction_date > end:
            code = "REV_CUTOFF_OUT_OF_PERIOD"
        else:
            continue

        amount = _amount(record.get(amount_column)) if amount_column else None
        findings.append({
            "rule_code": code,
            "severity": "MEDIUM",
            "source_row_number": row_number,
            "invoice_number": record.get(invoice_column) if invoice_column else None,
            "transaction_date": str(record.get(date_column) or ""),
            "amount_under_review": str(amount) if amount is not None else None,
            "explanation": "Review date and supporting dispatch/delivery evidence; this exception alone does not establish misstatement.",
        })

    return findings
