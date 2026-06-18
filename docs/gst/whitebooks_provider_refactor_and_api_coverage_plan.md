## WhiteBooks Provider Refactor And API Coverage Plan

Date: 2026-06-18

## Purpose

This document captures the current review of the active WhiteBooks statutory integration and defines the changes needed to make the implementation:

- provider-switchable
- scalable for additional vendor endpoints
- faithful to vendor API collections as source of truth
- free from legacy helper dependency

This plan covers both collections shared for review:

- e-invoice collection
- e-way bill collection, including B2C direct e-way usage

## Ground Rules

- vendor Postman/API JSON is the source of truth for endpoint contracts
- no new implementation should depend on legacy helper code under `helpers/utils/gst_api.py`
- active implementation should live in the provider stack under `sales/services/providers/*`
- service layer and API layer should remain provider-agnostic
- credential, endpoint, and payload behavior must be configurable enough to support a future provider switch

## Current Active Stack

The current active integration path is:

- provider registration: `sales/services/providers/__init__.py`
- provider contract: `sales/services/providers/base.py`
- provider implementation: `sales/services/providers/mastergst.py`
- HTTP client: `sales/services/providers/mastergst_client.py`
- runtime provider selection: `sales/services/providers/config.py`
- credential resolution: `sales/services/providers/credential_resolver.py`
- business orchestration: `sales/services/sales_compliance_service.py`
- compliance APIs: `sales/views/sales_invoice_compliance_api.py`
- e-way APIs: `sales/views/eway_views.py`

## What Is Already Covered

### E-Invoice Collection

Covered in the active provider stack:

- `GET /einvoice/authenticate`
- `POST /einvoice/type/GENERATE/version/V1_03`
- `POST /einvoice/type/CANCEL/version/V1_03`
- `GET /einvoice/type/GETIRN/version/V1_03`
- `POST /einvoice/type/GENERATE_EWAYBILL/version/V1_03`
- `GET /einvoice/type/GETEWAYBILLIRN/version/V1_03`
- `GET /einvoice/type/GSTNDETAILS/version/V1_03`
- `GET /einvoice/type/GETIRNBYDOCDETAILS/version/V1_03`
- `GET /einvoice/type/SYNC_GSTIN_FROMCP/version/V1_03`
- `GET /einvoice/qrcode`

### E-Way Collection

Covered in the active provider stack:

- `GET /ewaybillapi/v1.03/authenticate`
- `POST /ewaybillapi/v1.03/ewayapi/genewaybill`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybill`
- `GET /ewaybillapi/v1.03/ewayapi/gettransporterdetails`
- `GET /ewaybillapi/v1.03/ewayapi/getgstindetails`
- `GET /ewaybillapi/v1.03/ewayapi/gethsndetailsbyhsncode`
- `GET /ewaybillapi/v1.03/ewayapi/geterrorlist`
- `POST /ewaybillapi/v1.03/ewayapi/canewb`
- `POST /ewaybillapi/v1.03/ewayapi/vehewb`
- `POST /ewaybillapi/v1.03/ewayapi/updatetransporter`
- `POST /ewaybillapi/v1.03/ewayapi/extendvalidity`
- `POST /ewaybillapi/v1.03/ewayapi/rejewb`
- `GET /ewaybillapi/v1.03/ewayapi/gettripsheet`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillgeneratedbyconsigner`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsfortransporter`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillreportbytransporterassigneddate`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsbydate`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsrejectedbyothers`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsfortransporterbygstin`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsfortransporterbystate`
- `GET /ewaybillapi/v1.03/ewayapi/getewaybillsofotherparty`
- `POST /ewaybillapi/v1.03/ewayapi/gencewb`
- `POST /ewaybillapi/v1.03/ewayapi/regentripsheet`
- `POST /ewaybillapi/v1.03/ewayapi/initmulti`
- `POST /ewaybillapi/v1.03/ewayapi/addmulti`
- `POST /ewaybillapi/v1.03/ewayapi/updtmulti`

App-facing B2C direct e-way support already exists through:

- `GET /api/sales/sales-invoices/<id>/compliance/eway-b2c-prefill/`
- `POST /api/sales/sales-invoices/<id>/compliance/generate-eway-b2c/`

## Key Review Findings

### 1. WhiteBooks Is Not Yet A First-Class Provider

`WhitebooksProvider` currently inherits `MasterGSTProvider` behavior directly.

Impact:
- vendor-specific behavior is implicit
- future provider switch is harder than necessary
- endpoint differences will accumulate in shared code instead of provider-specific code

### 2. Endpoint Metadata Is Hardcoded In Methods

Client methods currently hardcode:

- path
- API version
- query parameter layout
- header names
- retry pattern

Impact:
- every new endpoint requires repetitive custom method code
- vendor contract changes require code edits instead of config updates

### 3. Credential Model Is More Flexible Than Runtime Resolution

The data model supports:

- environment
- service scope: `EINVOICE` and `EWAY`

But runtime resolution still leans on `EINVOICE` scope in important flows.

Impact:
- current runtime does not fully honor the credential model
- e-way specific credentials are not consistently selected

### 4. Client Reads Attributes Not Explicitly Modeled

The e-way client path reads `eway_username` and `eway_password` through `getattr(...)`, but these are not first-class fields on `SalesMasterGSTCredential`.

Impact:
- behavior is implicit
- onboarding expectations are unclear
- future provider work may become error-prone

### 5. IP Handling Is Hardcoded

The client currently resolves IP using a hardcoded localhost value instead of fully honoring credential-level configuration.

Impact:
- implementation does not use its own configurability surface
- deployment behavior is less predictable

### 6. B2C Payload Builder Contains Business Hardcoding

The B2C direct e-way payload builder currently hardcodes values like:

- `supplyType = "O"`
- `subSupplyType = "1"`
- `toGstin = "URP"`
- default `docType = "INV"`

Impact:
- hard to adapt if provider contract or business rules vary
- difficult to audit which values come from invoice data versus code defaults

### 7. Request And Response Modeling Is Still Endpoint-Local

Normalization is currently done method-by-method using per-endpoint field alias logic.

Impact:
- acceptable for a small surface area
- not ideal once more collection endpoints are added

## Current Audit Gaps

These are the meaningful remaining gaps after endpoint coverage is complete.

### 1. Two Token Cache Models Exist For Similar Responsibility

The codebase currently has both:

- `SalesMasterGSTToken`
- `MasterGSTToken`

Findings:
- active provider client uses `SalesMasterGSTToken`
- legacy token helper uses `MasterGSTToken`
- admin registers both, which makes support/debugging ambiguous

Impact:
- token inspection is harder
- cleanup and provider switch work becomes riskier

Recommendation:
- standardize on one token cache model for the active stack
- mark the other as legacy and plan data migration/removal if safe

Current status:
- legacy helper `sales/services/mastergst_eway_token_service.py` has been removed from the active codebase
- `MasterGSTToken` remains only as a legacy model/admin artifact

### 2. B2C Direct E-Way Builder Still Has Business Defaults In Code

The current B2C direct payload builder still relies on code-level defaults rather than an explicit policy/config object.

Examples already noted in code review:
- `supplyType = "O"`
- `subSupplyType = "1"`
- `toGstin = "URP"`
- fallback `docType = "INV"`

Impact:
- hard to explain whether these are vendor constants or business defaults
- harder to adapt if B2C use cases expand

Recommendation:
- move B2C defaults into a provider-aware payload policy layer
- document which values are vendor-mandated versus app defaults

Current status:
- active B2C payload builder now reads explicit defaults from `SALES_EWAY_B2C_POLICY`
- defaults like `supplyType`, `subSupplyType`, `docType`, `toGstin`, `transactionType`, and fallback `vehicleType` are now policy values rather than hidden literals
- unused duplicate B2C builder/service files were removed so only one active path remains

### 3. Serializer Contracts Still Mirror Vendor Naming Too Closely In Some Areas

The newer compliance serializers are clean, but request naming is still mixed:

- app-style names such as `state_code`, `gen_gstin`
- vendor-style names such as `transMode`, `tripSheetEwbBills`, `ewbNo`

Impact:
- frontend integration is less predictable
- future provider switching will be noisier because vendor field names leak upward

Recommendation:
- define one app-facing request contract
- translate to vendor field names only inside the service/provider boundary

Current status:
- advanced e-way operational endpoints now accept snake_case app contracts
- legacy camelCase/vendor field names remain accepted for backward compatibility
- vendor payload translation now happens in `SalesComplianceService`

### 4. Provider Layer Is Switchable, But WhiteBooks Is Still An Alias Provider

`WhitebooksProvider` currently inherits `MasterGSTProvider` directly and only changes the provider name.

Impact:
- easy to switch today only while contracts remain identical
- real divergence later will force branching inside shared classes

Recommendation:
- keep the current inheritance short term
- introduce a dedicated WhiteBooks adapter/client only when the first real contract difference appears
- keep endpoint metadata and normalization rules overrideable per provider spec

Current status:
- thin split completed: `whitebooks.py` and `whitebooks_client.py` now exist as dedicated boundaries
- shared provider methods now instantiate the provider's own `client_class`
- current behavior remains shared, but future WhiteBooks divergence no longer needs to start inside `mastergst.py`

### 5. Query Contract Assembly Is Still Repeated Method By Method

Even after the provider spec refactor, query-string building is still handwritten per client method.

Examples:
- `param1` based e-invoice lookups
- mixed `GSTIN`, `Gen_gstin`, `stateCode`, `docType` e-way queries

Impact:
- endpoint coverage is complete, but maintainability is still medium effort
- typo risk remains for future provider additions

Recommendation:
- consider a small request-builder utility driven by provider specs
- especially for GET query contracts and auth header variants

Current status:
- `MasterGSTClient` now centralizes common query-string construction and e-invoice GET-with-retry behavior
- endpoint methods still remain explicit, but much less repetitive
- future provider work should now need less hand-built URL/header logic

### 6. Planning Doc Coverage Section Was Previously Stale

The collection-backed endpoint coverage is now complete for the shared WhiteBooks collections:

- e-invoice collection: 10/10 covered
- e-way collection: 26/26 covered

Remaining work is now primarily structural cleanup and contract hardening, not raw endpoint addition.

## Target Architecture

The integration should evolve toward this shape:

### 1. Provider Contract Layer

`sales/services/providers/base.py`

Responsibility:
- define normalized operations the app understands
- define normalized result types

Examples:
- authenticate
- generate IRN
- cancel IRN
- get IRN details
- get IRN by doc details
- get GSTN details
- generate e-way
- cancel e-way
- update vehicle
- update transporter
- extend validity

### 2. Provider Metadata Layer

New recommended module:
- `sales/services/providers/provider_specs.py`

Responsibility:
- provider endpoint map
- version strings
- auth header names
- query parameter conventions
- retryable error patterns
- endpoint capability flags

Example provider spec concerns:
- e-invoice auth path
- e-way auth path
- whether e-way token comes from headers or body
- whether direct e-way calls require username/password in headers

### 3. Provider Client Layer

Examples:
- `sales/services/providers/mastergst_client.py`
- future `sales/services/providers/whitebooks_client.py` if needed

Responsibility:
- raw HTTP transport
- assemble requests from provider spec
- no business orchestration
- no invoice mutation

### 4. Provider Adapter Layer

Examples:
- `sales/services/providers/mastergst.py`
- future `sales/services/providers/whitebooks.py`

Responsibility:
- translate raw vendor responses into normalized app results
- vendor-specific field mapping
- vendor-specific error mapping

## Recommended Next Implementation Order

1. Decide the surviving token cache model and eventual migration/removal plan for `MasterGSTToken`.
2. Introduce an app-facing payload contract for B2C and advanced E-Way operations.
3. Move B2C hardcoded defaults into a documented policy/config layer.
4. Add a small provider-spec-driven request builder for repeated query/header assembly.
5. Re-evaluate whether `WhitebooksProvider` should stay as an alias or split into a dedicated adapter.

### 5. Service Layer

`sales/services/sales_compliance_service.py`

Responsibility:
- invoice state guards
- permission and action policy
- persistence of compliance artifacts
- audit logs
- provider-agnostic orchestration

### 6. API Layer

Examples:
- `sales/views/sales_invoice_compliance_api.py`
- `sales/views/eway_views.py`

Responsibility:
- validation
- permission entry checks
- response envelope

## Required Refactors Before Broad Endpoint Expansion

### Refactor A: Make WhiteBooks Explicit

Create explicit provider identity and spec for WhiteBooks instead of relying on alias inheritance only.

Outcome:
- easier switching
- cleaner vendor divergence handling

### Refactor B: Split Credential Resolution By Scope

Add explicit resolver paths for:

- e-invoice credentials
- e-way credentials

Outcome:
- runtime behavior matches the model design

### Refactor C: Move Endpoint Definitions Into Provider Specs

Extract hardcoded paths and version strings into a provider endpoint map.

Outcome:
- easier to add new endpoints from vendor collections
- safer future provider switch

### Refactor D: Define Request And Response Contracts

For each endpoint family, introduce a clear normalized request and response contract.

Outcome:
- less field guessing
- cleaner API expansion

### Refactor E: Clarify Credential Fields

Decide one of these:

- add first-class modeled e-way-specific credential fields if the vendor truly needs them
- or remove implicit `getattr(...)` behavior and standardize on shared credentials

Outcome:
- cleaner onboarding and runtime expectations

### Refactor F: Use Configurable IP Resolution

Replace hardcoded IP behavior with model- or setting-driven resolution.

Outcome:
- deployment-safe behavior

## Recommended Implementation Phases

### Phase 1: Provider Hardening

Goals:
- create provider spec abstraction
- split credential resolution by scope
- remove hidden assumptions around fields and IP handling

Deliverables:
- provider spec module
- updated resolver
- cleaned client request assembly

### Phase 2: Fill Remaining E-Invoice Gaps

Endpoints:
- `SYNC_GSTIN_FROMCP`
- `GETIRNBYDOCDETAILS`
- `qrcode`

Deliverables:
- provider methods
- service methods where needed
- app endpoints if required by product

### Phase 3: Fill Core E-Way Lookup Gaps

Priority candidates:
- `getewaybill`
- `gettransporterdetails`
- `getgstindetails`
- `gethsndetailsbyhsncode`
- `geterrorlist`

Deliverables:
- provider coverage for high-value lookup APIs

### Phase 4: Fill Operational E-Way Gaps

Priority candidates:
- `rejewb`
- consolidated EWB APIs
- multi-vehicle APIs

Deliverables:
- provider and service support for operational transport workflows

### Phase 5: Payload And UI Surface Review

Goals:
- ensure frontend/API inputs expose the required vendor attributes
- remove hardcoded B2C assumptions where values should be explicit

## Attribute Review Checklist For Each New Endpoint

Before implementing any remaining endpoint, verify:

- required headers
- required query params
- required body fields
- optional fields that should not be dropped
- vendor defaults versus business defaults
- whether any value is being hardcoded today
- whether serializer/API contracts expose all needed attributes
- whether response normalization preserves useful vendor fields

## Proposed Working Rules For Future Implementation

1. Add endpoint contract from vendor JSON first.
2. Add provider spec entry second.
3. Add raw client call third.
4. Add normalized provider adapter fourth.
5. Add service orchestration only if the product needs business behavior.
6. Add API/view exposure only if the product needs a user-facing endpoint.
7. Add focused tests for:
   - request formation
   - response normalization
   - service orchestration
   - API validation

## Suggested Next Planning Session

In the next planning pass, align on:

1. whether to do provider hardening first before new endpoints
2. the minimum endpoint priority list from both collections
3. whether B2C QR and e-way lookup/report APIs are product requirements now or later
4. whether credential model changes are acceptable in the current release window

## Summary

The current active stack works for the core implemented flows, but it is only partially structured for long-term provider switching and broad API coverage.

The most important next step is not simply adding the next endpoint. It is making the provider layer explicit and configurable enough that the remaining vendor APIs can be added without growing more hardcoded behavior.
