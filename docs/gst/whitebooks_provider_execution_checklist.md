## WhiteBooks Provider Execution Checklist

Date: 2026-06-18

Companion document:
- `docs/gst/whitebooks_provider_refactor_and_api_coverage_plan.md`

## Goal

Execute the WhiteBooks statutory integration cleanup and API expansion in a way that:

- keeps vendor API collections as source of truth
- avoids legacy helper reuse
- preserves provider-switchability
- reduces hardcoding before broader endpoint expansion

## Batch 1: Must-Do Refactors First

These should happen before broad endpoint expansion.

### 1. Provider Spec Abstraction

Create a provider metadata layer for:

- base URLs
- endpoint paths
- API versions
- auth header names
- token extraction rules
- retryable auth failure patterns

Done when:
- endpoint strings are no longer scattered through client methods
- WhiteBooks and MasterGST can differ by spec, not by copy-paste logic

### 2. Credential Resolution By Scope

Split runtime credential resolution into:

- e-invoice credential resolution
- e-way credential resolution

Done when:
- active e-way flows do not silently depend on `EINVOICE` scope credentials
- runtime behavior matches `SalesMasterGSTCredential.service_scope`

### 3. Credential Contract Cleanup

Decide whether e-way-specific username/password are:

- first-class stored fields
- or intentionally shared with GST credentials

Done when:
- client code no longer relies on ambiguous `getattr(...)` fallback for credential shape

### 4. IP Resolution Cleanup

Replace hardcoded localhost IP handling with explicit configuration behavior.

Done when:
- client IP behavior comes from settings or credential data
- no request path depends on `127.0.0.1` being baked into code

### 5. Payload Contract Review

Review hardcoded request values in B2C and other payload builders.

Done when:
- hardcoded business defaults are documented or moved into request/spec logic
- payload builders clearly distinguish:
  - vendor-required constants
  - business defaults
  - values sourced from invoice state

## Batch 2: E-Invoice Endpoint Completion

Implement the remaining e-invoice collection endpoints in the active provider stack.

### Priority

1. `GET /einvoice/type/GETIRNBYDOCDETAILS/version/V1_03` - done
2. `GET /einvoice/type/SYNC_GSTIN_FROMCP/version/V1_03` - done
3. `GET /einvoice/qrcode` - done

### Done When

- raw client methods exist
- provider adapters normalize responses
- service methods exist where product needs orchestration
- API routes exist where user-facing access is required
- focused tests cover request formation and response mapping

## Batch 3: E-Way High-Value Lookup APIs

Implement the highest-value read-side e-way endpoints first.

### Priority

1. `GET /ewayapi/getewaybill` - done
2. `GET /ewayapi/gettransporterdetails` - done
3. `GET /ewayapi/getgstindetails` - done
4. `GET /ewayapi/gethsndetailsbyhsncode` - done
5. `GET /ewayapi/geterrorlist` - done

### Done When

- provider/client coverage exists for each
- API exposure is added only where product actually needs it
- response shape is normalized for reuse

## Batch 4: E-Way Operational APIs

Implement transport-ops endpoints after the provider layer is hardened.

### Priority

1. `POST /ewayapi/rejewb`
2. `POST /ewayapi/gencewb`
3. `GET /ewayapi/gettripsheet`
4. `POST /ewayapi/regentripsheet`
5. multi-vehicle endpoints:
   - `initmulti`
   - `addmulti`
   - `updtmulti`

### Done When

- operations fit the same provider-service-view pattern
- request payloads do not rely on ad hoc field guessing

## Batch 5: Reporting And Transporter List APIs

These can follow after core operational coverage.

### Endpoints

- `getewaybillsfortransporter`
- `getewaybillreportbytransporterassigneddate`
- `getewaybillsbydate`
- `getewaybillsrejectedbyothers`
- `getewaybillsfortransporterbygstin`
- `getewaybillsfortransporterbystate`
- `getewaybillsofotherparty`
- `getewaybillgeneratedbyconsigner`

Status:
- `getewaybillsfortransporter` - done
- `getewaybillreportbytransporterassigneddate` - done
- `getewaybillsbydate` - done
- `getewaybillsrejectedbyothers` - done
- `getewaybillsfortransporterbygstin` - done
- `getewaybillsfortransporterbystate` - done
- `getewaybillsofotherparty` - done
- `getewaybillgeneratedbyconsigner` - done

## Batch 6: Structural Cleanup After Coverage

Now that the shared WhiteBooks collections are fully covered, the next batch should focus on maintainability.

### Priority

1. choose one active token cache model between `SalesMasterGSTToken` and `MasterGSTToken`
2. normalize app-facing request contracts for advanced e-way operations
3. move B2C code defaults into a policy/config surface
4. reduce repeated query/header assembly in provider client methods

Progress:
- unused `sales/services/mastergst_eway_token_service.py` removed
- `MasterGSTToken` kept as legacy admin-visible record only
- advanced e-way action serializers now accept app-facing snake_case contracts with vendor alias compatibility
- B2C direct e-way defaults now come from `SALES_EWAY_B2C_POLICY` instead of hidden builder literals
- duplicate unused B2C builder/service files removed
- provider client query/header assembly is now partially centralized for lower-cost endpoint expansion
- thin provider/client split completed for WhiteBooks with dedicated `whitebooks.py` and `whitebooks_client.py`

### Done When

- active and legacy token paths are no longer competing
- app-facing APIs no longer leak vendor naming unnecessarily
- business defaults are documented and overrideable
- future provider divergence can be handled without shared-class branching

## Per-Endpoint Implementation Checklist

For every new endpoint:

1. Confirm vendor collection request contract.
2. Add provider spec entry.
3. Add raw client method.
4. Add provider adapter normalization.
5. Add service orchestration if needed.
6. Add API exposure if product needs it.
7. Add focused tests.

## Decision Gates Before Coding Each Batch

Before starting a batch, confirm:

1. Is this endpoint user-facing now or just provider coverage?
2. Does it need persistence or is it stateless lookup only?
3. Are all required vendor attributes exposed by current serializers/models?
4. Are any current hardcoded defaults blocking accurate implementation?

## Suggested Implementation Order

1. Provider spec abstraction
2. Credential resolution cleanup
3. Credential field contract cleanup
4. IP resolution cleanup
5. `GETIRNBYDOCDETAILS`
6. `SYNC_GSTIN_FROMCP`
7. `qrcode`
8. `getewaybill`
9. `gettransporterdetails`
10. `getgstindetails`
11. `gethsndetailsbyhsncode`
12. remaining operational e-way APIs
13. reporting and transporter list e-way APIs

## Definition Of Ready

A new vendor endpoint is ready for implementation only when:

- request contract is reviewed from vendor JSON
- target layer is identified
- missing attributes are known
- hardcoded blockers are identified

## Definition Of Done

A new vendor endpoint is done only when:

- active provider stack implements it
- no legacy helper is used
- tests exist
- provider switchability is not reduced by the implementation
