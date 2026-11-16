"""Dual-mode JWT authentication and authorization handler."""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
import logging
from typing import Optional
from src.config import settings

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)

class UserClaims(BaseModel):
    user_id: str
    role: str = "user"  # "admin" | "user"
    name: Optional[str] = "User"

def create_access_token(user_id: str, role: str = "user", name: str = "User") -> str:
    """Generate a signed JWT token."""
    payload = {
        "user_id": user_id,
        "role": role,
        "name": name,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)
) -> UserClaims:
    """Validate Bearer token or return mock user when DEV_AUTH_BYPASS is active."""
    # 1. Dev Bypass Mode
    if settings.DEV_AUTH_BYPASS:
        if not credentials:
            return UserClaims(
                user_id="dev_admin_001",
                role="admin",
                name="Development Admin"
            )

    # 2. Strict Authentication
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return UserClaims(
            user_id=payload.get("user_id", "unknown"),
            role=payload.get("role", "user"),
            name=payload.get("name", "User")
        )
    except jwt.PyJWTError as e:
        logger.warning(f"JWT validation failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def require_admin(
    user: UserClaims = Security(get_current_user)
) -> UserClaims:
    """Enforce admin-only access."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    return user
