# Invoice Performance Phase 0 Results

Status: initial Phase 0 findings captured. No code changes applied.

Date: 2026-06-13

Related documents:
- [invoice-performance-phase0-checklist.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-phase0-checklist.md:1)
- [invoice-performance-implementation-plan.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-implementation-plan.md:1)

## Captured Scenario 1

Scenario:
- Sales invoice create screen load

Route:
- `http://localhost:4200/#/saleinvoice`

Browser timing from HAR:
- `DOMContentLoaded`: about `1.03s`
- `Load`: about `1.03s`

Network summary from HAR:
- total captured API entries: `21`

## Key Findings

### Top slowest API requests

1. `GET /api/financial/accounts/simple-v2?entity=10`
- time: `1137.2 ms`
- transfer size: `18419 B`
- content size: `18060 B`

2. `GET /api/entity/me/entities`
- time: `907.0 ms`
- transfer size: `2334 B`
- content size: `1976 B`

3. `GET /api/rbac/me/menus?entity=10`
- time: `664.7 ms`
- transfer size: `56671 B`
- content size: `56312 B`

4. `GET /api/sales/meta/invoice-lines/?entity=10&subentity=8`
- time: `622.5 ms`
- transfer size: `13584 B`
- content size: `13225 B`

5. `GET /api/catalog/product-page-all/?entity=10`
- time: `496.0 ms`
- transfer size: `10147 B`
- content size: `9789 B`

### Largest payloads

1. `GET /api/rbac/me/menus?entity=10`
- content size: `56312 B`

2. `GET /api/rbac/me/permissions?entity=10`
- content size: `18354 B`

3. `GET /api/financial/accounts/simple-v2?entity=10`
- content size: `18060 B`

4. `GET /api/sales/meta/invoice-lines/?entity=10&subentity=8`
- content size: `13225 B`

5. `GET /api/catalog/product-page-all/?entity=10`
- content size: `9789 B`

### Invoice-specific metadata calls observed

Sales invoice screen-specific requests:

1. `GET /api/sales/meta/invoice-form/?entity=10&subentity=8`
- time: `106.2 ms`
- transfer size: `8275 B`
- content size: `7917 B`

2. `GET /api/sales/meta/invoice-lines/?entity=10&subentity=8`
- time: `622.5 ms`
- transfer size: `13584 B`
- content size: `13225 B`

3. `GET /api/sales/meta/settings/?entity=10&entityfinid=8&subentity=8`
- time: `129.1 ms`
- transfer size: `6396 B`
- content size: `6038 B`

### Other supporting calls observed

- `GET /api/inventory-ops/godowns/?entity=10&subentity=8`
- `GET /api/geography/country`
- `GET /api/geography/state?country=1`
- `GET /api/tcs/sections/?entity=10&q=&law_type=INCOME_TAX`
- `GET /api/entity/me/entities/10/financial-years`
- `GET /api/auth/me` called twice
- `GET /api/entity/notifications/unread-count/?entity=10&subentity=8` called multiple times

## Initial Interpretation

### 1. The biggest invoice-screen cost is not the sales form meta call

The sales form meta call is relatively small and fast:
- about `7.9 KB`
- about `106 ms`

So for the plain create-screen load, `sales/meta/invoice-form` is not the first bottleneck.

### 2. The heavier invoice-screen cost is `sales/meta/invoice-lines`

This request is both slower and larger than the sales form meta call:
- about `13.2 KB`
- about `622 ms`

That makes line metadata a stronger candidate for optimization than form meta on initial load.

### 3. Global shell/bootstrap APIs are a large part of the total cost

The biggest payloads are not invoice-specific:
- RBAC menus
- RBAC permissions
- simple account list

This means invoice-page performance is partly constrained by app-shell/bootstrap behavior, not only the invoice module.

### 4. There may be duplicate/general app traffic worth reviewing

Observed duplicates:
- `/api/auth/me` twice
- unread notification count multiple times

These may not be invoice-specific problems, but they still affect perceived invoice load time.

## Current Phase 0 Ranking From This One Capture

Based on this first scenario alone, likely optimization order is:

1. Review `sales/meta/invoice-lines`
2. Review global `simple-v2` account loading on invoice screens
3. Review shell-level `menus` and `permissions` payload cost
4. Review duplicate `auth/me` and notification polling behavior
5. Review `sales/meta/invoice-form` later for popup refresh cases, not initial create-load

## Recorded Worksheet Entry

| Scenario | Route / Action | Total API Calls | Time To Usable | Slowest Request | Largest Payload | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Sales create | `/#/saleinvoice` | `21` | about `1.03s` browser load marker | `financial/accounts/simple-v2` at `1137.2 ms` | `rbac/me/menus` at `56312 B` | invoice-specific hotspot appears to be `sales/meta/invoice-lines` |

## Recommended Next Measurement

Run next:
- Sales customer popup return

Reason:
- that is the scenario most likely to confirm whether full form-meta refresh is an actual practical hotspot
- the initial create-load result suggests the create-screen bottleneck is broader than form meta alone

## Captured Scenario 2

Scenario:
- Sales customer popup return

Observed API entries:
- `8`

## Key Findings For Scenario 2

### Main sequence observed

1. Customer save:
- `POST /api/financial/accounts-v2`
- time: `231.5 ms`
- transfer size: `2404 B`

2. Customer detail fetch:
- `GET /api/financial/accounts-v2/661`
- time: `34.7 ms`
- transfer size: `2321 B`

3. Shipping details fetch:
- `GET /api/financial/shipping-details/account/661/`
- time: `43.7 ms`
- transfer size: `357 B`

4. Full sales form meta reload:
- `GET /api/sales/meta/invoice-form/?entity=10&subentity=8`
- time: `180.9 ms`
- transfer size: `8521 B`

5. Full sales form meta reload again:
- `GET /api/sales/meta/invoice-form/?entity=10&subentity=8`
- time: `182.4 ms`
- transfer size: `8521 B`

6. Godown reloads:
- `GET /api/inventory-ops/godowns/?entity=10&subentity=8`
- called twice

### Important conclusion

This scenario confirms a real optimization target:

- after customer popup save/return, full sales form meta is reloaded
- it is reloaded twice in the same flow

That makes this a stronger Phase 1 candidate than it looked from the initial create-screen load alone.

## Comparison: Sales Create vs Sales Customer Popup Return

### Sales create screen

What dominated:
- global shell/bootstrap calls
- `sales/meta/invoice-lines`
- `financial/accounts/simple-v2`

What did not dominate:
- `sales/meta/invoice-form`

### Sales customer popup return

What dominated the invoice refresh path:
- duplicated `sales/meta/invoice-form`

Interpretation:
- form meta is not the main issue on clean create load
- form meta is a real issue in popup refresh workflow because it is broader than needed and duplicated

## Updated Phase 0 Recommendation

Based on the first two captures, the strongest Phase 1 candidates are now:

1. Fix duplicate/full `sales/meta/invoice-form` refresh after customer popup save
2. Review whether customer refresh can be replaced with a customer-only endpoint or narrower refresh
3. Review duplicate godown refresh in the same return flow
4. Keep `sales/meta/invoice-lines` as a separate optimization target for create/load performance

## Recorded Worksheet Entry

| Scenario | Route / Action | Total API Calls | Time To Usable | Slowest Request | Largest Payload | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Sales customer popup return | create/update customer and return | `8` | not directly provided by HAR page timing for isolated popup action | `financial/accounts-v2` POST at `231.5 ms` | duplicated `sales/meta/invoice-form` at `8163 B` content each | confirms duplicate full form-meta refresh |

## Purchase Vendor Popup Return Confirmation

User confirmation:
- purchase vendor popup return shows the same broad refresh pattern as the sales customer popup return flow

Evidence level:
- user-confirmed behavior
- not yet documented here with a second parsed HAR summary table

Working conclusion:
- both sales and purchase party popup return flows should be treated as confirmed Phase 1 candidates

## Phase 0 Exit View

At this point, Phase 0 has enough evidence to support implementation planning for the first optimization slice.

What is sufficiently established:
- initial sales create-screen latency is influenced by both invoice-specific and app-shell/bootstrap requests
- `sales/meta/invoice-lines` is a meaningful invoice-specific initial-load hotspot
- popup return flows are a separate class of problem
- sales customer popup return clearly triggers duplicated full form-meta refresh
- purchase vendor popup return appears to follow the same pattern

## Final Phase 0 Recommendation

Recommended Phase 1 start:

1. Fix duplicate/full sales form-meta refresh after customer popup save
2. Fix duplicate/full purchase form-meta refresh after vendor popup save
3. Replace party refresh with narrower customer/vendor refresh flows where possible
4. Review duplicate godown refresh in popup return flows
5. Keep `sales/meta/invoice-lines` for the next optimization slice focused on create/load latency

## Phase 0 Completion Status

Phase 0 can now be treated as functionally complete for the first implementation slice because:
- one initial create-screen HAR was analyzed
- one popup-return HAR was analyzed
- the matching purchase popup pattern has been confirmed by user testing
- the first low-risk target is now clear
