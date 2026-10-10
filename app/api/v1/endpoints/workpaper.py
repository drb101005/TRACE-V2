import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.uploads import ensure_upload_access, get_upload_or_404
from app.db.session import get_db
from app.models.audit import AuditRun, AuditFinding
from app.models.ingestion import SourceUpload
from app.models.evidence import Evidence
from app.models.evidence_link import EvidenceLink
from app.models.finding_review import FindingReviewRecord
from app.models.identity import User
from app.services.audit_trail import verify_engagement_chain

router = APIRouter()


def iso(value):
    return value.isoformat() if value else None


@router.get("/audit-runs/{run_id}/workpaper")
def export_workpaper(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(AuditRun).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found")

    upload = get_upload_or_404(db, run.upload_id)
    ensure_upload_access(db, user, upload)

    findings = (
        db.query(AuditFinding)
        .filter_by(audit_run_id=run.id)
        .order_by(AuditFinding.created_at.asc(), AuditFinding.id.asc())
        .all()
    )

    finding_items = []
    for finding in findings:
        links = (
            db.query(EvidenceLink)
            .filter_by(resource_type="FINDING", resource_id=finding.id)
            .order_by(EvidenceLink.id.asc())
            .all()
        )

        evidence_items = []
        for link in links:
            evidence = db.query(Evidence).filter_by(id=link.evidence_id).first()
            if evidence is None:
                evidence_items.append({
                    "evidence_id": link.evidence_id,
                    "link_id": link.id,
                    "available": False,
                })
                continue

            evidence_items.append({
                "evidence_id": evidence.id,
                "link_id": link.id,
                "evidence_type": evidence.evidence_type,
                "evidence_reference": evidence.evidence_reference,
                "description": evidence.description,
                "source_row_number": evidence.source_row_number,
                "document_sha256": evidence.document_sha256,
                "verification_status": evidence.status,
                "verification_note": evidence.verification_note,
                "verified_by": evidence.verified_by,
                "verified_at": iso(evidence.verified_at),
                "available": True,
            })

        reviews = (
            db.query(FindingReviewRecord)
            .filter_by(finding_id=finding.id)
            .order_by(FindingReviewRecord.created_at.asc(), FindingReviewRecord.id.asc())
            .all()
        )

        finding_items.append({
            "id": finding.id,
            "fingerprint": finding.fingerprint,
            "rule_code": finding.rule_code,
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
            "explanation": finding.explanation,
            "source_row_number": finding.source_row_number,
            "source_record_id": finding.source_record_id,
            "amount_under_review": finding.amount_under_review,
            "calculation": json.loads(finding.calculation_json),
            "created_at": iso(finding.created_at),
            "evidence": evidence_items,
            "review_history": [
                {
                    "id": review.id,
                    "reviewer_id": review.reviewer_id,
                    "decision": review.decision,
                    "review_note": review.review_note,
                    "confirmed_misstatement_amount": (
                        str(review.confirmed_misstatement_amount)
                        if review.confirmed_misstatement_amount is not None
                        else None
                    ),
                    "created_at": iso(review.created_at),
                }
                for review in reviews
            ],
        })

    chain = verify_engagement_chain(db, run.engagement_id)

    return {
        "report_type": "TRACE_V2_AUDIT_WORKPAPER",
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "engagement_id": run.engagement_id,
            "audit_run_id": run.id,
            "audit_status": run.status,
            "engine_version": run.engine_version,
            "rules_version": run.rules_version,
            "initiated_by": run.initiated_by,
            "created_at": iso(run.created_at),
        },
        "source": {
            "upload_id": upload.id,
            "filename": upload.original_filename,
            "dataset_type": upload.dataset_type,
            "sha256": upload.sha256,
            "size_bytes": upload.size_bytes,
            "row_count": upload.row_count,
            "upload_status": upload.status,
            "validation": (
                json.loads(upload.validation_summary)
                if upload.validation_summary else None
            ),
        },
        "audit_results": {
            "population_count": run.population_count,
            "finding_count_recorded_on_run": run.finding_count,
            "run_summary": json.loads(run.summary_json),
            "findings_in_run": len(finding_items),
            "findings": finding_items,
        },
        "audit_trail": chain,
        "limitations": [
            "This workpaper reflects persisted database records at generation time.",
            "It does not independently recalculate the audit engine's results.",
            "Evidence metadata and a document hash do not by themselves prove the underlying document is authentic.",
            "Reconciliation and sampling results are not asserted unless separately persisted and explicitly included.",
            "This export is a workpaper, not a signed statutory audit opinion.",
        ],
    }
