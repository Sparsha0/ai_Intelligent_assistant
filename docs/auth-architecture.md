# Authentication Architecture

## Overview

Our authentication system is built on industry-standard JWT (JSON Web Tokens) with RS256 asymmetric signing.
All authentication flows are handled by the `auth-service`, a dedicated microservice.

## Token Lifecycle

| Token Type    | Expiry    | Storage         | Rotation       |
|---------------|-----------|-----------------|----------------|
| Access Token  | 15 minutes| Memory only     | Every request  |
| Refresh Token | 7 days    | httpOnly cookie | On use         |
| API Key       | Never     | Hashed in DB    | Manual         |

### Access Token Structure

```json
{
  "header": { "alg": "RS256", "typ": "JWT", "kid": "key-2024-01" },
  "payload": {
    "sub": "user-uuid",
    "iat": 1700000000,
    "exp": 1700000900,
    "jti": "unique-token-id",
    "roles": ["engineer", "reader"],
    "org":  "my-org"
  }
}
```

## Authentication Flows

### Standard Login Flow

1. Client POSTs credentials to `/auth/login`
2. Auth service validates against user store (bcrypt comparison)
3. On success: generates access + refresh token pair
4. Access token returned in response body
5. Refresh token set as httpOnly cookie (SameSite=Strict)
6. Audit log entry written

### Token Refresh Flow

1. Client GETs `/auth/refresh` (cookie sent automatically)
2. Auth service validates refresh token signature and expiry
3. Checks token has not been revoked (Redis lookup)
4. Issues new access token + rotates refresh token
5. Old refresh token is immediately invalidated

### SSO / OAuth2 Flow

1. Client redirected to identity provider
2. IdP returns authorization code
3. Auth service exchanges code for IdP tokens
4. Auth service issues our own JWT pair
5. User session established

## Key Management

- RSA 2048-bit key pairs generated on service startup
- Private key stored in HashiCorp Vault (never in env vars or config files)
- Public key served at `/auth/.well-known/jwks.json` for verification
- Key rotation: every 90 days with 24-hour overlap window
- Each key identified by `kid` (key ID) in JWT header

## Session Management

Sessions tracked in Redis:
```
sessions:{user_id} → SET of session IDs
session:{session_id} → {user_id, created_at, ip, user_agent, last_active}
TTL: 7 days (reset on activity)
```

Maximum 10 concurrent sessions per user. Oldest session evicted on overflow.

## Security Controls

| Control              | Implementation                         |
|----------------------|----------------------------------------|
| CSRF Protection      | Double-submit cookie on state-changing requests |
| Rate Limiting        | 10 login/min per IP, 60 refresh/min per user |
| Brute Force          | Account lockout after 20 failures/hour |
| Audit Logging        | All auth events → audit_logs table     |
| Token Revocation     | Redis blocklist, checked on every request |
| Secure Transport     | TLS 1.2+ enforced, HSTS enabled        |

## Known Limitations and Gotchas

1. **Key Rotation Window**: During the 24-hour rotation overlap, both old and new keys
   are valid. This is intentional to allow graceful token refresh without forcing
   immediate re-authentication.

2. **Redis Dependency**: Token revocation requires Redis. If Redis is unavailable,
   revocation checks fail open (tokens remain valid until expiry). This is a known
   trade-off: availability over strict revocation.

3. **Clock Skew**: Auth service tolerates ±30 seconds of clock skew between services.
   Tokens with `exp` within 30 seconds of server time are accepted. Ensure NTP sync.

4. **Mobile App Considerations**: Mobile clients use a different refresh token flow
   with longer expiry (30 days) and device fingerprinting. See `mobile-auth.md`.
