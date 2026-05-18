# Payroll Calculation Engine Audit

## Scope
- File audited: [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:82)
- Runtime input source audited: [payroll_calculation_input_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_calculation_input_resolver.py:446)
- Effective-dated config resolver audited: [payroll_config_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_config_resolver.py:8)
- Readiness/statutory snapshot resolver audited: [payroll_run_readiness_resolver_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_readiness_resolver_service.py:84)
- Attendance runtime engine audited: [payroll_attendance_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_attendance_engine.py:1)

## Executive Summary
The runtime is partially contract-native today.

## Phase 1 Status
Completed in Phase 1:
- explicit `PayrollComponent.semantic_code` binding added
- migration/backfill added for seeded legacy component codes
- `PayrollRunService` no longer derives semantic meaning from component code prefixes at runtime
- unsupported salary line rule modes and unsupported generic `INPUT` usage now fail loudly with contextual `PayrollCalculationError`

Removed prefix-inference areas:
- runtime semantic detection for `BASIC`, `HRA`, `SPECIAL_ALLOWANCE`, `PF_*`, `ESI_*`, `PROFESSIONAL_TAX`, and `TDS`

Remaining compatibility shims:
- legacy seeded component codes are still auto-mapped to semantic codes during migration and model save
- `calculation_basis_snapshot.semantic_role` is still emitted as a backward-compatible alias of the new semantic code
- special semantic branches for `SPECIAL_ALLOWANCE`, `PT`, `TDS`, `PF_*`, and `ESI_*` still live inside `PayrollRunService`

Phase 2 still pending:
- formula engine for `CUSTOM_FORMULA`
- generic `INPUT` execution
- `rule_json` execution engine
- statutory runtime engine using `StatutoryRule` and `StatutorySlab`
- policy-driven rounding and richer proration methods

What is working well:
- runtime input resolution is contract-native
- salary structure assignment/version resolution is contract-native
- attendance, tax declaration, recurring item, one-time item, statutory profile, and statutory registration snapshots are all being resolved per contract
- component posting and ledger policy resolution are effective-dated
- traceability snapshots are materially better than before

What is still hardcoded or weak:
- component meaning is still inferred from component code prefixes
- salary structure line math only supports a narrow subset of the model
- recurring and one-time item math is simplistic
- statutory math is still mostly embedded in `PayrollRunService`
- rounding policy is captured in assumptions/preflight but not actually driving numeric behavior

Bottom line:
- input resolution is contract-native
- calculation execution is still mostly engine-hardcoded with policy-assisted fallbacks

## Phase 2 Status
Completed in Phase 2:
- added dedicated safe formula execution in [payroll_formula_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_formula_engine.py:1)
- added rule interpreter support in [payroll_rule_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_rule_engine.py:1)
- refactored `PayrollRunService` salary-line execution to route generic line math through the formula/rule layer while keeping orchestration in place
- added component-level calculation trace snapshots for salary lines, recurring items, and one-time items

Supported salary line modes:
- `FIXED`
- `PERCENT_OF_CTC`
- `PERCENT_OF_COMPONENT`
- `INPUT`
- `CUSTOM_FORMULA`

Supported `rule_json` patterns:
- percentage override
- slab-based result selection
- min/max caps
- fixed amount fallback
- conditional applicability with `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `truthy`, `falsy`

Current limitations:
- custom formulas support arithmetic expressions only; no calls, attribute access, boolean expressions, or arbitrary Python syntax
- `CUSTOM_FORMULA` does not auto-apply proration; formulas must explicitly use attendance variables when they want proration-aware math
- generic `INPUT` resolves from contract-native snapshots and falls back to zero when no configured input is present and no fixed fallback exists
- seeded statutory branches for `SPECIAL_ALLOWANCE`, `PF_*`, `ESI_*`, `PT`, and `TDS` still remain as compatibility logic inside `PayrollRunService`
- recurring item `formula_override` is still recorded for traceability but not executed as a generic formula path yet

Phase 3 still pending:
- policy-driven rounding beyond fixed `ROUND_HALF_UP`
- richer proration methods from payroll policy
- broader recurring and one-time pay item rule execution
- attendance and leave runtime engine

## Phase 3 Status
Completed in Phase 3:
- added dedicated statutory runtime execution in [payroll_statutory_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_statutory_engine.py:1)
- refactored `PayrollRunService` to delegate statutory component execution by explicit `semantic_code`
- removed remaining PF/ESI/PT/TDS statutory math branches from `_line_amount()` orchestration
- added statutory trace snapshots for scheme, registration, rule, slab, wage base, rate or amount, ceiling, applicability decision, and final amount

Supported statutory schemes:
- PF employee and employer contribution
- ESI employee and employer contribution
- Professional Tax
- Labour Welfare Fund
- TDS projection hook

Known limitations:
- TDS is still a projection hook backed by runtime tax snapshots and policy JSON, not a full statutory annual income tax engine
- statutory rule interpretation currently supports the existing percentage, threshold, ceiling, fixed amount, and slab patterns used by PF/ESI/PT/LWF, but not arbitrary formula-style statutory rules
- entity registration presence is resolved and traced, but the runtime still prefers explicit contract/entity snapshots and scheme rules over deeper jurisdiction-specific composition logic
- policy-driven numeric rounding is still fixed to `ROUND_HALF_UP`

## Phase 4 Status
Completed in Phase 4:
- added dedicated attendance/payable-day execution in [payroll_attendance_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_attendance_engine.py:1)
- refactored `PayrollRunService` to delegate proration and attendance-impact resolution to the attendance engine
- normalized attendance-driven formula variables and component trace snapshots for salary-line execution
- added strict failures for missing required attendance, negative attendance metrics, invalid payable/base-day combinations, and unknown proration methods

Supported policy methods:
- `CALENDAR_DAYS`
- `WORKING_DAYS`
- `FIXED_26_DAYS`
- `FIXED_30_DAYS`
- `ACTUAL_ATTENDANCE`
- `MANUAL_PAYABLE_DAYS`

Supported attendance adjustment handling:
- manual payable-day override
- payable-day delta adjustment
- LOP adjustment
- overtime adjustment
- half-day adjustment
- late-deduction day derivation from policy rules

Known limitations:
- paid and unpaid leave are runtime trace fields today and depend on attendance summary metadata or adjustment metadata; there is not yet a richer leave-balance or leave-approval execution layer
- the attendance input resolver still emits a coarse aggregated attendance snapshot for backward compatibility, while the attendance engine re-resolves raw summaries and adjustments to avoid double counting
- periodic leave and arrear semantics depend on adjustment metadata conventions rather than a dedicated leave runtime schema

## Phase 5 Status
Completed in Phase 5:
- added dedicated FnF execution in [payroll_fnf_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_fnf_engine.py:1)
- added contract-native settlement persistence with [FnFSettlement and FnFSettlementComponent](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/models/core.py:2032)
- reused the attendance, salary-line, formula/rule, and statutory runtime layers instead of duplicating payroll math
- integrated regular payroll exclusion for contracts with active FnF settlements through policy-driven runtime filtering in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:196)

Supported settlement components:
- earned salary till last working day using existing salary-line and proration engines
- notice pay recovery and notice pay payout hooks
- leave encashment
- reimbursement payable
- bonus and incentive payout hooks
- loan recovery and advance recovery
- asset recovery
- final statutory deductions via the statutory runtime engine
- gratuity hook placeholder
- final TDS hook placeholder

Known limitations:
- gratuity remains a clean hook or manual amount path; there is not yet a service-year or eligibility engine
- final TDS remains a placeholder or manual projection hook and does not implement full annual separation-tax recomputation
- notice-period handling currently depends on explicit FnF inputs such as shortfall or payout days rather than a deeper workflow-driven resignation model
- leave encashment currently depends on explicit days or input snapshot data and does not yet consume a leave-balance ledger
- asset and non-payroll recovery inputs are hook-driven unless represented through existing recurring or one-time payroll items

Phase 6 still pending:
- ESS / employee portal settlement visibility and acknowledgement flows
- employee self-service tax and settlement document workflows
- broader operational workflow around payout handoff, document generation, and final communication

## Detailed Audit

### 1. Salary structure line calculation
Current runtime path:
- `calculate_run()` loads active `SalaryStructureLine` rows and computes each amount through `_line_amount()` in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1409)

Config-driven parts working:
- active contract salary assignment and approved version are used at runtime via [payroll_calculation_input_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_calculation_input_resolver.py:476)
- line basis, rate, fixed amount, basis component, and proration flag are read from the actual structure version

Hardcoded or weak parts:
- `_line_amount()` only supports:
  - `FIXED`
  - `PERCENT_OF_CTC`
  - `PERCENT_OF_COMPONENT`
  in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1205)
- `INPUT` is treated only through a few special semantic-role branches, not as a general input-driven basis
- `CUSTOM_FORMULA` and `rule_mode` are not executed at all
- `rule_json` is not interpreted by the engine
- `recurrence_frequency`, `compensation_bucket`, `ctc_treatment`, and `gross_treatment` are persisted in the model but not used in amount calculation
- `SPECIAL_ALLOWANCE` balancing is hardcoded by semantic role in gross mode in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1137)

Risk:
- seeded/global templates can express richer behavior than the runtime can execute
- the structure data model implies a formula-driven engine, but the current run engine is still mostly branch-driven

### 2. Recurring pay item calculation
Current runtime path:
- recurring items are resolved contract-natively in [payroll_calculation_input_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_calculation_input_resolver.py:381)
- run calculation applies them using `_resolve_contract_item_amount()` in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:551)

Config-driven parts working:
- active recurring items are selected by contract and payroll date
- amount and percentage are serialized into runtime input
- source snapshots are persisted onto run component rows

Hardcoded or weak parts:
- recurring item math supports only:
  - explicit amount
  - percentage of salary basis
- `formula_override` is only stored in snapshots and never evaluated in runtime in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1553)
- `recurrence_frequency` is resolved upstream but not actively used by the calculator itself

Risk:
- users can configure recurring items with metadata that appears meaningful but does not actually affect payroll math

### 3. One-time pay item calculation
Current runtime path:
- one-time items are resolved contract-natively in [payroll_calculation_input_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_calculation_input_resolver.py:412)
- run calculation posts the item `amount` directly in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1574)

Config-driven parts working:
- one-time items are contract-native and period/date filtered
- source type, quantity, and full item snapshot are persisted

Hardcoded or weak parts:
- amount is taken as-is
- `quantity` is stored but not used to derive amount
- `source_type` does not influence treatment
- there is no formula or rate-based one-time calculation path

Risk:
- one-time items look richer in schema than in runtime behavior

### 4. Attendance and proration calculation
Current runtime path:
- attendance summary and adjustments are aggregated by the contract-native resolver
- attendance execution and proration are now normalized in [payroll_attendance_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_attendance_engine.py:1)
- `PayrollRunService` consumes the normalized attendance result when building formula variables, proration context, employee assumptions, and component trace snapshots

Config-driven parts working:
- attendance source is contract-native
- approved/manual/imported attendance summaries are resolved contract-natively
- approved attendance adjustments are applied at runtime without double counting the already-aggregated snapshot
- proration only applies when `line.is_pro_rated` is true
- payroll policy rules can now drive richer proration methods and missing-attendance behavior
- salary-line formulas can explicitly consume `calendar_days`, `working_days`, `attendance_days`, `payable_days`, `lop_days`, `paid_leave_days`, `unpaid_leave_days`, `half_days`, `overtime_hours`, `late_instances`, `late_deduction_days`, and `proration_factor`

Supported runtime methods:
- `CALENDAR_DAYS`
- `WORKING_DAYS`
- `FIXED_26_DAYS`
- `FIXED_30_DAYS`
- `ACTUAL_ATTENDANCE`
- `MANUAL_PAYABLE_DAYS`

Hardcoded or weak parts:
- paid/unpaid leave semantics are only as rich as the attendance summary metadata and adjustment metadata provided upstream
- the payroll policy model still exposes `LOPCalculationMethod` values that do not map one-to-one to every richer runtime proration method, so policy rules are the preferred driver for new methods
- late-deduction day semantics currently come from a policy rule multiplier rather than a broader attendance-policy DSL
- recurring and one-time items still do not use the attendance engine directly unless their formulas explicitly reference attendance variables

Risk:
- runtime attendance execution is now centralized and traceable, but richer leave lifecycle behavior still sits outside payroll calculation
- settlement-era edge cases are now handled by the FnF engine, but richer leave-balance, gratuity, and tax recomputation logic still remain outside payroll execution

### 5. TDS calculation
Current runtime path:
- TDS is resolved through `_resolve_tds_amount()` and helper methods in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1040)

Config-driven parts working:
- tax regime comes from contract payroll profile/runtime input
- tax declaration and tax projection snapshots are contract-native
- old/new regime slabs can come from structure policy JSON
- standard deduction, surcharge slabs, cess rate, rebate thresholds, caps, and remaining periods can come from policy keys
- HRA exemption and prior-employer income/TDS are considered

Hardcoded or weak parts:
- if slabs are missing, TDS falls back to default projection rate logic rather than statutory-rule execution
- hardcoded defaults still exist for:
  - projection rate fallback `10%`
  - standard deduction fallback `50,000`
  - 80C cap fallback `150,000`
  - 80D cap fallback `25,000`
  - default remaining periods `12`
- all TDS logic lives inside `PayrollRunService` rather than a separate tax engine

Risk:
- TDS is the most policy-aware part of the calculator, but it is still tightly coupled to one service and can drift from statutory master data if policy JSON is incomplete

### 6. PF / ESI / PT / LWF calculation
Current runtime path:
- statutory components now route through [payroll_statutory_engine.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_statutory_engine.py:1)
- `PayrollRunService` keeps orchestration and trace persistence only

Config-driven parts working:
- contract-native readiness/input resolution provides statutory flags, profiles, and registrations
- `StatutoryScheme`, `StatutoryRule`, and `StatutorySlab` are resolved at runtime when present
- policy JSON remains available as a compatibility fallback for seeded payroll behavior where statutory master data is not yet populated
- runtime input carries statutory flags like `pf_applicable`, `esi_applicable`, `pt_applicable`, `tds_applicable`, `lwf_applicable`
- runtime trace now records scheme, registration, rule, slab, wage base, rate or amount, cap or ceiling, applicability decision, and final amount

Hardcoded or weak parts:
- TDS is still intentionally a projection hook, not a full annual income-tax engine
- PF/ESI defaults still exist inside the statutory engine as compatibility fallbacks when config is incomplete
- the statutory engine currently interprets a constrained set of rule patterns rather than every possible statutory formula model
- deeper jurisdiction-specific edge cases still depend on how well `rule_json` and slab data are modeled upstream

Risk:
- statutory execution is now centralized and traceable, but TDS and edge-case jurisdiction logic still need a fuller tax/statutory runtime in later phases

### 7. Rounding
Current runtime path:
- helper `q2()` quantizes with `ROUND_HALF_UP` in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:43)

Config-driven parts working:
- `rounding_policy` is required in structure calculation policy
- preflight warns when mixed rounding policies exist
- run assumptions persist the configured rounding policy

Hardcoded or weak parts:
- actual arithmetic always uses `ROUND_HALF_UP`
- `EntityPayrollPolicy.rounding_mode`, `net_pay_rounding`, and `component_rounding` are not applied in runtime math
- traceability/reconciliation services also quantize with `ROUND_HALF_UP`

Risk:
- the system advertises configurable rounding, but the runtime is effectively fixed to one rounding behavior

### 8. Policy usage
Config-driven areas working:
- structure version `calculation_policy_json` is heavily used for:
  - country code
  - salary mode
  - proration basis
  - TDS policy keys
  - PF/ESI/PT fallback values
- readiness resolves `EntityPayrollPolicy`

Weakness:
- run calculator primarily uses structure policy JSON, not `EntityPayrollPolicy` as a first-class execution source
- policy model fields like:
  - `pay_frequency`
  - `payroll_month_start_day`
  - `lop_calculation_method`
  - `arrear_calculation_method`
  - `negative_salary_policy`
  - `payslip_publish_policy`
  - `payroll_lock_policy`
  are not materially driving calculation math in `calculate_run()`

Risk:
- there is a split-brain between:
  - calculation policy embedded in salary structure version JSON
  - standalone entity payroll policy model

### 9. Statutory config usage
Config-driven areas working:
- readiness resolves required schemes, contract statutory profiles, and entity registrations in [payroll_run_readiness_resolver_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_readiness_resolver_service.py:262)
- runtime input carries:
  - `statutory_flags`
  - `statutory_profile_snapshots`
  - `statutory_registration_snapshots`

Weakness:
- those snapshots are not used by a generic statutory rule evaluation engine during amount computation
- `StatutoryRule`, `StatutorySlab`, and `override_rule_json` are not directly executed by `PayrollRunService`
- statutory config is mostly used for readiness, traceability, and policy snapshots, not for a rule-driven compute path

Risk:
- master-data richness is ahead of engine richness
- future statutory changes may require code changes where the system should ideally accept master updates

### 10. Component snapshot traceability
Working well:
- every structure-derived component stores:
  - component snapshot
  - posting snapshot
  - calculation basis snapshot
- recurring and one-time items also persist source snapshots
- run employee payload stores:
  - salary structure snapshot
  - payroll profile snapshot
  - full contract payroll profile runtime snapshot
  - attendance snapshot
  - payable days snapshot
  - tax projection snapshot
  - source markers

Code references:
- line snapshots in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1450)
- recurring item snapshots in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1549)
- one-time item snapshots in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1609)
- run employee payload snapshot in [payroll_run_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payroll/services/payroll_run_service.py:1638)

Gap:
- traceability is good for "what happened"
- the actual engine still lacks a generic explanation layer for "why this statutory/formula result was chosen"

## Hardcoded Areas Found
- semantic component meaning inferred from code prefixes instead of explicit component semantics
- special allowance balancing hardcoded for gross mode
- PT calculation hardcoded as threshold + amount
- PF and ESI computation hardcoded in the run service with fallback constants
- TDS lives in `PayrollRunService` instead of a dedicated policy/statutory engine
- rounding always uses `ROUND_HALF_UP`
- recurring items only support amount or percent-of-salary-basis
- one-time items only support direct amount passthrough
- unsupported modeled features are silently non-executed:
  - `CUSTOM_FORMULA`
  - `rule_json`
  - `formula_override`
  - `INPUT` as a general calculator mode
  - `LWF` compute path

## Config-Driven Areas Working
- contract-native runtime input resolution
- contract-native salary assignment selection
- contract-native attendance summary and adjustments
- contract-native tax declaration and projection snapshot merge
- effective-dated ledger policy resolution
- effective-dated component posting resolution
- policy-driven slab-based TDS when slab metadata is present
- detailed run/component/input traceability snapshots

## Risky Calculation Logic
- engine behavior depends on component naming conventions
- model richness is greater than runtime capability, which can mislead setup users
- policy split between structure-policy JSON and entity policy model increases drift risk
- statutory setup is resolved but not generically executed
- LWF appears configured but not calculated
- unsupported policy values often fail soft by fallback instead of raising explicit unsupported-configuration errors
- mixed salary modes and proration semantics are only partially enforced by runtime

## Recommended Next Implementation Order
1. Replace code-prefix semantic inference with explicit component semantic keys or rule binding metadata.
2. Extract statutory math from `PayrollRunService` into a dedicated statutory calculation engine that consumes `StatutoryRule`, `StatutorySlab`, contract statutory profiles, and overrides.
3. Implement a real salary-line rule engine for:
   - `CUSTOM_FORMULA`
   - `INPUT`
   - `rule_json`
   - balancing/manual rules as first-class config
4. Make recurring pay item calculation rule-driven:
   - respect `formula_override`
   - respect recurrence semantics in-engine
5. Make one-time pay item calculation honor `quantity` and configurable derivation rules.
6. Wire runtime rounding to actual configured rounding policies and policy-level rounding amounts.
7. Make proration honor entity payroll policy methods, not only `attendance_days` and `payable_days`.
8. Add explicit unsupported-configuration errors so setup cannot silently degrade to fallback math.

## Exact Next Prompt
Use this prompt next:

```text
Implement phase 1 of the payroll calculation engine hardening based on docs/payroll-frontend/payroll-calculation-engine-audit.md.

Goal:
Remove semantic hardcoding and introduce explicit runtime semantics for payroll component calculation.

Scope:
1. Add explicit semantic binding for payroll components instead of code-prefix inference.
2. Refactor PayrollRunService to use that semantic binding.
3. Fail loudly for unsupported salary line rule modes/bases instead of silently returning fallback zeros.
4. Keep behavior backward compatible for existing seeded components by providing a migration/backfill path.
5. Do not implement the full formula engine yet.

Deliver:
- model changes if needed
- migration/backfill
- service refactor
- tests
- update docs/payroll-frontend/payroll-calculation-engine-audit.md with phase-1 status notes

Also report:
- what old hardcoded branches were removed
- what compatibility shims remain
- what phase 2 should implement next
```
