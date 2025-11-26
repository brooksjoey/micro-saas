"""FastAPI authentication dependencies.

This module provides FastAPI dependencies for authenticating requests
using Supabase JWT tokens.

Usage:
    @router.get("/protected")
    async def protected_endpoint(
        user: UserPrincipal = Depends(get_current_user),
    ):
        return {"user_id": str(user.id)}
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_validator import (
    JWTValidationError,
    UserPrincipal,
    validate_jwt_async,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Security Scheme
# =============================================================================

# HTTPBearer extracts the token from Authorization header
_bearer_scheme = HTTPBearer(
    scheme_name="Bearer",
    description="Supabase JWT token",
    auto_error=False,  # We handle missing tokens ourselves
)


# =============================================================================
# Configuration
# =============================================================================

def _get_supabase_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get Supabase configuration from settings.
    
    Returns:
        Tuple of (jwks_url, issuer, audience)
    """
    try:
        from app.config import get_settings
        settings = get_settings()
        
        # Use centralized JWKS URL property
        jwks_url = settings.supabase_jwks_url
        issuer = settings.SUPABASE_URL
        audience = settings.SUPABASE_JWT_AUDIENCE
        
        return jwks_url, issuer, audience
        
    except Exception as e:
        logger.warning("supabase_config_error", extra={"error": str(e)})
        return None, None, None


# =============================================================================
# Dependencies
# =============================================================================

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> UserPrincipal:
    """Get the current authenticated user from the request.
    
    This dependency:
    1. Extracts the Bearer token from Authorization header
    2. Validates the token against Supabase JWKS
    3. Returns a UserPrincipal with user information
    
    Args:
        request: The FastAPI request object
        credentials: The extracted authorization credentials
        
    Returns:
        UserPrincipal representing the authenticated user
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get Supabase configuration
    jwks_url, issuer, audience = _get_supabase_config()
    
    try:
        user = await validate_jwt_async(
            token,
            jwks_url=jwks_url,
            expected_issuer=issuer,
            expected_audience=audience,
        )
        
        # Attach user to request state for logging/tracing
        request.state.user_id = str(user.id)
        request.state.user_email = user.email
        request.state.user_plan = user.plan
        
        return user
        
    except JWTValidationError as e:
        logger.info(
            "authentication_failed",
            extra={
                "reason": e.reason,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        )
        
        # Map validation errors to appropriate HTTP responses
        if e.reason == "expired":
            detail = "Token has expired"
        elif e.reason == "invalid_signature":
            detail = "Invalid token signature"
        elif e.reason == "invalid_audience":
            detail = "Token not valid for this service"
        elif e.reason == "invalid_issuer":
            detail = "Token issuer not trusted"
        else:
            detail = "Authentication failed"
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[UserPrincipal]:
    """Get the current user if authenticated, or None if not.
    
    This is useful for endpoints that work differently for authenticated
    vs unauthenticated users.
    
    Args:
        request: The FastAPI request object
        credentials: The extracted authorization credentials
        
    Returns:
        UserPrincipal if authenticated, None otherwise
    """
    if not credentials or not credentials.credentials:
        return None
    
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_plan(*allowed_plans: str):
    """Dependency factory that requires specific subscription plans.
    
    Usage:
        @router.post("/premium-feature")
        async def premium_feature(
            user: UserPrincipal = Depends(require_plan("PRO", "ENTERPRISE")),
        ):
            ...
    
    Args:
        allowed_plans: Plan names that are allowed to access the endpoint
        
    Returns:
        A dependency function that checks the user's plan
    """
    async def _check_plan(
        user: UserPrincipal = Depends(get_current_user),
    ) -> UserPrincipal:
        if user.plan not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires one of: {', '.join(allowed_plans)}",
            )
        return user
    
    return _check_plan
