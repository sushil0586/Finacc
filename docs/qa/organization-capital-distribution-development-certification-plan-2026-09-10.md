# Organization Capital, Appropriation, And Distribution Development Plan

Last updated: 12 September 2026

## Purpose

Deliver a configurable, auditable capital, appropriation, and distribution framework
that selects the correct accounting strategy for the entity's verified constitution.
The first delivery wave covers partnership firms, LLPs, and proprietorships. Later
waves add company/OPC equity and dividends, HUF allocation, trust/society/NGO fund
accounting, cooperative distributions, and government/PSU capital and grant rules.

The shared framework manages effective-dated governing terms, calculation snapshots,
periodic runs, approval, posting, reversal, and financial-report reconciliation.
Formation-specific engines own the legal and accounting calculations; one formation
must never silently inherit another formation's rules.

This is a living document. After every phase, update its status, execution date,
test evidence, defects, residual risks, and confidence assessment. A phase is not
complete because its screen renders; its calculations, persistence, accounting,
permissions, recovery, and reports must satisfy the stated exit criteria.

## Product Outcome

An authorized finance user should be able to:

1. Maintain owners, partners, members, shareholders, trustees, or other applicable
   stakeholders and dated governing terms without rewriting history.
2. Configure only the policies supported by the selected constitution, including
   allocation, remuneration, interest, reserves, funds, dividends, rounding,
   cadence, approval, and posting behavior.
3. Preview the exact calculation and source balances before saving or posting.
4. Submit a frozen run for approval and post balanced stakeholder/fund journals.
5. Reverse a posted run without deleting its audit history.
6. Reconcile the run to subledgers, trial balance, Profit & Loss, Balance Sheet,
   fund/equity statements, and year-end opening generation.

## Scope And Boundaries

### First release scope

- Partnership and LLP entities with one or more effective-dated partners.
- Proprietorship entities with one effective-dated proprietor.
- Partner capital and current accounts.
- Fixed, periodic, and formula-driven remuneration.
- Interest on capital using opening, monthly weighted, or daily weighted balance.
- Interest on drawings from actual mapped drawing transactions.
- Mid-period and mid-year ratio changes.
- Monthly, quarterly, custom-period, and annual appropriation runs.
- Draft, calculate, submit, approve, post, unpost/reverse, and supersede lifecycle.
- Book presentation and a separate tax-adjustment working view.
- Entity, financial-year, branch, and permission isolation.

### Planned formation engines

| Formation | Accounting strategy | Delivery wave |
| --- | --- | --- |
| Proprietorship | Owner capital/current account, drawings, optional interest, retained result | Wave 1 |
| Partnership firm | Partner remuneration, interest, drawings, and profit/loss appropriation | Wave 1 |
| LLP | Contribution/current accounts, remuneration, interest, and profit/loss appropriation | Wave 1 |
| Private/public company | Share capital, securities premium, reserves, retained earnings, and dividends | Wave 2 |
| One Person Company | Company equity/dividend treatment with a single eligible shareholder | Wave 2 |
| HUF | Karta/member capital and allocation under an HUF-specific policy | Wave 3 |
| Trust, society, or NGO | Corpus, restricted/unrestricted funds, grants, and accumulated surplus | Wave 3 |
| Section 8 company | Company accounting plus non-distribution and restricted-fund safeguards | Wave 3 |
| Cooperative | Member capital, statutory reserves, patronage, and dividend distribution | Wave 4 |
| Government entity or PSU | Government equity, grants, reserves, and approved surplus transfer | Wave 4 |

### Constitution authority and safe dispatch

The engine is selected from verified entity constitution and registration evidence,
not merely the number or type of ownership rows. LLPIN, CIN, constitution master,
registration category, and approved governing profile participate in resolution.

```text
CapitalDistributionEngine
+-- ProprietorCapitalEngine
+-- PartnershipAppropriationEngine
+-- LLPAppropriationEngine
+-- CompanyEquityDividendEngine
+-- HUFCapitalEngine
+-- TrustFundAllocationEngine
+-- CooperativeDistributionEngine
+-- GovernmentCapitalTransferEngine
```

Resolution returns the selected strategy, evidence, policy schema version, readiness
issues, and supported operations. Ambiguous, contradictory, incomplete, or currently
unsupported formations return `distribution_setup_not_configured` and cannot calculate
or post. There is no generic partnership fallback.

### Explicitly out of scope for the first release

- Income-tax return filing or legal interpretation of partnership deeds.
- Automatic amendment of signed partnership agreements.
- Partner banking or payment settlement.
- Company, HUF, trust, NGO, cooperative, and government distribution posting until
  their planned formation engine reaches its own certification gate.
- Trust beneficiary payments; Wave 3 initially covers fund accounting and approved
  allocations, not beneficiary settlement.
- Foreign-currency partner capital unless the entity ledger supports it end to end.

Later-wave formations are architecture scope but not launch-certified first-release
features. Menus may show readiness status, but calculation/posting actions remain
blocked until that formation engine is enabled and certified.

## Existing Foundation

- `EntityOwnershipV2` already stores proprietor, partner, director, shareholder,
  trustee, and other stakeholder identity plus percentage, contribution, effective
  dates, account preference, and agreement reference.
- `YearOpeningPostingAdapter` already validates partnership ownership totals,
  creates partner-specific opening targets, and allocates profit/loss by ratio.
- `PostingService` already provides atomic batches, balanced journal validation,
  revisions, financial-year locks, and source traceability.
- Financial controls already expose posting setup and year-end generation.

The new module must reuse these services and models where they remain authoritative.
It must not create a second identity master or write journal tables directly. A
formation-profile service will resolve which existing registration and ownership
records are authoritative for each strategy.

## Non-Configurable Accounting Invariants

The following rules are system controls and cannot be disabled by configuration:

- Every formation satisfies its own conservation rule: partner/shareholder ratios
  reconcile where applicable; trust/government fund allocations reconcile to their
  approved source amount without inventing ownership percentages.
- Strategy resolution is deterministic and supported by verified constitution data.
- A run cannot mix policies or journal semantics from different formation engines.
- Effective intervals for an agreement cannot overlap.
- Every calculated amount records its inputs, rule version, and rounding result.
- A posted run has exactly one active posting batch for its scope and source ID.
- Posted debit and credit totals are equal.
- Retry cannot produce duplicate runs, lines, or journals.
- Posted calculations and approved terms are immutable.
- Corrections use supersession or reversal, never history deletion.
- Closed or locked periods reject posting and reversal according to lock policy.
- Cross-entity and unauthorized direct-object access is denied by the API.
- Report totals are sourced from posted journals, not editable calculation rows.

## Configurable Policy Catalogue

Configuration is effective-dated and versioned. Defaults may be supplied by the
system, but every saved run stores a snapshot so later policy changes cannot alter
historical results.

| Policy | Supported configuration |
| --- | --- |
| Formation strategy | Derived from verified constitution; operator cannot freely override |
| Policy schema | Strategy-specific, versioned schema and validation rules |
| Run cadence | Monthly, quarterly, annual, custom period |
| Profit source | Posted actuals, approved adjusted actuals |
| Ratio application | Actual profit by effective segment; day-weighted fallback only with explicit approval |
| Remuneration | None, fixed monthly, fixed annual, per-period, percentage/formula, capped amount |
| Remuneration proration | Calendar days, active days, full period, no proration |
| Capital-interest basis | Opening, monthly weighted, daily weighted |
| Capital-interest rate | Partner-specific or agreement default; effective-dated |
| Capital transaction inclusion | Introductions, withdrawals, transfers, selected mapped transaction types |
| Drawing-interest basis | Transaction-date daily balance, monthly product, fixed-period convention |
| Drawing-interest rate | Partner-specific or agreement default; effective-dated |
| Day-count convention | Actual/365, Actual/366, Actual/Actual, 30/360 where approved |
| Residual allocation | Effective profit ratio; separate loss ratio when agreement permits |
| Rounding | Currency precision, half-up default, remainder partner selection |
| Destination account | Current account default; capital account only when policy explicitly permits |
| Negative current balance | Allow, warn, or block |
| Run overlap | Block by default; adjustment run allowed with reference to original |
| Approval | None, maker-checker, amount threshold, mandatory year-end approval |
| Posting timing | On approval, explicit post action, scheduled post after approval |
| Reversal | Same-period only, controlled later-period reversal, approval requirement |
| Tax working | Book-only, book-versus-allowable comparison, manual tax adjustment |
| Evidence | Agreement reference required, attachment required, optional by entity policy |

Later formation engines add only their relevant policy families:

| Formation family | Additional configurable policies |
| --- | --- |
| Proprietorship | Owner drawing treatment, interest, capital/current destination, retained result |
| Company/OPC | Share classes, declared dividend, record/payment dates, reserve transfer, withholding mapping |
| HUF | Karta/member roles, approved allocation basis, capital/current treatment |
| Trust/society/NGO | Corpus restrictions, donor restrictions, fund transfer rules, grant recognition, surplus carry-forward |
| Section 8 company | Restricted-fund treatment and hard prohibition of member profit distribution |
| Cooperative | Statutory reserve sequence, patronage basis, member dividend policy, caps and approvals |
| Government/PSU | Grant class, government equity, reserve/surplus transfer authority, budget reference |

Rates and statutory limits must be policy data with jurisdiction, effective dates,
source reference, and override controls. They must not be hard-coded into calculation
methods. Overrides require a reason and appear in the audit report.

## Target Information Architecture

```text
Finance
+-- Capital & Distributions
    +-- Setup
    |   +-- Stakeholders & Funds
    |   +-- Terms & Policies
    +-- Runs
    +-- Reports
```

Labels are strategy-aware. A partnership sees Partners, Terms & Ratios, and
Appropriation Runs. A company sees Shareholders & Equity, Dividend Policies, and
Distribution Runs. A trust sees Funds & Trustees, Fund Policies, and Allocation
Runs. This retains one predictable navigation structure without exposing irrelevant
partner controls to other formations.

## Domain Model

### Existing models retained

`EntityOwnershipV2` remains the stakeholder identity source where applicable.
Existing constitution, tax, registration, and compliance profiles remain evidence
for strategy resolution. Historical records must not be overwritten when an owner,
partner, shareholder, trustee, or member changes status.

### Shared new models

#### `EntityFormationProfile`

- Entity, resolved formation, source evidence, confidence/readiness, and status.
- Active strategy code and policy-schema version.
- Verification, approval, effective dates, and contradiction details.
- One active profile per entity/date; changes are versioned, never overwritten.

#### `DistributionPolicyVersion`

- Entity, formation strategy, financial-year applicability, version number, status.
- Effective-from and effective-to dates.
- Governing-document reference, attachment reference, notes.
- Default calculation policies and day-count convention.
- Created, submitted, approved, superseded, and cancelled audit fields.
- Strategy-specific configuration stored in typed detail models or a validated,
  schema-versioned configuration payload; arbitrary unvalidated JSON is prohibited.

#### `DistributionPolicyStakeholder`

- Policy version and applicable ownership/member/trustee/fund reference.
- Profit percentage and optional loss percentage.
- Remuneration method, amount/formula, cap, and proration method.
- Interest-on-capital applicability, rate, and balance basis.
- Interest-on-drawings applicability, rate, and balance basis.
- Destination capital/current static-account role.
- Remainder-priority and active flags.
- Fields irrelevant to the selected strategy must be absent or rejected rather than
  tolerated as nullable noise.

#### `CapitalDistributionRun`

- Entity, formation strategy, financial year, optional branch scope, period,
  cadence, sequence, and run type.
- Formation profile and policy versions used.
- Status and optimistic version.
- Profit source, book profit, adjustments, distributable result.
- Calculation hash, idempotency key, posting batch, and reversal reference.
- Maker, checker, poster, timestamps, and reason fields.

#### `CapitalDistributionSegment`

- Run, segment dates, agreement version, source profit, and allocation basis.
- Records every boundary introduced by a ratio or rate change.

#### `CapitalDistributionLine`

- Run, segment, stakeholder/fund/equity target, component type, basis, rate, days,
  amount, and side.
- Component types include remuneration, capital interest, drawing interest,
  residual profit, residual loss, tax adjustment, and rounding.
- Stores source ledger IDs and a structured calculation explanation.

#### `DistributionBalanceSnapshot`

- Run, stakeholder/fund/equity target, ledger, cutoff, opening balance, dated
  movements, and closing basis.
- Immutable after submission.

#### `CapitalDistributionAuditEvent`

- Run, actor, action, before/after state, correlation ID, reason, and timestamp.

### Strategy-specific detail models

- `PartnerAppropriationPolicyDetail` for partnership and LLP rules.
- `ProprietorCapitalPolicyDetail` for proprietor rules.
- `CompanyDistributionPolicyDetail` and share-class lines.
- `HUFAllocationPolicyDetail` and member lines.
- `FundAllocationPolicyDetail` for trust/society/NGO/Section 8 funds.
- `CooperativeDistributionPolicyDetail` and member/patronage lines.
- `GovernmentCapitalPolicyDetail` for grant/equity/reserve authority.

Shared workflow models hold lifecycle and audit information. Strategy detail models
hold accounting meaning, preventing one oversized table full of unrelated nullable
fields.

### Required database controls

- Unique policy version per entity, strategy, and version number.
- Exclusion/service validation preventing overlapping approved policy periods for
  the same strategy and scope.
- Unique active run by entity, financial year, period, cadence, and run type.
- Unique run/segment/target/component line identity.
- Database/service guard that run strategy equals the approved formation strategy.
- Check constraints for non-negative rates, valid date ranges, and supported states.
- Indexed entity/FY/period/status and partner/date lookup paths.

## Calculation Contract

### Shared strategy interface

Every formation engine implements the same orchestration contract:

```text
resolve_readiness(context)
validate_policy(policy, effective_on)
build_segments(period, policy_versions)
collect_source_balances(segment)
calculate(snapshot, policy)
build_posting_preview(calculation)
build_report_projection(calculation)
reconcile(calculation, journals, reports)
```

The orchestration service owns lifecycle, snapshots, approvals, idempotency, and
audit. The selected engine owns formation-specific validation, formulas, posting
semantics, and report classification.

### Partnership and LLP calculation

### Segment construction

The engine splits a run at every relevant boundary:

- Agreement or ratio effective date.
- Partner joining or retirement date.
- Remuneration or interest-rate effective date.
- Financial-year boundary and requested run boundary.

For each segment, applicable shares must total 100.00%.

### Calculation order

1. Read posted operating result for each segment.
2. Apply approved manual book adjustments, if permitted.
3. Calculate remuneration by partner.
4. Calculate interest on capital from frozen ledger movements.
5. Calculate interest on drawings from frozen drawing movements.
6. Determine residual distributable profit or loss.
7. Allocate the residual using the segment's effective ratio.
8. Apply deterministic currency rounding and final remainder.
9. Reconcile all segment and run totals before allowing submission.

### Mid-year ratio changes

Actual segment profit is the default. A day-weighted annual fallback is allowed
only when the entity enables it and an approver accepts a visible warning. The run
must disclose which basis was used; the two methods must never be mixed silently.

### Capital and drawings basis

- Capital calculations consume posted movements from explicitly mapped partner
  capital/current ledgers.
- Drawings calculations consume posted drawing transactions or mapped debit
  movements, according to policy.
- Draft, reversed, cross-entity, and out-of-period transactions are excluded.
- Backdated transactions after calculation mark the run stale and require
  recalculation before submission or posting.

### Other formation calculation contracts

- Proprietorship transfers the retained result to the owner capital/current account
  according to policy and accounts for drawings without partner-ratio logic.
- Company/OPC validates share classes, declared amounts, eligible holders, record
  date, reserve availability, approvals, and withholding before dividend posting.
- HUF uses only the approved HUF allocation basis and member/Karta effective dates.
- Trust/society/NGO/Section 8 engines allocate between corpus, restricted,
  unrestricted, designated, and grant funds without treating beneficiaries or
  members as equity owners.
- Cooperative engines apply the configured statutory sequence before patronage or
  member dividend distribution.
- Government/PSU engines require an approved authority/budget reference and classify
  movements as grant, equity, reserve, or surplus transfer.

## Accounting And Reporting Contract

Partnership and LLP default book postings use partner current accounts:

```text
Remuneration / interest on capital
Profit & Loss Appropriation       Dr
    Partner Current Account           Cr

Interest on drawings
Partner Current Account           Dr
    Profit & Loss Appropriation        Cr

Residual profit allocation
Profit & Loss Appropriation       Dr
    Partner Current Accounts           Cr

Residual loss allocation
Partner Current Accounts          Dr
    Profit & Loss Appropriation        Cr
```

Required static-account roles include Profit & Loss Appropriation and one
partner-specific capital/current role per ownership row. Posting Setup must preview
missing mappings and block posting until they are resolved.

### Profit & Loss presentation

- Operating result before partner appropriation.
- Remuneration, capital interest, drawing interest, and residual distribution.
- Profit after appropriation and undistributed balance.
- Separate tax-working columns for book, allowable, disallowed, and adjusted values.

### Balance Sheet presentation

- Each partner shown independently under Partners' Funds.
- Capital and current accounts shown separately.
- Opening, introductions, remuneration, interest, allocation, drawings, loss, and
  closing balances available in drilldown.
- Allocation changes the composition of equity, not total equity.

### Mandatory reconciliations

```text
Profit available for distribution
= partner allocations + undistributed balance

Partner closing balance
= opening + introductions + remuneration + capital interest + profit share
 - drawings - drawing interest - loss share +/- transfers

Appropriation run total
= posted journal total
= partner ledger movement total
```

Year-end opening generation must consume already-posted closing partner balances
without allocating the same profit a second time.

### Formation-specific financial-statement effects

| Formation | Profit/result presentation | Balance Sheet presentation |
| --- | --- | --- |
| Proprietorship | Operating result and owner transfer | Owner capital/current account |
| Partnership/LLP | Result before appropriation and appropriation statement | Partner-wise capital/current accounts |
| Company/OPC | Profit after tax, reserve movement, dividend disclosure | Share capital, premium, reserves, retained earnings, dividend liability |
| HUF | Result and approved allocation working | Karta/member capital/current balances |
| Trust/society/NGO | Surplus/deficit by restricted status | Corpus and restricted/unrestricted funds |
| Section 8 company | Surplus/deficit with non-distribution control | Company equity plus restricted funds |
| Cooperative | Surplus appropriation and statutory sequence | Member capital, statutory reserves, payable distributions |
| Government/PSU | Surplus/deficit and authorized transfers | Government equity, grants, reserves, deferred balances |

Each report strategy must reconcile to the same posted journal spine while preserving
the terminology and classification appropriate to that formation.

## Workflow And Permissions

### Lifecycle

```text
DRAFT -> CALCULATED -> SUBMITTED -> APPROVED -> POSTED
   |         |             |           |
   +---------+-------------+-----------+-> CANCELLED where permitted
                                      POSTED -> REVERSED
```

- Recalculation creates a new calculation revision.
- Submission freezes sources, policies, and calculation lines.
- Approval becomes stale if any source balance or term version changes.
- Posting uses the approved frozen revision only.
- Reversal creates opposite journals linked to the original batch.

### Permission catalogue

```text
capital_distribution.setup.view
capital_distribution.setup.manage
capital_distribution.policy.view
capital_distribution.policy.manage
capital_distribution.policy.approve
capital_distribution.run.view
capital_distribution.run.calculate
capital_distribution.run.submit
capital_distribution.run.approve
capital_distribution.run.post
capital_distribution.run.reverse
capital_distribution.report.view
capital_distribution.report.export
```

Formation-specific permissions may further restrict high-risk operations such as
dividend declaration, restricted-fund release, or government surplus transfer.

Backend permissions are authoritative. Entity, branch, and financial-year scope
must be validated for list, detail, calculate, approve, posting, reversal, report,
and export endpoints.

## Phase Plan

### Phase 0: Formation Discovery And Accounting Decisions

Status: In progress

Implementation evidence (2026-09-10):

- Existing entity registration, constitution, ownership, financial-year, posting,
  control, report, entitlement, and RBAC paths were mapped for the new boundary.
- The evidence hierarchy is implemented as registration identifier, constitution,
  ownership pattern, then business-type fallback. Conflicts are explicit blockers.
- Wave 1 is gated to proprietorship, partnership, and LLP. All other recognized
  formations return an unsupported strategy instead of silently sharing an engine.
- Remaining before exit: accounting-owner approval and the complete hand-calculated
  journal/report traceability matrix.

Development:

- Map existing constitution, registration, ownership, member/fund, ledger,
  year-opening, P&L, Balance Sheet, trial balance, locks, approval, and posting behavior.
- Approve the constitution-resolution evidence hierarchy and contradiction handling.
- Confirm each planned formation's book presentation with the accounting owner.
- Approve configurable-policy catalogue, defaults, formulas, and rounding rules.
- Create requirement-to-code-to-test traceability matrix.

Testing:

- Record current constitution, ownership, and year-opening regression baseline.
- Build hand-calculated examples for profit, loss, ratio change, capital movement,
  drawings, leap year, rounding, and adjustment run.
- Build expected accounting examples for every later-wave formation before its
  engine implementation begins.

Exit gate:

- Formation-resolution and Wave 1 accounting contracts are signed off.
- Every requirement has an expected journal and report effect.

### Phase 1: Formation Profile And Effective-Dated Policies

Status: In progress

Implementation evidence (2026-09-10):

- Added the `capital_distribution` backend boundary with versioned formation
  profiles, effective-dated policies, stakeholders, audit events, serializers,
  services, scoped APIs, admin registration, migrations, and Phase 1 RBAC seeds.
- Deterministic resolution, idempotent materialization, percentage/date/overlap
  validation, ownership-period validation, transaction rollback, entity isolation,
  submit/approve/reject/supersede lifecycle, and maker-checker approval are implemented.
- Draft policies can be seeded from ownership rows active on the policy date. Scoped
  version comparison ignores database-only row IDs, and every mutation requires an
  optimistic `updated_at` token so stale browser tabs fail with HTTP 409.
- Focused backend suite: 16 tests passing locally, including API lifecycle,
  contradictory/unsupported formations, overlap, ownership retirement, rollback,
  version comparison, stale updates, and direct-object scope.
- Existing onboarding regression gate: three previously failing nested financial-year
  tests were corrected and now pass. Explicit FY labels are preserved and nested
  duplicate-code errors have a stable field-error structure.
- Added the Angular `Capital & Distribution` setup workspace and dynamic menu under
  Accounts > Settings. It supports entity/FY scope, formation readiness, ownership-
  seeded drafts, effective dates, ratio editing, submit/approve/reject/supersede,
  history, and normalized version comparison with responsive layouts.
- Frontend evidence: strict TypeScript and targeted ESLint pass, development build
  passes, and 2 focused ChromeHeadless component tests pass for initial loading and
  ownership-seeded draft creation.
- Remaining before exit: immutable approved-version amendment convenience flow,
  richer comparison/history API metadata, full formation matrix, join/retirement
  segmentation cases, and real API browser, responsive, accessibility, and cross-
  browser certification.

Development:

- Add formation-profile, shared policy-version, policy-target, migrations,
  serializers, services, APIs, audit events, and RBAC.
- Implement deterministic constitution resolution, readiness, contradiction, and
  unsupported-strategy responses.
- Extend partner setup with Master and Terms & Ratios tabs.
- Provide version comparison, preview, submit, approve, supersede, and history.
- Seed an initial draft term set from valid current ownership rows without
  modifying those rows.

Testing:

- Formation dispatch for every known/unknown/contradictory constitution.
- CRUD, normalization, percentage total, overlap, gap, duplicate partner, invalid
  dates, inactive partner, join/retirement, versioning, concurrency, and rollback.
- Entity/FY/permission isolation and direct-object access.
- Desktop, tablet, mobile, keyboard, focus, labels, errors, and empty states.

Exit gate:

- Approved policies are immutable and every effective date resolves to one valid set.
- Unsupported formations cannot access a calculate or post path.
- Existing onboarding and year-opening behavior remains green.

### Phase 2: Partnership And LLP Calculation Engine

Status: Implemented locally; staging and independent spreadsheet certification pending

Development:

- Add run, segment, calculation-line, snapshot, and audit models.
- Implement pure calculation services using `Decimal` and explicit rounding.
- Add actual segment profit, day-weighted fallback, remuneration, capital interest,
  drawing interest, residual allocation, and stale-source detection.
- Return human-readable calculation explanations with source IDs.

Testing:

- Golden-value unit tests for every method and day-count convention.
- Zero/negative profit, zero/negative balances, partner joins/retires, multiple
  mid-period changes, leap day, decimal rates, paise remainder, caps, and overrides.
- Property tests for allocation totals and determinism.
- API tests for malformed policy, missing mappings, stale source, retries, timeout,
  and concurrent calculations.

Exit gate:

- Independent spreadsheet examples match exactly to currency precision.
- Same snapshot and policy always produce the same calculation hash and result.

Implementation checkpoint (2026-09-10):

- Added persisted run, policy segment, calculation line, balance snapshot, and
  run-linked audit models in migration `capital_distribution.0002`.
- Added deterministic Decimal calculations for fixed and book-profit-percentage
  remuneration, interest on capital, interest on drawings, residual profit/loss,
  separate loss ratios, and paise remainder allocation.
- Added `actual/365`, `actual/360`, and calendar-year-split `actual/actual`
  conventions. Percentage-of-period-book-profit remuneration is deliberately not
  time-prorated twice.
- Added effective-policy coverage segmentation and explicit rejection of policy
  gaps. Manual and day-weighted source totals allocate their final paise to the
  last segment so segment totals always equal the run input.
- Posted-books mode reads the existing posted Profit & Loss service for every
  segment. Approved-manual and policy-enabled day-weighted modes remain visibly
  distinct and are captured in the immutable source snapshot.
- Added request hashing, calculation hashing, entity-scoped idempotency, immutable
  input snapshots, source explanations, and retry protection against reusing an
  idempotency key with changed inputs.
- Added scoped list/calculate/detail APIs and the `run.view` and `run.calculate`
  permissions. No posting endpoint is exposed in this phase.
- Extended the operational frontend with configurable partner remuneration and
  interest terms, day-count policy, an explicit day-weighted fallback switch,
  period calculation controls, balance inputs, run history, segment disclosure,
  and component-level preview results.
- Focused evidence: 24 backend tests pass; strict frontend typecheck and targeted
  lint pass; Angular development build passes; 3 ChromeHeadless component tests
  pass; Django checks and migration drift checks pass.
- Remaining Phase 2 certification: independent spreadsheet sign-off, real staging
  posted-book examples, multi-policy staging examples, property-based invariants,
  cross-browser responsive review, and automated/manual accessibility review.
- Temporary boundary: capital and drawing balances are frozen as explicit run
  inputs. Phase 3 Posting Setup will map partner ledgers and replace manual balance
  entry with posted-ledger collection and stale-transaction detection.

### Phase 3: Wave 1 Approval, Posting, And Reversal

Status: Implemented locally; staging, concurrency, and independent accounting certification pending

Development:

- Add a capital-distribution transaction-type registry and the Wave 1 proprietor,
  partnership, and LLP posting adapters. Transaction types remain distinguishable
  for audit and reporting; later engines register their own supported source types.
- Extend Posting Setup with partner appropriation mappings and readiness checks.
- Implement maker-checker, threshold approvals, idempotent post, safe retry,
  reversal, lock handling, and immutable posting references.
- Prevent double allocation between periodic runs and year-end opening generation.

Testing:

- Exact debit/credit assertions for every component and profit/loss direction.
- Calculate-submit-approve-post-retry-reverse lifecycle.
- Duplicate click, simultaneous post, stale approval, closed period, changed FY,
  missing ledger, inactive ledger, wrong entity/branch, and failed transaction.
- Prove no partial journals and exact reversal of all original lines.

Exit gate:

- Posting is balanced, atomic, idempotent, correctly scoped, and fully reversible.
- Existing posting, close, and opening-generation suites remain green.

Implementation checkpoint (2026-09-10):

- Added effective-dated partner capital/current/drawings account mappings and an
  entity-level Profit & Loss Appropriation static account, with readiness checks for
  missing, inactive, cross-entity, and period-inapplicable mappings.
- Posted-ledger capital and drawings collection is now the operational default. Each
  run freezes source controls and rejects submission if balances, policy, ownership,
  or source data changed after calculation.
- Added calculated, submitted, approved, posted, and reversed states with optimistic
  concurrency tokens, maker-checker approval, overlap prevention, reasons, actor/time
  attribution, and immutable audit events.
- Added the `CAPDIST` posting source and a PostingService adapter. Partner credits
  debit Profit & Loss Appropriation and credit the configured partner destination;
  partner debits apply the inverse. Posting is atomic and repeat posting is idempotent.
- Reversal uses a new posting revision with every frozen line and debit/credit side
  inverted. Original and reversal batch references remain on the run.
- Year-end close now detects complete, non-overlapping posted appropriation coverage.
  It clears the close result through Profit & Loss Appropriation and blocks incomplete
  or mismatched coverage, preventing a second partner allocation during year opening.
- Added scoped mapping and lifecycle APIs plus separate manage, submit, approve, post,
  and reverse RBAC permissions. The Angular workspace exposes Posting Accounts,
  readiness, posted-ledger calculation, lifecycle actions, status, and posting refs.
- Local evidence: Django checks and migration drift checks pass; all four new
  migrations apply cleanly; 86 capital-distribution/posting/year-close/year-opening
  tests pass, including a real scoped HTTP lifecycle; 5 focused ChromeHeadless UI
  tests pass; strict TypeScript, targeted ESLint, and the production Angular build pass.
- Remaining Phase 3 certification: two-session simultaneous post/reversal tests on
  PostgreSQL, locked/closed-period staging cases, forced mid-transaction failure,
  branch policy decision, and accounting-owner comparison to independent journals.

### Phase 4: Strategy-Aware Operational Frontend

Status: Local browser certification substantially complete; staging and manual assistive-technology gates pending

Development:

- Build the Capital & Distributions shell and partnership/LLP Appropriation Runs
  browser and workspace.
- Add period/cadence controls, calculation summary, partner/component drilldown,
  source-balance drawer, warnings, validation, approval history, and posting status.
- Keep actions state-aware and hide or disable them according to permission and
  lifecycle, with an accessible reason.

Testing:

- Playwright coverage for every control, state, transition, validation, filter,
  pagination, sorting, refresh, retry, and deep link.
- Chromium, Firefox, WebKit; desktop, tablet, and mobile.
- Keyboard-only flow, focus trapping, screen-reader names, automated WCAG scan,
  loading/error/empty/offline states, and approved screenshot baselines.

Exit gate:

- An accountant can complete the workflow without database/admin intervention.
- No hidden, clipped, overlapping, misleading, or dead controls at supported sizes.

Implementation checkpoint (2026-09-10):

- The routed Capital & Distribution workspace now exposes formation status, effective
  policy terms, partner calculation controls, account mappings, readiness, frozen
  run results, history, and state-aware submit/approve/post/reverse actions.
- Corrected the no-approved-policy state so the day-weighted option does not
  dereference an absent policy while warning the user to approve terms first.
- Added deterministic Playwright coverage for the complete visible run lifecycle,
  mapping readiness and blocker details, partner rows, reversal reason gating,
  view-only permissions, keyboard tab activation, stale-session conflicts, useful API
  load errors, and an approved desktop screenshot baseline.
- Fixed missing accessible names on the partner account selectors. Automated axe
  scans now report no serious or critical violations in the operational workspace.
- Local browser evidence: 24 Playwright scenarios pass across Chromium, Firefox, and
  WebKit. Responsive assertions cover 320x568, 390x844, and 768x1024 without
  document-level horizontal overflow. Component evidence remains 5 ChromeHeadless
  tests passing.
- Remaining before Phase 4 exit: live backend lifecycle validation on staging,
  additional submit/approve/post role permutations, 401/403/422 and offline recovery,
  manual screen-reader and full Tab-order review, focus behavior during asynchronous
  errors, and production-like simultaneous-session testing.

### Phase 5: Financial Reports And Reconciliation

Status: Staging accounting, UI, reports, exports, reversal, branch isolation, controlled year-end/opening integration, custom-range Balance Sheet reconciliation, and three-browser automation complete; manual assistive-technology review remains pending

Development:

- Enhance P&L with operating and appropriation presentation.
- Enhance Balance Sheet with partner-wise capital/current breakdown.
- Add appropriation statement, partner balance, capital-interest, drawing-interest,
  remuneration, ratio-history, audit, and reconciliation report tabs.
- Add PDF/XLSX/CSV exports with the same filters and totals as the browser.

Testing:

- Reconcile every run to journals, trial balance, P&L, Balance Sheet, partner ledger,
  year-end close, and next-year opening.
- Empty/single/multi-page, sort, filter, drilldown, export, large values, negative
  values, rounding, period comparison, branch consolidation, and FY boundaries.
- Validate PDF pagination, headings, partner names, percentages, totals, and file names.

Exit gate:

- All mandatory reconciliation equations equal zero difference.
- Browser and exported report totals agree exactly.

Implementation checkpoint (2026-09-10):

- Added a scoped appropriation-statement API for entity, financial year, branch, and
  date range. It reports frozen calculation totals, partner and component totals,
  original and reversal journal checks, effective financial impact, and exceptions.
- Posted runs reconcile each frozen partner line to its journal detail row. Reversed
  runs remain visible but contribute zero effective balance when the inverse journal
  exactly matches the frozen run.
- The operational workspace now includes a Statement tab with period totals,
  partner balances, component totals, and run-level journal status. Backend readiness
  issue codes are translated into actionable partner/account messages.
- Local evidence: all 34 capital-distribution backend tests pass; the focused Angular
  appropriation workspace suite passes 5 tests; TypeScript, targeted ESLint, and the production build pass;
  and 27 Playwright scenarios pass across Chromium, Firefox, and WebKit, including
  the new statement view.
- P&L and Balance Sheet now expose a dedicated capital-distribution disclosure with
  a strict boundary between pending calculation and posted accounting. Operating
  profit impact is always zero; report impact is derived only from CAPDIST journal
  lines whose entry status is Posted.
- Posted partner movements are resolved from the actual journal ledger and active
  owner mapping. Trial Balance and partner Ledger Book assertions prove debit-credit
  equality and partner allocation; reversal removes the effective report impact.
- P&L shows Posted Appropriation and Balance Sheet shows Partner Equity Movement as
  separate summary cards without changing statement totals. Both reports now include
  a compact posted-partner schedule with destination ledger, debit, credit, net
  movement, reconciliation status, and direct Ledger Book navigation using the
  active report scope.
- Generated-file tests parse the real CSV, XLSX, PDF, and inline-print responses for
  both reports and verify movement labels and balanced reconciliation metadata.
  Multi-period tests prove date filtering, while two-branch tests prove exact branch
  isolation, consolidated totals, and the remaining movement after one branch run is
  reversed.
- Cross-report evidence: 34 capital-distribution tests pass, including draft,
  approval, posting, reversal, P&L invariance, Balance Sheet disclosure, Trial
  Balance equality, partner ledger drill-down, generated exports, periodic filtering,
  and branch consolidation; 4 legacy financial-report tests pass; and 66 focused
  P&L/Balance Sheet Angular tests pass with TypeScript, targeted ESLint, and the
  production build.
- Two focused Chromium browser scenarios certify the posted schedule on both reports,
  current-scope Ledger Book navigation, and internal table overflow at 390x844
  without document-level horizontal scrolling.
- Shared-engine residual risk: `PostingService` deletes prior journal rows when it
  creates a replacement revision. For reversed capital-distribution runs, the report
  therefore labels the original journal as reconstructed from immutable frozen run
  lines and validates the live reversal against them. Preserving journal rows for all
  posting revisions requires a separately tested posting-engine migration.
- Remaining before Phase 5 exit: complete manual assistive-technology review.

Staging certification checkpoint (2026-09-10):

- Configured a controlled Manav-T partnership scope with two QA partners at 60/40,
  separate current ledgers, an approved policy, and a mapped P&L appropriation ledger.
- The real API lifecycle calculated INR 1,000.00 as INR 600.00 and INR 400.00,
  rejected maker self-approval, accepted approval by a separate checker, and posted
  one four-line journal batch with INR 1,000.00 debit and credit.
- The appropriation statement reported one reconciled run and zero exceptions. Trial
  Balance and the three scoped Ledger Books agreed exactly with the posted journal.
  P&L retained zero operating-profit impact; P&L and Balance Sheet disclosed the
  posted partner movement independently.
- Real CSV, XLSX, PDF, and inline-print downloads succeeded for both P&L and Balance
  Sheet. Content types, attachment/inline disposition, entity/date filenames,
  appropriation labels, and Balanced reconciliation text were verified from the
  generated files.
- Reversal was completed after certification. The run remains as a reconciled audit
  record with zero effective movement; all three QA ledgers close at zero and both
  financial reports show zero posted capital-distribution impact.
- A live browser pass found a production-path defect before certification could be
  signed off: `AccountBindApi` referenced the retired `/api/financial/accountbind`
  route, so nginx returned 404 and the workspace's combined load aborted. The client
  now requests the canonical `/api/financial/accounts/simple-v2` endpoint, with a
  config regression assertion and updated deterministic Playwright route.
- Local verification for that correction: 15 focused Angular tests pass. The
  desktop baseline change was visually reviewed and approved because it contained
  only the intentional Statement tab. All nine deterministic Chromium checks now
  pass against the approved baseline.
- Manav-T's pre-existing Balance Sheet is materially out of balance before the QA
  run as well as on its posting date. This is an independent source-data/reporting
  investigation item; the controlled journal itself balanced and reversed to zero.
- The canonical account-endpoint correction was deployed and verified against
  `/api/financial/accounts/simple-v2?entity=2`, which returned the complete scoped
  account list without aborting the workspace load.
- A second controlled INR 1,000.00 run (`stage-cert-20260910-v2`) repeated the
  calculate, submit, independent approve, post, report, export, and reversal lifecycle.
  The posted allocation was INR 600.00 and INR 400.00 with a balanced four-line
  journal. The reversal was also four lines and balanced at INR 1,000.00 debit and
  credit.
- The deployed Chromium suite passes all four live scenarios: formation and mapping
  readiness, appropriation-statement effective movements and reconciliation, P&L and
  Balance Sheet partner schedules, partner Ledger Book drilldown, 390x844 responsive
  layout, and no serious or critical axe findings in the operational workspace.
- All eight real generated artifacts pass content inspection: CSV, XLSX, PDF, and
  inline print for P&L and Balance Sheet contain their expected appropriation labels,
  the Appropriation Reconciliation section, and Balanced status.
- Post-reversal checks report zero effective debit/credit, zero financial-report
  capital-distribution impact, and zero debit, credit, and closing balance on both
  partner ledgers and the appropriation ledger. Both retained runs reconcile with
  zero exceptions and remain available as immutable audit history.
- A branch-role audit found that the workspace did not forward the active subentity
  on formation, policy, mapping, run, and statement reads. This caused the combined
  workspace load to fail for a correctly restricted branch user. The client now
  forwards the active branch consistently, while the API validates direct run and
  policy access against each object's persisted branch instead of trusting only
  request query parameters. Global policies remain readable as inherited setup in
  an explicitly allowed branch context; global formation and mapping mutations stay
  restricted to entity-wide operators.
- Local branch-isolation evidence: all 36 backend capital-distribution tests pass,
  including own-branch list/detail/action access, foreign-branch denial, unscoped
  branch denial, and inherited global-policy reads. The five focused Angular tests
  verify branch forwarding on every workspace read and mutation. TypeScript passes,
  and all nine deterministic Chromium scenarios pass, covering lifecycle, mobile,
  view-only behavior, stale-session recovery, accessibility, errors, and visual
  baseline stability.
- The deployed branch-scope correction was exercised with a disposable Head Office
  viewer carrying only setup, policy, and run read permissions. Formation, policy,
  run list, mapping, and statement reads returned 200 for the assigned branch;
  unscoped formation, the foreign branch, and direct access to an entity-wide run
  returned 403. The real restricted browser workspace passed at 390x844, exposed no
  entity-wide runs or mutation controls, had no document overflow, and produced no
  serious or critical axe findings. The reusable live Playwright gate passed 2/2.
- That staging pass also exposed a shared-shell defect outside the capital API: the
  entity-context endpoint listed both branches and accepted the foreign branch as
  saved context, after which correctly scoped business APIs failed. The local fix
  filters both branch-option endpoints, repairs stale defaults to an allowed branch,
  and rejects foreign or unscoped context for branch-only users. All 43 focused
  entity-context and capital-distribution backend tests pass.
- Final staging isolation certification (2026-09-11): the shared context correction
  was deployed and the reusable restricted-user Playwright gate passed 2/2. The
  entity payload exposed only Head Office; assigned-branch formation, policies,
  runs, mappings, and statement reads succeeded; and unscoped, foreign-branch,
  foreign-context, and entity-wide run access returned 403. The read-only workspace
  loaded at 390x844 with every capital API request carrying the assigned branch,
  no leaked entity-wide run, no enabled mutation control, no horizontal overflow,
  and no serious or critical axe finding. The disposable user and role were removed,
  with zero temporary records remaining.
- Local year-end/opening certification (2026-09-11): a real posted annual
  partnership run allocated INR 100,000.00 as INR 60,000.00 and INR 40,000.00.
  The generated year-end close lines credited Profit & Loss Appropriation by the
  same INR 100,000.00 that the distribution posting debited, proving the temporary
  appropriation balance clears to zero. A post-close opening snapshot carried the
  two partner balances once, remained debit-credit balanced, and produced no
  synthetic second 60/40 allocation.
- The same gate proves incomplete annual coverage blocks year-end qualification, a
  reversed partial run is excluded from active coverage, and full-date coverage is
  still rejected when its posted allocation differs from closeable book profit.
  Existing duplicate opening-generation and rollback tests also remain green. The
  focused regression passed 50 tests across capital distribution, year-end close,
  opening generation, and destructive close/opening workflows, with no production-
  code change required.
- Controlled staging year-end/opening certification (2026-09-11): a disposable,
  balanced partnership entity on staging PostgreSQL posted INR 100,000.00 of book
  profit and distributed it to two partner current accounts at 60/40. The CAPDIST
  journal debited Profit & Loss Appropriation by INR 100,000.00, and the YEC journal
  credited it by the same amount, leaving the appropriation account at zero.
- The generated FY2027-28 opening journal debited cash by INR 100,000.00 and credited
  the partner accounts by INR 60,000.00 and INR 40,000.00 exactly once. It contained
  no appropriation line or duplicate synthetic allocation. The destination Balance
  Sheet reported INR 100,000.00 on both sides with zero balance difference, while
  destination P&L income, expense, and net profit were all zero.
- Opening rollback, year-end rollback, and distribution reversal completed through
  the production service layer. The disposable entity, user, runs, entries, and
  posting batches were then removed, and all fixture residue checks returned zero.
- Staging cross-browser certification (2026-09-11): the finalized live suite passed
  4/4 in Firefox and 4/4 in WebKit. It validated verified formation and posting
  mappings, API-to-UI appropriation totals, P&L and Balance Sheet treatment of
  effective partner movements, 390x844 responsive behavior, and zero serious or
  critical axe findings.
- The live suite no longer assumes a permanently posted sample run. It derives
  calculated and effective partner totals from the scoped reconciliation API and
  proves the two existing reversed Manav-T runs remain reconciled while contributing
  zero active P&L or Balance Sheet movement. Authentication and entity/FY scope are
  established through the API before direct screen navigation, removing unrelated
  dashboard-load instability from the report certificate.
- Manav-T imbalance root-cause and local correction (2026-09-11): full-FY staging
  Balance Sheet and Trial Balance were balanced at zero difference, but a one-day
  custom-range Balance Sheet omitted INR 2,638,433.72 of profit earned earlier in
  the same financial year. Asset and liability ledger balances correctly included
  pre-range movements as effective opening balances, while the profit transferred
  into equity was incorrectly calculated from only the selected day.
- The Balance Sheet engine now accumulates current-year profit from the active FY
  start through the selected as-of date, independent of the display range start.
  A new isolated regression proves opening capital plus profit earned before a later
  custom range remains balanced and exposes the applied profit accumulation date.
  The expanded regression passed 129 tests across book reports, capital distribution,
  year-end close, opening generation, and destructive rollback workflows.
- Deployed custom-range verification (2026-09-11): Manav-T's Balance Sheet for the
  original one-day scope, 10 September 2026, now reports INR 3,162,687.72 for both
  total assets and total liabilities and equity, with a zero balance difference.
  It brings INR 2,638,433.72 of current-year profit into equity and reports
  `profit_accumulation_from` as 1 April 2026. The full FY remains unchanged and
  balanced at the same totals.
- Staging generated-file verification downloaded CSV, XLSX, PDF, and inline-print
  output for that one-day scope. All responses returned the expected content type,
  file signature, date-scoped filename, and attachment or inline disposition; the
  CSV and PDF content identified the report as Balance Sheet.
- The reusable live Playwright certificate now carries the custom-date regression,
  full-FY control, generated-file checks, and rendered Balanced state. It passed
  5/5 in Chromium, 5/5 in Firefox, and 5/5 in WebKit; the narrow 390x844 check also
  retained zero serious or critical axe findings.
- Remaining before Phase 5 exit: complete manual VoiceOver or equivalent
  assistive-technology review of the setup, statement, P&L, Balance Sheet, and
  partner-ledger drilldown flow.

### Phase 6: Tax Working And Policy Governance

Status: Substantially complete; local implementation and staging service/browser certification complete, with independent accounting and manual assistive-technology gates pending

Development:

- Add effective-dated statutory policy records with jurisdiction and references.
- Separate book calculation from tax allowability and disallowance working.
- Add controlled override, reason, attachment, approval, and audit behavior.
- Never change posted book journals merely because a tax-policy version changes.

Testing:

- Effective-date boundary, expired/future policies, missing policy, cap boundary,
  manual override, approval, amended policy, and historical reproducibility.
- Verify tax views do not alter operating P&L or partner book balances.

Exit gate:

- Every tax adjustment identifies its policy version or approved manual basis.
- Historical runs reproduce from their stored snapshot.

Implementation checkpoint (2026-09-11):

- Added entity-scoped `TaxPolicyVersion` records with stable policy code, formation,
  tax type, country/state jurisdiction, effective dates, statutory and source
  references, schema version, configuration, and complete maker-checker metadata.
- Tax policy configuration is controlled but extensible. It supports currency,
  rounding, metadata, and one treatment rule per appropriation component. Rules can
  be allowed, disallowed, capped, or informational, with rate, amount, formula, and
  structured condition inputs.
- Draft, submit, approve, reject, and supersede transitions use row locking and
  optimistic concurrency. Approved versions are immutable, makers cannot approve
  their own submission, rejection/supersession requires a reason, and overlapping
  approved policies for the same entity, jurisdiction, formation, tax type, and code
  are blocked.
- Every transition writes a complete policy snapshot to the existing capital and
  distribution audit stream with a correlation ID. Historical versions are retained
  instead of edited in place.
- Added entity-level REST endpoints for policy list/create, detail/update, submit,
  approve, reject, and supersede. Branch-scoped requests are rejected because this
  tax governance is entity-wide. Dedicated view/manage/submit/approve permissions
  are granted to entity administration roles through RBAC migration 0149.
- Added `CapitalDistributionTaxWorking` and immutable source-line working records.
  Calculation is allowed only from a posted appropriation run and an approved policy
  that matches entity, financial year, formation, and the complete run period. Every
  source component must resolve to an explicit policy rule.
- Each working freezes the book-run hash, posting-batch reference, source line inputs,
  complete tax-policy snapshot, rule used for each line, and a calculation hash. Each
  line and the working total enforce `book amount = allowable amount + disallowed
  amount`; allowed, disallowed, informational, fixed-cap, rate-cap, and governed
  externally evaluated-cap treatments are supported.
- Formula identifiers are never silently guessed. The governed
  `india_partnership_remuneration_v1` evaluator applies the current aggregate section
  40(b) slab to frozen statutory book profit, limits the result to actual book
  remuneration, and allocates allowable paise pro rata across partner lines using a
  deterministic largest-remainder rule. The governed
  `india_partnership_interest_v1` evaluator caps partner interest at 12% simple annual
  interest and uses the frozen run year fraction for partial periods.
- The remuneration evaluator treats `source_profit + book_adjustments` as statutory
  book profit because the run captures profit before appropriation. This mapping and
  the policy's statutory source must be independently approved for each deployment;
  the evaluator never reclassifies or mutates the posted books.
- Formula assumptions were checked against the Income Tax Department's current
  [section 40 text](https://www.incometaxindia.gov.in/documents/20117/42998/Section-40_2026-05-05_11-48-27_06f241_en.pdf/6374c1e3-46ae-d0c0-31d4-9219c6635baf?t=1779519449631&version=2.0):
  the remuneration first band is INR 600,000, the loss/first-band minimum is INR
  300,000, the first-band percentage is 90%, the balance percentage is 60%, and
  partner interest is limited to 12% simple interest per annum.
- Statutory remuneration policies cannot be submitted until users explicitly confirm
  deed authorization and working-partner-only eligibility. Partner-interest policies
  require explicit deed authorization. Unsupported formulas still fail visibly unless
  a governed external evaluated cap is supplied.
- Added controlled line override behavior. Override amounts must remain between zero
  and the frozen book amount and require a reason plus at least one structured evidence
  reference. Overrides are available only in calculated status and are frozen at
  submission.
- Added calculated, submitted, approved, and reversed lifecycle states with optimistic
  concurrency, row locking, maker-checker separation, mandatory reversal reason, and
  complete before/after audit snapshots. Reproduction recalculates from frozen source
  and rule snapshots and compares both line results and the stored hash.
- Added scoped REST endpoints for working list/calculate, detail, line override,
  reproduction, submit, approve, and reverse. Dedicated view/calculate/override/
  submit/approve/reverse permissions are seeded through RBAC migration 0150.
- Added a separately authorized tax-working export endpoint for CSV, XLSX, and PDF.
  Every format carries entity/FY/branch scope, source run and posting batch, policy
  version and statutory source, lifecycle actors/timestamps, calculation hash,
  reconciled totals, calculated-versus-final line treatment, override reason, and
  evidence references. Spreadsheet text is neutralized against formula injection.
  Export permission is distinct from view permission and is seeded only to entity
  administration roles through RBAC migration 0151.
- Tax working has no posting-batch foreign key and calls no journal or posting service.
  The source posting-batch identifier is copied only into its audit snapshot. Tests
  prove calculation, override, approval, and reversal leave journal-line counts
  unchanged.
- Local evidence: governance tests cover normalization, valid lifecycle,
  complete audit snapshots, maker-checker separation, approved immutability,
  malformed and duplicate rules, incomplete policy submission, overlap and
  replacement sequencing, mandatory reasons, stale edits, REST lifecycle, entity
  scope, and permission denial. Ten tax-working tests cover reconciliation,
  idempotency, zero-rate cap boundaries, missing and partial-period policies,
  unsupported formulas, required override evidence, API override, maker-checker,
  immutable submitted state, reversal, permission denial, journal neutrality, and
  historical reproduction after policy supersession. Two authenticated API clients
  now prove that a repeated calculation returns one working and one calculation audit,
  while stale submit, approve, and reverse attempts return HTTP 409, create exactly one
  audit event per successful transition, and leave journal counts unchanged. A true
  PostgreSQL two-thread test additionally proves simultaneous calculations serialize
  to one working/one audit and simultaneous submissions produce one success plus one
  stale conflict. Forced audit-storage failures during calculation and submission roll
  back the complete transaction; clean retries then succeed without duplicate records
  or journal movement. New
  statutory golden tests cover
  loss, nil-profit, first-band, one-paise-above-band, and upper-band remuneration
  boundaries; exact aggregate pro-rata allocation; actual-payment restriction;
  missing eligibility; 12% interest; and partial-period proration. A persisted
  half-year working proves aggregate partner allocation, frozen formula context,
  excess-interest disallowance, reproduction, and journal neutrality.
  A binary export contract test parses the workbook, verifies CSV evidence and hashes,
  validates the PDF signature, checks invalid format, foreign scope, and missing
  permission failures, and proves export leaves journal counts unchanged. The full
  capital-distribution backend suite passes 67/67; the focused tax-working lifecycle
  and PostgreSQL concurrency suites pass 14/14; Django system checks and
  migration drift checks also pass.
- Added `Tax Policies` and `Tax Working` views to the existing Capital & Distribution
  workspace. Policy users can create a version from a fixed component matrix, maintain
  jurisdiction/source/effective-date inputs, save drafts, and perform governed submit,
  approve, reject, and supersede transitions. Raw policy JSON is not exposed as a user
  editing surface.
- The tax-working view restricts selection to posted appropriation runs and approved
  policies, displays the frozen book/allowable/disallowed bridge and hash, supports
  reason-and-evidence-backed line overrides, verifies historical reproduction, and
  exposes only status-valid submit, approve, and reverse actions. Server calculations
  remain authoritative; the browser does not calculate statutory outcomes.
- The selected working now presents compact, permission-aware PDF, Excel, and CSV
  actions with deterministic period-based filenames. The action group wraps below
  the working title on narrow screens instead of widening the page.
- The policy workspace now seeds both supported formulas and shows clear deed and
  working-partner eligibility checkboxes for both new and existing draft versions.
  These confirmations are visible workflow controls rather than hidden JSON settings.
- Frontend evidence: the focused Angular component suite passes 11/11 in headless Chrome;
  strict TypeScript, targeted component/service/template lint, and the development
  build pass. Tax-working mutation, reproduction, and export methods now reject
  programmatic re-entry while another request is active, supplementing disabled-button
  protection against duplicate requests. The deterministic Chromium workspace suite
  passes 17/17, covering policy
  creation/approval, tax calculation, evidence override, reproduction, approval,
  permissions, stale-state recovery, accessibility, and responsive layouts at 320,
  390, and 768 pixels with no document-level horizontal overflow. The new statutory
  confirmation grid is explicitly exercised at 390 pixels with contained table
  scrolling. Browser tests exercise actual PDF/XLSX/CSV download events,
  deterministic filenames, dedicated export-permission denial, and the export action
  group at 390 pixels without document-level overflow. Browser recovery cases prove a
  failed calculation preserves run/policy scope and can be retried, a stale tax-working
  submit remains actionable after HTTP 409, and an interrupted export creates no file
  before one successful retry. The approved desktop visual baseline remains green. The
  same 17-scenario suite passes in Chromium, Firefox, and WebKit (51/51 total, snapshots
  intentionally asserted only in Chromium), including automated serious/critical
  accessibility checks.
- The live staging certificate now contains seven non-destructive scenarios. Its new
  Phase 6 coverage verifies scoped tax-policy/tax-working endpoint and workspace
  readiness, reconciles every frozen working as book = allowable + disallowed, requires
  a posted source run, reproduces each frozen hash, checks authorized CSV/XLSX/PDF
  signatures and filenames, and confirms the appropriation statement is unchanged.
  The reconciliation scenario reports a skip when no staged frozen working exists so
  absent certification data cannot be mistaken for a pass. TypeScript compilation and
  Playwright discovery of all seven live scenarios pass locally.
- Staging certification checkpoint (2026-09-11): a rollback-only scenario on the
  deployed PostgreSQL environment used Manav-T's verified partnership profile,
  approved 60/40 distribution policy, and live account mappings. It calculated and
  posted a one-day INR 12,345.67 appropriation run, created and independently approved
  an effective tax policy, produced a frozen working with the full amount explicitly
  disallowed, and reconciled book amount exactly to allowable plus disallowed amount.
  Reproduction matched the stored calculation hash, a repeated calculation returned
  the same working, and tax calculation left journal-line count unchanged. CSV, XLSX,
  and PDF outputs passed content/signature checks. The tax working and posting were
  reversed before the enclosing transaction was deliberately rolled back; follow-up
  queries confirmed zero residual runs, policies, or workings.
- The seven-scenario live browser certificate then ran against the deployed UI in
  Chromium, Firefox, and WebKit. It passed 18/18 executable checks, including setup
  and mapping readiness, appropriation statement reconciliation, P&L, Balance Sheet,
  custom-date accumulation, generated-file contracts, tax workspace readiness, and
  narrow-viewport accessibility with no serious findings. Three expected skips (one
  per browser) recorded that Manav-T has no permanently persisted tax working. The
  rollback-only staging service certificate above supplies the corresponding
  book-to-tax lifecycle evidence without leaving certification records in customer
  books.
- Remaining Phase 6 slices: independent accounting-owner approval of statutory golden
  examples; binary evidence upload integration if required beyond document IDs/URLs;
  manual assistive-technology review;
  and production-like concurrent load certification. Two-client optimistic concurrency,
  real simultaneous PostgreSQL row-lock
  behavior, transactional rollback, idempotent retry, duplicate-action suppression, and
  browser failure-recovery gates are complete locally; the principal book-to-tax
  lifecycle and three-browser operational path are also certified on staging.

### Phase 7: Wave 1 Migration And Proprietorship Engine

Status: Automatable local and non-destructive staging certification complete; manual assistive-technology certification pending

Development:

- Add the proprietor capital/current/drawings calculation and posting strategy.
- Provide dry-run migration/report for existing proprietor/partner ownership and mappings.
- Create initial draft terms only for constitutionally valid entities.
- Report invalid totals, overlaps, missing PAN/reference, and ledger gaps without
  partially enabling the module.
- Add feature flag and per-entity activation readiness check.

Testing:

- Empty system, proprietor, single partner, many partners, invalid legacy data,
  rerun, rollback,
  interrupted migration, and production-like volume.
- Verify untouched entities retain current year-opening behavior.

Exit gate:

- Migration is repeatable, non-destructive, observable, and reversible.
- No existing entity is activated with incomplete policies or ledger mappings.
- Proprietor flows never expose partner ratio/remuneration controls.

Implementation checkpoint (2026-09-11):

- Added a one-per-entity Wave 1 activation gate with pending, ready, enabled, and
  disabled states, frozen readiness evidence, timestamps, and actor attribution.
  Entities without an activation record retain their existing behavior; once an
  entity enters the migration flow, calculation is blocked until explicitly enabled.
- Added read-only migration preview, idempotent preparation, and explicit
  enable/disable APIs. Preparation locks the entity, materializes a verified formation
  profile, creates an initial draft only when none exists, records an audit event, and
  never enables posting. Enable is rejected until preparation has created the gate and
  profile, approved policy, owner mappings, and appropriation mapping are all ready.
- Readiness covers proprietorship, partnership, and LLP; full-FY owner coverage;
  proprietor count and 100% share; partner share completeness and 100% totals; stale
  profiles; approved policy coverage; PAN/reference warnings; and posting-account gaps.
  Invalid source data aborts transactionally without partial profiles, policies, or
  activation records.
- Proprietorship now runs through the shared frozen calculation, approval, posting,
  reporting, and reversal engine at 100%. Proprietor remuneration is rejected at the
  domain boundary, and mixed approved policies from different formations cannot be
  combined in one run.
- Added an operator-facing Migration & Activation workspace with formation, owner,
  evidence, policy, and posting readiness; named blockers; and explicit Prepare,
  Enable, and Disable actions. Proprietor policy screens show a fixed 100% result and
  suppress partner-only ratio and remuneration controls. Owner terminology is also
  applied to mappings, balances, statements, and success messages.
- Local evidence: all 71 capital-distribution backend tests pass, including migration
  preview purity, idempotency, invalid-data rollback, activation gating, proprietor
  calculation, balanced journals, exact reversal, tenant/FY scope, and API permission
  behavior. The focused Angular suite passes 13/13, the full deterministic Chromium
  browser suite passes 18/18, and migration/mobile/keyboard/axe checks pass 9/9 across
  Chromium, Firefox, and WebKit with no serious or critical automated accessibility
  findings.
- Remaining Phase 7 gate: manual VoiceOver or equivalent review.

Staging checkpoint (2026-09-11):

- Confirmed the deployed application and API are healthy over HTTPS and the Wave 1
  migration view/manage permissions are present for the certified entity scope.
- Completed read-only migration assessments across five staging entities. Four
  unconfigured entities were correctly blocked without creating activation records.
  The configured Manav-T partnership was reported ready while retaining the
  `not_created` activation state, proving that assessment is non-mutating and that an
  untouched entity remains on the compatibility path. Its missing owner PAN was
  surfaced as a warning rather than silently ignored.
- Ran the live capital-distribution browser certification against Manav-T in Chromium,
  Firefox, and WebKit: 18 tests passed and 3 tax-working reproduction tests were
  explicitly skipped because no persisted frozen tax working exists in this staging
  scope. Setup, mappings, statements, P&L, Balance Sheet, custom-date accumulation,
  export, scoped tax workspace, narrow-mobile usability, and automated serious/critical
  accessibility checks passed.
- No migration preparation, activation, calculation, posting, reversal, or book data
  mutation was performed during this checkpoint.
- This browser checkpoint was deliberately read-only. The subsequent rollback-only
  service certificates below cover the controlled migration and accounting lifecycle.

Rollback-only staging migration checkpoint (2026-09-11):

- Executed a complete proprietor lifecycle against deployed PostgreSQL inside a forced-
  rollback transaction: preview, idempotent prepare, pre-enable rejection, policy
  approval, posting mappings, enable, INR 75,000 calculation at fixed 100%, maker-
  checker enforcement, balanced posting, idempotent posting retry, appropriation
  statement, P&L, Balance Sheet, trial balance, proprietor ledger, exact reversal,
  report zeroing, disable, and post-disable rejection all passed.
- The proprietor posting produced INR 75,000 debit and credit, left operating profit
  unchanged, appeared as a balanced equity movement in both financial statements, and
  returned to zero after reversal. Before/after model counts matched and the temporary
  entity, run, users, accounts, journals, policy, profile, and activation did not persist.
- Executed 100 proprietor migration previews, 100 first prepares, and 100 idempotent
  retries in a second forced-rollback transaction. Preview took 1.067 seconds, first
  preparation 6.549 seconds, and retry 3.053 seconds on staging. An injected failure
  during policy seeding and a separate invalid 75% proprietor source both left no
  partial profile, policy, or activation. All 102 temporary entities were rolled back.
- Executed a separate 60/40 partnership migration certificate covering preview,
  preparation, seeded ownership percentages, policy approval, two owner mappings,
  readiness, enable, disable, object-count idempotency, and full transaction rollback.
  Manav-T and all other customer entities remained untouched.
- Remaining Phase 7 gate is manual VoiceOver or equivalent assistive-technology review.

### Phase 8: Wave 1 Production Certification

Status: In progress; backend operational observability Wave 1 complete

Development:

- Add operational metrics, structured errors, correlation IDs, calculation/posting
  duration, failure counters, and stale-run monitoring.
- Document support diagnosis, reversal, recovery, and data-retention procedures.

Testing:

- Full real-data lifecycle locally and on staging.
- Role matrix: admin, proprietor/partner accountant, approver, poster, read-only,
  and restricted user.
- API timeout, 401/403/409/422/500, offline, interrupted request, retry, and recovery.
- Concurrent calculate/approve/post/reverse and repeated-suite flake testing.
- Agreed volume tests for partners, movements, periods, reports, and exports.
- Manual screen-reader review and approved cross-browser visual baselines.

Exit gate:

- Zero unresolved critical/high defects.
- No conditional skips in the launch-critical browser lane.
- Reconciliation, security, accessibility, recovery, and performance gates pass.
- Product owner, accounting owner, engineering, and QA approve the Wave 1 launch matrix.

Implementation checkpoint (2026-09-11):

- Added a request-scoped correlation context for every capital-distribution API. A
  caller-supplied safe `X-Correlation-ID` is preserved; invalid or absent values are
  replaced with a generated ID. The response header, success audit events, structured
  error response, failure audit event, and server log now use the same identifier.
- Added duration metadata to migration, activation, calculation, run lifecycle, tax
  policy, and tax-working audit events. Validation, conflict, permission, and unexpected
  failures are logged without request bodies or credentials; failures after successful
  entity scoping are also persisted for operator diagnosis. Unexpected failures retain
  the application's support-safe structured error contract and expose no exception text.
- Added scoped `GET /api/capital-distribution/operations/health/` visibility for run
  totals by status, stale runs, calculated/submitted/approved actions older than 24
  hours, recent failure summaries, and recent audit latency. The endpoint uses existing
  subscription, entity/FY/branch, and run-view permission enforcement.
- Added the production support, recovery, reconciliation, escalation, and retention
  runbook at `docs/capital-distribution-production-runbook.md`.
- Local evidence: all 73 capital-distribution tests pass. New API tests prove success
  correlation and duration, persisted validation failure diagnostics, stale-run health,
  24-hour failure visibility, safe HTTP 500 handling, and correlation propagation.
  Django system checks and migration-drift checks pass with no schema changes.
- Staging backend smoke passed for Manav-T on 2026-09-11. The scoped health request
  returned HTTP 200, the expected entity and financial-year scope, a generated
  `X-Correlation-ID`, healthy status, two reversed runs, and no stale, aging, or failed
  operations. A separate non-mutating invalid-scope request returned structured HTTP 400
  validation and preserved its caller correlation ID in both response header and body.
  No business records were mutated by these smokes.
- Added a permission-gated Health tab to the capital-distribution workspace. It presents
  run lifecycle counts, stale and aging work, 24-hour failures, latency samples, and
  diagnostic correlation IDs. A health-endpoint failure remains isolated from the core
  setup and workflow screens, and the tab is hidden without run-view access.
- Frontend evidence: TypeScript passes, all 14 focused Angular component tests pass, and
  the complete 22-case Chromium workspace suite passes. Healthy, attention, unavailable,
  permission, and 390px mobile states also pass in Firefox and WebKit. Automated serious
  and critical accessibility findings remain zero, and the updated Chromium operational
  baseline was reviewed and approved.
- The deployed Health tab passed three staging browser checks on 2026-09-12: scoped
  backend correlation, rendered health data and refresh, zero browser console/page
  errors, 390px mobile containment, and zero serious or critical automated accessibility
  findings.
- Completed the deterministic frontend role matrix for administrator, setup-only,
  restricted, read-only, accountant/maker, approver, poster, and reverser. Run, history,
  statement, and health data are no longer requested or displayed without compatible
  run-view or policy-view access. The full backend suite remains 73/73 green and the
  expanded Chromium workspace suite passes all 31 cases. The visual baseline also passed
  twice consecutively after masking the unrelated live header date.
- Completed the recovery response matrix for this workspace: live staging `401` preserves
  correlation without exposing data; browser `403` preserves the calculated run; `409`
  preserves stale run/tax-working state for retry; `422` permits corrected calculation;
  `500` leaves the workspace intact; timeout isolates operational health; and interrupted
  download retries without duplicate output. The critical role, recovery, mobile, and
  visual lane then passed 54/54 across three consecutive executions.
- Completed PostgreSQL write-concurrency certification for the primary appropriation
  lifecycle. Calculation creation now locks the parent entity before checking a new
  idempotency key, closing the race where two transactions could both observe that no
  run existed. A true two-thread test proves one calculated run and calculation audit,
  one submit winner, one approve winner, one idempotent posting batch, balanced journals,
  one reverse winner, one reversal batch, stale-version rejection for losing transitions,
  and one audit event for every committed lifecycle action. The complete backend suite
  passes 74/74 with system checks and migration-drift checks clean. The focused threaded
  lifecycle certificate also passed five consecutive executions without a flaky result.
- Staging read-concurrency certification issued 20 simultaneous scoped operational-health
  requests on 2026-09-12. All 20 returned HTTP 200 in 1.857 seconds, preserved their
  unique correlation IDs, matched entity 2 / financial year 2, and returned one stable
  run-count snapshot. The existing deployed health smoke also passed independently.
- Completed deployed write-concurrency certification on staging on 2026-09-12 using a
  temporary PostgreSQL database containing the deployed schema and migration ledger but
  no customer rows. The true two-thread calculation-through-reversal certificate passed
  in 15.070 seconds with system checks clean. The temporary database was removed after
  teardown and a following live scoped-health browser smoke passed; customer books were
  not touched.
- Added a deterministic local volume certificate covering 100 partners, 5,000 captured
  capital movements, 12 monthly calculated/approved/posted periods, 1,200 allocation
  lines, 2,400 journal lines, annual appropriation reconciliation, and Profit & Loss plus
  Balance Sheet generation in CSV, XLSX, and PDF. Counts reconciled exactly, every period
  reported as reconciled, effective annual credit was 120,000.00, and journals remained
  balanced. In the full suite the lifecycle completed in 2.895 seconds, statement build
  in 0.415 seconds, and six exports in 4.097 seconds, all below the certification limits.
  The complete capital-distribution suite now passes 75/75.
- Remaining Phase 8 work: deployed volume confirmation, removal of the persisted-tax-working
  conditional skip, manual screen-reader review, and formal launch signoff.

### Phase 9: Company And OPC Equity/Dividend Engine

Status: Planned after Wave 1 certification

Development:

- Add share classes, shareholder eligibility snapshots, declared distributions,
  record/payment dates, reserves, dividend payable, withholding mapping, and approval.
- Enforce company/OPC strategy resolution and prohibit partner appropriation semantics.
- Add company equity, retained-earnings, reserve, and dividend reports.

Testing:

- Single/multiple share classes, partly paid or ineligible holdings where supported,
  insufficient reserves, cancelled declaration, unpaid dividend, withholding,
  rounding, shareholder changes, and duplicate declaration.
- Reconcile declaration, payable, payment, withholding, retained earnings, trial
  balance, P&L disclosures, and Balance Sheet.

Exit gate:

- Company distributions are independently certified and cannot use partner engines.

### Phase 10: HUF Capital And Allocation Engine

Status: Planned after Phase 9

Development:

- Add Karta/member roles, dated membership, approved allocation policy, capital and
  current-account treatment, and HUF-specific reporting.

Testing:

- Karta change, member join/exit, invalid role combinations, allocation boundaries,
  capital/drawings movements, approval, reversal, and report reconciliation.

Exit gate:

- HUF calculations use only approved HUF policies and resolve no partnership rules.

### Phase 11: Trust, Society, NGO, And Section 8 Fund Engine

Status: Planned after Phase 10

Development:

- Add corpus, restricted, unrestricted, designated, and grant fund policies.
- Add restriction release/transfer workflow and prohibit member profit distribution
  for non-distribution formations.
- Add fund-movement and restriction reconciliation reports.

Testing:

- Restricted grant receipt/use/release, corpus movement, purpose mismatch, deficit,
  expired restriction, unauthorized transfer, Section 8 distribution attempt,
  reversal, and consolidated fund reporting.

Exit gate:

- Fund balances reconcile to ledgers and prohibited owner/member distributions are
  blocked at service and API layers.

### Phase 12: Cooperative Distribution Engine

Status: Planned after Phase 11

Development:

- Add member capital, statutory reserve sequence, patronage basis, member dividend,
  caps, effective policy, approval, and reports.

Testing:

- Reserve ordering, cap boundaries, patronage volume, membership changes, insufficient
  surplus, duplicate member, withheld/unpaid amounts, reversal, and reconciliation.

Exit gate:

- Statutory sequence and member-level totals are reproducible and fully reconciled.

### Phase 13: Government/PSU Engine And Cross-Formation Certification

Status: Planned after Phase 12

Development:

- Add government equity, grant, reserve, and authorized surplus-transfer policies.
- Require authority/budget reference and controlled approvals.
- Complete strategy registry, operational documentation, and cross-formation health
  dashboard.

Testing:

- Grant/equity classification, restricted authority, budget mismatch, reserve and
  surplus transfer, cancellation, reversal, consolidated reporting, and audit export.
- Execute a cross-formation negative suite proving every formation rejects every
  incompatible policy, calculation, endpoint, posting, report, and direct object.

Exit gate:

- Every advertised formation has its own launch matrix and no cross-strategy posting
  or report-classification leakage exists.

## Minimum Scenario Matrix

Every calculation method must cover these dimensions using risk-based pairwise
combinations, plus exhaustive boundary tests for money, posting, and isolation:

| Dimension | Required scenarios |
| --- | --- |
| Constitution | Proprietorship, partnership, LLP, company, OPC, HUF, trust, society, NGO, Section 8, cooperative, government/PSU, unknown, contradictory |
| Strategy isolation | Every formation against every incompatible policy, calculation, posting, report, and direct-object endpoint |
| Stakeholders | 1, 2, 3+, join, retire/exit, inactive, renamed, role change |
| Ratio | 100, 60/40, three-way decimal, mid-period change, invalid total, overlap/gap |
| Result | Profit, loss, zero, adjusted profit, prior-period correction |
| Remuneration | None, fixed, periodic, formula, cap, prorated, overridden |
| Capital | Opening only, introduction, withdrawal, transfer, negative current balance |
| Capital interest | Opening, monthly weighted, daily weighted, rate change, leap year |
| Drawings | None, one, many, backdated, reversed, boundary date, mapped/unmapped |
| Cadence | Monthly, quarterly, annual, custom, overlapping run, adjustment run |
| Workflow | Draft, stale, submitted, approved, rejected, posted, reversed, cancelled |
| Scope | Entity, branch, consolidated branch, FY, closed period, foreign object ID |
| Access | Maker, checker, poster, read-only, restricted, self-approval attempt |
| Failure | Timeout, offline, duplicate click, stale version, concurrent post, server error |
| Reporting | Browser, PDF, XLSX, CSV, drilldown, empty, multipage, large/negative values |
| Funds/equity | Capital, current, retained earnings, reserves, share classes, corpus, restricted/unrestricted fund, grant, payable |

## Automation Strategy

### Backend

- Formation-resolution, model, and serializer validation tests.
- Pure calculation golden tests and property/invariant tests.
- Contract tests that every registered strategy implements readiness, validation,
  calculation, posting preview, report projection, and reconciliation.
- Service tests for snapshot, staleness, approval, posting, and reversal.
- API tests for lifecycle, scope, permissions, idempotency, and concurrency.
- Report and export reconciliation tests.

### Frontend

- Component tests for strategy-specific labels, relevant controls, calculations,
  states, validation, and permissions.
- Service tests for typed API contracts and structured error handling.
- Responsive tests for long partner names, large amounts, and dense component tables.

### Playwright

- Mocked deterministic UI/error suites for breadth.
- Real browser/database lifecycle suites for each certified formation.
- Cross-browser visual and accessibility certification.
- Post-run API/database assertions proving journals and reports, not only UI messages.

All test data must carry a unique run identifier and have a controlled cleanup or
retention policy. A skipped launch-critical test is an open coverage item, not a pass.

## Delivery Dependencies

1. Constitution evidence hierarchy and deterministic strategy resolution.
2. Formation-specific accounting decisions and configurable-policy defaults.
3. Valid stakeholder/fund data and strategy-specific ledger mappings.
4. Policy versioning before calculation.
5. Formation calculation engine before its posting UI is enabled.
6. Posting correctness before financial-report presentation.
7. Report reconciliation before migration or production activation.
8. Independent certification before advertising support for a formation.

## Confidence Tracking

Confidence is evidence-based and updated only after each exit gate:

| Area | Baseline | Current local evidence | Target |
| --- | ---: | ---: | ---: |
| Formation resolution and strategy isolation | 35% | 76% | 99% |
| Ownership and ratio history | 70% | 86% | 97% |
| Calculation correctness | 25% | 88% | 98% |
| Posting and reversal | 45% | 94% | 98% |
| P&L and Balance Sheet presentation | 40% | 95% | 97% |
| Permissions and isolation | 40% | 96% | 98% |
| UX and accessibility | 20% | 92% | 95% |
| Wave 1 partnership/LLP appropriation | 30% | 95% | 96%+ |
| Wave 1 proprietorship appropriation | 30% | 95% | 96%+ |
| Later-wave formation engines | 0% | 0% | 96%+ each |

Baseline reflects reusable foundations, not implemented formation engines. Confidence
is reported per formation and must never be averaged into a number that implies an
uncertified formation is supported. A formation score must not exceed 95% until real
staging postings reconcile through all relevant financial reports and reversal. It
must not exceed 96% until accessibility, cross-browser, concurrency, migration, and
recovery gates are complete.

## Initial Risks And Decisions Required

- Approve the constitution evidence hierarchy and handling of conflicting CIN,
  LLPIN, registration, constitution, and ownership data.
- Confirm whether partner remuneration is presented below operating profit in all
  book reports or whether an alternate statutory presentation is required.
- Confirm actual segmented profit as the default for ratio changes.
- Confirm whether loss ratio may differ from profit ratio.
- Confirm supported capital/drawing source transaction types and ledger mappings.
- Confirm whether branch-level appropriation is allowed or only entity-consolidated.
- Confirm destination current-account default and capital-account exceptions.
- Confirm maker-checker thresholds and who may reverse posted runs.
- Confirm initial statutory-policy ownership and update process.
- Confirm company share-class/dividend boundaries before Phase 9.
- Confirm HUF member/Karta data authority before Phase 10.
- Confirm trust/NGO fund restriction sources and non-distribution rules before Phase 11.
- Confirm cooperative statutory sequence before Phase 12.
- Confirm government/PSU authority and budget references before Phase 13.

These decisions are configuration and governance choices. They do not relax the
non-configurable accounting, audit, balance, and tenant-isolation invariants.
