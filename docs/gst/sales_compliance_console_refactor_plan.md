# Sales Compliance Console Refactor Plan

## Objective

Reduce the weight of the current sales invoice compliance modal while keeping the end-to-end WhiteBooks flow accessible, reliable, and easy to extend.

The current compliance console in:

- `/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice-compliance/saleinvoice-compliance.component.html`
- `/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice-compliance/saleinvoice-compliance.component.ts`

mixes four different responsibilities in a single modal:

1. Invoice-level next-step guidance
2. Primary operational actions
3. Lookup and sync utilities
4. Advanced transit, registry, and reporting operations

This makes the invoice page feel heavy even when the user only needs one or two actions.

## Design Principle

The sales invoice page should support the normal workflow:

- understand current compliance state
- see the next recommended action
- complete the primary task with minimal clicks

Everything else should move to a dedicated compliance workspace or secondary surface.

## Proposed Information Architecture

### 1. Keep On Sales Invoice Page

Keep a compact `Compliance Overview` block on the invoice page or in a lightweight modal.

This block should contain only:

- compliance status badges
- stage and flow summary
- recommended next step
- key identifiers:
  - IRN
  - EWB number
  - Ack No / valid upto if available
- primary actions:
  - `Ensure`
  - `Generate IRN`
  - `Generate E-Way`
  - `Generate IRN + E-Way` only when relevant
  - `Cancel IRN`
  - `Cancel E-Way`
- one navigation action:
  - `Open Compliance Workspace`

### 2. Move To Compliance Workspace

Create a dedicated compliance workspace for sales invoices.

Suggested route patterns:

- `/saleinvoice/:id/compliance`
- or invoice drawer/tab opened from sale invoice page

Suggested tabs or sections:

1. `Overview`
2. `Lookup & Sync`
3. `E-Way Operations`
4. `Reports`
5. `Audit Log`

## Section Ownership

### Overview

Purpose:

- operational summary for current invoice
- actions most users need

Keep here:

- invoice id / doc / applicability tags
- stage
- flow
- recommended next step
- compact artifact summary
- recent high-level status
- primary action buttons

Do not keep here:

- long lists of report buttons
- specialist registry queries
- multi-vehicle administration

### Lookup & Sync

Purpose:

- support and verification tools

Move here:

- `IRN By Document`
- `GSTN Details`
- `Sync GSTIN`
- `B2C QR Code`
- `E-Way Details`
- `E-Way By Document`
- `Trip Sheet`
- `Error List`

Reason:

These are diagnostic or fetch utilities, not invoice-entry actions.

### E-Way Operations

Purpose:

- advanced transport and transit maintenance

Move here:

- `Update Vehicle`
- `Update Transporter`
- `Extend Validity`
- `Reject E-Way`
- `Consolidated E-Way`
- `Regenerate Trip Sheet`
- `Init Multi Vehicle`
- `Add Multi Vehicle`
- `Update Multi Vehicle`
- `Transporter Details`
- `GSTIN Details`
- `HSN Details`

Reason:

These are specialist logistics actions and should not compete with primary invoice actions.

### Reports

Purpose:

- transporter and cross-document reporting

Move here:

- `Transporter Bills`
- `Assigned Date Report`
- `Bills By Date`
- `Rejected By Others`
- `Bills By GSTIN`
- `Bills By State`
- `Other Party Bills`

Reason:

These are report workflows, not invoice workflows.

### Audit Log

Purpose:

- troubleshooting and support visibility

Move here:

- recent compliance actions timeline
- raw response/error summary if needed
- retry history / attempt count
- sync timestamps

Reason:

Operational history is important, but it should not dominate the primary action surface.

## Recommended Page Split

### Sales Invoice Page

Should answer:

- Is compliance applicable?
- What is the current state?
- What is the next action?
- Can I complete the main compliance task now?

Recommended visible content:

- `Compliance` launch button
- compact badges:
  - E-Invoice applicable
  - E-Way applicable
  - B2B/B2C
  - IRN state
  - EWB state
- compact summary card
- 3 to 6 primary buttons maximum

### Compliance Workspace

Should answer:

- What deeper actions are available?
- What data has already been synced?
- What registry or transport operations are possible?
- What reports exist for this invoice / transporter context?

## Proposed Component Strategy

### Current State

The current component combines:

- launcher
- console summary
- primary actions
- lookup utilities
- registry/transit actions
- reports
- details
- timeline
- action dialogs

in a single component.

### Target State

Refactor into smaller units:

1. `saleinvoice-compliance-launcher`
   - button + compact badges on invoice page

2. `saleinvoice-compliance-overview`
   - summary card and primary actions

3. `saleinvoice-compliance-workspace`
   - container for secondary tabs/sections

4. `saleinvoice-compliance-lookup`
   - lookup and sync actions

5. `saleinvoice-compliance-eway-ops`
   - advanced E-Way operations

6. `saleinvoice-compliance-reports`
   - reports and lists

7. `saleinvoice-compliance-audit`
   - artifact details, attempts, timeline

8. shared dialog/form components
   - action dialogs should remain centralized or be grouped by category

## Action Grouping Recommendation

### Primary Action Set

Use only these on the invoice page:

- `Ensure`
- `Generate IRN`
- `Generate E-Way`
- `Generate IRN + E-Way`
- `Cancel IRN`
- `Cancel E-Way`

Conditional visibility should continue to come from backend action flags.

### Secondary Action Set

Keep out of invoice page:

- prefill actions
- all lookup-only actions
- transporter/gstin/hsn registry actions
- all multi-vehicle actions
- report-generation actions
- trip sheet maintenance

## Data and Behavior Rules

### Backend Should Stay As Source Of Truth

Do not duplicate workflow decisions only in frontend.

Frontend should use backend-provided flags for:

- `can_generate_irn`
- `can_generate_eway`
- `can_cancel_irn`
- `can_cancel_eway`
- `recommended next step`
- applicability and stage

### UI Should Be Progressive

The user should see:

1. current status
2. next recommended action
3. only then advanced tools

### Avoid Action Flooding

No single visible section should contain more than 5 to 7 buttons before grouping or collapsing.

## Phased Implementation Plan

### Phase 1. Reduce Invoice Page Weight

Scope:

- keep existing backend APIs unchanged
- keep existing action dialogs unchanged
- reduce visible actions in current modal
- move non-primary action groups behind `Open Compliance Workspace`

Deliverables:

- compact compliance overview on invoice page
- primary actions only
- secondary navigation entry

### Phase 2. Introduce Dedicated Compliance Workspace

Scope:

- create workspace route or large drawer
- move lookup, transit, reports, audit sections out of invoice page

Deliverables:

- modular sections
- cleaner primary invoice experience
- no functional loss

### Phase 3. Component Decomposition

Scope:

- break current monolithic component into smaller standalone components
- centralize shared state and action dispatch

Deliverables:

- lower component complexity
- easier testing
- easier provider-specific evolution later

### Phase 4. Role-Based Simplification

Scope:

- expose advanced sections only for users with stronger compliance/logistics permissions

Deliverables:

- accountants see primary workflow
- logistics/compliance/admin users see advanced operations

## Suggested Rollout Order

1. Freeze current action list and group ownership
2. Build compact overview for invoice page
3. Move secondary groups into workspace without changing backend contracts
4. Refactor action dialogs by category
5. Add role-based visibility refinements

## Risks To Watch

### User Confusion During Transition

Mitigation:

- keep button labels unchanged initially
- add `Open Compliance Workspace`
- preserve current APIs and action names

### Broken Primary Workflow

Mitigation:

- do not move `Generate IRN`, `Generate E-Way`, `Cancel IRN`, `Cancel E-Way` in first pass
- keep current backend action gating intact

### Component State Drift

Mitigation:

- keep a single source for compliance status snapshot
- avoid duplicating fetch logic across subcomponents

## Definition Of Good Outcome

The refactor is successful when:

- invoice page shows only the minimum needed to act
- advanced tools remain available but not intrusive
- support and logistics operations become easier to find by category
- the WhiteBooks flow remains unchanged functionally
- future provider switching does not require another UI rewrite

## Immediate Execution Recommendation

Start with a low-risk split:

1. Keep `Overview` in current sale invoice flow
2. Move `Lookup & Sync`, `Registry & Transit Ops`, `Reports & Lists`, and `Recent Compliance Actions` into a separate workspace
3. Reuse current action APIs and dialog payloads
4. Refactor component boundaries only after the UX split is accepted

