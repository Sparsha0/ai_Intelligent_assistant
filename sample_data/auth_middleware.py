"""
Sample Authentication Middleware
Used for filesystem tool demonstration and code analysis.
"""

import jwt
import functools
from datetime import datetime, timezone
from flask import request, jsonify, g

SECRET_KEY = "loaded-from-vault-not-hardcoded"
ALGORITHM = "RS256"
CLOCK_SKEW_SECONDS = 30


def require_auth(f):
    """Decorator to protect endpoints with JWT authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        payload = _validate_token(token)
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        g.current_user = payload["sub"]
        g.token_payload = payload
        return f(*args, **kwargs)
    return decorated


def _extract_token() -> str | None:
    """Extract bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _validate_token(token: str) -> dict | None:
    """
    Validate JWT token.
    Returns payload dict if valid, None if invalid.
    """
    try:
        # Load public key from key store (not hardcoded)
        public_key = _get_public_key()

        payload = jwt.decode(
            token,
            public_key,
            algorithms=[ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "leeway": CLOCK_SKEW_SECONDS,
            },
        )

        # Additional validation: check token not revoked
        if _is_token_revoked(payload.get("jti")):
            return None

        return payload

    except jwt.ExpiredSignatureError:
        _log_auth_event("token_expired", token[:20])
        return None
    except jwt.InvalidTokenError as e:
        _log_auth_event("token_invalid", str(e))
        return None


def _get_public_key() -> str:
    """Load public key from Vault or key cache."""
    # In production: fetch from HashiCorp Vault
    # For demo: reads from environment
    import os
    return os.getenv("JWT_PUBLIC_KEY", "")


def _is_token_revoked(jti: str | None) -> bool:
    """Check Redis blocklist for revoked tokens."""
    if not jti:
        return True
    # Redis check: SISMEMBER revoked_tokens {jti}
    return False  # Simplified for demo


def _log_auth_event(event_type: str, detail: str = ""):
    """Write to audit log."""
    print(f"[AUTH] {event_type}: {detail} at {datetime.now(timezone.utc).isoformat()}")
