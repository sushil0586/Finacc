# Platform Operations Phase 4 Progress

## Increment 1: Customer Contact Corrections

Completed on 2026-09-07.

- Added the typed `customer_contact_update` operation; no generic patch API was
  introduced.
- Restricted changes to customer contact fields and operational status notes.
- Added request reason, ticket reference, correlation ID, and idempotency
  enforcement.
- Persisted before/after preview evidence without changing the customer during
  request preparation.
- Added optimistic locking against `CustomerAccount.updated_at` and refused
  execution when the target changed after preview.
- Captured persisted before/after values and the resulting target version after
  successful execution.
- Reused platform mutation kill-switch, update permission, execution permission,
  and immutable audit controls.

Verification:

- Six focused API tests passed for preview, execution, allowlisting,
  idempotency, stale-target refusal, and permissions.
- Full platform operations suite: 43 tests passed.
- Django checks passed and no migration drift was detected.
- Migration `0005` applied to the local development database.

## Remaining Phase 4 Work

## Increment 2: Maker-Checker And Account Status

Completed on 2026-09-07.

- Added immutable approval decisions with reviewer identity, comment, decision
  time, and approved target version.
- Prevented requesters from deciding their own operations even when they also
  hold the approval permission.
- Added typed high-risk customer suspension and reactivation requests; no closed
  account transition or arbitrary status update is exposed.
- Required a ticket, operational reason, before/after preview, and independent
  approval before execution.
- Invalidated requests changed before review and approvals changed before
  execution.
- Added indexed customer and entity targets to platform audit writes.
- Added customer-detail request controls and operation-detail approve, reject,
  evidence, and post-approval execution controls.
- Added cross-browser Playwright coverage for the visible maker-checker gate.

Verification:

- Eight focused maker-checker API tests passed.
- Full platform operations suite: 52 tests passed.
- Angular typecheck and production build passed; six focused service tests
  passed.
- Playwright: 12 runs passed across Chromium, Firefox, WebKit, and browser auth
  setup.
- Django checks and migration drift checks passed.
- Migration `0006` applied to the local development database.

## Remaining Phase 4 Work

## Increment 3: Branch And Financial-Year Additions

Completed on 2026-09-07.

- Added typed, additive branch and financial-year operations without exposing a
  generic entity update or destructive nested-row replacement.
- Classified normal branch creation as medium risk and financial-year creation
  as high risk requiring independent approval.
- Reused entity onboarding serializers, then narrowed persisted branch data to
  the branch identity model's owned fields.
- Rejected head-office replacement, duplicate branch codes, duplicate FY codes,
  overlapping FY periods, missing dates, reversed dates, and stale entity
  versions.
- Seeded document numbering scopes for all current branch/FY combinations after
  successful creation, using the existing idempotent numbering service.
- Added entity-detail controls for branch and FY requests and linked each result
  to the operation review screen.
- Added cross-browser payload and presentation coverage for both operation types.

Verification:

- Six focused entity-change API tests passed.
- Full platform operations suite: 58 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- Playwright: 15 runs passed across Chromium, Firefox, WebKit, and browser auth
  setup.
- Migration `0007` applied locally; Django checks and migration drift checks
  passed.

## Remaining Phase 4 Work

## Increment 4: GST Registration Control

Completed on 2026-09-07.

- Added a typed high-risk GST registration operation covering registration,
  status/GSTIN replacement, and movement to unregistered/non-GST.
- Required independent approval, ticket evidence, a reason, and optimistic entity
  version checks before execution.
- Enforced GSTIN format, global active-registration uniqueness, entity state-code
  matching, and blank GSTIN for unregistered entities.
- Preserved deactivated registrations as history when removing GST registration.
- Synchronized existing portal credentials after GSTIN replacement and disabled
  active credentials when an entity becomes unregistered.
- Kept GST portal usernames, passwords, client IDs, and secrets out of operation
  request and result snapshots.
- Added GST controls to entity detail with dynamic GSTIN requirements and
  uppercase normalization.
- Extended the cross-browser entity workflow to cover GST request payloads and
  approval-required presentation.

Verification:

- Four focused GST operation integration tests passed.
- Full platform operations suite: 62 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- Playwright: 15 runs passed across Chromium, Firefox, WebKit, and browser auth
  setup.
- Migration `0008` applied locally; Django checks and migration drift checks
  passed.

## Remaining Phase 4 Work

## Increment 5: Subscription Plan Changes

Completed on 2026-09-07.

- Added a typed high-risk subscription plan-change operation using the
  authoritative subscription service instead of directly mutating plan fields.
- Bound optimistic concurrency to the current subscription version and locked
  both the subscription and customer account during approval and execution.
- Required an independent approval, ticket reference, operational reason, and
  exact target plan code before execution.
- Rejected inactive plans, same-plan requests, missing subscriptions, stale
  approvals, and cross-customer targets.
- Closed the prior subscription and preserved exactly one current subscription
  after a successful change, with idempotent replay protection.
- Added customer-detail controls with isolated status and subscription feedback.
- Added cross-browser coverage for normalized request data, target version,
  approval-required presentation, and the operation review link.

Verification:

- Five focused subscription operation integration tests passed.
- Full platform operations suite: 67 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- Playwright: 18 runs passed across Chromium, Firefox, WebKit, and browser auth
  setup.
- Migration `0009` applied locally; Django checks and migration drift checks
  passed.

## Remaining Phase 4 Work

## Increment 6: Tenant Membership Access Changes

Completed on 2026-09-07.

- Added a typed high-risk membership operation for role, active/suspended state,
  and access expiry changes.
- Bound requests and approvals to the exact membership version and customer,
  with idempotent replay and stale-approval rejection.
- Protected owner membership from this workflow so ownership cannot be silently
  reassigned or removed.
- Reused tenant deactivation behavior to disable related active RBAC assignments
  during suspension.
- Added customer-detail access controls with owner actions disabled, explicit
  role/status/expiry inputs, and operation review links.
- Added cross-browser assertions for owner protection and the complete versioned
  access-change request payload.

Verification:

- Five focused membership operation integration tests passed.
- Full platform operations suite: 72 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- Playwright: 21 runs passed across Chromium, Firefox, WebKit, and browser auth
  setup.
- Migration `0010` applied locally; migration drift checks passed.

## Remaining Phase 4 Work

## Increment 7: Tenant User Invitations

Completed on 2026-09-07.

- Added a typed, medium-risk invitation request for new and existing identities,
  scoped to an exact customer version.
- Removed operator-managed passwords from the workflow: new users receive an
  unusable initial password and must complete email verification.
- Reused subscription seat-limit and account-operational checks immediately
  before execution.
- Added idempotent replay, duplicate active-membership rejection, active-entity
  requirements, stale-customer invalidation, and owner-role protection.
- Stamped invitation audit metadata and generated verification OTPs only for
  unverified identities.
- Added a customer-level invitation form and operation review flow without any
  credential field or credential-bearing request data.

Verification:

- Four focused invitation operation integration tests passed.
- Full platform operations suite: 76 tests passed.
- Angular typecheck passed; seven focused service tests passed.
- The invitation browser scenario passed in Chromium, Firefox, and WebKit;
  Chromium's complete eight-run file passed.
- The broader WebKit file remains affected by existing shared auth entity lookup
  and provisioning-retry timing instability, outside the invitation scenario.
- Migration `0011` applied locally.

## Remaining Phase 4 Work

## Increment 8: Invitation Resend Control

Completed on 2026-09-07.

- Added a typed, medium-risk invitation resend operation bound to the exact
  membership and customer.
- Enforced a 60-second cooldown and five sends per rolling 24-hour period both
  at request time and immediately before execution.
- Blocked owner, verified, inactive, and expired memberships.
- Invalidated stale requests and made successful execution replay-safe so an
  operation cannot generate a second OTP.
- Reused the authentication OTP service, which invalidates prior open codes and
  records delivery failures without exposing OTP values.
- Added delivery evidence containing only timestamp, resend count, membership,
  user, and delivery-request status.
- Added an eligibility-driven customer UI with an explicit preparation and
  ticket/reason confirmation step.

Verification:

- Four focused resend integration tests passed.
- Full platform operations suite: 80 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- The resend workflow passed in Chromium, Firefox, and WebKit.
- Migration `0012` applied locally.

## Remaining Phase 4 Work

## Increment 9: Customer Ownership Transfer

Completed on 2026-09-07.

- Added a critical-risk ownership transfer operation available only to platform
  security administrators.
- Required a verified, active, unexpired target membership and rejected the
  current owner or memberships belonging to another customer.
- Bound approval to the customer version and execution to both the approved
  customer version and target membership version.
- Required independent maker-checker approval and prevented requester
  self-approval.
- Atomically demoted all previous owner memberships, promoted exactly one new
  owner, removed ownership expiry, and updated the customer owner foreign key.
- Added stale-customer, stale-membership, eligibility, and idempotent replay
  handling.
- Added a security-only UI selector that lists only eligible memberships and
  clearly presents the operation as critical.

Verification:

- Five focused ownership transfer integration tests passed.
- Full platform operations suite: 85 tests passed.
- Angular typecheck and production build passed; seven focused service tests
  passed.
- The ownership request workflow passed in Chromium, Firefox, and WebKit.
- Migration `0013` applied locally.

## Remaining Phase 4 Work

## Increment 10: Operation Lifecycle Controls

Completed on 2026-09-07.

- Added permission-controlled cancellation for draft, validated, pending,
  approved, and failed operations, with immutable actor, timestamp, and reason
  evidence returned by the operation API.
- Prevented cancellation after execution starts or after a terminal success or
  rejection, while keeping repeated cancellation requests replay-safe.
- Added a configurable approval lifetime and fail-closed execution behavior for
  expired approvals so stale authorization cannot mutate tenant data.
- Restricted retries to failed onboarding operations whose provisioning job is
  also failed; unrelated and nonfailed operations cannot use the retry route.
- Added cancellation controls and evidence to the operation detail UI, including
  permission, mutation-toggle, status, and minimum-reason safeguards.
- Improved operation execution errors to surface approval-expiry and retry
  validation details returned by the API.

Verification:

- Five focused lifecycle integration tests passed.
- Full platform operations suite: 90 tests passed.
- Migration `0014` applied locally; migration drift and Django checks passed.
- Angular typecheck and development build passed; seven focused service tests
  passed.
- The cancellation workflow passed in Chromium, Firefox, and WebKit.

## Remaining Phase 4 Work

- Apply maker-checker to remaining high-risk operations.
- Add scheduled expiry processing and operational alerting so expired approvals
  are visible before an execution attempt.

## Increment 11: Controlled Onboarding Repair

Completed on 2026-09-07.

- Added a read-only repair preview for failed onboarding operations that reports
  the failed stage, attempt count, rollback verification, recovery strategy,
  blockers, and identifier collisions.
- Detects owner-email, external-customer-reference, and entity-code collisions
  before permitting another provisioning attempt.
- Added a separately permissioned repair execution endpoint that delegates to
  the existing atomic onboarding service; it does not introduce direct or
  generic tenant-table repair writes.
- Tightened the legacy retry endpoint to require both operation execution and
  repair execution permissions.
- Assigned repair preview and execution permissions to onboarding operators and
  platform security administrators through migration `0015`.
- Added an operator UI that requires an assessment before controlled repair and
  presents manual-review blockers without exposing an execution action.

Verification:

- Five focused repair integration tests passed, including permission denial and
  identifier-collision handling.
- Full platform operations suite: 95 tests passed.
- Migration `0015` applied locally; migration drift and Django checks passed.
- Angular typecheck and development build passed; seven focused service tests
  passed.
- Eligible repair and blocked manual-review scenarios passed in Chromium,
  Firefox, and WebKit.

## Remaining Phase 4 Work

- Apply maker-checker to remaining high-risk operations.
- Design tenant consistency repair operations separately; this increment only
  recovers fully rolled-back onboarding transactions.

## Increment 12: Approval Expiry And Operational Alerts

Completed on 2026-09-07.

- Added an idempotent approval-expiry sweep using the configurable
  `PLATFORM_OPS_APPROVAL_TTL_HOURS` execution window.
- Added `expire_platform_approvals`, including `--dry-run`, for invocation by the
  deployment scheduler without introducing an unsupported background-job stack.
- Added immutable system-attributed audit events for scheduled expiry and
  human-attributed events when expiry is discovered during execution.
- Extended the platform dashboard with pending approval, expiring-soon, expired
  approval, and failed-onboarding counts.
- Added a responsive attention queue to the platform overview and corrected its
  narrow-viewport sizing and navigation wrapping.

Deployment scheduler:

```bash
python manage.py expire_platform_approvals
```

Run it at least hourly. Validate production scope before activation with:

```bash
python manage.py expire_platform_approvals --dry-run
```

Verification:

- Four focused expiry/command tests and a dashboard-count integration test
  passed.
- Full platform operations suite: 100 tests passed.
- Migration `0016` applied locally; migration drift and Django checks passed.
- Angular typecheck and development build passed; seven focused service tests
  passed.
- Desktop and compact attention-queue checks passed in Chromium, Firefox, and
  WebKit.

## Remaining Phase 4 Work

- Configure and observe the expiry command in staging before production launch.
- Design tenant consistency repair operations separately; this increment only
  recovers fully rolled-back onboarding transactions.

## Increment 13: Critical Dual Approval

Completed on 2026-09-07.

- Audited all operation types against risk classification, initial status,
  approval policy, optimistic target version, and execution guard.
- Confirmed customer status, financial year, GST registration, subscription,
  and membership changes remain high risk with one independent maker-checker
  approval.
- Upgraded immutable approval records from one-to-one to one-to-many and added a
  database uniqueness constraint preventing the same approver from deciding an
  operation twice.
- Critical ownership transfers now require two distinct approvers, neither of
  whom may be the requester. The first approval leaves the operation pending and
  execution independently verifies quorum before changing ownership.
- Any rejection remains terminal, including rejection after the first critical
  approval.
- Approval expiry now checks every approval in the completed quorum, and stale
  target checks continue to bind all decisions to the same reviewed version.
- Added approval quorum and complete decision evidence to the operation detail
  API and UI.

Verification:

- Focused approval matrix: 38 tests passed across critical ownership, customer
  status, financial year, GST, subscription, membership, and expiry workflows.
- Full platform operations suite: 101 tests passed.
- Migration `0017` applied locally; migration drift and Django checks passed.
- Angular typecheck and development build passed; seven focused service tests
  passed.
- Critical one-of-two approval presentation and blocked execution passed in
  Chromium, Firefox, and WebKit.

## Remaining Phase 4 Work

- Configure and observe the expiry command in staging before production launch.
- Design tenant consistency repair operations separately; onboarding repair is
  intentionally limited to fully rolled-back provisioning transactions.

## Increment 14: Entity Numbering Consistency Repair

Completed on 2026-09-07.

- Added a read-only, separately permissioned assessment of default document
  numbering across active financial years, entity-wide scope, and every active
  branch scope.
- Added a typed high-risk repair request containing the exact missing-series
  snapshot, entity version, reason, ticket, correlation ID, and idempotency key.
- Repair execution requires independent approval, locks and revalidates the
  entity version, and creates only missing default series. Existing series,
  formats, and counters are preserved.
- Healthy entities and entities without an active financial year cannot create
  a repair operation. Successful execution is replay-safe.
- Added the assessment and request workflow to entity detail without exposing
  generic tenant-table mutation controls.

Verification:

- Five focused backend tests passed for exact preview, counter preservation,
  stale approval, healthy-state blocking, idempotent replay, and strict
  approved-snapshot scope.
- Full platform operations suite: 106 tests passed.
- Migration `0018` generated with no further migration drift; Django checks
  passed.
- Angular typecheck, development build, and seven service tests passed.
- Assessment, request creation, and compact-layout overflow checks passed in
  Chromium, Firefox, and WebKit.

## Remaining Phase 4 Work

- Configure and observe the expiry command in staging before production launch.
- Add further tenant consistency repairs one bounded domain at a time; financial
  masters, RBAC, catalog, assets, and choice overrides remain intentionally out
  of scope for this numbering operation.

## Increment 15: Required Posting Mapping Repair

Completed on 2026-09-07.

- Added a read-only assessment of mandatory static posting roles against the
  configured template entity and the target entity's existing ledger codes.
- Missing roles are repairable only when every role resolves to a specific
  existing target ledger. Any unresolved role blocks the entire request.
- Added a typed high-risk operation with reason, ticket, idempotency,
  optimistic entity version, immutable target account/ledger IDs, and
  independent approval.
- Execution creates only approved missing mappings, skips mappings restored in
  the meantime, validates target ownership and ledger code again, invalidates
  the mapping cache, and is replay-safe.
- The operation does not create, rename, reclassify, or otherwise mutate
  accounts and ledgers, and it never replaces an active mapping.
- Added an independent posting-mapping control to entity detail alongside the
  numbering control.

Verification:

- Four focused backend tests passed for exact resolution, unresolved blocking,
  stale approval, target preservation, and idempotent replay.
- Full platform operations suite: 110 tests passed.
- Migration `0019` generated with no further migration drift; Django checks
  passed.
- Angular typecheck, development build, and seven service tests passed.
- Combined numbering and posting-mapping assessment/request workflow passed in
  Chromium, Firefox, and WebKit, including compact-layout overflow checks.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Treat broader chart-of-accounts reconciliation as a separate, higher-risk
  design; the existing reconciler remains intentionally unavailable from the
  platform UI.
- Design similarly bounded consistency operations for RBAC, catalog, assets,
  and purchase/sales choice overrides.

## Increment 16: Baseline RBAC Role Repair

Completed on 2026-09-07.

- Added a read-only assessment for the nine entity baseline role templates.
- Missing roles are snapshotted with exact role metadata and active permission
  IDs. Inactive roles with the same code and templates without permissions
  block repair for manual review.
- Added a typed high-risk operation with independent approval, idempotency,
  optimistic entity versioning, and immutable permission scope.
- Execution creates only approved missing roles and permission links. It does
  not update existing roles, include permissions introduced after approval, or
  create user assignments.
- Custom roles, allow/deny choices, data policies, assignments, and entity
  super-admin access are deliberately outside this operation.
- Added an independent baseline-role consistency control to entity detail with
  explicit unassigned-role wording.

Verification:

- Five focused backend tests passed for exact preview, custom-role and
  assignment preservation, inactive-role blocking, stale approval, permission
  deactivation, and replay safety.
- Full platform operations suite: 115 tests passed.
- Migration `0020` generated with no further migration drift; Django checks
  passed.
- Angular typecheck, development build, and seven service tests passed.
- Combined numbering, posting, and RBAC consistency workflow passed in
  Chromium, Firefox, and WebKit, including compact-layout and independent-form
  checks.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Design super-admin or assignment recovery as a separate critical operation
  with stronger identity evidence and dual approval.
- Continue with bounded catalog, asset, and purchase/sales choice consistency
  operations.

## Increment 17: Catalog Defaults Consistency Repair

Completed on 2026-09-07.

- Added a read-only assessment for the seeded category, unit-of-measure, and
  HSN/SAC catalog defaults required by tenant setup.
- Added a typed high-risk operation carrying the exact approved missing-record
  snapshot, entity version, reason, ticket, correlation ID, and idempotency
  key.
- Execution creates only approved records that remain missing. Existing active
  catalog rows, tax settings, tenant-specific categories, and custom HSN/SAC
  records are preserved unchanged.
- Inactive rows using a required seed code and unresolved parent references
  block the entire repair for manual review. A UQC already owned by another
  UOM is not reassigned; the missing seeded UOM is safely created without
  taking that tenant value.
- Added an independent catalog assessment and repair-request control to entity
  detail. Execution still requires approval by another authorized operator.

Verification:

- Four focused backend tests passed for custom-data preservation, exact
  missing-only creation, inactive-code blocking, stale approval, UQC collision
  handling, and idempotent replay.
- Full platform operations suite: 119 tests passed.
- Migration `0021` applied with no further migration drift; Django checks
  passed.
- Angular development build and seven service tests passed.
- Combined numbering, posting, RBAC, and catalog consistency workflow passed
  in Chromium, Firefox, and WebKit, including compact-layout overflow and
  independent-form checks.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Continue with bounded asset and purchase/sales choice consistency operations.
- Keep catalog updates, tax-rate changes, deactivation recovery, and duplicate
  consolidation outside this missing-default repair and under manual review.

## Increment 18: Asset Defaults Consistency Repair

Completed on 2026-09-07.

- Added a read-only assessment for missing entity-level asset settings and the
  twenty seeded global asset category codes.
- Added a typed high-risk operation containing the exact category fields and
  ledger IDs approved for creation, protected by entity versioning,
  idempotency, and independent approval.
- Execution creates only approved defaults that remain missing. Existing asset
  settings, customized categories, ledger mappings, fixed assets, lifecycle
  events, depreciation runs, and postings are preserved unchanged.
- Inactive category codes, category-name collisions, duplicate global settings,
  and unresolved or deactivated ledgers block repair for manual review.
- Added an independent asset-default assessment and request control to entity
  detail with explicit operational boundaries.

Verification:

- Four focused backend tests passed for missing-only assessment, customized
  category preservation, exact creation, inactive-code blocking, stale
  approval, and idempotent replay.
- Full platform operations suite: 123 tests passed.
- Migration `0022` generated with no further migration drift; Django checks
  passed.
- Angular development build and seven service tests passed.
- Combined numbering, posting, RBAC, catalog, and asset consistency workflow
  passed in Chromium, Firefox, and WebKit, including compact-layout overflow
  and independent-form checks.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Continue with bounded purchase and sales choice consistency operations.
- Keep asset ledger creation, category updates, branch overrides, and all
  transactional asset/depreciation recovery outside this defaults repair.

## Increment 19: Purchase And Sales Settings Repair

Completed on 2026-09-07.

- Added a read-only assessment for missing entity-level purchase and sales
  settings.
- Added a typed high-risk operation with independent approval, idempotency,
  optimistic entity versioning, and an exact sales financial-year snapshot.
- Missing sales settings are repairable only when exactly one active financial
  year exists. Ambiguous or absent active-year scope blocks the request.
- Execution creates only approved missing rows using model defaults. Existing
  entity or branch settings and all tenant policy values remain unchanged.
- Duplicate entity-level settings block repair for manual consolidation.
- Added an independent transaction-settings assessment and request control to
  entity detail.

Verification:

- Four focused backend tests passed for exact creation, custom purchase-setting
  preservation, active-year ambiguity, stale approval, and idempotent replay.
- Full platform operations suite: 127 tests passed.
- Migration `0023` generated with no further migration drift; Django checks
  passed.
- Angular development build and seven service tests passed.
- Combined consistency workflow passed in Chromium, Firefox, and WebKit,
  including compact-layout overflow and independent-form checks.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Assess purchase and sales choice-override completeness separately; do not
  infer enabled states or labels from absence without an explicit policy.
- Keep numbering series, branch overrides, lock periods, transactional records,
  and existing tenant policy values outside this settings repair.

## Increment 20: Choice Override Audit

Completed on 2026-09-07.

- Added a read-only entity audit for purchase and sales choice overrides across
  global and branch scopes.
- Reports explicit global coverage, inherited/missing global choices, disabled
  choices, relabeled choices, unknown keys, and duplicate scoped rows.
- Missing global overrides are informational because the application inherits
  system choices. Disabled and relabeled rows are reported as intentional
  tenant policy rather than defects.
- Unknown and duplicate rows are surfaced for operator review, with no
  automatic update, deletion, or repair endpoint.
- Added an audited platform endpoint and entity-detail panel that deliberately
  exposes no mutation action.

Verification:

- Five focused purchase/sales settings tests passed, including a zero-write
  choice audit with disabled, relabeled, unknown, and duplicate rows.
- Full platform operations suite: 128 tests passed.
- No model migration was required and migration drift remains clean.
- Angular development build and seven service tests passed.
- The combined platform consistency workflow passed in Chromium, Firefox, and
  WebKit, including compact overflow and absence of choice-audit mutation
  controls.

## Remaining Phase 4 Work

- Configure and observe the approval-expiry command in staging.
- Define an explicit tenant policy before adding any choice-override mutation
  operation; the audit alone does not classify inherited choices as broken.
- Complete production-like concurrency, operational alerting, and final
  staging permission-matrix certification.

## Increment 21: Approval Expiry Deployment Hardening

Completed locally on 2026-09-07; staging observation remains required.

- Added stable single-line JSON output to `expire_platform_approvals` while
  preserving its existing human-readable output and dry-run behavior.
- Added an hourly persistent systemd timer and hardened oneshot service. A
  missed trigger runs after host recovery, and systemd prevents overlapping
  execution of the same oneshot unit.
- Updated both EC2 backend deployment paths to install, enable, immediately
  exercise, and display the timer status.
- Added a staging acceptance runbook covering dry-run comparison, journal and
  timer evidence, idempotency, controlled dependency-failure recovery,
  monitoring expectations, and rollback.

Verification:

- Six focused approval-expiry tests passed, including JSON output and static
  scheduler deployment contracts.
- Full platform operations suite: 130 tests passed.
- A real local dry-run returned valid JSON with zero matched operations.
- Both staging deployment scripts passed `bash -n`; Django checks, migration
  drift, and diff checks passed.
- `systemd-analyze verify` is unavailable on the macOS development host, so
  unit loading and journal observation remain part of staging acceptance.

## Remaining Phase 4 Work

- Deploy and capture successful timer/service/journal evidence on staging.
- Connect the failed-unit and missing-success signals to the staging alerting
  destination and assign an incident owner.
- Complete production-like concurrency and the final staging permission matrix.
