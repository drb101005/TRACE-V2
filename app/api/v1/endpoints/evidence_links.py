import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import Evidence
from app.models.evidence_link import EvidenceLink
from app.models.ai_analysis import AIAnalysisRun
from app.api.v1.endpoints.auth import get_current_user
from app.models.identity import User

router = APIRouter()


def role_name(user):
    role = getattr(user, "role", "")
    return str(getattr(role, "value", role)).upper()


def require_roles(user, allowed):
    if role_name(user) not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def accessible_evidence(db, evidence_id, user):
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    # Reuse the existing upload-access check used by evidence endpoints.
    from app.api.v1.endpoints.uploads import ensure_upload_access
    upload = db.query(__import__(
        "app.models.ingestion", fromlist=["SourceUpload"]
    ).SourceUpload).filter_by(id=evidence.upload_id).first()
    if upload is None:
        raise HTTPException(status_code=404, detail="Source upload not found")
    ensure_upload_access(db, user, upload)
    return evidence


class EvidenceLinkCreate(BaseModel):
    evidence_id: str
    analysis_run_id: str
    source_row_number: int | None = Field(default=None, ge=2)


def serialize(link):
    return {
        "id": link.id,
        "engagement_id": link.engagement_id,
        "evidence_id": link.evidence_id,
        "resource_type": link.resource_type,
        "resource_id": link.resource_id,
        "source_row_number": link.source_row_number,
        "linked_by": link.linked_by,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.post("/evidence-links", status_code=201)
def create_evidence_link(
    body: EvidenceLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_roles(user, {
        "ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR"
    })

    evidence = accessible_evidence(db, body.evidence_id, user)
    run = db.query(AIAnalysisRun).filter(
        AIAnalysisRun.id == body.analysis_run_id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    if str(run.engagement_id) != str(evidence.engagement_id):
        raise HTTPException(
            status_code=409,
            detail="Evidence and analysis run belong to different engagements",
        )

    link = EvidenceLink(
        id=str(uuid.uuid4()),
        engagement_id=str(evidence.engagement_id),
        evidence_id=evidence.id,
        resource_type="AI_ANALYSIS_RUN",
        resource_id=run.id,
        source_row_number=body.source_row_number,
        linked_by=str(user.id),
    )
    db.add(link)
    try:
        db.commit()
        db.refresh(link)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This evidence link already exists",
        )
    return serialize(link)


@router.get("/analysis-runs/{analysis_run_id}/evidence-links")
def list_analysis_evidence_links(
    analysis_run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.query(AIAnalysisRun).filter(
        AIAnalysisRun.id == analysis_run_id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    from app.api.v1.endpoints.uploads import ensure_upload_access
    from app.models.ingestion import SourceUpload
    upload = db.query(SourceUpload).filter_by(id=run.upload_id).first()
    if upload is None:
        raise HTTPException(status_code=404, detail="Source upload not found")
    ensure_upload_access(db, user, upload)

    links = db.query(EvidenceLink).filter(
        EvidenceLink.resource_type == "AI_ANALYSIS_RUN",
        EvidenceLink.resource_id == analysis_run_id,
    ).order_by(EvidenceLink.created_at.asc()).all()
    return {"items": [serialize(link) for link in links], "total": len(links)}


@router.delete("/evidence-links/{link_id}", status_code=200)
def remove_evidence_link(
    link_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_roles(user, {"ADMIN", "HUMAN_AUDITOR"})
    link = db.query(EvidenceLink).filter(EvidenceLink.id == link_id).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Evidence link not found")

    accessible_evidence(db, link.evidence_id, user)
    # This removes only the relationship; the evidence record remains.
    db.delete(link)
    db.commit()
    return {"removed": True, "link_id": link_id, "evidence_preserved": True}
