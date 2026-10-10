from pydantic import BaseModel, EmailStr, Field
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    model_config = {"from_attributes": True}
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
