# Entity Formation Onboarding E2E Verification Plan

Date: 2026-09-25  
Scope: Entity onboarding, entity master maintenance, ownership/partner details, organization structure, setup seeding, and downstream finance readiness.

## Objective

Verify that every supported entity formation can be created, edited, corrected, and used in the ERP without broken screens, missing menus, failed CRUD operations, stale validation messages, or layout/design regressions.

This plan covers the full workflow from first onboarding through post-onboarding setup and accounting readiness. It is intentionally workflow-first: each scenario must prove that the entity can move from setup data to operational use.

## Entity Formation Matrix

| Formation | Expected status | Main data to verify | Downstream expectation |
|---|---:|---|---|
| Proprietorship | Wave 1 supported | One proprietor, 100% ownership, PAN/reference optional warning | Capital distribution can resolve, prepare, enable, calculate, post |
| Partnership | Wave 1 supported | Partner rows, shares total 100%, deed/reference | Capital distribution can resolve, prepare, enable, calculate, post |
| LLP | Wave 1 supported | LLPIN/constitution signal, partner rows total 100% | Capital distribution behaves like partnership strategy |
| Company | Recognized, not Wave 1 capital distribution | CIN/company constitution, directors/shareholders | Entity onboarding works; capital distribution shows unsupported strategy clearly |
| OPC | Recognized, not Wave 1 capital distribution | CIN/OPC constitution, one member/director | Entity onboarding works; unsupported message is clear |
| Section 8 Company | Recognized, not Wave 1 capital distribution | CIN/Section 8 constitution | Entity onboarding works; no partnership-only actions enabled |
| HUF | Recognized, not Wave 1 capital distribution | Karta/member-style ownership where available | Entity onboarding works; unsupported message is clear |
| Trust | Recognized, not Wave 1 capital distribution | Trustee rows, registration/reference | Entity onboarding works; unsupported message is clear |
| Society | Recognized, not Wave 1 capital distribution | Society constitution/member rows | Entity onboarding works; unsupported message is clear |
| NGO | Recognized, not Wave 1 capital distribution | NGO business type/constitution | Entity onboarding works; unsupported message is clear |
| Cooperative | Recognized, not Wave 1 capital distribution | Cooperative constitution/member rows | Entity onboarding works; unsupported message is clear |
| Government Entity | Recognized, not Wave 1 capital distribution | Government business type | Entity onboarding works; unsupported message is clear |
| PSU | Recognized, not Wave 1 capital distribution | PSU/company evidence | Entity onboarding works; unsupported message is clear |
| Unconfigured | Negative case | No constitution or ownership signal | Must show actionable validation, not crash |
| Contradictory evidence | Negative case | Conflicting CIN/LLPIN/ownership/constitution | Must block governed workflows with exact correction message |

## Formation-Wise Phase Plan

Use this section as the execution checklist. Each entity type should be tested independently with fresh data, screenshots, API evidence, and UX notes.

### Common Phases For Every Entity Type

Every formation follows these phases first:

| Phase | Name | Screens | Goal |
|---|---|---|---|
| 0 | Preflight | Login, menu, entity selector | Confirm user, permissions, menu routes, and seed data |
| 1 | Onboarding create | Public/internal onboarding wizard | Create entity with formation-specific identity, FY, branch, bank, ownership data |
| 2 | Entity master maintenance | Entity & Partner Details, Dashboard entity editor | Verify create/read/update/delete for ownership, legal, branch, bank, FY fields |
| 3 | Organization setup | Organization Structure | Verify org unit CRUD, hierarchy, validation, mobile layout |
| 4 | Business setup | Business Settings, Branch, Static Account Settings | Verify module settings, static account mapping, and branch/account readiness |
| 5 | Formation resolution | Capital & Distribution | Resolve formation and verify expected supported/unsupported behavior |
| 6 | Finance readiness | Accounts, Posting Setup, Reports | Verify accounting setup and downstream report behavior |
| 7 | RBAC/isolation | Menu/direct route/API | Verify role-based access, cross-entity denial, branch scope |
| 8 | UX certification | All screens | Review screenshots for alignment, clarity, responsiveness, and user friendliness |

### Proprietorship

**Goal:** one proprietor entity should complete onboarding and full Wave 1 capital distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with proprietorship constitution/business evidence | Entity saves and dashboard opens |
| 2 | Add exactly one `Proprietor` ownership row; share `100%`; effective date covers FY | Ownership persists after refresh |
| 3 | Create head office and at least one org unit | Org structure works |
| 4 | Map bank/account/static accounts, especially Profit and Loss Appropriation | Posting readiness can pass |
| 5 | Resolve formation | `proprietorship`, verified |
| 5 | Prepare Wave 1 | Draft policy generated with proprietor 100% |
| 5 | Submit/approve policy | Approved policy available |
| 5 | Map proprietor capital/current/drawings account | Mapping readiness ready |
| 5 | Enable capital distribution | Activation enabled |
| 6 | Calculate, submit, approve, post appropriation run | Balanced journal posted |
| 6 | Reverse posted run with reason | Reversal journal posted |
| 8 | Screenshots for every state | No alignment or usability defects |

Negative cases:

- Two proprietor rows should block readiness.
- Proprietor share not equal to `100%` should show actionable validation.
- Missing Profit and Loss Appropriation mapping should block posting, not calculation review.

### Partnership

**Goal:** partner entity should complete onboarding and full partner appropriation workflow.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with partnership constitution/business evidence | Entity saves and dashboard opens |
| 2 | Add two or more `Partner` ownership rows | Rows persist |
| 2 | Partner shares total exactly `100%` | Formation readiness passes |
| 2 | Add PAN/reference where available | Missing values show warning, not hard crash |
| 4 | Map static accounts and partner ledgers | Posting readiness can pass |
| 5 | Resolve formation | `partnership`, verified |
| 5 | Prepare Wave 1 | Draft policy generated from partner shares |
| 5 | Configure profit/loss %, remuneration, interest on capital, interest on drawings | Save draft works |
| 5 | Submit/approve policy with maker-checker | Maker cannot approve own policy |
| 5 | Map each partner capital/current/drawings account | Mapping readiness ready |
| 5 | Enable capital distribution | Activation enabled |
| 6 | Calculate from posted books | Run lines show remuneration/interest/residual allocation |
| 6 | Submit/approve/post run | Balanced journal posted |
| 6 | Statement reconciliation | Posted run reconciled |
| 6 | Tax policy/tax working optional path | Working calculates from posted run |
| 8 | Screenshots for every state | No alignment or usability defects |

Negative cases:

- Partner shares total `99%` or `101%` should block policy/readiness.
- Missing partner mapping should block submit/post.
- Overlapping submitted/approved/posted run should be blocked.
- Changed source books after calculation should require recalculation.

### LLP

**Goal:** LLP should behave like partnership strategy but resolve from LLP evidence.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with LLP constitution or LLPIN evidence | Entity saves |
| 2 | Add partner rows with shares totaling `100%` | Ownership persists |
| 3 | Organization units and branches save | Setup works |
| 4 | Static accounts and ledgers mapped | Posting readiness can pass |
| 5 | Resolve formation | `llp`, verified |
| 5 | Prepare Wave 1 | Draft LLP appropriation policy generated |
| 5 | Configure terms/ratios | Save/submit/approve works |
| 5 | Enable capital distribution | Activation enabled |
| 6 | Calculate/post/reverse run | Journals balanced |
| 8 | Screenshots for every state | No design defects |

Negative cases:

- LLPIN plus conflicting company/partnership evidence should show contradiction.
- Missing partner shares should block Wave 1 readiness.

### Company

**Goal:** company onboarding and setup should work, while partnership-style capital distribution is not enabled.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with company/private limited/public limited constitution or CIN | Entity saves |
| 2 | Add director/shareholder rows | Rows persist |
| 3 | Organization units work | Hierarchy saves |
| 4 | Business settings, branches, bank accounts, static mappings work | Setup usable |
| 5 | Resolve formation in Capital & Distribution | `company` recognized |
| 5 | Wave 1 capital distribution | Disabled with clear unsupported strategy message |
| 6 | Normal accounts/vouchers/reports work | No dependency on capital distribution |
| 8 | Screenshots | Unsupported state is understandable |

Negative cases:

- Company should not create partner policy.
- Company should not show misleading partner/proprietor action labels.

### One Person Company

**Goal:** OPC setup should work as company-like entity, with no Wave 1 capital distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with OPC constitution/evidence | Entity saves |
| 2 | Add director/shareholder or member row | Rows persist |
| 3 | Organization and branches save | Setup works |
| 5 | Resolve formation | `opc` recognized |
| 5 | Capital distribution | Unsupported message; Wave 1 actions disabled |
| 8 | Screenshots | Clear, aligned, no irrelevant partner workflow |

### Section 8 Company

**Goal:** Section 8 company should onboard cleanly and be recognized as unsupported for Wave 1 distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity with Section 8/company evidence | Entity saves |
| 2 | Add directors/members/shareholders as applicable | Rows persist |
| 4 | Business settings and static setup work | Setup usable |
| 5 | Resolve formation | `section_8` recognized |
| 5 | Capital distribution | Unsupported message; no invalid enable path |
| 8 | Screenshots | Professional unsupported-state guidance |

### HUF

**Goal:** HUF should onboard and operate normally, while capital distribution remains unsupported in Wave 1.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create HUF formation evidence | Entity saves |
| 2 | Add Karta/member ownership-style rows if supported by dropdowns | Rows persist or unsupported row type is clearly handled |
| 3 | Org/branch setup works | Setup complete |
| 5 | Resolve formation | `huf` recognized |
| 5 | Capital distribution | Unsupported strategy message |
| 8 | Screenshots | No layout issues |

### Trust

**Goal:** trust should support entity setup and trustee details without Wave 1 appropriation.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create trust evidence | Entity saves |
| 2 | Add trustee rows | Rows persist |
| 3 | Organization structure works | Units save |
| 4 | Business settings and accounts work | Setup usable |
| 5 | Resolve formation | `trust` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | Trustee wording is not confused with partner workflow |

### Society

**Goal:** society should onboard and operate normally with unsupported Wave 1 capital distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create society evidence | Entity saves |
| 2 | Add member/other ownership rows as available | Rows persist |
| 3 | Organization units work | Setup works |
| 5 | Resolve formation | `society` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | Layout/copy clear |

### NGO

**Goal:** NGO should onboard and operate normally; capital distribution should not expose partnership posting.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create NGO business type/constitution | Entity saves |
| 2 | Add trustee/member/other rows if needed | Rows persist |
| 3 | Organization and branch setup work | Setup complete |
| 5 | Resolve formation | `ngo` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | No misleading profit distribution action |

### Cooperative

**Goal:** cooperative should onboard and be recognized, but Wave 1 distribution is disabled.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create cooperative constitution/evidence | Entity saves |
| 2 | Add member/shareholder rows | Rows persist |
| 3 | Org/business settings work | Setup usable |
| 5 | Resolve formation | `cooperative` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | Clear disabled state |

### Government Entity

**Goal:** government entity should onboard and run operational setup without private-owner distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create government business type/evidence | Entity saves |
| 2 | Ownership rows optional or government/other rows save if used | No forced partner setup |
| 3 | Organization structure works | Setup complete |
| 4 | Business settings/static accounts work | Setup usable |
| 5 | Resolve formation | `government` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | No owner-profit language where inappropriate |

### PSU

**Goal:** PSU should onboard as company/government-like formation and avoid Wave 1 distribution.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create PSU evidence | Entity saves |
| 2 | Add government/shareholder/director rows as applicable | Rows persist |
| 3 | Org/business setup works | Setup usable |
| 5 | Resolve formation | `psu` recognized |
| 5 | Capital distribution | Unsupported message |
| 8 | Screenshots | Correct copy and layout |

### Unconfigured Entity Negative Case

**Goal:** prove incomplete setup is friendly and actionable.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create entity without constitution/ownership signals | Entity can exist if allowed |
| 5 | Open Capital & Distribution | Shows `Organization formation is not configured` |
| 5 | Resolve formation | Remains blocked until entity data is added |
| 2 | Add missing ownership/constitution data | Validation disappears after correction |
| 8 | Screenshots | Error state clearly tells user where to fix |

### Contradictory Evidence Negative Case

**Goal:** prove conflicting setup is blocked before accounting actions.

| Phase | What to verify | Expected result |
|---|---|---|
| 1 | Create conflicting evidence, such as CIN + LLPIN or company constitution + partner ownership | Entity saves only if base entity policy allows |
| 5 | Resolve formation | Contradictory formation status |
| 5 | Prepare/enable Wave 1 | Blocked |
| 2 | Correct conflicting data | Formation resolves correctly |
| 8 | Screenshots | Conflict message identifies correction path |

## Suggested Execution Order

Run in this order so defects are easier to isolate:

1. Unconfigured negative case
2. Proprietorship
3. Partnership
4. LLP
5. Company
6. OPC
7. Section 8
8. Trust
9. HUF
10. Society
11. NGO
12. Cooperative
13. Government Entity
14. PSU
15. Contradictory evidence negative case

Stop after each formation, log defects, and only move to the next formation after confirming whether the issue is formation-specific or shared across onboarding.

## Screen Inventory

Every formation scenario must verify these screens where relevant:

| Screen | Route | What to prove |
|---|---|---|
| Public signup/onboarding | `/#/register` or public wizard route | New entity can be created with formation-specific data |
| Dashboard entity workspace | `/#/dashboard` | Entity cards load; edit opens entity master; context persists |
| Entity & Partner Details | `/#/entity-partner-details` | Opens Ownership tab directly; ownership CRUD works |
| Organization Structure | `/#/hrms/organization-units` | Organization unit CRUD works after onboarding |
| Business Settings | `/#/businesssettings` | Module settings load/save/reset independently |
| Branch workspace | `/#/branch` | Branch CRUD works; head office remains valid |
| Posting Setup / Static Account Settings | `/#/staticaccountsettings` | Required static accounts can be mapped |
| Capital & Distribution | `/#/capital-distribution-setup` | Supported formations complete Wave 1; unsupported formations show correct blocker |
| Reports / Balance Sheet / P&L | report routes | Capital distribution disclosure reconciles where posted |

## End-To-End Workflow

### 1. Preflight And Data Isolation

Verify before every run:

- Test user has Entity Super Admin access.
- Entity context switcher updates `entity`, `financial year`, and branch correctly.
- Browser session storage can be cleared without breaking menu reload.
- Test data uses unique entity names and GST/PAN placeholders.
- Seed data exists for countries, states, districts, cities, financial year defaults, chart of accounts, static account masters, RBAC menus, and module settings.

Acceptance:

- Login works.
- Menus include `Entity & Partner Details`, `Organization Structure`, `Business Settings`, and `Capital & Distribution`.
- No stale menu route sends the user to the wrong screen.

### 2. Create Entity Through Onboarding

For each formation:

1. Start onboarding.
2. Enter account/user details.
3. Enter business identity:
   - business name
   - legal name
   - constitution
   - business type
   - statutory identifiers where applicable
4. Enter GST/address details:
   - registered GST case
   - unregistered/non-GST case
   - invalid GST negative case
5. Enter compliance credentials where enabled.
6. Enter financial year.
7. Enter head office branch.
8. Enter bank accounts.
9. Enter ownership/partner/shareholder/trustee rows.
10. Review normalized payload.
11. Submit.

Acceptance:

- Required validations appear next to the correct fields.
- Optional missing data creates warnings, not hard failures, where policy says soft.
- Backend validation messages map back to the right screen section.
- Created entity appears in dashboard.
- Active financial year and head office are selected correctly.
- No duplicate entity, duplicate branch, or partial entity is created on retry.

### 3. Entity Master Maintenance CRUD

Run after initial onboarding.

For each formation:

- Update entity identity fields.
- Update legal/statutory identifiers.
- Add/edit/delete branch rows.
- Add/edit/delete bank accounts.
- Add/edit/delete ownership rows.
- Save with invalid ownership share.
- Save with corrected ownership share.
- Save with effective date gaps.
- Save with corrected effective dates.

Formation-specific ownership checks:

- Proprietorship: exactly one proprietor; share 100% or blank treated as allowed only if business rule allows.
- Partnership/LLP: at least one partner; shares total exactly 100%.
- Company/OPC/Section 8/PSU: shareholder/director rows should save; capital distribution should not treat them as Wave 1 partners.
- Trust: trustee rows save.
- Society/NGO/Cooperative: member/other rows save according to available dropdowns.
- Contradictory case: mixed proprietor + partner + company evidence should show conflict.

Acceptance:

- CRUD persists after refresh.
- Deleted rows do not reappear.
- Effective dates survive reload.
- Capital distribution formation resolution changes after correcting entity master data.
- Save button state, loading, validation, and success notifications are consistent.

### 4. Organization Structure Workflow

For each entity after onboarding:

- Open Organization Structure.
- Create root organization unit.
- Create child department/location/cost center.
- Edit name/code/parent.
- Attempt invalid parent cycle.
- Deactivate/delete where supported.
- Verify search/filter/list state.

Acceptance:

- CRUD works in selected entity only.
- No cross-entity unit leakage.
- Parent/child display remains readable.
- Empty state and validation state are clear.
- Mobile and desktop layouts do not overlap.

### 5. Business Settings Workflow

For each entity:

- Open Business Settings.
- Switch modules: Financial, Sales, Purchase, Payments, Receipts, Vouchers, Assets.
- Edit one setting per module.
- Reset current module.
- Save module.
- Save all changes.
- Switch financial year and branch.
- Verify scope-specific settings do not leak.

Acceptance:

- Dirty indicators are accurate.
- Reset only resets intended scope/module.
- Save handles backend errors without losing edits.
- The page is not confused with Entity & Partner Details.
- Design remains aligned across desktop and mobile.

### 6. Posting Setup And Accounting Readiness

For each finance-enabled entity:

- Verify baseline chart of accounts exists.
- Verify ledger/account CRUD after onboarding.
- Verify static account mappings:
  - Profit and Loss Appropriation
  - trade receivables/payables where applicable
  - cash/bank defaults
- Verify branch/global mapping behavior.

Acceptance:

- Missing static account shows actionable message.
- Saving mapping persists after refresh.
- Capital distribution readiness recognizes the mapping.

### 7. Capital Distribution Workflow

Run this only for Wave 1 formations: proprietorship, partnership, LLP.

Steps:

1. Open Capital & Distribution.
2. Resolve formation.
3. Confirm formation profile becomes verified.
4. Prepare Wave 1.
5. Review generated draft policy.
6. Edit terms/ratios:
   - profit %
   - loss %
   - remuneration
   - interest on capital
   - interest on drawings
7. Save draft.
8. Submit policy.
9. Approve policy with a different user where maker-checker is enforced.
10. Map posting accounts.
11. Enable capital distribution.
12. Calculate run from posted books.
13. Calculate run with manual approved amount.
14. Submit run.
15. Approve run.
16. Post journals.
17. Verify statement reconciliation.
18. Reverse with reason.
19. Verify reversal journal and statement.

Acceptance:

- Each validation disappears after the correct data is fixed.
- Buttons are enabled only when permission and readiness allow.
- Overlapping submitted/approved/posted runs are blocked.
- Source-change detection forces recalculation.
- Posting creates balanced journals.
- Reversal requires reason.
- Audit/health captures failures and correlation IDs.

### 8. Unsupported Formation Capital Distribution Checks

Run for company, OPC, Section 8, HUF, trust, society, NGO, cooperative, government, PSU.

Acceptance:

- Formation resolves to recognized type.
- Capital distribution shows unsupported strategy message.
- Wave 1 buttons remain disabled.
- User can still use normal entity, branch, organization, business settings, vouchers, reports, and module workflows.
- No partnership/proprietor wording appears where misleading.

### 9. Tax Policy And Tax Working Workflow

Run after a posted Wave 1 appropriation run.

Steps:

- Create tax policy draft.
- Verify statutory reference required.
- Configure rules for remuneration, capital interest, drawing interest, residual profit/loss.
- Submit and approve tax policy.
- Calculate tax working from posted run.
- Override line with evidence.
- Verify reproduction.
- Export PDF/XLSX/CSV.
- Submit and approve tax working.
- Reverse tax working with reason.

Acceptance:

- Missing rules are blocked.
- Overrides require reason and evidence.
- Reproduction hash must pass before approval.
- Exports download valid files.

### 10. RBAC And Access Verification

Roles to verify:

- Entity Super Admin
- Admin
- Accounts Manager
- Read-only finance/report user
- Restricted branch user
- User without setup access

Checks:

- Menu visibility matches role.
- Direct route access is blocked when permission is absent.
- CRUD buttons hide/disable correctly.
- Backend denies unauthorized API calls.
- Cross-entity IDs are rejected.
- Branch-scoped users cannot mutate all-branch/global data unless allowed.

### 11. UI, Design, And Accessibility Verification

Every screen in this plan must pass:

- Desktop viewport: 1440 x 900.
- Laptop viewport: 1280 x 800.
- Tablet viewport: 768 x 1024.
- Mobile viewport: 390 x 844.
- No text overlap.
- No button text clipping.
- Sticky headers/footers do not hide form fields.
- Tables scroll horizontally only where needed.
- Empty/error/loading states are polished.
- Keyboard focus is visible.
- Dialogs trap focus and close correctly.
- Forms remain usable at 125% browser zoom.
- Basic axe accessibility scan has no serious/critical violations.

## Screenshot And UX Evidence Protocol

Screenshots are mandatory for every workflow test. The tester must review each screenshot from an end-user point of view, not only from a technical pass/fail point of view.

### Required Viewports

Capture every core screen at:

| Viewport | Size | Purpose |
|---|---:|---|
| Desktop | 1440 x 900 | Normal finance/admin workstation |
| Laptop | 1280 x 800 | Common business laptop |
| Tablet | 768 x 1024 | Narrow setup review |
| Mobile | 390 x 844 | Emergency correction / mobile approval |

### Screenshot Naming

Use this naming format:

```text
{phase}-{formation}-{workflow}-{screen}-{state}-{viewport}.png
```

Examples:

```text
phase1-partnership-onboarding-ownership-empty-desktop.png
phase1-partnership-onboarding-ownership-saved-desktop.png
phase3-llp-capital-distribution-policy-approved-laptop.png
phase3-proprietorship-capital-distribution-run-posted-desktop.png
phase4-company-capital-distribution-unsupported-mobile.png
```

### Required Page States

For each screen, capture these states where applicable:

| State | What to capture |
|---|---|
| Initial load | Page after data loads, with no interaction |
| Empty state | No rows/no setup data available |
| Validation state | Required or invalid field messages visible |
| Edit state | Form with user-entered values before save |
| Saved state | Data persisted and visible after refresh |
| Error state | API/business error shown to user |
| Permission restricted state | Buttons hidden/disabled or access denied |
| Mobile state | Same page without clipped/overlapping controls |

### Page-By-Page Screenshot Checklist

| Screen | Required screenshots |
|---|---|
| Public onboarding | each wizard step, validation, review, success |
| Dashboard entity workspace | entity card list, edit dialog, post-save state |
| Entity & Partner Details | initial ownership tab, add row, validation, saved ownership rows |
| Organization Structure | empty tree/list, create modal/form, saved hierarchy, invalid parent/cycle error |
| Business Settings | module list, dirty state, saved state, reset state, mobile layout |
| Branch workspace | branch list, add/edit branch, head office indicator, validation |
| Bank accounts | empty, add, edit, saved, delete/deactivate state |
| Static Account Settings | missing mapping, selected mapping, saved mapping |
| Capital & Distribution | migration blockers, resolved formation, policy draft, policy approved, mappings ready, calculated run, posted run, statement reconciliation, reverse state |
| Tax Policies | draft, validation, approved policy |
| Tax Working | calculated working, override form, reproduction passed, exported/approved state |
| Unsupported formation | resolved unsupported formation and disabled Wave 1 actions |
| RBAC denied | menu hidden/direct route denied/API error state |

### UX Review Rubric

For every screenshot, mark each item `Pass`, `Fail`, or `Needs design review`.

| UX item | Expected behavior |
|---|---|
| Screen purpose is obvious | User can tell what the page is for within five seconds |
| Primary next action is clear | User knows what to do next without reading a manual |
| Validation is actionable | Message tells what to fix and where |
| Buttons are aligned | Actions do not jump, clip, overlap, or appear disconnected |
| Form grouping is logical | Related fields are near each other |
| Tables are readable | Columns fit or scroll predictably |
| Empty states are useful | Empty page explains what to create next |
| Loading states are calm | No broken blank page while API is running |
| Save feedback is visible | User sees success/failure clearly |
| Mobile remains usable | No clipped text, hidden buttons, or impossible horizontal scrolling |
| Copy matches user language | Avoids internal-only terms where business wording is better |
| Critical actions feel controlled | Approval, posting, reversal, delete/deactivate require appropriate confirmation/reason |

### Screenshot Storage

Store manual and automated evidence under:

```text
docs/qa/evidence/entity-formation-onboarding/2026-09-25/
```

Recommended subfolders:

```text
screenshots/
network/
api-payloads/
accessibility/
notes/
```

Each run should include a short `run-summary.md` with:

- tester name
- date/time
- build/commit
- browser
- entity formation
- pass/fail summary
- links to screenshots
- defects found
- retest status

### Automated Screenshot Requirements

Playwright tests should call `page.screenshot()` or `expect(page).toHaveScreenshot()` at each major workflow checkpoint.

Minimum automated screenshot checkpoints:

- onboarding review screen for every formation
- Entity & Partner Details ownership tab for every Wave 1 formation
- Organization Structure saved hierarchy
- Business Settings saved module
- Capital Distribution blocker state
- Capital Distribution ready/enabled state
- Capital Distribution posted statement
- unsupported formation state
- mobile layout for the three most important screens:
  - Entity & Partner Details
  - Capital & Distribution
  - Business Settings

Automated screenshots must be reviewed manually before signoff; screenshot generation alone is not enough.

### 12. CRUD Coverage Matrix

| Domain | Create | Read | Update | Delete/Deactivate | Negative validation |
|---|---:|---:|---:|---:|---:|
| Entity identity | Yes | Yes | Yes | No/controlled | Yes |
| Financial year | Yes | Yes | Yes | Deactivate where allowed | Yes |
| Branch/subentity | Yes | Yes | Yes | Yes | Yes |
| Bank account | Yes | Yes | Yes | Yes | Yes |
| Ownership/partner rows | Yes | Yes | Yes | Yes | Yes |
| Organization units | Yes | Yes | Yes | Yes | Yes |
| Business settings | Yes/save | Yes | Yes | Reset | Yes |
| Static account mapping | Yes | Yes | Yes | Replace/deactivate where supported | Yes |
| Distribution policy | Seed/create | Yes | Draft only | Supersede/reject | Yes |
| Distribution run | Calculate | Yes | Lifecycle only | Reverse | Yes |
| Tax policy | Yes | Yes | Draft only | Supersede/reject | Yes |
| Tax working | Calculate | Yes | Override only | Reverse | Yes |

## Automation Plan

### Backend Tests

Add tests for:

- formation resolver for every formation type
- contradictory evidence
- ownership percentage validation
- onboarding create/update idempotency
- entity isolation
- capital distribution readiness
- Wave 1 activation
- policy/run maker-checker
- posting/reversal journal balance

### Frontend Unit Tests

Add tests for:

- entity master section navigation
- ownership row add/edit/remove
- new `entity-partner-details` route wrapper
- validation section routing
- business settings dirty/reset/save behavior
- capital distribution button enablement

### Playwright Browser Tests

Create a new spec group:

```text
playwright/tests/entity-formation-onboarding-e2e.spec.ts
playwright/tests/entity-formation-post-onboarding-workflows.spec.ts
playwright/tests/entity-formation-capital-distribution.spec.ts
```

Browser scenarios:

- smoke all formation routes with mocked APIs
- full Wave 1 proprietorship
- full Wave 1 partnership
- full Wave 1 LLP
- unsupported company/HUF/trust cases
- RBAC direct route denial
- mobile screenshots for core setup screens

## Execution Phases

### Phase 0: Baseline Discovery

- Inventory current routes, menus, permissions, APIs, and test coverage.
- Confirm all formation dropdown options exist.
- Confirm current onboarding payload contract.
- Confirm seed requirements.

Exit criteria:

- Data matrix finalized.
- Missing route/menu/permission issues listed.

### Phase 1: Entity Master And Onboarding

- Verify create/edit flows for all formation types.
- Fix broken field mappings and validation placement.
- Add/repair browser tests for onboarding and Entity & Partner Details.

Exit criteria:

- All formation entities can be created and edited.
- Ownership rows persist correctly.

### Phase 2: Setup Workflows

- Verify branch, organization structure, business settings, bank accounts, and static account mappings.
- Fix CRUD and layout issues.

Exit criteria:

- Post-onboarding setup works without manual DB fixes.

### Phase 3: Capital Distribution

- Verify proprietorship, partnership, and LLP end to end.
- Verify unsupported formations fail gracefully.
- Verify posting/reversal/reconciliation.

Exit criteria:

- Wave 1 formations can reach posted/reversed run.
- Unsupported formations show correct guidance.

### Phase 4: RBAC, Isolation, And Recovery

- Verify roles, direct API denial, cross-entity denial, branch scope, retry, stale sessions, and failed saves.

Exit criteria:

- No restricted user can access or mutate unauthorized data.
- Failed operations recover without corrupting setup.

### Phase 5: Design And Certification

- Run visual, responsive, accessibility, and copy checks.
- Capture screenshots for key states.
- Produce signoff report with pass/fail/evidence.

Exit criteria:

- All P0/P1 workflows pass.
- Known issues are triaged with severity and owner.

## Evidence To Capture

For each scenario:

- Entity name/id.
- Formation type.
- Financial year.
- Browser.
- User/role.
- Screens visited.
- CRUD actions performed.
- API failures, if any.
- Screenshots for before/after important saves.
- Journal batch id for posted capital distribution runs.
- Audit/correlation id for failed operations.

## Definition Of Done

The onboarding flow is certified when:

- Every formation in the matrix has a documented pass/fail result.
- Supported Wave 1 formations complete capital distribution through posting and reversal.
- Unsupported formations show clear guidance and do not expose invalid actions.
- Every setup screen has working CRUD or explicitly documented read-only behavior.
- Menus route to the correct screens.
- All role and cross-entity checks pass.
- Desktop/mobile design is clean, aligned, and accessible.
- Automated backend, frontend, and Playwright tests exist for the critical workflows.
