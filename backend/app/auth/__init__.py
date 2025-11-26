"""Authentication module for Micro-SaaS Platform.

This module provides JWT-based authentication using Supabase as the identity provider.
"""
from .dependencies import (
    get_current_user,
    get_current_user_optional,
    require_plan,
)
from .jwt_validator import (
    DecodedToken,
    JWKSCache,
    JWTValidationError,
    UserPrincipal,
    refresh_jwks_if_needed,
    validate_jwt,
    validate_jwt_async,
    validate_jwt_sync,
)

__all__ = [
    # Dependencies
    "get_current_user",
    "get_current_user_optional",
    "require_plan",
    # JWT Validation
    "DecodedToken",
    "JWKSCache",
    "JWTValidationError",
    "UserPrincipal",
    "refresh_jwks_if_needed",
    "validate_jwt",
    "validate_jwt_async",
    "validate_jwt_sync",
]
