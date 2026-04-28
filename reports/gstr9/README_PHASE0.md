# GSTR-9 Phase 0 Scope Lock

This document locks the foundation decisions for GSTR-9 implementation in Finacc.

## Objectives
- Keep GSTR-9 design aligned with existing GSTR-1 and GSTR-3B report contracts.
- Freeze table coverage and source ownership before computation coding starts.
- Define boundaries between report computation and future filing workflow.

## Locked Decisions
1. **Architecture style**
- Follow `reports/gstr1` style: modular package with `services`, `views`, `serializers`, `selectors`, `exporters`, `tests`.
- Keep API paths under `/api/reports/gstr9/*`.

2. **Scope parameters (Phase 0 baseline)**
- `entity` (required)
- `entityfinid` (optional in request, required before compute/freeze)
- `subentity` (optional)
- Future phase params (for filing context): `as_of_date`, `include_adjustments`, `include_cancelled`.

3. **Phase split**
- Phase 0: scope lock + meta contract + table catalog.
- Phase 1+: computations, validations, exports, freeze snapshots.
- Filing APIs are out-of-scope for Phase 0 and will be built after report stability.

4. **Data ownership**
- Outward tax/taxable: sales posting models.
- Input tax credit/tax paid: purchase + posting models.
- Cross-return reconciliation: GSTR-1 and GSTR-3B generated datasets.

5. **Control points**
- Every table computation must be deterministic and reproducible for same scope.
- Rounding policy must be centralized before Phase 2 totals implementation.
- Freeze snapshot versioning is mandatory before filing integration.

## Initial Table Catalog (working baseline)
- Table 4: outward supplies on which tax is payable.
- Table 5: outward supplies on which tax is not payable.
- Table 6: ITC availed during the year.
- Table 7: ITC reversed/ineligible.
- Table 8: ITC as per GSTR-2A/2B reconciliation view.
- Table 9: tax paid and payable.
- Table 10-14: amendments and related adjustments.
- Table 15-19: demands/refunds and HSN-level reporting.

This catalog will be finalized with finance/compliance sign-off before Phase 2 coding.

