"""Unified deterministic revenue-audit orchestration."""

from typing import Any, Mapping, Sequence

from app.services.audit_risk import score_audit_risk, rank_audit_exceptions
from app.services.revenue_audit_rules import (
    find_duplicate_invoices,
    reconcile_amounts,
    test_sales_cutoff,
)


def run_revenue_audit(
    *,
    sales: Sequence[Mapping[str, Any]],
    ledger: Sequence[Mapping[str, Any]],
    invoice_column: str,
    sales_amount_column: str,
    ledger_invoice_column: str,
    ledger_amount_column: str,
    date_column: str,
    period_start: str,
    period_end: str,
    materiality_threshold: str,
    evidence_status_by_invoice: Mapping[str, str] | None = None,
) -> dict:
    """
    Execute deterministic checks and return a reproducible review queue.

    Results are proposed exceptions, not confirmed misstatements.
    This function does not mutate input records or persist findings.
    """
    evidence_status_by_invoice = evidence_status_by_invoice or {}

    exceptions = []
    exceptions.extend(
        find_duplicate_invoices(sales, invoice_column)
    )
    exceptions.extend(
        reconcile_amounts(
            sales,
            ledger,
            invoice_column,
            ledger_invoice_column,
            sales_amount_column,
            ledger_amount_column,
        )
    )
    exceptions.extend(
        test_sales_cutoff(
            sales,
            date_column,
            period_start,
            period_end,
            invoice_column,
            sales_amount_column,
        )
    )

    ranked = []
    for exception in exceptions:
        invoice = str(exception.get("invoice_number") or "")
        amount = (
            exception.get("amount_under_review")
            if exception.get("amount_under_review") is not None
            else exception.get("difference")
        )

        severity = exception.get("severity", "MEDIUM")
        evidence_status = evidence_status_by_invoice.get(invoice, "UNKNOWN")

        risk = score_audit_risk(
            amount=amount,
            materiality_threshold=materiality_threshold,
            rule_severity=severity,
            evidence_status=evidence_status,
        )

        ranked.append({
            **exception,
            "risk": risk,
            "review_status": "REQUIRES_REVIEW",
            "confirmed_misstatement": False,
        })

    ranked = rank_audit_exceptions(ranked)

    counts = {}
    for item in ranked:
        code = item["rule_code"]
        counts[code] = counts.get(code, 0) + 1

    return {
        "engine": "trace-deterministic-revenue-pipeline-v1",
        "status": "COMPLETED",
        "sales_record_count": len(sales),
        "ledger_record_count": len(ledger),
        "exception_count": len(ranked),
        "rule_counts": dict(sorted(counts.items())),
        "exceptions": ranked,
        "limitations": [
            "Exceptions require investigation; they are not automatically misstatements.",
            "Risk scores prioritize review and do not establish fraud.",
            "Evidence status defaults to UNKNOWN when no status is supplied.",
            "Results are not persisted until committed through the audit API.",
        ],
    }
