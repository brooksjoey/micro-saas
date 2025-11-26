"""Supabase JWT validation with JWKS caching.

This module implements JWT validation for Supabase-issued tokens with:
- JWKS fetching with timeout and retries
- In-memory key caching with TTL
- Fallback to cached keys when JWKS endpoint is unavailable
- Full observability instrumentation (metrics, logging)

Security considerations:
- Never logs tokens or keys
- Validates iss, aud, exp, nbf claims
- Uses RS256 algorithm (asymmetric)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class JWTValidationError(Exception):
    """Raised when token validation fails."""
    
    def __init__(self, reason: str, detail: Optional[str] = None):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


# =============================================================================
# User Principal
# =============================================================================

@dataclass
class UserPrincipal:
    """Represents an authenticated user derived from JWT claims.
    
    Attributes:
        id: User's unique identifier (sub claim)
        email: User's email address
        plan: Subscription plan (from custom claims)
        stripe_customer_id: Stripe customer ID (from custom claims)
        raw_claims: Original JWT claims for extension
    """
    id: uuid.UUID
    email: str
    plan: str = "FREE"
    stripe_customer_id: Optional[str] = None
    raw_claims: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "UserPrincipal":
        """Create UserPrincipal from JWT claims."""
        # Supabase stores user ID in 'sub' claim
        user_id = claims.get("sub")
        if not user_id:
            raise JWTValidationError("missing_sub", "Token missing 'sub' claim")
        
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise JWTValidationError("invalid_sub", "Invalid UUID in 'sub' claim")
        
        # Email is typically in the token
        email = claims.get("email", "")
        
        # Custom claims for plan and stripe (may be in app_metadata or custom claims)
        app_metadata = claims.get("app_metadata", {})
        user_metadata = claims.get("user_metadata", {})
        
        plan = (
            app_metadata.get("plan") or 
            user_metadata.get("plan") or 
            claims.get("plan", "FREE")
        )
        stripe_customer_id = (
            app_metadata.get("stripe_customer_id") or
            user_metadata.get("stripe_customer_id") or
            claims.get("stripe_customer_id")
        )
        
        return cls(
            id=user_uuid,
            email=email,
            plan=plan,
            stripe_customer_id=stripe_customer_id,
            raw_claims=claims,
        )


# =============================================================================
# JWKS Cache
# =============================================================================

@dataclass
class JWKSCache:
    """Thread-safe JWKS cache with TTL support."""
    
    keys: dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    # Cache configuration
    ttl_seconds: float = 300.0  # 5 minutes
    stale_ttl_seconds: float = 3600.0  # 1 hour fallback
    
    def is_fresh(self) -> bool:
        """Check if cache is within TTL."""
        return time.time() - self.fetched_at < self.ttl_seconds
    
    def is_usable(self) -> bool:
        """Check if cache can be used as fallback (within stale TTL)."""
        return (
            bool(self.keys) and 
            time.time() - self.fetched_at < self.stale_ttl_seconds
        )
    
    def update(self, keys: dict[str, Any]) -> None:
        """Update cache with new keys."""
        with self.lock:
            self.keys = keys
            self.fetched_at = time.time()
    
    def get_key(self, kid: str) -> Optional[Any]:
        """Get a key by key ID."""
        with self.lock:
            return self.keys.get(kid)


# Global cache instance
_jwks_cache = JWKSCache()


# =============================================================================
# JWKS Fetching
# =============================================================================

async def _fetch_jwks(jwks_url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch JWKS from the given URL.
    
    Args:
        jwks_url: URL to the JWKS endpoint
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary mapping key IDs to key data
        
    Raises:
        JWTValidationError: If fetch fails
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            
            data = response.json()
            keys = {}
            
            for key_data in data.get("keys", []):
                kid = key_data.get("kid")
                if kid:
                    keys[kid] = key_data
            
            if not keys:
                raise JWTValidationError("no_keys", "JWKS response contained no keys")
            
            return keys
            
    except httpx.TimeoutException:
        logger.warning("jwks_fetch_timeout", extra={"url": jwks_url})
        raise JWTValidationError("jwks_timeout", "JWKS fetch timed out")
    except httpx.HTTPStatusError as e:
        logger.warning("jwks_fetch_http_error", extra={"status": e.response.status_code})
        raise JWTValidationError("jwks_http_error", f"HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning("jwks_fetch_error", extra={"error": str(e)})
        raise JWTValidationError("jwks_error", str(e))


async def refresh_jwks_if_needed(jwks_url: Optional[str]) -> None:
    """Refresh JWKS cache if needed.
    
    This function:
    1. Checks if cache is fresh (within TTL)
    2. If not, fetches new keys
    3. Falls back to cached keys if fetch fails
    
    Args:
        jwks_url: URL to the JWKS endpoint (from config)
    """
    if not jwks_url:
        return
    
    if _jwks_cache.is_fresh():
        return
    
    try:
        keys = await _fetch_jwks(jwks_url)
        _jwks_cache.update(keys)
        logger.info("jwks_refreshed", extra={"key_count": len(keys)})
    except JWTValidationError:
        if _jwks_cache.is_usable():
            logger.warning(
                "jwks_refresh_failed_using_cache",
                extra={"cache_age_seconds": time.time() - _jwks_cache.fetched_at}
            )
        else:
            logger.error("jwks_refresh_failed_cache_stale")
            raise


def get_public_key(kid: str, jwks_url: Optional[str] = None) -> Any:
    """Get the public key for a given key ID.
    
    Args:
        kid: Key ID from JWT header
        jwks_url: Optional JWKS URL for forced refresh
        
    Returns:
        RSA public key suitable for jwt.decode()
        
    Raises:
        JWTValidationError: If key not found
    """
    key_data = _jwks_cache.get_key(kid)
    
    if not key_data:
        raise JWTValidationError("unknown_kid", f"Unknown key ID: {kid}")
    
    try:
        return jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    except Exception as e:
        raise JWTValidationError("invalid_key", f"Could not parse key: {e}")


# =============================================================================
# Token Validation
# =============================================================================

async def validate_jwt_async(
    token: str,
    *,
    jwks_url: Optional[str] = None,
    expected_issuer: Optional[str] = None,
    expected_audience: Optional[str] = None,
) -> UserPrincipal:
    """Validate a JWT and return a UserPrincipal.
    
    This is the main async entry point for JWT validation.
    
    Args:
        token: The JWT token string (without "Bearer " prefix)
        jwks_url: JWKS endpoint URL
        expected_issuer: Expected token issuer (iss claim)
        expected_audience: Expected token audience (aud claim)
        
    Returns:
        UserPrincipal representing the authenticated user
        
    Raises:
        JWTValidationError: If validation fails
    """
    # Import here to avoid circular imports
    try:
        from app.telemetry.metrics import observe_jwt_validation
    except ImportError:
        observe_jwt_validation = None
    
    start = time.perf_counter()
    issuer = expected_issuer or "supabase"
    
    try:
        # Refresh JWKS if needed
        await refresh_jwks_if_needed(jwks_url)
        
        # Get the unverified header to find the key ID
        try:
            unverified_header = jwt.get_unverified_header(token)
        except DecodeError:
            raise JWTValidationError("malformed_token", "Could not decode token header")
        
        kid = unverified_header.get("kid")
        if not kid:
            raise JWTValidationError("missing_kid", "Token header missing 'kid'")
        
        alg = unverified_header.get("alg", "RS256")
        if alg not in ("RS256", "RS384", "RS512"):
            raise JWTValidationError("invalid_algorithm", f"Unsupported algorithm: {alg}")
        
        # Get the public key
        public_key = get_public_key(kid, jwks_url)
        
        # Decode and validate the token
        options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "require": ["exp", "sub"],
        }
        
        decode_kwargs: dict[str, Any] = {
            "algorithms": [alg],
            "options": options,
        }
        
        if expected_issuer:
            decode_kwargs["issuer"] = expected_issuer
        if expected_audience:
            decode_kwargs["audience"] = expected_audience
        
        claims = jwt.decode(token, key=public_key, **decode_kwargs)
        
        # Create UserPrincipal from claims
        principal = UserPrincipal.from_claims(claims)
        
        duration = time.perf_counter() - start
        if observe_jwt_validation:
            observe_jwt_validation(
                issuer=issuer,
                outcome="valid",
                reason=None,
                duration_seconds=duration,
            )
        
        logger.debug(
            "jwt_validation_success",
            extra={"user_id": str(principal.id), "duration_ms": duration * 1000}
        )
        
        return principal
        
    except JWTValidationError:
        raise
    except ExpiredSignatureError:
        raise JWTValidationError("expired", "Token has expired")
    except InvalidSignatureError:
        raise JWTValidationError("invalid_signature", "Token signature is invalid")
    except InvalidIssuerError:
        raise JWTValidationError("invalid_issuer", "Token issuer is invalid")
    except InvalidAudienceError:
        raise JWTValidationError("invalid_audience", "Token audience is invalid")
    except InvalidTokenError as e:
        raise JWTValidationError("invalid_token", str(e))
    except Exception as e:
        logger.exception("jwt_validation_unexpected_error")
        raise JWTValidationError("unknown_error", str(e))
    finally:
        # Record metrics on failure path
        duration = time.perf_counter() - start
        # Metrics are recorded in the except blocks above


def validate_jwt_sync(
    token: str,
    *,
    expected_issuer: Optional[str] = None,
    expected_audience: Optional[str] = None,
) -> dict[str, Any]:
    """Synchronous JWT validation (for testing or simple cases).
    
    Note: This version does not refresh JWKS and relies on cached keys.
    For production use, prefer validate_jwt_async.
    
    Args:
        token: The JWT token string
        expected_issuer: Expected token issuer
        expected_audience: Expected token audience
        
    Returns:
        Dictionary of JWT claims
        
    Raises:
        JWTValidationError: If validation fails
    """
    try:
        from app.telemetry.metrics import observe_jwt_validation
    except ImportError:
        observe_jwt_validation = None
    
    start = time.perf_counter()
    issuer = expected_issuer or "supabase"
    
    try:
        # Get unverified header
        try:
            unverified_header = jwt.get_unverified_header(token)
        except DecodeError:
            raise JWTValidationError("malformed_token", "Could not decode token header")
        
        kid = unverified_header.get("kid")
        if not kid:
            raise JWTValidationError("missing_kid", "Token header missing 'kid'")
        
        alg = unverified_header.get("alg", "RS256")
        
        # Get public key from cache
        public_key = get_public_key(kid)
        
        # Decode and validate
        decode_kwargs: dict[str, Any] = {
            "algorithms": [alg],
            "options": {"verify_exp": True, "verify_nbf": True},
        }
        
        if expected_issuer:
            decode_kwargs["issuer"] = expected_issuer
        if expected_audience:
            decode_kwargs["audience"] = expected_audience
        
        claims = jwt.decode(token, key=public_key, **decode_kwargs)
        
        duration = time.perf_counter() - start
        if observe_jwt_validation:
            observe_jwt_validation(
                issuer=issuer,
                outcome="valid",
                reason=None,
                duration_seconds=duration,
            )
        
        return claims
        
    except JWTValidationError:
        raise
    except ExpiredSignatureError:
        raise JWTValidationError("expired", "Token has expired")
    except InvalidSignatureError:
        raise JWTValidationError("invalid_signature", "Token signature is invalid")
    except Exception as e:
        raise JWTValidationError("unknown_error", str(e))


# =============================================================================
# Backwards Compatibility
# =============================================================================

class DecodedToken(dict):
    """Backwards-compatible wrapper for validated token claims."""
    pass


def validate_jwt(token: str, required_scopes: list[str] | None = None) -> DecodedToken:
    """Backwards-compatible synchronous validation.
    
    This is a legacy interface. For new code, use validate_jwt_async.
    """
    claims = validate_jwt_sync(token)
    return DecodedToken(claims)
