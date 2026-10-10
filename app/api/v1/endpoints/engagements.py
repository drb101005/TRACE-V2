from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models.engagement import Engagement, EngagementMembership
from app.models.identity import Organization, OrganizationMembership, User
from app.schemas.engagement import EngagementCreate, EngagementPublic

router = APIRouter()

def ensure_org_access(db: Session, user: User, organization_id: str):
    if user.role != "ADMIN" and not db.query(OrganizationMembership).filter_by(organization_id=organization_id, user_id=user.id).first():
        raise api_error(403, "ORGANIZATION_ACCESS_DENIED", "You do not have access to this organization.")

def ensure_engagement_access(db: Session, user: User, engagement: Engagement):
    if user.role != "ADMIN" and not db.query(EngagementMembership).filter_by(engagement_id=engagement.id, user_id=user.id).first():
        raise api_error(403, "ENGAGEMENT_ACCESS_DENIED", "You do not have access to this engagement.")

@router.get("")
def list_engagements(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Engagement)
    if user.role != "ADMIN":
        ids = [m.engagement_id for m in db.query(EngagementMembership).filter_by(user_id=user.id).all()]
        query = query.filter(Engagement.id.in_(ids)) if ids else query.filter(False)
    total = query.count()
    items = query.order_by(Engagement.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items": [EngagementPublic.model_validate(x).model_dump(mode="json") for x in items],
            "page": page, "page_size": page_size, "total": total}

@router.post("", response_model=EngagementPublic, status_code=201)
def create_engagement(body: EngagementCreate, user: User = Depends(require_roles("ADMIN", "HUMAN_AUDITOR")),
                      db: Session = Depends(get_db)):
    org = db.query(Organization).filter_by(id=body.organization_id).first()
    if not org:
        raise api_error(404, "ORGANIZATION_NOT_FOUND", "Organization was not found.")
    ensure_org_access(db, user, org.id)
    item = Engagement(organization_id=org.id, name=body.name, financial_year=body.financial_year,
        period_start=body.period_start, period_end=body.period_end, status="DATA_PENDING",
        is_demo=False, created_by=user.id)
    db.add(item)
    db.flush()
    db.add(EngagementMembership(engagement_id=item.id, user_id=user.id, role=user.role))
    db.commit()
    db.refresh(item)
    return item

@router.get("/{engagement_id}", response_model=EngagementPublic)
def get_engagement(engagement_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Engagement).filter_by(id=engagement_id).first()
    if not item:
        raise api_error(404, "ENGAGEMENT_NOT_FOUND", "Engagement was not found.")
    ensure_engagement_access(db, user, item)
    return item

@router.get("/{engagement_id}/workflow")
def workflow(engagement_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Engagement).filter_by(id=engagement_id).first()
    if not item:
        raise api_error(404, "ENGAGEMENT_NOT_FOUND", "Engagement was not found.")
    ensure_engagement_access(db, user, item)
    return {"engagement_id": item.id, "state": item.status, "steps": [
        {"key": "source_upload", "status": "PENDING"},
        {"key": "validation", "status": "PENDING"},
        {"key": "submission_lock", "status": "PENDING"},
        {"key": "reconciliation", "status": "PENDING"},
        {"key": "audit_testing", "status": "PENDING"},
        {"key": "human_review", "status": "PENDING"},
    ]}
