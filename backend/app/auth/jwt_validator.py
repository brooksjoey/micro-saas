from __future__ import annotations

import logging
import time
from typing import Any

from backend.app.telemetry.metrics import observe_jwt_validation


logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    """Raised when token validation fails."""


class DecodedToken(dict):
    """Minimal return type for validated tokens."""


def _decode_jwt(token: str) -> dict:
    """
    Minimal placeholder for actual JWT decoding.
    In real implementation, integrate with PyJWT / Auth0 / Supabase JWKS, etc.
    """
    if not token or token.strip() == "":
        raise JWTValidationError("missing_token")

    # Fake decode (replace with real decoding logic)
    if token.startswith("expired_"):
        raise JWTValidationError("expired")
    if token.startswith("invalidsig_"):
        raise JWTValidationError("invalid_signature")

    return {"sub": "user123", "iss": "internal_issuer"}


def validate_jwt(token: str, required_scopes: list[str] | None = None) -> DecodedToken:
    """
    Validate a JWT with full observability instrumentation.

    All success/failure paths emit:
        observe_jwt_validation(issuer, outcome, reason, duration_seconds)

    Any failure re-raises with JWTValidationError.
    """
    start = time.perf_counter()
    issuer = "internal"  # Real implementation: derive from actual JWT claims or provider.

    try:
        payload = _decode_jwt(token)

        # Scope-check placeholder
        if required_scopes:
            for scope in required_scopes:
                if scope not in payload:
                    raise JWTValidationError("missing_scope")

        duration = time.perf_counter() - start
        observe_jwt_validation(
            issuer=issuer,
            outcome="valid",
            reason=None,
            duration_seconds=duration,
        )
        return DecodedToken(payload)

    except JWTValidationError as exc:
        reason = exc.args[0] if exc.args else "unknown"
        duration = time.perf_counter() - start

        observe_jwt_validation(
            issuer=issuer,
            outcome="invalid",
            reason=reason,
            duration_seconds=duration,
        )

        logger.debug("jwt_validation_failed", extra={"reason": reason})
        raise
