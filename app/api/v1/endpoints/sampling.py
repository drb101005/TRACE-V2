import hashlib
import json
import random
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.endpoints.uploads import (
    ensure_upload_access, get_upload_or_404, parse_upload,
)
from app.db.session import get_db
from app.models.ai_analysis import AIAnalysisRun
from app.models.identity import User

router = APIRouter()


class SamplingRequest(BaseModel):
    upload_id: str
    period_start: date
    period_end: date
    sample_size: int = Field(default=30, ge=1, le=500)
    seed: int = 20261010
    invoice_column: str | None = None
    date_column: str | None = None
    amount_column: str | None = None


def sha256(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str,
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def money(value):
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    try:
        result = Decimal(raw)
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def choose_column(headers, mapping, explicit, canonical, aliases):
    if explicit:
        if explicit not in headers:
            raise HTTPException(422, {
                "message": f"Column {explicit!r} was not found.",
                "available_columns": headers,
            })
        return explicit
    mapped = mapping.get(canonical)
    if mapped in headers:
        return mapped
    normalized_headers = {
        norm(h).replace("_", " "): h for h in headers
    }
    for alias in aliases:
        found = normalized_headers.get(norm(alias).replace("_", " "))
        if found:
            return found
    return None


@router.post("/sample-sales-tod", status_code=201)
def sample_sales_tod(
    body: SamplingRequest,
    user: User = Depends(
        require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    if body.period_start > body.period_end:
        raise HTTPException(422, "period_start must not be after period_end.")

    upload = get_upload_or_404(db, body.upload_id)
    ensure_upload_access(db, user, upload)
    headers, rows, mapping = parse_upload(upload)
    if not rows:
        raise HTTPException(422, "Uploaded dataset has no rows.")

    invoice_col = choose_column(
        headers, mapping, body.invoice_column, "invoice_number",
        ["invoice number", "invoice no", "invoice no.", "document number"],
    )
    date_col = choose_column(
        headers, mapping, body.date_column, "invoice_date",
        ["invoice date", "document date", "date"],
    )
    amount_col = choose_column(
        headers, mapping, body.amount_column, "total_amount",
        ["total amount", "invoice amount", "gross amount", "amount"],
    )
    if not invoice_col or not date_col:
        raise HTTPException(422, {
            "message": "Invoice reference and date columns are required.",
            "available_columns": headers,
        })

    # Duplicate counts are calculated before scoring each row.
    reference_counts = {}
    for row in rows:
        key = norm(row.get(invoice_col))
        if key:
            reference_counts[key] = reference_counts.get(key, 0) + 1

    prepared = []
    for idx, row in enumerate(rows, start=2):
        reference = str(row.get(invoice_col) or "").strip()
        date_value = pd.to_datetime(row.get(date_col), errors="coerce")
        invoice_date = None if pd.isna(date_value) else date_value.date()
        amount = money(row.get(amount_col)) if amount_col else None
        factors = []
        score = 0

        def add(points, label):
            nonlocal score
            score += points
            factors.append(label)

        if not reference:
            add(25, "MISSING_INVOICE_REFERENCE")
        elif reference_counts.get(norm(reference), 0) > 1:
            add(25, "DUPLICATE_INVOICE_REFERENCE")

        if invoice_date is None:
            add(20, "MISSING_OR_INVALID_INVOICE_DATE")
        elif invoice_date < body.period_start or invoice_date > body.period_end:
            add(30, "OUTSIDE_AUDIT_PERIOD")
        else:
            days_from_start = (invoice_date - body.period_start).days
            days_to_end = (body.period_end - invoice_date).days
            if min(days_from_start, days_to_end) <= 10:
                add(20, "PERIOD_CUTOFF_PROXIMITY")

        if amount is None:
            add(15, "MISSING_OR_INVALID_AMOUNT")

        # Only test arithmetic when all three mapped components are present.
        taxable_col = mapping.get("taxable_value")
        tax_col = mapping.get("tax_amount")
        total_col = amount_col
        if taxable_col in headers and tax_col in headers and total_col in headers:
            taxable = money(row.get(taxable_col))
            tax = money(row.get(tax_col))
            total = money(row.get(total_col))
            if taxable is not None and tax is not None and total is not None:
                if abs((taxable + tax) - total) > Decimal("0.01"):
                    add(25, "INVOICE_ARITHMETIC_MISMATCH")

        # Optional evidence fields: only score when present in the source.
        for canonical, aliases in [
            ("dispatch_reference", ["dispatch reference", "dispatch no", "delivery challan"]),
            ("eway_bill_number", ["e-way bill", "eway bill number", "e-way bill number"]),
        ]:
            col = mapping.get(canonical)
            if col not in headers:
                col = next(
                    (h for h in headers if norm(h).replace("_", " ") in
                     {norm(a).replace("_", " ") for a in aliases}),
                    None,
                )
            if col and not str(row.get(col) or "").strip():
                add(15, f"MISSING_{canonical.upper()}")

        score = min(score, 100)
        prepared.append({
            "source_row_number": idx,
            "invoice_number": reference or None,
            "invoice_date": invoice_date.isoformat() if invoice_date else None,
            "amount": str(amount) if amount is not None else None,
            "risk_score": score,
            "risk_level": "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW",
            "risk_factors": factors,
            "mandatory_priority": bool(factors),
            "record": row,
        })

    rng = random.Random(body.seed)
    # Seeded tie-breakers and random fill make a run reproducible.
    for item in prepared:
        item["_tie"] = rng.random()

    # Priority: risk flags first, then higher score; random tie-breaks.
    ranked = sorted(
        prepared,
        key=lambda item: (
            not item["mandatory_priority"],
            -item["risk_score"],
            item["_tie"],
            item["source_row_number"],
        ),
    )
    selected = ranked[:min(body.sample_size, len(ranked))]
    selected_ids = {item["source_row_number"] for item in selected}

    # Random fill from unselected records when risk priorities do not fill the sample.
    remaining = [item for item in prepared if item["source_row_number"] not in selected_ids]
    rng.shuffle(remaining)
    for item in remaining:
        if len(selected) >= min(body.sample_size, len(prepared)):
            break
        selected.append(item)

    selected.sort(key=lambda item: (-item["risk_score"], item["source_row_number"]))
    output = [
        {k: v for k, v in item.items() if k not in {"record", "_tie"}}
        | {"selection_method": (
            "RISK_PRIORITY" if item["mandatory_priority"] else "SEEDED_RANDOM_FILL"
        )}
        for item in selected
    ]

    result = {
        "analysis_type": "SALES_TOD_SAMPLING",
        "rule_version": "1.0",
        "upload_id": upload.id,
        "source_sha256": upload.sha256,
        "period_start": body.period_start.isoformat(),
        "period_end": body.period_end.isoformat(),
        "requested_sample_size": body.sample_size,
        "population_count": len(rows),
        "selected_count": len(output),
        "seed": body.seed,
        "reproducible": True,
        "scoring_dimensions_available": [
            "invoice_reference", "invoice_date_cutoff", "amount_validity",
            "duplicate_reference", "invoice_arithmetic",
            "optional_dispatch_evidence",
        ],
        "scoring_dimensions_not_assessed": [
            "related_party_relationships",
            "sales_to_ledger_reconciliation",
            "counterparty_concentration",
            "counterparty_graph",
            "credit_note_lifecycle",
        ],
        "selected_sample": output,
        "conclusion": (
            "This is a risk-based audit sample for auditor review, not a "
            "statistical projection of the entire population. A population "
            "smaller than the requested sample is selected in full."
        ),
    }
    result_json = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    run = AIAnalysisRun(
        upload_id=upload.id,
        engagement_id=upload.engagement_id,
        executed_by=user.id,
        analysis_type="SALES_TOD_SAMPLE",
        rule_version="1.0",
        source_sha256=upload.sha256,
        parameters_json=json.dumps({
            "period_start": body.period_start.isoformat(),
            "period_end": body.period_end.isoformat(),
            "sample_size": body.sample_size,
            "seed": body.seed,
            "invoice_column": invoice_col,
            "date_column": date_col,
            "amount_column": amount_col,
        }, sort_keys=True),
        proposed_script=None,
        proposed_script_sha256=None,
        result_json=result_json,
        result_sha256=hashlib.sha256(result_json.encode()).hexdigest(),
        population_count=len(rows),
        exception_count=sum(1 for item in selected if item["risk_score"] > 0),
        status="SUCCEEDED",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "run_id": run.id,
        "status": run.status,
        "result_sha256": run.result_sha256,
        **result,
    }
