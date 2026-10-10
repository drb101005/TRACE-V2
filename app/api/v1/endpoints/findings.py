import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.endpoints.uploads import ensure_upload_access, get_upload_or_404
from app.db.session import get_db
from app.models.audit import AuditRun, AuditFinding
from app.models.evidence import Evidence
from app.models.evidence_link import EvidenceLink
from app.models.finding_review import FindingReviewRecord
from app.models.identity import User
from app.services.audit_trail import append_audit_event

router = APIRouter()


def validate_amount(value, field_name, required=False):
    if value is None:
        if required:
            raise HTTPException(status_code=422, detail=f"{field_name} is required")
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a decimal")
    if not amount.is_finite() or amount < 0:
        raise HTTPException(status_code=422, detail=f"{field_name} must be finite and non-negative")
    return amount


def serialize_finding(f):
    calculation = json.loads(f.calculation_json)
    return {
        "id": f.id,
        "audit_run_id": f.audit_run_id,
        "engagement_id": f.engagement_id,
        "upload_id": f.upload_id,
        "source_record_id": f.source_record_id,
        "source_row_number": f.source_row_number,
        "fingerprint": f.fingerprint,
        "rule_code": f.rule_code,
        "title": f.title,
        "severity": f.severity,
        "status": f.status,
        "explanation": f.explanation,
        "amount_under_review": f.amount_under_review,
        "calculation": calculation,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def get_finding_or_404(db, finding_id):
    finding = db.query(AuditFinding).filter_by(id=finding_id).first()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


def check_finding_access(db, user, finding):
    upload = get_upload_or_404(db, finding.upload_id)
    ensure_upload_access(db, user, upload)
    return upload


class FindingCreate(BaseModel):
    audit_run_id: str
    rule_code: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=3, max_length=240)
    explanation: str = Field(min_length=10, max_length=10000)
    severity: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    source_row_number: int | None = Field(default=None, ge=2)
    amount_under_review: str | None = None
    calculation: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)


class FindingReview(BaseModel):
    decision: str = Field(pattern="^(CONFIRM|REJECT|REQUEST_CHANGES)$")
    review_note: str = Field(min_length=5, max_length=5000)
    confirmed_misstatement_amount: str | None = None


@router.post("/findings", status_code=201)
def create_finding(
    body: FindingCreate,
    user: User = Depends(require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")),
    db: Session = Depends(get_db),
):
    run = db.query(AuditRun).filter_by(id=body.audit_run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found")
    if run.status != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="Findings require a successful audit run")

    upload = get_upload_or_404(db, run.upload_id)
    ensure_upload_access(db, user, upload)

    amount = validate_amount(body.amount_under_review, "amount_under_review")
    evidence_records = []
    for evidence_id in body.evidence_ids:
        evidence = db.query(Evidence).filter_by(id=evidence_id).first()
        if evidence is None:
            raise HTTPException(status_code=404, detail=f"Evidence not found: {evidence_id}")
        if str(evidence.engagement_id) != str(run.engagement_id):
            raise HTTPException(status_code=409, detail="Evidence belongs to a different engagement")
        evidence_upload = get_upload_or_404(db, evidence.upload_id)
        ensure_upload_access(db, user, evidence_upload)
        evidence_records.append(evidence)

    fingerprint_input = {
        "audit_run_id": run.id,
        "rule_code": body.rule_code,
        "title": body.title,
        "source_row_number": body.source_row_number,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True).encode("utf-8")
    ).hexdigest()

    existing = db.query(AuditFinding).filter_by(
        audit_run_id=run.id, fingerprint=fingerprint
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A finding with this fingerprint already exists")

    source_record_id = None
    if body.source_row_number is not None:
        from app.models.ingestion import SourceRecord
        record = db.query(SourceRecord).filter_by(
            upload_id=run.upload_id,
            source_row_number=body.source_row_number,
        ).first()
        if record is None:
            raise HTTPException(status_code=422, detail="Source row does not exist in this upload")
        source_record_id = record.id

    finding = AuditFinding(
        id=str(uuid.uuid4()),
        audit_run_id=run.id,
        engagement_id=run.engagement_id,
        upload_id=run.upload_id,
        source_record_id=source_record_id,
        source_row_number=body.source_row_number,
        fingerprint=fingerprint,
        rule_code=body.rule_code,
        title=body.title,
        severity=body.severity,
        status="DRAFT",
        explanation=body.explanation,
        amount_under_review=format(amount, "f") if amount is not None else None,
        calculation_json=json.dumps(body.calculation, sort_keys=True),
    )
    try:
        db.add(finding)
        db.flush()
        append_audit_event(
            db,
            engagement_id=run.engagement_id,
            actor_id=str(user.id),
            event_type="FINDING_CREATED",
            resource_type="FINDING",
            resource_id=finding.id,
            previous_status=None,
            new_status=finding.status,
            details={"audit_run_id": run.id, "rule_code": finding.rule_code},
        )
        for evidence in evidence_records:
            db.add(EvidenceLink(
                id=str(uuid.uuid4()),
                engagement_id=run.engagement_id,
                evidence_id=evidence.id,
                resource_type="FINDING",
                resource_id=finding.id,
                source_row_number=body.source_row_number,
                linked_by=str(user.id),
            ))
        db.commit()
        db.refresh(finding)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate finding or evidence link")
    except Exception:
        db.rollback()
        raise
    return serialize_finding(finding)


@router.get("/findings")
def list_findings(
    engagement_id: str,
    audit_run_id: str | None = None,
    user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")),
    db: Session = Depends(get_db),
):
    query = db.query(AuditFinding).filter_by(engagement_id=engagement_id)
    if audit_run_id:
        query = query.filter_by(audit_run_id=audit_run_id)

    results = []
    for finding in query.order_by(AuditFinding.created_at.desc()).all():
        try:
            check_finding_access(db, user, finding)
            results.append(serialize_finding(finding))
        except HTTPException:
            continue
    return {"items": results, "total": len(results)}


@router.get("/findings/{finding_id}")
def get_finding(
    finding_id: str,
    user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")),
    db: Session = Depends(get_db),
):
    finding = get_finding_or_404(db, finding_id)
    check_finding_access(db, user, finding)
    links = db.query(EvidenceLink).filter_by(
        resource_type="FINDING", resource_id=finding.id
    ).all()
    reviews = db.query(FindingReviewRecord).filter_by(
        finding_id=finding.id
    ).order_by(FindingReviewRecord.created_at.desc()).all()

    return {
        **serialize_finding(finding),
        "evidence_links": [
            {"link_id": link.id, "evidence_id": link.evidence_id,
             "source_row_number": link.source_row_number}
            for link in links
        ],
        "review_history": [
            {
                "id": review.id,
                "reviewer_id": review.reviewer_id,
                "decision": review.decision,
                "review_note": review.review_note,
                "confirmed_misstatement_amount": (
                    str(review.confirmed_misstatement_amount)
                    if review.confirmed_misstatement_amount is not None else None
                ),
                "created_at": review.created_at.isoformat() if review.created_at else None,
            }
            for review in reviews
        ],
    }


@router.post("/findings/{finding_id}/review")
def review_finding(
    finding_id: str,
    body: FindingReview,
    user: User = Depends(require_roles("ADMIN", "HUMAN_AUDITOR")),
    db: Session = Depends(get_db),
):
    finding = get_finding_or_404(db, finding_id)
    check_finding_access(db, user, finding)

    if finding.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT findings can be reviewed")

    previous_status = finding.status
    confirmed_amount = validate_amount(
        body.confirmed_misstatement_amount,
        "confirmed_misstatement_amount",
        required=(body.decision == "CONFIRM"),
    )
    if body.decision == "CONFIRM":
        finding.status = "CONFIRMED"
    elif body.decision == "REJECT":
        finding.status = "REJECTED"
    else:
        finding.status = "DRAFT"

    review = FindingReviewRecord(
        id=str(uuid.uuid4()),
        finding_id=finding.id,
        reviewer_id=str(user.id),
        decision=body.decision,
        review_note=body.review_note,
        confirmed_misstatement_amount=confirmed_amount,
    )
    try:
        db.add(review)
        db.flush()
        append_audit_event(
            db,
            engagement_id=finding.engagement_id,
            actor_id=str(user.id),
            event_type="FINDING_REVIEWED",
            resource_type="FINDING",
            resource_id=finding.id,
            previous_status=previous_status,
            new_status=finding.status,
            details={
                "decision": body.decision,
                "review_record_id": review.id,
            },
        )
        db.commit()
        db.refresh(finding)
    except Exception:
        db.rollback()
        raise

    return {
        **serialize_finding(finding),
        "review": {
            "id": review.id,
            "reviewer_id": review.reviewer_id,
            "decision": review.decision,
            "review_note": review.review_note,
            "confirmed_misstatement_amount": (
                str(review.confirmed_misstatement_amount)
                if review.confirmed_misstatement_amount is not None else None
            ),
        },
    }
