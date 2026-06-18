# Sales Compliance Button State Matrix

## Objective

Define the button-state contract for the sales invoice compliance UI so frontend behavior stays consistent even when backend action flags are stale or optimistic.

This note applies to the Angular compliance surface implemented in:

- `/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice-compliance/saleinvoice-compliance.component.ts`

## Core Rule

Backend action flags are advisory.

Frontend must always clamp mutating actions against the actual artifact state already present on the invoice:

- if IRN is already generated, IRN generation actions must be disabled
- if E-Way is already active/generated, E-Way generation and prefill actions must be disabled
- if E-Way is active/generated, `Cancel IRN` must be disabled
- if E-Way is active/generated, E-Way maintenance actions may remain enabled

This prevents duplicate generation flows when provider sync and UI state are briefly out of step.

## Canonical State Inputs

The current UI derives its state from:

- `complianceState.irn`
- `complianceState.eway`
- `isB2CInvoice`
- `isEwayApplicable`
- backend `action_flags`

The following computed booleans are the canonical gatekeepers:

- `isIrnGenerated`
- `isEwayActive`
- `canGenerateIrn`
- `canGenerateIrnAndEway`
- `canGenerateEwayB2B`
- `canGenerateEwayB2C`
- `canLoadEwayPrefill`
- `canLoadEwayB2CPrefill`
- `canCancelIrn`
- `canCancelEway`
- `canUpdateVehicle`
- `canUpdateTransporter`
- `canExtendValidity`

## Button Contract

### Overview Surface

`Ensure`

- enabled when compliance actions are allowed for the user
- not tied to IRN/EWB artifact state

`Generate IRN + E-Way`

- enabled only for B2B or other non-B2C invoices
- requires E-Way applicability
- requires IRN not generated
- requires E-Way not active

`Generate IRN only`

- enabled only when IRN is not already generated

`Generate E-Way`

- enabled for B2B only when IRN is generated and E-Way is not active
- enabled for B2C only when the invoice is B2C and E-Way is not active

Important:

- prefill availability must not keep the overview generate button enabled after E-Way is already generated

`Cancel IRN`

- enabled only when IRN is generated and E-Way is not active

`Cancel E-Way`

- enabled only when E-Way is active/generated

`Open Compliance Workspace`

- always enabled once the invoice compliance surface is accessible

### Workspace Quick Actions

`IRN Details`

- enabled when IRN is generated

`E-Way by IRN`

- enabled when IRN is generated

`E-Way Prefill`

- enabled only for non-B2C invoices where IRN is generated and E-Way is not active

`B2C Prefill`

- enabled only for B2C invoices where E-Way is not active

### Workspace E-Way Operations

The following are enabled only when E-Way is active/generated:

- `Update Vehicle`
- `Update Transporter`
- `Extend Validity`

The remaining lookup/report utilities may still depend on broader lookup permissions, but they should not be shown as primary invoice next-step actions.

## Recommended State Matrix

### 1. Initial

Conditions:

- IRN not generated
- E-Way not generated

Expected behavior:

- `Generate IRN` enabled for B2B
- `Generate IRN + E-Way` enabled for B2B when applicable
- `Generate E-Way` disabled for B2B
- `Generate E-Way` enabled for B2C only if direct B2C E-Way flow is valid
- all cancel actions disabled

### 2. IRN Generated, E-Way Pending

Conditions:

- IRN generated
- E-Way not generated

Expected behavior:

- `Generate IRN` disabled
- `Generate IRN + E-Way` disabled
- `Generate E-Way` enabled when applicable
- `E-Way Prefill` enabled when applicable
- `Cancel IRN` enabled
- `Cancel E-Way` disabled

### 3. Both Generated

Conditions:

- IRN generated
- E-Way generated/active

Expected behavior:

- all generate actions disabled
- all prefill actions disabled
- `Cancel IRN` disabled
- `Cancel E-Way` enabled
- `Update Vehicle` enabled
- `Update Transporter` enabled
- `Extend Validity` enabled
- recommended next step should move toward sync or maintenance, not generation

### 4. E-Way Cancelled After Earlier Generation

Conditions:

- IRN generated
- E-Way not active

Expected behavior:

- behave like `IRN Generated, E-Way Pending`
- re-generation may be allowed depending on provider/state rules

## Defensive Frontend Principle

If backend flags say an action is allowed but the invoice artifacts already prove the action is no longer valid, the frontend should disable the action.

This is especially important for:

- `can_generate_irn`
- `can_generate_irn_and_eway`
- `can_generate_eway`
- `can_load_eway_prefill`
- `can_cancel_irn`

These flags should never override an already-generated IRN/EWB artifact on the screen.

## Current Regression Coverage

The current spec coverage includes the generated-state guard:

- `/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice-compliance/saleinvoice-compliance.component.spec.ts`

Verified scenario:

- IRN generated
- E-Way generated
- backend flags still `true`

Expected result:

- overview generate buttons disabled
- prefill disabled
- `Cancel IRN` disabled
- `Cancel E-Way` enabled

## Follow-Up Recommendation

Use this matrix as the reference when:

- refining backend `action_flags`
- writing API-to-UI contract tests
- reviewing future compliance console changes
- validating UAT scenarios for B2B and B2C invoice flows
