import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.endpoints.uploads import (
    ensure_upload_access,
    get_upload_or_404,
    parse_upload,
)
from app.db.session import get_db
from app.models.ai_analysis import AIAnalysisRun
from app.models.identity import User

router = APIRouter()


class ReconciliationRequest(BaseModel):
    sales_upload_id: str
    ledger_upload_id: str
    sales_invoice_column: str | None = None
    ledger_invoice_column: str | None = None
    sales_amount_column: str | None = None
    ledger_amount_column: str | None = None


def digest(value) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalized(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def find_column(headers, mapping, explicit, canonical, aliases):
    if explicit:
        if explicit not in headers:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Column {explicit!r} was not found.",
                    "available_columns": headers,
                },
            )
        return explicit

    mapped = mapping.get(canonical)
    if mapped in headers:
        return mapped

    normalized_headers = {
        normalized(header).replace("_", " "): header for header in headers
    }
    for alias in aliases:
        found = normalized_headers.get(normalized(alias).replace("_", " "))
        if found:
            return found
    return None


def parse_amount(value):
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    try:
        amount = Decimal(raw)
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def index_records(rows, key_column, amount_column, source_name):
    indexed = defaultdict(list)
    exceptions = []

    for row_number, row in enumerate(rows, start=2):
        key = normalized(row.get(key_column))
        amount = parse_amount(row.get(amount_column)) if amount_column else None

        if not key:
            exceptions.append({
                "source": source_name,
                "source_row_number": row_number,
                "rule_code": f"{source_name.upper()}_REFERENCE_MISSING",
                "status": "REQUIRES_REVIEW",
                "amount_under_review": None,
                "reason": "Cannot match this record because its reference is missing.",
            })
            continue

        indexed[key].append({
            "source_row_number": row_number,
            "reference": str(row.get(key_column)).strip(),
            "amount": amount,
        })

        if amount is None:
            exceptions.append({
                "source": source_name,
                "source_row_number": row_number,
                "reference": str(row.get(key_column)).strip(),
                "rule_code": f"{source_name.upper()}_AMOUNT_INVALID_OR_MISSING",
                "status": "REQUIRES_REVIEW",
                "amount_under_review": None,
                "reason": "Amount is missing or invalid; it was not treated as zero.",
            })

    return indexed, exceptions


@router.post("/reconcile", status_code=201)
def reconcile_sales_to_ledger(
    body: ReconciliationRequest,
    user: User = Depends(
        require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    if body.sales_upload_id == body.ledger_upload_id:
        raise HTTPException(
            status_code=422,
            detail="Sales register and ledger must be separate uploads.",
        )

    sales_upload = get_upload_or_404(db, body.sales_upload_id)
    ledger_upload = get_upload_or_404(db, body.ledger_upload_id)
    ensure_upload_access(db, user, sales_upload)
    ensure_upload_access(db, user, ledger_upload)

    if sales_upload.engagement_id != ledger_upload.engagement_id:
        raise HTTPException(
            status_code=422,
            detail="Both uploads must belong to the same engagement.",
        )

    sales_headers, sales_rows, sales_mapping = parse_upload(sales_upload)
    ledger_headers, ledger_rows, ledger_mapping = parse_upload(ledger_upload)

    if not sales_rows or not ledger_rows:
        raise HTTPException(
            status_code=422,
            detail="Both datasets must contain at least one data row.",
        )

    sales_key_col = find_column(
        sales_headers, sales_mapping, body.sales_invoice_column,
        "invoice_number",
        ["invoice number", "invoice no", "invoice no.", "document number",
         "document no", "voucher number", "reference"],
    )
    ledger_key_col = find_column(
        ledger_headers, ledger_mapping, body.ledger_invoice_column,
        "invoice_number",
        ["invoice number", "invoice no", "invoice no.", "document number",
         "document no", "voucher number", "reference", "bill reference"],
    )
    sales_amount_col = find_column(
        sales_headers, sales_mapping, body.sales_amount_column,
        "total_amount",
        ["total amount", "invoice amount", "gross amount", "amount"],
    )
    ledger_amount_col = find_column(
        ledger_headers, ledger_mapping, body.ledger_amount_column,
        "total_amount",
        ["total amount", "transaction amount", "credit amount",
         "amount", "value"],
    )

    missing = []
    for name, column in [
        ("sales invoice reference", sales_key_col),
        ("ledger invoice reference", ledger_key_col),
        ("sales total amount", sales_amount_col),
        ("ledger transaction amount", ledger_amount_col),
    ]:
        if not column:
            missing.append(name)

    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Required reconciliation columns could not be identified.",
                "missing_fields": missing,
                "sales_columns": sales_headers,
                "ledger_columns": ledger_headers,
            },
        )

    sales, sales_exceptions = index_records(
        sales_rows, sales_key_col, sales_amount_col, "sales"
    )
    ledger, ledger_exceptions = index_records(
        ledger_rows, ledger_key_col, ledger_amount_col, "ledger"
    )

    findings = []
    matched_count = 0
    compared_count = 0
    amount_difference_total = Decimal("0.00")

    # Duplicates are explicitly reported and excluded from automatic matching.
    duplicate_keys = set()
    for source_name, indexed in [("SALES", sales), ("LEDGER", ledger)]:
        for key, entries in indexed.items():
            if len(entries) > 1:
                duplicate_keys.add(key)
                findings.append({
                    "rule_code": f"{source_name}_DUPLICATE_REFERENCE",
                    "status": "REQUIRES_REVIEW",
                    "reference": entries[0]["reference"],
                    "source": source_name.lower(),
                    "source_rows": [entry["source_row_number"] for entry in entries],
                    "amount_under_review": None,
                    "reason": (
                        "Reference appears more than once; automatic matching "
                        "is suppressed until the duplicate is investigated."
                    ),
                })

    all_keys = set(sales) | set(ledger)

    for key in sorted(all_keys):
        sales_entries = sales.get(key, [])
        ledger_entries = ledger.get(key, [])

        if key in duplicate_keys:
            continue

        if sales_entries and not ledger_entries:
            entry = sales_entries[0]
            findings.append({
                "rule_code": "SALES_INVOICE_NOT_FOUND_IN_LEDGER",
                "status": "REQUIRES_REVIEW",
                "reference": entry["reference"],
                "sales_row": entry["source_row_number"],
                "ledger_row": None,
                "amount_under_review": (
                    str(entry["amount"].quantize(Decimal("0.01")))
                    if entry["amount"] is not None else None
                ),
                "reason": "Sales invoice reference was not found in the ledger.",
            })
            continue

        if ledger_entries and not sales_entries:
            entry = ledger_entries[0]
            findings.append({
                "rule_code": "LEDGER_ENTRY_NOT_FOUND_IN_SALES",
                "status": "REQUIRES_REVIEW",
                "reference": entry["reference"],
                "sales_row": None,
                "ledger_row": entry["source_row_number"],
                "amount_under_review": (
                    str(entry["amount"].quantize(Decimal("0.01")))
                    if entry["amount"] is not None else None
                ),
                "reason": "Ledger reference was not found in the sales register.",
            })
            continue

        sales_entry = sales_entries[0]
        ledger_entry = ledger_entries[0]

        if sales_entry["amount"] is None or ledger_entry["amount"] is None:
            continue

        compared_count += 1
        difference = sales_entry["amount"] - ledger_entry["amount"]

        if difference == 0:
            matched_count += 1
        else:
            amount_difference_total += abs(difference)
            findings.append({
                "rule_code": "SALES_LEDGER_AMOUNT_MISMATCH",
                "status": "REQUIRES_REVIEW",
                "reference": sales_entry["reference"],
                "sales_row": sales_entry["source_row_number"],
                "ledger_row": ledger_entry["source_row_number"],
                "sales_amount": str(sales_entry["amount"]),
                "ledger_amount": str(ledger_entry["amount"]),
                "difference_sales_minus_ledger": str(difference),
                "amount_under_review": str(abs(difference)),
                "reason": (
                    "Amounts differ for the same normalized reference. "
                    "Confirm signs, posting structure, tax treatment, and currency."
                ),
            })

    findings.extend(sales_exceptions)
    findings.extend(ledger_exceptions)

    result = {
        "analysis_type": "SALES_LEDGER_RECONCILIATION",
        "rule_version": "1.0",
        "engagement_id": sales_upload.engagement_id,
        "sales_upload_id": sales_upload.id,
        "ledger_upload_id": ledger_upload.id,
        "sales_source_sha256": sales_upload.sha256,
        "ledger_source_sha256": ledger_upload.sha256,
        "matching_method": "NORMALIZED_REFERENCE_AND_EXACT_DECIMAL_AMOUNT",
        "sales_reference_column": sales_key_col,
        "ledger_reference_column": ledger_key_col,
        "sales_amount_column": sales_amount_col,
        "ledger_amount_column": ledger_amount_col,
        "sales_population_count": len(sales_rows),
        "ledger_population_count": len(ledger_rows),
        "unique_reference_matches_compared": compared_count,
        "exact_amount_matches": matched_count,
        "exception_count": len(findings),
        "absolute_amount_difference_total": str(amount_difference_total),
        "currency": "AS_UPLOADED",
        "findings": findings,
        "conclusion": (
            "All exceptions require investigation. A missing match or amount "
            "difference does not, by itself, establish fraud or a confirmed "
            "misstatement. This first version does not infer many-to-one postings."
        ),
    }

    result_json = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    run = AIAnalysisRun(
        upload_id=sales_upload.id,
        engagement_id=sales_upload.engagement_id,
        executed_by=user.id,
        analysis_type="SALES_LEDGER_RECON",
        rule_version="1.0",
        source_sha256=digest({
            "sales": sales_upload.sha256,
            "ledger": ledger_upload.sha256,
        }),
        parameters_json=json.dumps({
            "sales_upload_id": sales_upload.id,
            "ledger_upload_id": ledger_upload.id,
            "sales_reference_column": sales_key_col,
            "ledger_reference_column": ledger_key_col,
            "sales_amount_column": sales_amount_col,
            "ledger_amount_column": ledger_amount_col,
            "ledger_source_sha256": ledger_upload.sha256,
        }, sort_keys=True),
        proposed_script=None,
        proposed_script_sha256=None,
        result_json=result_json,
        result_sha256=hashlib.sha256(result_json.encode("utf-8")).hexdigest(),
        population_count=len(sales_rows) + len(ledger_rows),
        exception_count=len(findings),
        status="SUCCEEDED",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "run_id": run.id,
        "status": run.status,
        "source_sha256": run.source_sha256,
        "result_sha256": run.result_sha256,
        **result,
    }
