from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import api_error
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.identity import User
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise api_error(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    if not user.is_active:
        raise api_error(403, "USER_INACTIVE", "This user account is inactive.")
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.model_validate(user),
    )

@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return user

@router.get("/permissions")
def permissions(user: User = Depends(get_current_user)):
    role_permissions = {
        "ADMIN": ["platform:admin", "users:manage", "organizations:manage", "engagements:read"],
        "CLIENT_EMPLOYEE": ["uploads:create", "source_data:read_own", "evidence:upload"],
        "INDEPENDENT_AUDITOR": ["source_data:read_assigned", "audit:execute", "findings:draft", "workpapers:draft"],
        "HUMAN_AUDITOR": ["source_data:read_assigned", "audit:execute", "findings:review", "workpapers:review", "engagement:signoff"],
    }
    return {"user_id": user.id, "role": user.role, "permissions": role_permissions.get(user.role, [])}
