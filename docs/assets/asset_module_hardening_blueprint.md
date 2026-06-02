# Asset Module Hardening Blueprint

Date: 2026-06-02

## Purpose

This blueprint documents the Asset module hardening program across backend and frontend.

It now serves two purposes:

- define the operating model we want to preserve
- record what has already been implemented so frontend and backend stay aligned

The module is being shaped into a controlled accounting workspace that is:

- configuration-driven
- validation-heavy where it matters
- informative when it blocks or warns
- correctable through governed reversal and unposting flows
- auditable after posting and after correction

---

## 1. Core Product Principle

The Asset module should not behave like a plain CRUD form.

Every important action should answer these questions clearly:

1. Is the action allowed by policy?
2. Is the setup and transaction data complete?
3. What accounting impact will be created if posting proceeds?
4. If the posting was wrong, how can it be corrected without damaging audit history?

The working model is built on three pillars:

- configurable governance
- staged validation and prechecks
- controlled correction through reversal

---

## 2. Current Implementation Status

Many of the original governance gaps have now been closed.

### 2.1 Backend hardening completed

Implemented:

- multi-period `SLM` depreciation logic
- overlap protection for depreciation runs
- locked-period enforcement for capitalization, impairment, disposal, and depreciation correction paths
- explicit rejection of immutable posted-field edits
- governed reversal for capitalization, impairment, and disposal
- reversal precheck APIs
- lifecycle posting precheck APIs for capitalization, impairment, and disposal
- reversal-aware reporting support in asset events and asset history

### 2.2 Frontend hardening completed

Implemented:

- policy-driven settings screens
- category-level override editing for traceability and accounting readiness
- action precheck review panels before posting lifecycle actions
- in-app reversal dialogs instead of browser `prompt` / `confirm`
- reversal precheck display with authoritative blockers and impact
- policy provenance display in lifecycle prechecks
- traceability advisory provenance display in asset master
- hard validation mirroring for operational master fields where policy requires it

### 2.3 Remaining focus areas

Still worth doing:

- update supporting docs and rollout notes continuously as rules evolve
- keep frontend rendering aligned with backend payload shape whenever new policy keys are added
- further polish reporting, usability, and visual quality now that core governance is stronger
- extend the same policy/provenance pattern to additional screens if needed

---

## 3. Design Principles

### 3.1 No silent acceptance

If a user attempts an invalid change, the system should not silently ignore it.

The system should:

- allow it
- warn clearly
- or block clearly

### 3.2 No posting without explainability

Before capitalization, impairment, or disposal is posted, the user should be able to see:

- whether the action is allowed
- what is blocking it
- what is risky but still allowed
- what effect the action will have
- which policy is driving the decision

### 3.3 No destructive correction without audit

Wrong entries should be corrected through reversal, not history deletion.

### 3.4 Configuration over hardcoding

Business behavior should come from settings and category overrides, not from embedded assumptions about asset types or operator behavior.

### 3.5 Frontend and backend must share one contract

If the backend exposes a configurable rule, the frontend should:

- know the rule
- render the correct control or advisory state
- avoid inventing stronger or weaker behavior than the API actually enforces

---

## 4. Policy Model Implemented

The Asset module now has a layered governance model.

### 4.1 Scope-level policy controls

The baseline rule set lives in `AssetSettings.policy_controls`.

Implemented scope-level controls include:

- `purchase_review_completeness_rule`
- `counter_ledger_match_rule`
- `full_impairment_rule`
- `require_location_rule`
- `require_department_rule`
- `require_custodian_rule`
- `require_serial_number_rule`
- `require_manufacturer_rule`
- `require_model_number_rule`
- `require_vendor_account_rule`
- `require_asset_ledger_rule`
- `require_depreciation_ledgers_rule`
- `require_impairment_ledgers_rule`
- `require_disposal_ledgers_rule`
- `require_cwip_ledger_rule`

The broader legacy policy set remains available as part of the settings model, including depreciation, threshold, backdating, tag, and multi-book controls.

### 4.2 Category-level traceability controls

Each asset category now supports `traceability_controls` with inheritance.

Implemented traceability keys:

- `serial_number_rule`
- `manufacturer_rule`
- `model_number_rule`
- `vendor_account_rule`

Allowed category values:

- `inherit`
- `off`
- `warn`

These controls are advisory by design. They do not hard-block asset save.

### 4.3 Category-level accounting controls

Each asset category also supports `accounting_controls` with inheritance.

Implemented accounting keys:

- `asset_ledger_rule`
- `depreciation_ledgers_rule`
- `impairment_ledgers_rule`
- `disposal_ledgers_rule`
- `cwip_ledger_rule`

Allowed category values:

- `inherit`
- `off`
- `warn`
- `hard`

These controls can influence category setup validation and lifecycle posting prechecks.

### 4.4 Inheritance model

The inheritance model is:

1. scope policy provides the baseline
2. category override can inherit or replace that baseline per rule
3. frontend displays the effective rule and, where implemented, the source of that rule

This keeps behavior configurable without hardcoded category assumptions.

---

## 5. Validation Model Implemented

Validation is now staged instead of being limited to final posting-time failure.

### 5.1 Save-time validation

Implemented save-time checks include:

- asset scope consistency
- field-level serializer validation
- rejection of posted immutable-field edits
- hard enforcement of operational master fields where configured:
  - location
  - department
  - custodian
- category accounting completeness checks where category-effective rules are `hard`

### 5.2 Advisory validation

Implemented advisory checks include:

- missing serial number
- missing manufacturer
- missing model number
- missing vendor reference

These are controlled by policy and remain advisory-only.

### 5.3 Lifecycle action prechecks

Before posting capitalization, impairment, or disposal, the backend now evaluates the actual request payload and returns:

- `allowed`
- `blocking_reasons`
- `warnings`
- `impact`
- `snapshot`
- `policy_profile`

Implemented precheck themes include:

- status eligibility
- locked-period constraints
- purchase intake review completeness
- suspicious counter-ledger selections
- full-impairment rule handling
- disposal date and lifecycle consistency
- category accounting readiness

### 5.4 Reversal prechecks

Before reversal of capitalization, impairment, or disposal, the backend now returns:

- `allowed`
- `blocking_reasons`
- `warnings`
- `impact`
- `snapshot`

These checks are authoritative and reflect downstream dependencies and lock constraints.

---

## 6. Correction And Reversal Model Implemented

The module now supports governed correction for the main lifecycle postings.

### 6.1 Implemented reversal actions

Implemented:

- capitalization reversal
- impairment reversal
- disposal reversal
- depreciation run cancellation and reversal-aware controls

### 6.2 Reversal characteristics

The implemented reversal pattern:

- requires a reason payload for lifecycle reversal
- marks the related posting `Entry` as reversed
- deactivates the related posting batch
- restores the asset state where appropriate
- blocks unsafe reversal when later lifecycle activity depends on the posting

### 6.3 Correction standards now in place

The module now follows these correction standards:

- wrong posted entries are corrected through reversal, not edit
- reversal paths are visible in the UI
- users can see precheck blockers before attempting reversal
- reporting can distinguish active versus reversed lifecycle effects

---

## 7. Frontend/Backend Contract Alignment

This section is important for keeping both layers matched.

### 7.1 Asset settings contract

Backend:

- `AssetSettingsAPIView` returns the settings payload including `policy_controls`

Frontend:

- `asset.ts` defines `AssetPolicyControls`
- `asset-settings.component` renders and persists the same keys

Rule for future work:

- add policy keys in backend normalization and frontend typings together

### 7.2 Category contract

Backend category create/update/read uses `AssetCategorySerializer`, which now supports:

- `traceability_controls`
- `accounting_controls`

Frontend:

- `AssetCategoryListItem` and `AssetCategoryDetail` include both
- `asset-category-master` edits both override families

Important nuance:

- category master APIs carry both override objects
- `AssetMetaAPIView` currently exposes category `traceability_controls` for asset-form advisory resolution
- `AssetMetaAPIView` does not currently expose category `accounting_controls`

This is intentional in the current contract and should be preserved unless both backend and frontend are changed together.

### 7.3 Lifecycle precheck contract

Backend precheck endpoints:

- `fixed-assets/<id>/capitalize/precheck/`
- `fixed-assets/<id>/impair/precheck/`
- `fixed-assets/<id>/dispose/precheck/`

Frontend:

- `asset.service.ts` posts the action payload to these endpoints
- `asset.ts` models the response as `AssetLifecyclePrecheck`
- `asset-master` renders blockers, warnings, impact, snapshot, and policy profile

Important alignment point:

- the action precheck response includes `policy_profile`
- the frontend already expects and renders this structure

### 7.4 Reversal precheck contract

Backend reversal endpoints support:

- `GET` for precheck
- `POST` for actual reversal

Implemented endpoints:

- `fixed-assets/<id>/reverse-capitalization/`
- `fixed-assets/<id>/reverse-impairment/`
- `fixed-assets/<id>/reverse-disposal/`

Frontend:

- opens reversal dialog
- loads the `GET` precheck
- disables confirmation while blocked or loading
- submits the reason payload through `POST`

### 7.5 Traceability provenance contract

Traceability provenance shown in asset master is resolved from:

1. scope-level `policy_controls`
2. selected category `traceability_controls` from asset meta

The frontend is not inventing those rules. It is resolving the effective advisory state from backend-provided configuration.

### 7.6 Accounting provenance contract

Accounting provenance shown in action prechecks is backend-authored.

The backend returns `policy_profile` with:

- rule code
- label
- effective rule
- source
- configured value

The frontend should continue treating this payload as authoritative.

---

## 8. UX Standards Now In Effect

The asset workspace should behave like a reviewed action flow, not a blind submit form.

Implemented standards:

- precheck before major lifecycle posting
- guided reversal dialog instead of browser-native confirm flow
- snapshot visibility before reversal
- policy provenance visibility for accounting decisions
- advisory provenance visibility for traceability prompts
- clear hard validation for configured operational master rules

Desired standard for future additions:

- any new governed backend rule should have a visible frontend explanation path

---

## 9. Reporting And Audit Position

The reporting layer has been strengthened to reflect correction state.

Implemented direction:

- asset events and history now carry reversal-aware state
- journal-linked history rows can show entry status
- lifecycle traceability is cleaner for capitalization, impairment, disposal, and their reversals

This should remain a guiding rule:

- a corrected asset story must still be readable after multiple lifecycle actions

---

## 10. Delivery Rules For Future Changes

To keep the module safe and coherent, future changes should follow these rules.

### 10.1 Add policy keys end-to-end

Whenever a new policy rule is introduced:

- add backend default
- add backend normalization
- add backend enforcement or advisory usage
- add serializer and API coverage if needed
- add frontend typing
- add frontend settings or rendering support
- add tests on both sides where practical

### 10.2 Avoid frontend-only rules

Do not hardcode category behavior, posting restrictions, or advisory requirements only in Angular.

### 10.3 Avoid backend-only invisible enforcement

If a backend rule changes action eligibility, the UI should surface that result through:

- field validation
- precheck
- warning
- policy provenance

### 10.4 Preserve correction-first accounting behavior

Do not reintroduce patterns that:

- silently skip posted-field edits
- allow destructive correction
- hide reversal impact

---

## 11. Remaining Roadmap

The foundation is much stronger now. The next tranches are more about completeness, polish, and operational clarity.

Recommended next steps:

1. Keep this blueprint updated whenever the payload contract changes.
2. Extend provenance and precheck visibility to any additional governed asset actions introduced later.
3. Continue improving report readability for complex correction histories.
4. Apply a visual polish pass across asset screens now that the accounting controls are substantially hardened.
5. Add rollout/UAT notes for finance users so policy behavior is understandable outside the development team.

---

## 12. File Map

Primary backend files:

- `assets/models.py`
- `assets/services/settings.py`
- `assets/services/asset_service.py`
- `assets/services/depreciation.py`
- `assets/serializers.py`
- `assets/views.py`
- `assets/urls.py`
- `reports/services/assets.py`

Primary frontend files:

- `src/app/model/asset.ts`
- `src/app/service/asset/asset.service.ts`
- `src/app/component/asset/asset-settings/*`
- `src/app/component/asset/asset-category-master/*`
- `src/app/component/asset/asset-master/*`
- asset report components that consume event and history payloads

This file map should be treated as the main impact surface for future hardening work.
