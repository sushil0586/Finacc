# Platform Operations Implementation Plan

## 1. Purpose

Build a secure platform-level operations module for Finacc staff to onboard and
support customer accounts and entities without weakening tenant isolation.

The module is a control plane above tenant operations. It must reuse existing
domain services for subscriptions, entity onboarding, membership, RBAC, and
auditing instead of duplicating their business rules.

## 2. Desired Outcomes

- Platform operators can locate and understand any customer account or entity.
- Authorized operators can onboard a customer, owner, entity, branches,
  financial years, subscription, and initial access end to end.
- Controlled changes can be made after onboarding with validation, preview,
  approval, execution tracking, and recovery.
- Support access is temporary, scoped, visible, and fully audited.
- Sensitive operations follow maker-checker segregation of duties.
- Failed provisioning can be retried without duplicate records or partial state.
- Tenant users cannot discover or invoke platform functionality.

## 3. Architectural Boundary

### 3.1 Control Plane

The platform module owns:

- Platform operator identities and permissions.
- Global customer and entity discovery.
- Operation requests, approvals, execution status, and support sessions.
- Cross-tenant operational audit evidence.
- Provisioning orchestration and health checks.

### 3.2 Tenant Plane

The existing application remains authoritative for:

- `CustomerAccount`, subscription, and tenant membership.
- Entity, branch, financial year, tax, and compliance configuration.
- Entity-scoped roles and permissions.
- Accounting, invoicing, inventory, payroll, assets, and reports.

Platform code must invoke existing services such as `SubscriptionService` and
`EntityOnboardingService`. It must not create parallel onboarding rules or write
directly to accounting transaction tables.

### 3.3 Hard Rules

- A platform role is not an entity role.
- Django `is_staff` or `is_superuser` alone does not grant API access.
- Platform endpoints use a separate `/api/platform/` namespace.
- Every platform mutation requires an operation record and correlation ID.
- High-risk operations require approval by a different operator.
- Cross-tenant support access is read-only by default and expires automatically.
- Posted financial documents cannot be edited through the platform console.

## 4. Personas And Permissions

### 4.1 Initial Personas

| Persona | Primary scope |
| --- | --- |
| Platform Viewer | Read customer, entity, subscription, health, and audit data |
| Onboarding Operator | Create accounts, entities, branches, FYs, and initial access |
| Support Operator | Diagnose tenants and request controlled support access |
| Billing Operator | Manage plans, trials, limits, and billing metadata |
| Compliance Operator | Correct approved tax, registration, FY, and lock settings |
| Platform Approver | Approve high-risk requests created by another operator |
| Security Administrator | Manage platform identities, roles, MFA, and sessions |
| Emergency Administrator | Time-limited break-glass access only |

### 4.2 Permission Naming

Use stable permission codes grouped by resource and action:

```text
platform.customer.view
platform.customer.create
platform.customer.update
platform.entity.view
platform.entity.onboard
platform.entity.update
platform.entity.suspend
platform.subscription.view
platform.subscription.change
platform.membership.view
platform.membership.manage
platform.support.request
platform.support.activate
platform.operation.view
platform.operation.approve
platform.operation.execute
platform.repair.preview
platform.repair.execute
platform.audit.view
platform.audit.export
platform.security.manage
```

Authorization checks must consider permission, operation risk, target scope,
and support-session scope. Frontend guards are usability controls only; the API
is always authoritative.

## 5. Operation Risk Model

| Risk | Examples | Required control |
| --- | --- | --- |
| Low | Notes, contact correction, resend invitation | Reason and audit |
| Medium | Add branch, add FY, activate module, user status change | Preview and confirmation |
| High | GSTIN change, owner transfer, plan override, suspension | Maker-checker approval |
| Critical | Cross-tenant repair, destructive closure, emergency access | Dual approval, time limit, incident reference |

The requester cannot approve their own high or critical operation. An approved
request becomes invalid if the target version changes before execution.

## 6. Proposed Backend Domain

Create a dedicated Django app named `platform_ops`.

### 6.1 Core Models

- `PlatformRole`: platform-only role catalog.
- `PlatformPermission`: stable platform permission catalog.
- `PlatformUserRole`: operator-to-role assignment with effective dates.
- `PlatformOperationRequest`: requested action, target, risk, payload, snapshots,
  reason, ticket, status, idempotency key, and correlation ID.
- `PlatformOperationApproval`: approval decision, note, actor, and timestamp.
- `PlatformOperationExecution`: attempt number, stage, result, timing, and error.
- `PlatformProvisioningJob`: resumable onboarding or repair state machine.
- `PlatformSupportSession`: target, granted scopes, expiry, status, and revocation.
- `PlatformEntityNote`: operational notes with visibility classification.
- `PlatformAuditEvent`: immutable platform audit record.

### 6.2 Operation Statuses

```text
DRAFT -> VALIDATED -> PENDING_APPROVAL -> APPROVED -> QUEUED
      -> RUNNING -> SUCCEEDED
                 -> FAILED -> RETRY_QUEUED -> RUNNING
      -> REJECTED
      -> CANCELLED
```

Use database constraints to prevent invalid terminal transitions and duplicate
idempotency keys. Execution must lock the operation row before changing state.

### 6.3 Data Protection

- Store before/after snapshots with explicit field allowlists.
- Never snapshot passwords, authentication tokens, private keys, or raw provider
  credentials.
- Mask GST credentials, bank account numbers, email addresses, and phone numbers
  according to operator permission.
- Retain platform audit events according to an approved retention policy.

## 7. Proposed API Surface

```text
GET    /api/platform/me/
GET    /api/platform/dashboard/
GET    /api/platform/customers/
GET    /api/platform/customers/{id}/
GET    /api/platform/entities/
GET    /api/platform/entities/{id}/
POST   /api/platform/onboarding/validate/
POST   /api/platform/onboarding/requests/
GET    /api/platform/operations/
GET    /api/platform/operations/{id}/
POST   /api/platform/operations/{id}/validate/
POST   /api/platform/operations/{id}/submit/
POST   /api/platform/operations/{id}/approve/
POST   /api/platform/operations/{id}/reject/
POST   /api/platform/operations/{id}/execute/
POST   /api/platform/operations/{id}/retry/
POST   /api/platform/operations/{id}/cancel/
POST   /api/platform/support-sessions/
POST   /api/platform/support-sessions/{id}/activate/
POST   /api/platform/support-sessions/{id}/revoke/
GET    /api/platform/audit-events/
GET    /api/platform/health/
```

Mutation requests include `reason`, `ticket_reference`, `idempotency_key`, and
`expected_target_version`. Responses include `operation_id`, `correlation_id`,
`risk`, `approval_requirement`, and a structured result.

## 8. Frontend Information Architecture

Add a lazy-loaded platform area with its own route guard and shell:

```text
/platform/dashboard
/platform/customers
/platform/customers/:id
/platform/onboarding/new
/platform/operations
/platform/operations/:id
/platform/approvals
/platform/support-sessions
/platform/audit
/platform/access
```

The platform shell must be visually distinct from tenant workspaces and must not
inherit an entity context as authority. A persistent header identifies platform
mode, operator identity, and any active support session.

## 9. Phased Delivery Plan

### Phase 0: Discovery And Contracts

**Goal:** freeze boundaries and workflows before introducing platform writes.

Backend work:

- Inventory all entity creation and update paths.
- Map `CustomerAccount`, subscriptions, memberships, entity RBAC, onboarding,
  notifications, and audit dependencies.
- Define platform personas, permission matrix, risk classification, and approval
  policy.
- Define API schemas, operation state transitions, error codes, and audit fields.
- Record transaction boundaries and idempotency expectations for existing
  services.

Frontend work:

- Produce console navigation and low-fidelity workflow designs.
- Define loading, empty, validation, approval, execution, and recovery states.
- Define responsive and accessibility acceptance criteria.

Testing and exit gate:

- Architecture and threat-model review completed.
- API and permission contracts approved.
- Existing onboarding baseline tests recorded.
- No implementation starts until platform and tenant authority are unambiguous.

### Phase 1: Platform Identity And Security Foundation

**Goal:** establish the control-plane authorization boundary.

Backend work:

- Create `platform_ops` app and platform RBAC models.
- Seed initial platform permissions and roles.
- Implement `IsPlatformOperator` and permission-policy classes.
- Require MFA-ready authentication claims for privileged routes.
- Implement `/api/platform/me/` and immutable platform audit events.
- Add session revocation and emergency-access foundations.

Frontend work:

- Add lazy platform module, route guard, and platform shell.
- Add unauthorized, session-expired, and permission-denied states.
- Hide platform navigation from all tenant-only users.

Testing and exit gate:

- Tenant admins cannot access any platform endpoint.
- `is_staff` without a platform assignment receives 403.
- Platform permission matrix passes API tests.
- Every test mutation produces an audit event.
- Security review approves the control-plane boundary.

### Phase 2: Read-Only Operations Console

**Goal:** provide global operational visibility before enabling changes.

Backend work:

- Implement paginated customer and entity search.
- Add account, subscription, membership, entity, branch, FY, and health summaries.
- Add masked detail serialization based on permission.
- Build consistency checks for incomplete onboarding and broken context.

Frontend work:

- Build operations dashboard and customer directory.
- Build customer workspace tabs: overview, entities, users, subscription, health,
  operations, notes, and audit.
- Add server-side search, filters, pagination, stable URLs, and exports where
  permitted.

Testing and exit gate:

- Large-account pagination and search are correct.
- No cross-tenant data leaks through filters, counts, errors, or exports.
- Masking tests pass for every operator persona.
- WCAG automated scan and keyboard workflow pass.
- Query and page-load budgets are met with production-like data.

### Phase 3: Operator-Led Onboarding

**Goal:** onboard a new customer and entity from one controlled workflow.

Backend work:

- Implement duplicate detection for email, phone, legal name, GSTIN, and external
  customer ID.
- Implement onboarding validation and preview endpoints.
- Wrap existing subscription and entity onboarding services in a provisioning
  orchestrator.
- Add idempotency and a resumable provisioning state machine.
- Verify account, owner, subscription, entity, branches, FYs, defaults,
  membership, RBAC, and notification after execution.

Frontend work:

- Build a guided onboarding workspace.
- Support owner lookup/create, plan selection, entity details, GST status,
  branches, FYs, bank details, modules, initial users, review, and submit.
- Display warnings separately from blocking errors.
- Show stage-level provisioning progress and a completion report.

Testing and exit gate:

- Registered, unregistered, and non-GST entities pass end to end.
- Single and multi-branch onboarding pass.
- Duplicate submissions create one account/entity only.
- Failure at every provisioning stage can resume without duplication.
- New owner can verify, sign in, select the entity/FY/branch, and reach the home
  dashboard with correct permissions.

### Phase 4: Controlled Change Operations

**Goal:** support normal post-onboarding operational changes.

Initial operations:

- Correct customer contacts and metadata.
- Add or update branches and financial years.
- Update permitted legal, GST, and compliance settings.
- Change subscription, trial dates, limits, and feature flags.
- Invite, activate, deactivate, and recover tenant users.
- Transfer ownership through an approved workflow.
- Suspend, reactivate, or close an account.
- Preview and run onboarding repair routines.

Implementation rules:

- Each change uses a typed operation handler.
- Preview and execution share the same validation service.
- High-risk changes require maker-checker approval.
- Execution checks optimistic target version before writing.
- No generic model editor or arbitrary JSON patch endpoint is allowed.

Testing and exit gate:

- Before/after snapshots match persisted changes.
- Approval, rejection, stale-version, cancellation, and retry paths pass.
- Entity/FY/GST uniqueness errors are returned as structured validation.
- Suspension and reactivation behavior is verified throughout the tenant app.
- Accounting records remain unchanged by configuration operations.

### Phase 5: Support Sessions And Governance

**Goal:** permit diagnosis without permanent cross-tenant privilege.

Backend work:

- Implement scoped, short-lived support sessions.
- Default sessions to read-only.
- Require reason, ticket, target, requested scopes, and expiry.
- Add approval for write-capable or sensitive sessions.
- Enforce support context in middleware/policy without creating tenant membership.
- Add immediate revocation and automatic expiry.

Frontend work:

- Add support-session request and approval flows.
- Display an unmistakable support-mode banner with target and countdown.
- Provide an explicit exit action on every support-mode screen.
- Mask sensitive data unless separately authorized.

Testing and exit gate:

- Expired and revoked sessions fail immediately.
- Session scope cannot be widened client-side.
- Support access does not create or modify tenant memberships.
- Every read and write in support mode is attributable to operator and ticket.
- Write-capable support sessions require independent approval.

### Phase 6: Reliability, Observability, And Recovery

**Goal:** make operations supportable under real failure conditions.

Backend work:

- Run long operations through the project-standard background-job mechanism.
- Add retry policies, dead-letter handling, and idempotent stage checkpoints.
- Add reconciliation jobs for stuck and partially completed operations.
- Emit metrics for duration, failures, retries, approvals, and support access.
- Add structured logs using operation and correlation IDs.
- Create operator-safe diagnostics and administrator runbooks.

Frontend work:

- Add live job status, retry eligibility, failure detail, and recovery actions.
- Add operational health and failure queues.
- Prevent duplicate execution while a request is queued or running.

Testing and exit gate:

- Timeout, worker restart, database conflict, provider failure, and notification
  failure scenarios pass.
- No duplicate account, entity, FY, membership, or role is produced.
- Stuck operations are detectable and recoverable.
- Alerts and dashboards identify failures within the agreed service objective.

### Phase 7: Certification And Staged Rollout

**Goal:** prove production readiness and introduce the module safely.

Validation work:

- Backend unit, integration, permission, concurrency, and audit tests.
- Playwright coverage across Chromium, Firefox, and WebKit.
- Platform persona matrix and tenant isolation attack suite.
- Visual checks at desktop, tablet, and mobile sizes.
- Automated accessibility scans and manual screen-reader review.
- Production-like search, onboarding, execution, and audit-query load tests.
- Backup/restore and failed-provisioning recovery exercise.

Rollout stages:

1. Feature disabled in production while migrations and seed data deploy.
2. Read-only shadow access for security and operations leads.
3. Pilot onboarding with a small operator group.
4. Enable low and medium-risk operations.
5. Enable maker-checker high-risk operations.
6. Enable controlled support sessions.
7. General operations rollout after launch review.

Exit gate:

- No open critical or high-severity defects.
- Required audit coverage is 100% for mutations.
- Isolation and permission suites pass in staging.
- Provisioning retry and recovery exercises pass.
- Security, operations, product, and QA owners approve launch.

## 10. Test Strategy

### 10.1 Backend

- Model constraints and state transitions.
- Platform permission combinations.
- Self-approval prevention and approval expiry.
- Idempotency and concurrent execution.
- Serializer masking and secret exclusion.
- Existing service integration and rollback behavior.
- Audit completeness and immutability.
- Support-session scope, expiry, and revocation.

### 10.2 Browser Workflows

- Platform operator login and route isolation.
- Customer search and account inspection.
- Complete registered, unregistered, and non-GST onboarding.
- Multi-branch and multi-FY onboarding.
- Duplicate detection and duplicate-submit protection.
- Maker submits, approver approves, worker executes.
- Failed operation retry and visible recovery.
- Support session activation, use, exit, expiry, and revocation.
- Keyboard-only operation and accessible dialogs/tables.

### 10.3 Security Scenarios

- Tenant token against every platform endpoint.
- Platform viewer attempting mutation.
- Operator attempting ungranted target/action.
- Requester attempting self-approval.
- Modified target after approval.
- Replayed idempotency key and execution request.
- Expired support token and altered support scope.
- Sensitive values in API responses, logs, audit snapshots, and exports.

## 11. Operational Requirements

- Platform MFA is mandatory before write operations are enabled.
- Platform sessions use shorter idle and absolute timeouts than tenant sessions.
- Critical actions require a current ticket or incident reference.
- Alerts cover repeated access denials, emergency access, failed operations,
  unusual cross-tenant activity, and audit write failures.
- Audit storage must be searchable and exportable but not editable by operators.
- A kill switch disables all platform mutations while preserving read access.

## 12. Initial Non-Goals

- Editing posted invoices, vouchers, ledger entries, or statutory returns.
- Arbitrary database administration from the web console.
- Permanent impersonation or silent login as a tenant user.
- A generic endpoint that updates any entity model or field.
- Replacing tenant RBAC or the current customer onboarding domain services.
- Automating billing-provider settlement before core control-plane workflows pass.

## 13. Recommended Implementation Order

Begin with Phase 0 and Phase 1. Phase 2 then provides immediate operational value
with lower risk. Platform write capability starts only in Phase 3 after the
identity boundary, audit trail, and permission model are proven.

The first implementation milestone is:

```text
Platform operator assignment
-> platform login/authorization
-> read-only customer directory
-> customer/entity detail
-> health and audit visibility
```

This milestone gives the operations team useful visibility and validates the
control-plane architecture before onboarding or change execution is introduced.

## 14. Phase Tracking

Phase 0 evidence and accepted contracts are recorded in
[`platform-operations-phase0-contracts.md`](platform-operations-phase0-contracts.md).
Phase 1 and Phase 2 verification evidence is recorded in
[`platform-operations-phase1-results.md`](platform-operations-phase1-results.md)
and [`platform-operations-phase2-results.md`](platform-operations-phase2-results.md).

| Phase | Status | Release artifact |
| --- | --- | --- |
| 0. Discovery and contracts | Completed | Architecture baseline and Phase 0 contracts |
| 1. Identity and security | Completed | Secured platform shell and authorization API |
| 2. Read-only console | Completed | Searchable customer and entity operations console |
| 3. Operator onboarding | Completed | Validated, idempotent, recoverable end-to-end onboarding |
| 4. Change operations | In progress | Typed operational change workflows; customer contact correction complete |
| 5. Support and governance | Not started | Expiring support sessions and approvals |
| 6. Reliability and recovery | Not started | Observable resumable job execution |
| 7. Certification and rollout | Not started | Signed production launch gate |

Update this table and attach phase evidence as implementation progresses.
