import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.endpoints.uploads import (
    ensure_upload_access, get_upload_or_404,
)
from app.db.session import get_db
from app.models.evidence import Evidence
from app.models.identity import User

router = APIRouter()


class EvidenceCreate(BaseModel):
    upload_id: str
    evidence_type: str = Field(min_length=2, max_length=60)
    evidence_reference: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=5, max_length=3000)
    source_row_number: int | None = Field(default=None, ge=2)
    document_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")


class EvidenceVerification(BaseModel):
    status: str = Field(pattern=r"^(VERIFIED|REJECTED)$")
    verification_note: str = Field(min_length=5, max_length=3000)


def public_evidence(item):
    return {
        "id": item.id,
        "engagement_id": item.engagement_id,
        "upload_id": item.upload_id,
        "evidence_type": item.evidence_type,
        "evidence_reference": item.evidence_reference,
        "description": item.description,
        "source_row_number": item.source_row_number,
        "document_sha256": item.document_sha256,
        "status": item.status,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "verified_by": item.verified_by,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "verification_note": item.verification_note,
    }


def evidence_or_404(db, evidence_id):
    item = db.query(Evidence).filter_by(id=evidence_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    return item


def check_access(db, user, item):
    upload = get_upload_or_404(db, item.upload_id)
    ensure_upload_access(db, user, upload)
    return upload


@router.post("/evidence", status_code=201)
def create_evidence(
    body: EvidenceCreate,
    user: User = Depends(
        require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    upload = get_upload_or_404(db, body.upload_id)
    ensure_upload_access(db, user, upload)

    evidence_type = body.evidence_type.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{2,60}", evidence_type):
        raise HTTPException(
            status_code=422,
            detail="evidence_type must contain only letters, numbers, underscores, or hyphens.",
        )

    item = Evidence(
        id=str(uuid.uuid4()),
        engagement_id=upload.engagement_id,
        upload_id=upload.id,
        created_by=user.id,
        evidence_type=evidence_type,
        evidence_reference=body.evidence_reference.strip(),
        description=body.description.strip(),
        source_row_number=body.source_row_number,
        document_sha256=body.document_sha256.lower() if body.document_sha256 else None,
        status="UNVERIFIED",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return public_evidence(item)


@router.get("/evidence")
def list_evidence(
    upload_id: str | None = None,
    status: str | None = Query(default=None, pattern=r"^(UNVERIFIED|VERIFIED|REJECTED)$"),
    user: User = Depends(
        require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    query = db.query(Evidence)
    if upload_id:
        upload = get_upload_or_404(db, upload_id)
        ensure_upload_access(db, user, upload)
        query = query.filter(Evidence.upload_id == upload_id)
    else:
        # Filter by uploads accessible to the user before returning evidence.
        from app.models.ingestion import SourceUpload
        accessible = db.query(SourceUpload.id).all()
        accessible_ids = []
        for (candidate_id,) in accessible:
            try:
                candidate = get_upload_or_404(db, candidate_id)
                ensure_upload_access(db, user, candidate)
                accessible_ids.append(candidate_id)
            except HTTPException:
                continue
        query = query.filter(Evidence.upload_id.in_(accessible_ids))

    if status:
        query = query.filter(Evidence.status == status)

    items = query.order_by(Evidence.created_at.desc()).limit(500).all()
    return {"count": len(items), "items": [public_evidence(x) for x in items]}


@router.get("/evidence/{evidence_id}")
def get_evidence(
    evidence_id: str,
    user: User = Depends(
        require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    item = evidence_or_404(db, evidence_id)
    check_access(db, user, item)
    return public_evidence(item)


@router.post("/evidence/{evidence_id}/verify")
def verify_evidence(
    evidence_id: str,
    body: EvidenceVerification,
    user: User = Depends(require_roles("ADMIN", "HUMAN_AUDITOR")),
    db: Session = Depends(get_db),
):
    item = evidence_or_404(db, evidence_id)
    check_access(db, user, item)

    if item.status != "UNVERIFIED":
        raise HTTPException(
            status_code=409,
            detail="Only unverified evidence can receive an initial verification decision.",
        )

    item.status = body.status
    item.verification_note = body.verification_note.strip()
    item.verified_by = user.id
    item.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return public_evidence(item)
