from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.engagement import Engagement
from app.models.identity import User
from app.services.audit_trail import verify_engagement_chain

router = APIRouter()


@router.get("/audit-trail/verify")
def verify_audit_trail(
    engagement_id: str,
    user: User = Depends(
        require_roles("ADMIN", "CLIENT_EMPLOYEE", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    engagement = db.query(Engagement).filter_by(id=engagement_id).first()
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Reuse the application's existing upload-access guard for authorization.
    from app.models.ingestion import SourceUpload
    from app.api.v1.endpoints.uploads import ensure_upload_access

    upload = db.query(SourceUpload).filter_by(
        engagement_id=engagement_id
    ).first()
    if upload is not None:
        ensure_upload_access(db, user, upload)
    elif user.role != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Cannot verify an engagement without an accessible upload",
        )

    return {
        "engagement_id": engagement_id,
        **verify_engagement_chain(db, engagement_id),
    }
