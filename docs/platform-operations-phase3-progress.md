# Platform Operations Phase 3 Progress

## Increment 1: Validation And Preview

Completed on 2026-09-07.

- Added platform-only onboarding input validation and preview endpoints.
- Reused the authoritative entity onboarding serializer for nested entity, FY,
  branch, bank, policy, ownership, compliance, and seed-option rules.
- Added structured duplicate checks for owner email, customer contact email and
  phone, legal name, external customer ID, entity legal name and code, and GSTIN.
- Classified duplicate findings as blocking errors or operator warnings.
- Masked email, phone, and GSTIN match evidence in API responses.
- Added redacted success and failure audit events.
- Added a guided Angular validation workspace with explicit review states.
- Kept the workflow non-mutating while operation requests and recovery controls
  are still under construction.

Verification:

- Django platform suite: 25 tests passed.
- Angular platform guard/service suite: 6 tests passed.
- Angular production build: passed.

## Remaining Phase 3 Work

## Increment 2: Durable Provisioning Requests

Completed on 2026-09-07.

- Added durable operation and provisioning-job models with correlation IDs,
  statuses, payload hashes, validation snapshots, and stage progress.
- Enforced per-operator idempotency keys and rejected key reuse with changed data.
- Added request creation, replay, operation list, and operation detail APIs.
- Gated request creation behind the global platform mutation flag and onboarding
  permissions while keeping execution unavailable.
- Added audit evidence for disabled, invalid, blocked, created, replayed, and
  failed requests.
- Prohibited compliance secrets from operation snapshots and expanded global
  platform redaction for client secrets and GST passwords.
- Added request creation to the Angular validation workspace, reusing the same
  idempotency key on uncertain retries.

Verification:

- Django platform suite: 32 tests passed.
- Angular platform guard/service suite: 7 tests passed.
- Migration `0004` applied with no migration drift.
- Django application checks and Angular production build passed.

## Remaining Phase 3 Work

## Increment 3: Transactional Execution And Recovery

Completed on 2026-09-07.

- Added permission-gated execute and retry endpoints behind the platform mutation
  kill switch.
- Wrapped owner, customer, subscription, entity, defaults, membership, and
  verification scheduling in one database transaction.
- Locked operation and provisioning rows independently to prevent concurrent
  execution without invalid outer-join locking.
- Persisted canonical ISO/primary-key snapshots independent of API display date
  formats.
- Rolled back all tenant records on a forced entity-stage failure while retaining
  sanitized stage diagnostics and correlation evidence.
- Verified retry after rollback succeeds exactly once and increments the attempt
  counter without duplicate tenant records.
- Scheduled OTP generation after transaction commit to prevent invitation side
  effects for rolled-back tenants.
- Added an Angular operations queue and detail workspace with stage status,
  failure evidence, execute, and retry controls.

Verification:

- Django platform suite: 35 tests passed, including real end-to-end provisioning.
- Angular platform guard/service suite: 8 tests passed.
- Django schema and application checks passed with no migration drift.
- Angular production build passed.

## Remaining Phase 3 Work

## Increment 4: Permutation And Browser Certification

Completed on 2026-09-07.

- Verified real registered-GST onboarding with a head office and warehouse.
- Verified unregistered/non-GST onboarding with no false GST requirement.
- Verified subscription entity-limit failure rolls back the complete tenant.
- Replaced the invalid UI-only `not_applicable` GST status with the domain's
  supported unregistered/non-GST representation.
- Added a password-setup invitation using the existing reset-OTP flow.
- Marked mailbox ownership verified after successful password-reset OTP proof.
- Verified a platform-created owner can choose a password and authenticate.
- Added Playwright coverage for onboarding validation, durable request creation,
  operation failure evidence, and retry success.
- Passed browser workflows in Chromium, Firefox, and WebKit.

Final Phase 3 verification:

- Django platform suite: 37 tests passed.
- Authentication password-reset verification regression: passed.
- Playwright: 9 runs passed across browser setup and the three browser engines.
- Angular focused tests: 8 passed; production build passed.
- No migration drift or Django application check failures.

Phase 3 is complete. Broader accessibility, load, and security certification
remains part of the Phase 7 production launch gate.
