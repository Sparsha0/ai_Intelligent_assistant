# Example Prompts and Outputs

This document shows sample interactions with the Engineering AI Assistant.

---

## Example 1: RAG Query (Documentation Lookup)

**Prompt:**
> What is our authentication flow and how do JWT tokens expire?

**Mode:** RAG

**Output:**
```
Our authentication system uses JWT tokens with RS256 asymmetric signing.

**Token Expiry:**
- Access tokens expire after **15 minutes** [Source: auth-architecture.md (chunk 2)]
- Refresh tokens expire after **7 days** [Source: auth-architecture.md (chunk 2)]
- Tokens can also be explicitly revoked via the Redis blocklist [Source: auth-architecture.md (chunk 5)]

**Authentication Flow:**
1. Client POSTs credentials to `/auth/login`
2. Auth service validates against user store using bcrypt
3. On success: access token returned in body, refresh token set as httpOnly cookie
4. Access tokens are refreshed via `/auth/refresh` [Source: auth-architecture.md (chunk 4)]

During key rotation (every 90 days), both old and new keys are valid for 24 hours
to allow graceful token refresh without forced re-authentication. [Source: auth-architecture.md (chunk 6)]
```

**Sources:** `auth-architecture.md (chunk 2)`, `auth-architecture.md (chunk 4)`, `auth-architecture.md (chunk 6)`  
**Relevance Score:** 0.847  
**Mode:** rag

---

## Example 2: Multi-Agent Workflow (GitHub Issue Analysis)

**Prompt:**
> Find all authentication-related GitHub issues opened in the last 30 days and summarize recurring failures.

**Mode:** Agent (auto-detected)

**Agent Pipeline Output:**

```
[Planner] 142ms ✓
Decomposed into 3 subtasks:
1. Search GitHub for auth-related issues (last 30 days)
2. Cluster issues by failure type
3. Generate summary with recommendations

[Research] 1,847ms ✓
GitHub Issues Found (5 results):
  #1042: Authentication tokens expire prematurely during peak load [bug, authentication, high-priority]
         "Users report being logged out unexpectedly when traffic spikes..."
  #1038: Login fails for users with SSO enabled intermittently [bug, authentication, sso]
         "SSO callback URL is occasionally returning 404. Race condition in session..."
  #1027: Password reset emails not being delivered [bug, email, authentication]
         "SMTP service failing silently. No error logged..."
  #1019: Rate limiting on /auth/token endpoint too aggressive [enhancement, authentication]
         "Legitimate mobile clients getting 429 errors due to token refresh patterns..."
  #1011: CSRF tokens not validated on /api/auth/refresh [security, authentication]
         "Security audit: refresh endpoint accepts requests without CSRF header..."

Slack Messages: 4 relevant incident thread messages found.

[Analysis] 2,341ms ✓
Root Cause Analysis:
1. **JWT Key Propagation (HIGH CONFIDENCE)**: Issues #1042 and the Slack incident thread 
   both point to JWT signing keys not propagating to all pod instances during rotation.
   
2. **Race Condition in SSO (#1038)**: Session initialization race condition during high 
   concurrency. Redis lock not acquired before session write.
   
3. **Email Service Silent Failure (#1027)**: SMTP service failure not surfaced via health 
   checks. Notification service lacks retry queue.
   
4. **Rate Limit Misconfiguration (#1019)**: Mobile token refresh pattern (high frequency, 
   burst) misidentified as abuse. Needs client-type-aware rate limiting.
   
5. **Security Gap (#1011)**: Missing CSRF validation on refresh endpoint. Critical — 
   should be fixed immediately regardless of other work.

[QA] 1,203ms ✓
Validation:
- Finding 1 (JWT propagation): HIGH confidence — corroborated by Slack + GitHub
- Finding 2 (SSO race): MEDIUM confidence — single report, needs reproduction
- Finding 3 (Email): HIGH confidence — multiple user reports over 2+ days
- Finding 4 (Rate limit): MEDIUM confidence — need mobile client metrics
- Finding 5 (CSRF): HIGH confidence — security audit finding, reproducible

[Summary] 2,891ms ✓
```

**Final Answer:**
```markdown
## Summary

Analysis of 5 open authentication issues (last 30 days) reveals two critical security 
concerns and three operational failures. The most urgent is an unvalidated CSRF vulnerability 
on the token refresh endpoint. A recurring JWT key propagation bug is causing intermittent 
logouts during peak load.

## Key Findings

- **5 open auth issues** in the last 30 days, 2 labeled high-priority or security
- **Recurring pattern**: JWT key management issues appear in 2 separate incidents
- **Silent failures**: Both the SMTP service and SSO callback fail without alerting
- **Rate limiting too aggressive**: Mobile clients incorrectly throttled

## Root Cause Analysis

The primary operational issue is **JWT signing key rotation not propagating atomically** 
to all pod replicas. When rotation occurs, pods with old keys reject tokens signed by 
new keys during the overlap window. Fix: use a shared key cache (Redis) instead of 
in-memory key storage.

## Recommended Actions

1. **[IMMEDIATE - Security]** Add CSRF validation to `/api/auth/refresh` — Issue #1011
2. **[This Sprint]** Move JWT public key cache to Redis to ensure atomic propagation — Issue #1042
3. **[This Sprint]** Add health check + retry queue to notification service — Issue #1027
4. **[Next Sprint]** Implement client-type-aware rate limiting for mobile — Issue #1019
5. **[Next Sprint]** Add distributed lock to SSO session initialization — Issue #1038

## Risk Assessment

- CSRF gap (#1011): **CRITICAL** — exploitable today, low effort to fix
- JWT propagation (#1042): **HIGH** — affects all users during rotation window
- Confidence: High on findings 1, 3, 5. Medium on 2, 4 (need more data)
```

**Total Duration:** 8,424ms  
**Agents:** 5 (Planner, Research, Analysis, QA, Summary)

---

## Example 3: "I Don't Know" Response

**Prompt:**
> What is our Kubernetes cluster autoscaling configuration?

**Mode:** RAG

**Output:**
```
I don't have enough information in the knowledge base to answer this question.

The knowledge base contains documentation about authentication, incident response, 
and API gateway configuration, but does not include Kubernetes infrastructure configuration.

To get this information, consider:
- Uploading your infrastructure documentation (YAML configs, runbooks)
- Using the Agent mode to search your GitHub repository directly
```

**Sources:** []  
**Grounded:** false  
**Relevance Score:** 0.112

---

## Example 4: Tool Direct Execution

**Tool:** `github`  
**Params:** `{"action": "search_issues", "query": "authentication", "days": 30}`

**Output:**
```json
[
  {
    "number": 1042,
    "title": "Authentication tokens expire prematurely during peak load",
    "state": "open",
    "url": "https://github.com/my-org/backend/issues/1042",
    "labels": ["bug", "authentication", "high-priority"],
    "body_preview": "Users report being logged out unexpectedly when traffic spikes..."
  },
  ...
]
```
