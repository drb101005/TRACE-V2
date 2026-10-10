from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models.identity import Organization, OrganizationMembership, User
from app.schemas.engagement import OrganizationPublic

router = APIRouter()
class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)

@router.get("", response_model=list[OrganizationPublic])
def list_organizations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "ADMIN":
        return db.query(Organization).order_by(Organization.name).all()
    ids = [m.organization_id for m in db.query(OrganizationMembership).filter_by(user_id=user.id).all()]
    if not ids:
        return []
    return db.query(Organization).filter(Organization.id.in_(ids)).order_by(Organization.name).all()

@router.get("/{organization_id}", response_model=OrganizationPublic)
def get_organization(organization_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.query(Organization).filter_by(id=organization_id).first()
    if not org:
        raise api_error(404, "ORGANIZATION_NOT_FOUND", "Organization was not found.")
    if user.role != "ADMIN" and not db.query(OrganizationMembership).filter_by(organization_id=org.id, user_id=user.id).first():
        raise api_error(403, "ORGANIZATION_ACCESS_DENIED", "You do not have access to this organization.")
    return org

@router.post("", response_model=OrganizationPublic, status_code=201)
def create_organization(body: OrganizationCreate, user: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    org = Organization(name=body.name.strip(), is_demo=False)
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role="ADMIN"))
    db.commit()
    db.refresh(org)
    return org
