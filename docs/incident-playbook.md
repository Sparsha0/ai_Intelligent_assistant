# Incident Response Playbook

## Severity Definitions

| Level | Impact                           | Response SLA | Example                        |
|-------|----------------------------------|--------------|--------------------------------|
| P0    | Full service outage              | 15 minutes   | Login completely broken        |
| P1    | Major feature broken, >20% users | 1 hour       | SSO failing for enterprise     |
| P2    | Partial degradation, <20% users  | 4 hours      | Password reset emails delayed  |
| P3    | Minor issue, workaround exists   | Next biz day | UI glitch on login page        |

## On-Call Rotation

Primary: Auth Team on-call (rotates weekly)
Escalation: `#incidents` Slack channel → Team Lead → VP Engineering

PagerDuty schedule: `auth-oncall` rotation

## Authentication Incident Runbook

### Symptom: Users Cannot Log In (P0)

**Immediate Actions (first 5 minutes):**
1. Check auth service pod health:
   ```bash
   kubectl get pods -n auth -l app=auth-service
   kubectl describe pod -n auth <failing-pod>
   ```
2. Check recent deployments:
   ```bash
   kubectl rollout history deployment/auth-service -n auth
   ```
3. If recent deployment: rollback immediately:
   ```bash
   kubectl rollout undo deployment/auth-service -n auth
   ```

**Investigation (5-15 minutes):**
4. Check error logs:
   ```bash
   kubectl logs -n auth -l app=auth-service --tail=200 | grep ERROR
   ```
5. Verify Redis connectivity:
   ```bash
   kubectl exec -n auth deploy/auth-service -- redis-cli -h redis.internal ping
   ```
6. Check JWT signing key availability:
   ```bash
   kubectl exec -n auth deploy/auth-service -- curl -s vault.internal/v1/secret/jwt-keys | jq .
   ```
7. Check database connectivity:
   ```bash
   kubectl exec -n auth deploy/auth-service -- pg_isready -h postgres.internal
   ```

### Symptom: High Error Rate on /auth/token (P1)

1. Check token endpoint metrics in Grafana dashboard: `Auth Service Overview`
2. Verify rate limiting not too aggressive: check Redis `rate:token:*` keys
3. Check for unusual traffic spike (DDoS?): review nginx access logs
4. Inspect token validation errors in logs for patterns

### Symptom: SSO Failing (P1)

1. Verify IdP is reachable: `curl -I https://idp.company.com/.well-known/openid-configuration`
2. Check OAuth callback URL configuration (common misconfiguration after deployments)
3. Verify client credentials in Vault haven't expired
4. Check SAML certificate expiry dates

### Symptom: Password Reset Emails Not Delivered (P2)

1. Check SMTP service (SendGrid/SES) status page
2. Verify notification-service is running: `kubectl get pods -n notify`
3. Check email queue depth: `redis-cli llen email:queue`
4. Inspect failed email logs: `kubectl logs -n notify deploy/notification-service | grep FAILED`

## Post-Incident Checklist

- [ ] Service restored and verified by on-call
- [ ] Root cause identified
- [ ] Temporary mitigations documented
- [ ] Incident timeline written in `#incidents`
- [ ] Post-mortem scheduled (within 48 hours for P0/P1)
- [ ] Action items created in Jira with owners and due dates
- [ ] Runbook updated if new failure mode discovered

## Escalation Contacts

| Role              | Contact       | When to Escalate              |
|-------------------|---------------|-------------------------------|
| Auth Team Lead    | @alice        | P0 not resolved in 30 min     |
| Security Team     | @security     | Any suspected breach          |
| VP Engineering    | @bob          | P0 not resolved in 1 hour     |
| CTO               | @cto          | Data breach confirmed          |
