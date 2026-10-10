import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.errors import api_error
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.identity import User

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
                     db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise api_error(401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required.")
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = payload.get("sub")
    except (jwt.PyJWTError, ValueError, TypeError):
        raise api_error(401, "INVALID_TOKEN", "The access token is invalid or expired.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise api_error(401, "USER_INACTIVE_OR_MISSING", "The user is inactive or unavailable.")
    return user

def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise api_error(403, "PERMISSION_DENIED", "Your role cannot perform this operation.")
        return user
    return dependency
