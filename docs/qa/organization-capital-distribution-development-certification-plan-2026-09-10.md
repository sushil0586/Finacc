# Organization Capital, Appropriation, And Distribution Development Plan

Last updated: 10 September 2026

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

Status: Staging accounting, deployed UI, report, export, and reversal lifecycle certified; isolation and year-end gates pending

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
- Remaining before Phase 5 exit: post and reverse a controlled staging run and
  reconcile it independently to journals, Trial Balance, P&L, Balance Sheet, partner
  Ledger Book, year-end controls, and downloaded artifacts. Staging must also confirm
  permission/branch isolation and browser-export equality using production-like data.

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
  entity-context and capital-distribution backend tests pass. The disposable staging
  user and role were removed after certification; deployment and rerun of the two
  new header-context assertions remain pending.
- Remaining before Phase 5 exit: certify year-end/opening carry-forward and staging
  branch and permission isolation after deploying the shared context correction;
  complete staging Firefox/WebKit and manual
  assistive-technology review; and resolve or formally disposition the pre-existing
  Manav-T Balance Sheet imbalance.

### Phase 6: Tax Working And Policy Governance

Status: Planned

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

### Phase 7: Wave 1 Migration And Proprietorship Engine

Status: Planned

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

### Phase 8: Wave 1 Production Certification

Status: Planned

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
| Permissions and isolation | 40% | 82% | 98% |
| UX and accessibility | 20% | 88% | 95% |
| Wave 1 partnership/LLP appropriation | 30% | 95% | 96%+ |
| Wave 1 proprietorship appropriation | 30% | 45% | 96%+ |
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
