"""Deterministic, versioned sales-register checks. No LLM computes authoritative amounts."""
import hashlib, json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ENGINE_VERSION = "trace-audit-0.1.0"
RULES_VERSION = "sales-register-v1"
CENT = Decimal("0.01")

def money(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").replace("₹", "").strip())
        if not result.is_finite():
            return None
        return result.quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None

def parse_date(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None

def canonical(record):
    # Ingested record stores canonical fields alongside original row under "source".
    return record if isinstance(record, dict) else {}

def run_sales_register(records, period_start, period_end):
    findings = []
    parsed = []
    invoice_seen = {}
    totals = {"population_count": len(records), "total_amount": "0.00", "taxable_value": "0.00", "tax_amount": "0.00"}
    sums = {k: Decimal("0.00") for k in ("total_amount", "taxable_value", "tax_amount")}
    for item in records:
        rec = canonical(item.get("record", {}))
        for k in sums:
            val = money(rec.get(k))
            if val is not None:
                sums[k] += val
        parsed.append((item, rec))
    totals.update({k: format(v, "f") for k, v in sums.items()})

    for item, rec in parsed:
        row = item.get("source_row_number")
        rid = item.get("id")
        invoice = str(rec.get("invoice_number") or "").strip()
        inv_date = parse_date(rec.get("invoice_date"))
        amount = money(rec.get("total_amount"))
        taxable = money(rec.get("taxable_value"))
        tax = money(rec.get("tax_amount"))
        def add(code, title, severity, explanation, amount_review=None, calc=None):
            material = f"{item.get('upload_id')}|{rid}|{code}|{json.dumps(calc or {},sort_keys=True)}"
            findings.append({
                "source_record_id": rid, "source_row_number": row,
                "rule_code": code, "title": title, "severity": severity,
                "explanation": explanation,
                "amount_under_review": format(amount_review, "f") if amount_review is not None else None,
                "calculation": calc or {},
                "fingerprint": hashlib.sha256(material.encode()).hexdigest()
            })
        if not invoice:
            add("INV_NUMBER_MISSING", "Invoice number missing", "MEDIUM",
                "No invoice number was mapped for this source row.")
        elif invoice.casefold() in invoice_seen:
            add("DUPLICATE_INVOICE_NUMBER", "Possible duplicate invoice number", "HIGH",
                f"Invoice number duplicates source row {invoice_seen[invoice.casefold()]}; confirm whether this is a legitimate reissue.",
                amount, {"invoice_number": invoice, "first_source_row": invoice_seen[invoice.casefold()]})
        else:
            invoice_seen[invoice.casefold()] = row
        if amount is None:
            add("TOTAL_AMOUNT_INVALID_OR_MISSING", "Total amount missing or invalid", "HIGH",
                "Total amount could not be parsed as a finite decimal; it was not treated as zero.")
        if taxable is not None and tax is not None and amount is not None:
            expected = (taxable + tax).quantize(CENT, rounding=ROUND_HALF_UP)
            difference = (amount - expected).quantize(CENT, rounding=ROUND_HALF_UP)
            if difference != 0:
                add("INVOICE_ARITHMETIC_MISMATCH", "Invoice arithmetic mismatch", "HIGH",
                    "Total amount differs from taxable value plus tax. Verify source document and mapping.",
                    abs(difference), {"taxable_value": str(taxable), "tax_amount": str(tax),
                    "expected_total": str(expected), "reported_total": str(amount), "difference": str(difference)})
        elif any(v is None for v in (taxable, tax, amount)):
            add("ARITHMETIC_NOT_TESTABLE", "Invoice arithmetic could not be tested", "LOW",
                "One or more required amounts are unavailable. This is a data limitation, not a confirmed misstatement.")
        if inv_date is None:
            add("INVOICE_DATE_MISSING_OR_INVALID", "Invoice date missing or invalid", "MEDIUM",
                "Invoice date could not be parsed; period and cut-off tests are limited.")
        elif inv_date < period_start or inv_date > period_end:
            add("INVOICE_OUTSIDE_AUDIT_PERIOD", "Invoice date outside engagement period", "MEDIUM",
                f"Invoice date {inv_date.isoformat()} falls outside {period_start.isoformat()} to {period_end.isoformat()}. Verify cut-off and engagement scope.",
                amount, {"invoice_date": inv_date.isoformat(), "period_start": period_start.isoformat(), "period_end": period_end.isoformat()})
    return {"engine_version": ENGINE_VERSION, "rules_version": RULES_VERSION,
            "summary": totals, "findings": findings}
