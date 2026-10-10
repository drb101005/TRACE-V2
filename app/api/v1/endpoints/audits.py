import json
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models.engagement import Engagement, EngagementMembership
from app.models.identity import User
from app.models.ingestion import SourceUpload, SourceRecord
from app.models.audit import AuditRun, AuditFinding
from app.audit_engine.sales_register import run_sales_register

router = APIRouter()

def ensure_access(db, user, engagement_id):
    engagement = db.query(Engagement).filter_by(id=engagement_id).first()
    if not engagement:
        raise api_error(404, "ENGAGEMENT_NOT_FOUND", "Engagement was not found.")
    if user.role != "ADMIN" and not db.query(EngagementMembership).filter_by(engagement_id=engagement_id, user_id=user.id).first():
        raise api_error(403, "ENGAGEMENT_ACCESS_DENIED", "You do not have access to this engagement.")
    return engagement

def run_public(run):
    return {"id": run.id, "engagement_id": run.engagement_id, "upload_id": run.upload_id,
            "status": run.status, "engine_version": run.engine_version, "rules_version": run.rules_version,
            "population_count": run.population_count, "finding_count": run.finding_count,
            "summary": json.loads(run.summary_json), "created_at": run.created_at.isoformat()}

@router.post("/engagements/{engagement_id}/audit-runs", status_code=201)
def create_audit_run(engagement_id: str, upload_id: str,
                     user: User = Depends(require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")),
                     db: Session = Depends(get_db)):
    engagement = ensure_access(db, user, engagement_id)
    upload = db.query(SourceUpload).filter_by(id=upload_id, engagement_id=engagement_id).first()
    if not upload:
        raise api_error(404, "UPLOAD_NOT_FOUND", "Upload was not found in this engagement.")
    records = db.query(SourceRecord).filter_by(upload_id=upload.id).order_by(SourceRecord.source_row_number.asc()).all()
    if not records:
        raise api_error(409, "NO_SOURCE_RECORDS", "Ingest a validated upload before running audit tests.")
    if upload.dataset_type != "sales_register":
        raise api_error(422, "UNSUPPORTED_AUDIT_DATASET", "Phase 3A currently supports sales_register only.")
    inputs = [{"id": r.id, "upload_id": r.upload_id, "source_row_number": r.source_row_number,
               "record": json.loads(r.record_json)} for r in records]
    result = run_sales_register(inputs, engagement.period_start, engagement.period_end)
    run = AuditRun(engagement_id=engagement_id, upload_id=upload.id, initiated_by=user.id,
                   status="SUCCEEDED", engine_version=result["engine_version"], rules_version=result["rules_version"],
                   population_count=len(inputs), finding_count=len(result["findings"]),
                   summary_json=json.dumps(result["summary"], sort_keys=True))
    db.add(run); db.flush()
    for f in result["findings"]:
        db.add(AuditFinding(audit_run_id=run.id, engagement_id=engagement_id, upload_id=upload.id,
            source_record_id=f["source_record_id"], source_row_number=f["source_row_number"],
            fingerprint=f["fingerprint"], rule_code=f["rule_code"], title=f["title"], severity=f["severity"],
            status="DRAFT", explanation=f["explanation"], amount_under_review=f["amount_under_review"],
            calculation_json=json.dumps(f["calculation"], sort_keys=True)))
    db.commit(); db.refresh(run)
    return run_public(run)

@router.get("/engagements/{engagement_id}/audit-runs")
def list_audit_runs(engagement_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_access(db, user, engagement_id)
    q = db.query(AuditRun).filter_by(engagement_id=engagement_id).order_by(AuditRun.created_at.desc())
    total = q.count(); items = q.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [run_public(x) for x in items], "page": page, "page_size": page_size, "total": total}

@router.get("/audit-runs/{run_id}")
def get_audit_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.query(AuditRun).filter_by(id=run_id).first()
    if not run: raise api_error(404, "AUDIT_RUN_NOT_FOUND", "Audit run was not found.")
    ensure_access(db, user, run.engagement_id)
    return run_public(run)

@router.get("/audit-runs/{run_id}/findings")
def list_findings(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                  severity: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.query(AuditRun).filter_by(id=run_id).first()
    if not run: raise api_error(404, "AUDIT_RUN_NOT_FOUND", "Audit run was not found.")
    ensure_access(db, user, run.engagement_id)
    q = db.query(AuditFinding).filter_by(audit_run_id=run.id)
    if severity:
        q = q.filter(AuditFinding.severity == severity.upper())
    q = q.order_by(AuditFinding.source_row_number.asc(), AuditFinding.rule_code.asc())
    total = q.count(); items = q.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": x.id, "audit_run_id": x.audit_run_id, "source_record_id": x.source_record_id,
        "source_row_number": x.source_row_number, "rule_code": x.rule_code, "title": x.title,
        "severity": x.severity, "status": x.status, "explanation": x.explanation,
        "amount_under_review": x.amount_under_review, "calculation": json.loads(x.calculation_json),
        "created_at": x.created_at.isoformat()} for x in items],
        "page": page, "page_size": page_size, "total": total}



# Integrated revenue audit pipeline: deterministic rules + persisted findings.
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from app.services.audit_pipeline import run_revenue_audit
from app.services.audit_trail import append_audit_event


class RevenueAuditRequest(BaseModel):
    sales_upload_id: str
    ledger_upload_id: str
    invoice_column: str = Field(min_length=1, max_length=120)
    sales_amount_column: str = Field(min_length=1, max_length=120)
    ledger_invoice_column: str = Field(min_length=1, max_length=120)
    ledger_amount_column: str = Field(min_length=1, max_length=120)
    date_column: str = Field(min_length=1, max_length=120)
    materiality_threshold: str = Field(min_length=1, max_length=50)


@router.post("/engagements/{engagement_id}/revenue-audit-runs", status_code=201)
def create_revenue_audit_run(
    engagement_id: str,
    body: RevenueAuditRequest,
    user: User = Depends(require_roles(
        "ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR"
    )),
    db: Session = Depends(get_db),
):
    engagement = ensure_access(db, user, engagement_id)

    sales_upload = db.query(SourceUpload).filter_by(
        id=body.sales_upload_id, engagement_id=engagement_id
    ).first()
    ledger_upload = db.query(SourceUpload).filter_by(
        id=body.ledger_upload_id, engagement_id=engagement_id
    ).first()

    if not sales_upload or not ledger_upload:
        raise api_error(
            404, "UPLOAD_NOT_FOUND",
            "Both uploads must exist in the selected engagement."
        )

    if sales_upload.status != "INGESTED" or ledger_upload.status != "INGESTED":
        raise api_error(
            409, "UPLOAD_NOT_INGESTED",
            "Both uploads must be ingested before running the audit."
        )

    sales_records = db.query(SourceRecord).filter_by(
        upload_id=sales_upload.id
    ).order_by(SourceRecord.source_row_number.asc()).all()
    ledger_records = db.query(SourceRecord).filter_by(
        upload_id=ledger_upload.id
    ).order_by(SourceRecord.source_row_number.asc()).all()

    if not sales_records or not ledger_records:
        raise api_error(
            409, "NO_SOURCE_RECORDS",
            "Both datasets must contain ingested source records."
        )

    sales = [
        {**(record.get("source", {}) if isinstance(record.get("source"), dict) else {}),
         **record}
        for record in (json.loads(row.record_json) for row in sales_records)
    ]
    ledger = [
        {**(record.get("source", {}) if isinstance(record.get("source"), dict) else {}),
         **record}
        for record in (json.loads(row.record_json) for row in ledger_records)
    ]

    required_sales = {
        body.invoice_column, body.sales_amount_column, body.date_column
    }
    required_ledger = {
        body.ledger_invoice_column, body.ledger_amount_column
    }

    if not all(all(column in row for column in required_sales) for row in sales):
        raise api_error(
            422, "SALES_COLUMNS_MISSING",
            "One or more requested columns are missing from the sales dataset."
        )
    if not all(all(column in row for column in required_ledger) for row in ledger):
        raise api_error(
            422, "LEDGER_COLUMNS_MISSING",
            "One or more requested columns are missing from the ledger dataset."
        )

    if not engagement.period_start or not engagement.period_end:
        raise api_error(
            422, "AUDIT_PERIOD_REQUIRED",
            "Set the engagement period before running cutoff testing."
        )

    result = run_revenue_audit(
        sales=sales,
        ledger=ledger,
        invoice_column=body.invoice_column,
        sales_amount_column=body.sales_amount_column,
        ledger_invoice_column=body.ledger_invoice_column,
        ledger_amount_column=body.ledger_amount_column,
        date_column=body.date_column,
        period_start=str(engagement.period_start),
        period_end=str(engagement.period_end),
        materiality_threshold=body.materiality_threshold,
    )

    # Map invoice keys back to source records for traceability.
    source_by_invoice = {}
    for row in sales_records:
        record = json.loads(row.record_json)
        value = record.get(body.invoice_column)
        if value is not None and str(value).strip():
            source_by_invoice.setdefault(
                str(value).strip().casefold(), row
            )

    run = AuditRun(
        engagement_id=engagement_id,
        upload_id=sales_upload.id,
        initiated_by=user.id,
        status="SUCCEEDED",
        engine_version="trace-revenue-pipeline-v1",
        rules_version="revenue-rules-v1",
        population_count=len(sales_records),
        finding_count=len(result["exceptions"]),
        summary_json=json.dumps(result, sort_keys=True, default=str),
    )

    try:
        db.add(run)
        db.flush()

        for exception in result["exceptions"]:
            invoice = str(exception.get("invoice_number") or "").strip()
            source_row = source_by_invoice.get(invoice.casefold())
            row_number = exception.get("source_row_number")
            if row_number is not None:
                source_row = next(
                    (
                        row for row in sales_records
                        if row.source_row_number == row_number
                    ),
                    source_row,
                )

            rule_code = exception["rule_code"]
            calculation = {
                "pipeline": result["engine"],
                "exception": exception,
                "risk": exception["risk"],
                "sales_upload_sha256": sales_upload.sha256,
                "ledger_upload_sha256": ledger_upload.sha256,
            }
            fingerprint_payload = {
                "audit_run_id": run.id,
                "rule_code": rule_code,
                "source_row_number": (
                    source_row.source_row_number if source_row else None
                ),
                "invoice": invoice,
                "calculation": calculation,
            }
            fingerprint = __import__("hashlib").sha256(
                json.dumps(
                    fingerprint_payload, sort_keys=True, default=str
                ).encode()
            ).hexdigest()

            db.add(AuditFinding(
                audit_run_id=run.id,
                engagement_id=engagement_id,
                upload_id=sales_upload.id,
                source_record_id=source_row.id if source_row else None,
                source_row_number=(
                    source_row.source_row_number if source_row else None
                ),
                fingerprint=fingerprint,
                rule_code=rule_code,
                title=rule_code.replace("_", " ").title(),
                severity=exception.get("severity", "MEDIUM"),
                status="DRAFT",
                explanation=exception.get(
                    "explanation",
                    "Deterministic audit exception requires human review."
                ),
                amount_under_review=(
                    str(exception.get("amount_under_review"))
                    if exception.get("amount_under_review") is not None
                    else (
                        str(abs(__import__("decimal").Decimal(
                            exception["difference"]
                        )))
                        if exception.get("difference") is not None
                        else None
                    )
                ),
                calculation_json=json.dumps(
                    calculation, sort_keys=True, default=str
                ),
            ))

        db.flush()
        append_audit_event(
            db,
            engagement_id=engagement_id,
            actor_id=str(user.id),
            event_type="REVENUE_AUDIT_RUN_CREATED",
            resource_type="AUDIT_RUN",
            resource_id=run.id,
            previous_status=None,
            new_status="SUCCEEDED",
            details={
                "sales_upload_id": sales_upload.id,
                "ledger_upload_id": ledger_upload.id,
                "finding_count": len(result["exceptions"]),
                "engine": result["engine"],
                "rules_version": "revenue-rules-v1",
            },
        )
        db.commit()
        db.refresh(run)
    except Exception:
        db.rollback()
        raise

    return {
        "id": run.id,
        "engagement_id": run.engagement_id,
        "upload_id": run.upload_id,
        "ledger_upload_id": ledger_upload.id,
        "status": run.status,
        "engine_version": run.engine_version,
        "rules_version": run.rules_version,
        "population_count": run.population_count,
        "finding_count": run.finding_count,
        "summary": result,
        "created_at": run.created_at.isoformat(),
    }
