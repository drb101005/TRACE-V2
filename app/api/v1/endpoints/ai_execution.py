import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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
from app.services.groq_audit import generate_audit_script

router = APIRouter()


class CutoffTestRequest(BaseModel):
    upload_id: str
    period_start: date
    period_end: date
    date_column: str | None = None
    amount_column: str | None = None
    objective: str = Field(
        default="Identify invoices outside the specified audit period.",
        min_length=10,
        max_length=1000,
    )


def canonical_hash(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post("/execute-cutoff-test", status_code=201)
def execute_cutoff_test(
    body: CutoffTestRequest,
    user: User = Depends(
        require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    if body.period_start > body.period_end:
        raise HTTPException(
            status_code=422, detail="period_start must not be after period_end."
        )

    upload = get_upload_or_404(db, body.upload_id)
    ensure_upload_access(db, user, upload)

    headers, rows, mapping = parse_upload(upload)
    if not rows:
        raise HTTPException(status_code=422, detail="Uploaded dataset has no rows.")

    # Prefer saved canonical mapping; otherwise match a source header safely.
    date_column = body.date_column or mapping.get("invoice_date")
    if not date_column:
        aliases = {"invoice date", "invoice_date", "date", "document date"}
        date_column = next(
            (
                h for h in headers
                if " ".join(h.strip().lower().replace("_", " ").split()) in aliases
            ),
            None,
        )

    if not date_column or date_column not in headers:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Could not identify the invoice date column.",
                "available_columns": headers,
            },
        )

    amount_column = body.amount_column or mapping.get("total_amount")
    if amount_column not in headers:
        amount_column = None

    # Groq generates a proposal only. It is never executed by this endpoint.
    proposed_script = None
    proposal_status = "UNAVAILABLE"
    try:
        proposed_script = generate_audit_script(
            objective=(
                f"{body.objective} Audit period: {body.period_start} "
                f"through {body.period_end}. Use the actual column "
                f"{date_column!r}."
            ),
            columns=headers,
        )
        proposal_status = "GENERATED"
    except Exception:
        # Deterministic audit test must remain usable if the AI provider fails.
        proposal_status = "PROVIDER_ERROR"

    # Authoritative execution: deterministic date comparison, not generated code.
    exceptions = []
    amount_under_review = Decimal("0.00")
    invalid_date_count = 0

    for index, row in enumerate(rows, start=2):
        raw_date = row.get(date_column)
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed):
            invalid_date_count += 1
            continue

        invoice_date = parsed.date()
        if invoice_date < body.period_start or invoice_date > body.period_end:
            amount = None
            if amount_column:
                raw_amount = row.get(amount_column)
                if raw_amount not in (None, ""):
                    try:
                        candidate = Decimal(
                            str(raw_amount).replace(",", "").replace("₹", "").strip()
                        )
                        if candidate.is_finite():
                            amount = candidate
                            amount_under_review += candidate
                    except (InvalidOperation, ValueError):
                        pass

            exceptions.append({
                "source_row_number": index,
                "invoice_number": (
                    row.get(mapping.get("invoice_number"))
                    if mapping.get("invoice_number") else None
                ),
                "invoice_date": invoice_date.isoformat(),
                "amount": str(amount) if amount is not None else None,
                "amount_under_review": str(amount) if amount is not None else None,
                "status": "REQUIRES_REVIEW",
                "reason": "Invoice date falls outside the configured audit period.",
            })

    result = {
        "analysis_type": "SALES_CUTOFF",
        "rule_version": "1.0",
        "period_start": body.period_start.isoformat(),
        "period_end": body.period_end.isoformat(),
        "date_column": date_column,
        "amount_column": amount_column,
        "population_count": len(rows),
        "exception_count": len(exceptions),
        "invalid_or_missing_date_count": invalid_date_count,
        "amount_under_review": str(amount_under_review),
        "currency": "AS_UPLOADED",
        "exceptions": exceptions,
        "conclusion": (
            "Exceptions require auditor review; date alone does not establish "
            "fraud or a confirmed misstatement."
        ),
    }

    result_json = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    script_hash = (
        hashlib.sha256(proposed_script.encode()).hexdigest()
        if proposed_script else None
    )

    run = AIAnalysisRun(
        upload_id=upload.id,
        engagement_id=upload.engagement_id,
        executed_by=user.id,
        source_sha256=upload.sha256,
        parameters_json=json.dumps({
            "period_start": body.period_start.isoformat(),
            "period_end": body.period_end.isoformat(),
            "date_column": date_column,
            "amount_column": amount_column,
            "objective": body.objective,
            "proposal_status": proposal_status,
        }, sort_keys=True),
        proposed_script=proposed_script,
        proposed_script_sha256=script_hash,
        result_json=result_json,
        result_sha256=hashlib.sha256(result_json.encode()).hexdigest(),
        population_count=len(rows),
        exception_count=len(exceptions),
        status="SUCCEEDED",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "run_id": run.id,
        "status": run.status,
        "upload_id": upload.id,
        "source_sha256": run.source_sha256,
        "result_sha256": run.result_sha256,
        "created_at": run.created_at.isoformat(),
        "proposal_status": proposal_status,
        "execution_mode": "DETERMINISTIC_RULE_ENGINE",
        **result,
    }


@router.get("/analysis-runs/{run_id}")
def get_analysis_run(
    run_id: str,
    user: User = Depends(
        require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    run = db.query(AIAnalysisRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")

    upload = get_upload_or_404(db, run.upload_id)
    ensure_upload_access(db, user, upload)

    return {
        "run_id": run.id,
        "upload_id": run.upload_id,
        "engagement_id": run.engagement_id,
        "analysis_type": run.analysis_type,
        "rule_version": run.rule_version,
        "source_sha256": run.source_sha256,
        "result_sha256": run.result_sha256,
        "population_count": run.population_count,
        "exception_count": run.exception_count,
        "status": run.status,
        "parameters": json.loads(run.parameters_json),
        "result": json.loads(run.result_json),
        "proposed_script": run.proposed_script,
        "proposed_script_sha256": run.proposed_script_sha256,
        "created_at": run.created_at.isoformat(),
    }
