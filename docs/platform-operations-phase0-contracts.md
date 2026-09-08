# Platform Operations Phase 0: Discovery And Contracts

## Status

Phase 0 architecture baseline completed on 2026-09-07. This document records
the contracts that Phase 1 must implement. Changes to the authority boundary or
operation lifecycle require an explicit architecture review.

## 1. Existing System Map

| Concern | Current authority | Existing implementation | Platform integration decision |
| --- | --- | --- | --- |
| Login identity | Global application user | `Authentication.User`, auth sessions and token versioning | Reuse identity and sessions; add explicit platform assignment |
| Customer account | Subscription domain | `subscriptions.CustomerAccount` | Reuse as tenant root |
| Tenant membership | Subscription domain | `subscriptions.UserEntityAccess` | Never use as platform authorization |
| Subscription | Subscription domain | `CustomerSubscription`, plans, limits, `SubscriptionService` | Invoke through typed platform handlers |
| Entity onboarding | Entity domain | `EntityOnboardingService` and onboarding serializers | Extract owner/account-aware service entry point |
| Entity access | Entity and RBAC domains | `EffectivePermissionService`, roles and assignments | Keep tenant scoped; platform access is separate |
| Entity context | Entity domain | `/api/entity/me/*`, `UserEntityContext` | Do not create platform authority through context selection |
| Tenant user management | Subscription and RBAC domains | Membership APIs and role assignments | Reuse domain services after platform authorization |
| Tenant approvals | Entity domain | Entity approval policies and requests | Do not overload for platform approvals |
| Generic request audit | Audit logger | `AuditMiddleware`, `AuditLog` | Exclude/redact platform payloads; use structured platform audit |
| RBAC audit | RBAC domain | `RBACAuditLog` | Continue for tenant RBAC changes; link platform correlation ID |
| Platform subscription admin | Subscription views | `permissions.IsAdminUser` | Migrate to explicit platform permissions before console exposure |

## 2. Confirmed Constraints

### 2.1 Identity

`Authentication.User` is the global login identity and already supports active
status, email verification, token versioning, lockout, and revocable sessions.
Platform operators should therefore remain normal application users with a
separate platform assignment. A new user class is unnecessary.

`is_staff` remains limited to Django administration access. `is_superuser`
remains an emergency framework capability and is not accepted as the normal
authorization contract for `/api/platform/`.

### 2.2 Tenant Root

`CustomerAccount` is the effective tenant root. Entities belong to a customer
account and user memberships are account scoped. Platform APIs must identify
both account and entity where appropriate and must never infer cross-tenant
authority from an entity context stored for the operator.

### 2.3 Onboarding

The current `EntityOnboardingService.create_entity(actor, payload)` calls
`SubscriptionService.assert_can_create_entity(user=actor)`. This correctly
binds self-service onboarding to the actor's account, but it cannot be used
unchanged for platform-led onboarding because the actor is the operator rather
than the customer owner.

Phase 3 must introduce an explicit service contract similar to:

```python
EntityOnboardingService.create_entity_for_account(
    actor=platform_operator,
    owner=customer_owner,
    customer_account=customer_account,
    payload=validated_payload,
    operation_context=operation_context,
)
```

The new method must share the current normalization and provisioning internals.
It must not temporarily grant the operator tenant membership or call the public
API on behalf of the owner.

### 2.4 Subscription Administration

Current plan and account administration endpoints use DRF `IsAdminUser`. These
are valid internal endpoints today but are too broad for the platform console.
Platform handlers must enforce permissions such as
`platform.subscription.change`, capture a reason, classify risk, and create an
operation record. Existing subscription service methods remain authoritative.

### 2.5 Audit

`AuditMiddleware` captures request payloads broadly in `new_data`. Platform
requests may include bank, tax, contact, support, or credential metadata, so
they cannot rely on unfiltered request-body capture.

Before platform mutations ship:

- Platform paths must use explicit redaction or be excluded from raw body
  capture.
- A structured platform audit event must use field allowlists.
- Passwords, tokens, secrets, provider credentials, and full bank details must
  never enter audit JSON or application logs.
- Audit failure for a platform mutation must fail closed or be durably queued;
  logging and continuing is not sufficient for privileged operations.

## 3. Authority Contract

Authorization is evaluated in this order:

1. Authenticated and active application user.
2. Valid, active, unexpired platform role assignment.
3. Required platform permission.
4. Target-scope constraint, when present.
5. Operation risk and approval requirement.
6. Active support-session scope, only for support-context tenant access.
7. Request target version and operation state.

Tenant membership and entity RBAC are not inputs to platform authorization.
Platform authorization does not grant normal tenant API access unless an active
support-session policy explicitly permits it.

### 3.1 Initial Role Matrix

Legend: `R` read, `W` direct low/medium-risk write, `Q` request only, `A`
approve, `-` denied.

| Capability | Viewer | Onboarding | Support | Billing | Compliance | Approver | Security |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Customer/entity discovery | R | R | R | R | R | R | R |
| Onboarding request | - | W | - | - | - | A | - |
| Customer metadata | - | W | Q | W | Q | A | - |
| Subscription change | - | Q | - | W | - | A | - |
| GST/compliance change | - | - | Q | - | Q | A | - |
| Tenant membership recovery | - | W | Q | - | - | A | - |
| Read-only support session | - | - | Q | - | - | A | - |
| Write support session | - | - | Q | - | - | A | - |
| Platform access management | - | - | - | - | - | - | W |
| Platform audit | R | R | R | R | R | R | R |
| Audit export | - | - | - | - | - | A | Q |

Exact seed data will use atomic permission codes, not role-name checks.

## 4. Operation Contract

### 4.1 Common Request Envelope

```json
{
  "operation_type": "entity.onboard",
  "target": {
    "customer_account_id": 42,
    "entity_id": null
  },
  "payload": {},
  "reason": "Customer onboarding approved by operations",
  "ticket_reference": "OPS-12345",
  "idempotency_key": "client-generated-uuid",
  "expected_target_version": null
}
```

### 4.2 Common Response Envelope

```json
{
  "operation_id": "uuid",
  "correlation_id": "uuid",
  "operation_type": "entity.onboard",
  "risk": "medium",
  "status": "validated",
  "approval_requirement": {
    "required": false,
    "minimum_approvals": 0
  },
  "validation": {
    "errors": [],
    "warnings": []
  },
  "links": {
    "self": "/api/platform/operations/uuid"
  }
}
```

### 4.3 Error Contract

All platform errors use stable codes:

```json
{
  "detail": "The target changed after this request was approved.",
  "code": "platform_target_version_conflict",
  "correlation_id": "uuid",
  "field_errors": {},
  "retryable": false
}
```

Initial codes:

- `platform_access_denied`
- `platform_permission_missing`
- `platform_target_scope_denied`
- `platform_self_approval_denied`
- `platform_approval_required`
- `platform_operation_state_conflict`
- `platform_target_version_conflict`
- `platform_idempotency_conflict`
- `platform_validation_failed`
- `platform_execution_failed`
- `platform_support_session_expired`
- `platform_support_scope_denied`

### 4.4 Idempotency

- The tuple `(requested_by, operation_type, idempotency_key)` is unique.
- Repeating an identical request returns the original operation.
- Reusing the key with a different target or payload returns 409.
- Execution locks the operation record and permits one running attempt.
- Domain-level uniqueness remains the final protection for account, entity, FY,
  membership, and subscription records.

### 4.5 Optimistic Concurrency

Each mutable target exposes a deterministic version derived from its update
timestamp and relevant child state. Validation records that version. Execution
must reject stale approved requests rather than overwrite newer tenant changes.

## 5. Approval Contract

- Low-risk requests execute after validation and explicit confirmation.
- Medium-risk requests can execute directly only when policy allows.
- High-risk requests require one independent approver.
- Critical requests require two independent approvers or the configured policy.
- The requester cannot approve their own request.
- Approvals expire after the configured interval.
- Payload or target changes invalidate all prior approvals.
- Rejection and cancellation are terminal.
- Approval and execution are separate permissions.

## 6. Support Session Contract

A support session grants no permanent membership. It contains:

- Operator, customer account, and optional entity/branch scope.
- Approved read/write scopes.
- Reason and ticket reference.
- Start, absolute expiry, revocation, and last activity timestamps.
- Requester and approver identities.

Read-only is the default. The frontend must show a persistent platform-support
banner, target name, scope, and remaining time. The backend is authoritative
for expiry and scope enforcement.

## 7. Threat Model

| Threat | Control | Required evidence |
| --- | --- | --- |
| Tenant admin reaches platform API | Separate assignment and permission policy | Negative API tests for every platform route |
| Staff flag becomes global bypass | Never authorize with `IsAdminUser` alone | `is_staff`-only user receives 403 |
| Operator silently joins tenant | Support context never creates membership | Membership snapshots before/after session |
| Requester self-approves | Database/service actor separation check | Unit and concurrent approval tests |
| Approved request overwrites newer data | Target version checked at execution | Stale request returns 409 |
| Duplicate onboarding | Request and domain idempotency | Concurrent duplicate-submit tests |
| Sensitive values leak to audit/logs | Allowlists, redaction, no raw body audit | Secret canary scan across DB and logs |
| Support token is replayed | Short expiry, session ID, revocation, token version | Expiry/revocation browser and API tests |
| UI hides action but API permits it | API permission is authoritative | Direct API attack matrix |
| Partial provisioning is abandoned | Durable stages and reconciliation | Failure injection at every stage |
| Platform operator edits posted books | No transaction mutation handlers | Endpoint inventory and denied tests |
| Audit write fails silently | Fail closed or durable audit outbox | Forced audit failure test |

## 8. Audit Event Contract

Every mutation produces a structured event containing:

- Event and correlation IDs.
- Operation ID and type.
- Actor and effective platform permissions.
- Customer account and entity identifiers.
- Action, outcome, risk, and approval references.
- Redacted before and after snapshots.
- Request IP, user agent, and server timestamp.
- Error code and execution attempt when applicable.

Events are append-only. A correction creates another event; it never edits the
original event.

## 9. Phase 1 Implementation Backlog

### Backend

1. Scaffold `platform_ops` and mount `/api/platform/`.
2. Add platform permission, role, assignment, and audit-event models.
3. Add database constraints and indexes for active assignments.
4. Seed the initial permission catalog and conservative built-in roles.
5. Implement `PlatformAccessService` and DRF permission classes.
6. Implement `/api/platform/me/` with capabilities, roles, and session posture.
7. Add structured audit writer with explicit redaction.
8. Exclude or redact `/api/platform/` payloads in generic audit middleware.
9. Add a global feature flag and mutation kill switch.
10. Register read-only Django admin views for platform security models.

### Frontend

1. Add lazy `/platform` route and platform access guard.
2. Add a visually distinct platform shell.
3. Add a minimal platform home showing operator identity and capabilities.
4. Add dedicated 401, 403, expired-assignment, and disabled-feature states.
5. Ensure tenant navigation and entity context do not confer platform access.

### Tests

1. Model constraint and expiry tests.
2. Atomic permission matrix tests.
3. Tenant owner/admin/member denial tests.
4. `is_staff`-only denial test.
5. Inactive and expired assignment tests.
6. Mutation audit and redaction tests.
7. Feature-flag and kill-switch tests.
8. Playwright route isolation tests for tenant and platform operators.
9. Accessibility scan and keyboard navigation for the platform shell.

## 10. Phase 1 Definition Of Done

- Platform identity cannot be obtained through tenant membership or entity RBAC.
- Platform routes are absent or denied for tenant-only users.
- Atomic permission checks are enforced by APIs.
- Platform role assignments support activation, expiry, and revocation.
- `/api/platform/me/` returns the effective capabilities used by the frontend.
- Every platform mutation test produces a redacted immutable audit event.
- Raw secrets do not appear in generic audit records or logs.
- Feature flag disables the entire platform module.
- Mutation kill switch blocks writes while preserving authorized reads.
- Backend, frontend, Playwright, and deployment checks pass.

## 11. Architecture Decisions

| ID | Decision | Status |
| --- | --- | --- |
| PO-ADR-001 | Reuse `Authentication.User`; add separate platform assignments | Accepted |
| PO-ADR-002 | Treat `CustomerAccount` as tenant root | Accepted |
| PO-ADR-003 | Never use tenant membership as platform authority | Accepted |
| PO-ADR-004 | Use typed operation handlers, not generic model mutation | Accepted |
| PO-ADR-005 | Require durable operation and audit records for mutations | Accepted |
| PO-ADR-006 | Add owner/account-aware onboarding service entry point | Accepted |
| PO-ADR-007 | Use temporary support context, never silent impersonation | Accepted |
| PO-ADR-008 | Replace broad admin checks in platform-facing workflows | Accepted |
| PO-ADR-009 | Redact or exclude platform payloads from generic audit capture | Accepted |
| PO-ADR-010 | Deliver read-only visibility before platform writes | Accepted |

## 12. Deferred Decisions

The following must be selected before their implementation phase:

- Background worker technology and audit outbox transport in Phase 6.
- Final MFA provider and step-up authentication mechanism in Phase 1/5.
- Audit retention period and external archive destination.
- Critical-operation approval count and expiry by production policy.
- Whether platform assignments can be globally scoped only or constrained by
  region/account portfolio in the first release.

These decisions do not block the Phase 1 data model if scope and MFA metadata
are represented explicitly.
