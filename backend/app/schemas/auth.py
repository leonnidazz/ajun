from pydantic import BaseModel, Field
from app.schemas.user import UserResponse


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., description="Google ID Token JWT from Google Sign-In SDK")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Opaque refresh token string")
