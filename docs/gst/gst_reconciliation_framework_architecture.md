# GST Reconciliation Framework Architecture

Date: 2026-05-19

## Purpose

This document defines the backend architecture for a centralized GST reconciliation framework in Finacc.

The goal is to evolve the current GST reporting, validation, and purchase-side 2B matching features into a reusable reconciliation engine without breaking existing APIs or report screens.

This design covers:
- models
- workflow lifecycle
- API surface
- service interfaces
- matching engine interfaces
- import pipeline design
- auditability
- scalability and indexing
- phased rollout

This document does not cover UI implementation.

## Design Goals

The framework should be:
- reusable across `GSTR-2B`, `GSTR-1`, and `GSTR-3B`
- backward-compatible with current `reports` and `purchase` APIs
- SaaS-safe for multi-tenant entity isolation
- GSTIN-aware for multi-registration entities
- audit-friendly with maker-checker support
- performant for high-volume invoice matching
- extensible for later portal/API sync

## Current Reusable Building Blocks

Existing code that should be reused instead of replaced:

- Purchase 2B import and row review
  - [purchase_gstr2b_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_gstr2b_service.py)
  - [purchase_gstr2b.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_gstr2b.py)
  - [gstr2b_models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/gstr2b_models.py)

- Purchase ITC status and policy gating
  - [purchase_invoice_actions.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_actions.py)
  - [purchase_settings_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_settings_service.py)
  - [purchase_statutory_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_statutory_service.py)

- GSTR-1 summary, validations, readiness, exports
  - [reports/gstr1/services/report.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/gstr1/services/report.py)
  - [reports/gstr1/services/validation.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/gstr1/services/validation.py)
  - [reports/gstr1/services/readiness.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/gstr1/services/readiness.py)

- GSTR-3B computed summary and validations
  - [reports/gstr3b/services.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/gstr3b/services.py)

- Existing comparison and dashboard services
  - [reports/services/gst_reconciliation.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/services/gst_reconciliation.py)
  - [reports/services/gst_exception_dashboard.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/services/gst_exception_dashboard.py)

## High-Level Architecture

Introduce a new app or bounded module named `gst_reconciliation`.

Recommended package structure:

```text
gst_reconciliation/
  models/
    reconciliation_core.py
    imported_returns.py
    action_log.py
  services/
    run_service.py
    item_service.py
    import_service.py
    matching/
      base.py
      registry.py
      gstr2b_matcher.py
      gstr1_matcher.py
      gstr3b_matcher.py
    builders/
      purchase_2b_builder.py
      sales_gstr1_builder.py
      gstr3b_builder.py
  selectors/
    queries.py
  serializers/
    reconciliation.py
  views/
    run_views.py
    import_views.py
    review_views.py
  urls.py
```

Design principle:
- existing `purchase` and `reports` modules remain source systems
- `gst_reconciliation` becomes the orchestration and persistence layer
- matching strategies remain pluggable and return normalized results

## Core Data Model

### 1. GstReconciliationRun

Represents one reconciliation cycle for one scope, period, and return type.

Suggested fields:
- `id`
- `entity`
- `entityfinid`
- `subentity`
- `gst_registration`
  - nullable initially if no dedicated GST registration master exists
- `reconciliation_type`
  - `GSTR2B_PURCHASE`
  - `GSTR1_SALES`
  - `GSTR3B_BOOKS`
- `period_type`
  - monthly by default
- `period_from`
- `period_to`
- `return_period`
  - normalized `YYYY-MM`
- `source_mode`
  - `BOOKS_VS_IMPORTED`
  - `BOOKS_ONLY`
  - `IMPORTED_ONLY`
- `status`
  - `DRAFT`
  - `IMPORTED`
  - `MATCHING`
  - `READY_FOR_REVIEW`
  - `IN_REVIEW`
  - `APPROVED`
  - `REJECTED`
  - `CLOSED`
  - `FAILED`
- `match_strategy_code`
- `imported_return`
  - FK to `GstImportedReturn`, nullable
- `created_by`
- `submitted_by`
- `reviewed_by`
- `approved_by`
- `closed_by`
- `created_at`
- `submitted_at`
- `reviewed_at`
- `approved_at`
- `closed_at`
- `summary_json`
  - counts and totals snapshot
- `notes`
- `review_comment`
- `approval_comment`
- `close_comment`

Recommended constraints:
- unique on `(entity, entityfinid, subentity, gst_registration, reconciliation_type, return_period, revision_no, is_active)`

Recommended indexes:
- `(entity, entityfinid, subentity, reconciliation_type, return_period)`
- `(status, reconciliation_type, return_period)`
- `(gst_registration, reconciliation_type, return_period)`

### 2. GstImportedReturn

Represents imported portal payload or manually uploaded return data.

Suggested fields:
- `id`
- `entity`
- `entityfinid`
- `subentity`
- `gst_registration`
- `return_type`
  - `GSTR2B`
  - `GSTR1`
  - `GSTR3B`
- `return_period`
- `source`
  - `JSON_UPLOAD`
  - `EXCEL_UPLOAD`
  - `CSV_UPLOAD`
  - `PORTAL_API`
  - `MANUAL_ENTRY`
- `reference`
  - file name / ARN / import batch reference
- `status`
  - `UPLOADED`
  - `VALIDATED`
  - `PARTIAL`
  - `FAILED`
  - `CONSUMED`
- `checksum`
- `raw_payload_json`
- `normalized_payload_json`
- `validation_summary_json`
- `imported_by`
- `imported_at`

Recommended indexes:
- `(entity, entityfinid, subentity, return_type, return_period)`
- `(gst_registration, return_type, return_period)`
- `(status, return_type, return_period)`

### 3. GstReconciliationItem

Represents one comparable unit inside a run.

This is the main operational table.

Suggested fields:
- `id`
- `run`
- `item_type`
  - `INVOICE`
  - `CREDIT_NOTE`
  - `DEBIT_NOTE`
  - `SECTION_BUCKET`
  - `SUMMARY_BUCKET`
- `direction`
  - `PURCHASE`
  - `SALES`
  - `OUTPUT`
  - `INPUT`
- `match_key`
  - normalized compound key string
- `source_document_type`
  - `purchase_invoice`, `sales_invoice`, `imported_return_row`, `gstr3b_bucket`
- `source_document_id`
- `linked_document_type`
- `linked_document_id`
- `gstin`
- `counterparty_gstin`
- `invoice_number`
- `invoice_date`
- `doc_type_code`
- `taxable_value_books`
- `cgst_books`
- `sgst_books`
- `igst_books`
- `cess_books`
- `taxable_value_imported`
- `cgst_imported`
- `sgst_imported`
- `igst_imported`
- `cess_imported`
- `match_status`
  - `NOT_CHECKED`
  - `MATCHED`
  - `PARTIAL`
  - `MISMATCHED`
  - `MISSING_IN_BOOKS`
  - `MISSING_IN_RETURN`
  - `DUPLICATE`
  - `IGNORED`
  - `MANUALLY_RESOLVED`
- `severity`
  - `info`, `warning`, `error`
- `is_actionable`
- `manual_override`
- `override_reason`
- `review_comment`
- `mismatch_reason_codes`
  - cached list of reason codes for fast UI rendering
- `match_score`
- `sort_weight`
- `metadata_json`
- `reviewed_by`
- `reviewed_at`
- `resolved_by`
- `resolved_at`

Recommended indexes:
- `(run, match_status)`
- `(run, severity, is_actionable)`
- `(run, gstin, invoice_number)`
- `(run, counterparty_gstin, invoice_number, invoice_date)`
- `(run, source_document_type, source_document_id)`
- `(run, linked_document_type, linked_document_id)`

### 4. GstMismatchReason

Normalized mismatch reason catalog plus optional per-item link table.

Catalog table:
- `code`
- `label`
- `category`
- `severity_default`
- `is_blocking_default`
- `description`

Examples:
- `GSTIN_MISMATCH`
- `INVOICE_NUMBER_MISMATCH`
- `INVOICE_DATE_OUT_OF_TOLERANCE`
- `TAXABLE_VALUE_MISMATCH`
- `TAX_BREAKUP_MISMATCH`
- `DOC_TYPE_MISMATCH`
- `MISSING_IN_BOOKS`
- `MISSING_IN_RETURN`
- `DUPLICATE_IN_RETURN`
- `DUPLICATE_IN_BOOKS`
- `RCM_TREATMENT_DIFFERENCE`
- `NOTE_LINK_INVALID`

Optional link table:
- `GstReconciliationItemReason`
  - `item`
  - `reason_code`
  - `reason_payload_json`

### 5. GstReconciliationActionLog

Immutable audit trail for every major action.

Suggested fields:
- `id`
- `run`
- `item`
  - nullable for run-level actions
- `action_type`
  - `RUN_CREATED`
  - `IMPORT_VALIDATED`
  - `MATCH_EXECUTED`
  - `ITEM_REVIEWED`
  - `ITEM_OVERRIDDEN`
  - `RUN_SUBMITTED`
  - `RUN_APPROVED`
  - `RUN_REJECTED`
  - `RUN_CLOSED`
- `actor`
- `actor_role_snapshot`
- `old_status`
- `new_status`
- `remarks`
- `payload_json`
- `created_at`

Recommended indexes:
- `(run, created_at)`
- `(item, created_at)`
- `(action_type, created_at)`

## Optional Supporting Model

### GstRegistration

If Finacc later formalizes multiple GST registrations under one entity, introduce:
- `entity`
- `subentity`
- `gstin`
- `trade_name`
- `legal_name`
- `state_code`
- `registration_type`
- `is_active`

For phase 1, keep this optional and allow `gst_registration` to be nullable while using raw GSTIN text fields.

## Workflow Lifecycle

### Run Lifecycle

1. `DRAFT`
   - run created
   - scope and settings frozen

2. `IMPORTED`
   - imported return attached or books snapshot prepared

3. `MATCHING`
   - matcher building items

4. `READY_FOR_REVIEW`
   - system matching completed
   - counts and exception summary materialized

5. `IN_REVIEW`
   - user manually reviews items

6. `APPROVED`
   - checker approves run

7. `REJECTED`
   - run rejected and sent back

8. `CLOSED`
   - run finalized for the period

9. `FAILED`
   - import or match failure

### Item Lifecycle

1. created during matching
2. system assigns `match_status` and mismatch reasons
3. reviewer may:
   - accept
   - override
   - relink
   - ignore
4. final item state is frozen when run closes

## Maker-Checker Workflow

Recommended policy fields on run type or entity policy:
- `maker_checker_required`
- `allow_self_approval`
- `review_required_statuses`
- `blocking_reason_codes`
- `manual_override_requires_comment`

Rules:
- creator/importer cannot approve own run if maker-checker enabled
- manual override must create an action log entry
- run cannot close if blocking item count > 0 unless policy explicitly allows forced close

## Matching Engine Design

### Interface

Base matcher interface:

```python
class BaseGstMatcher:
    strategy_code: str

    def build_candidates(self, *, run) -> list[dict]:
        ...

    def match(self, *, run) -> MatchExecutionResult:
        ...

    def explain(self, *, left, right) -> list[MismatchResult]:
        ...
```

### Strategy Registry

Add registry:

```python
MATCHER_REGISTRY = {
    "gstr2b.default.v1": Gstr2bMatcher,
    "gstr1.default.v1": Gstr1Matcher,
    "gstr3b.bucket.v1": Gstr3bMatcher,
}
```

### Strategy Types

#### GSTR-2B matcher

Primary key logic:
- supplier GSTIN
- normalized supplier invoice number
- document type

Secondary checks:
- invoice date tolerance
- taxable/tax breakup tolerance
- note/original linkage

Output:
- invoice-level item matches

#### GSTR-1 matcher

Two modes:
- `books vs imported gstr1`
- `books-only readiness mirror`

Primary key logic:
- seller GSTIN
- invoice number
- doc type
- customer GSTIN where relevant

Secondary checks:
- POS
- tax regime
- tax values
- note linkage

#### GSTR-3B matcher

Mode:
- bucket-level reconciliation, not invoice-level by default

Primary comparison buckets:
- outward taxable supplies
- zero-rated supplies
- nil/exempt/non-GST
- interstate disclosure
- input tax credit buckets
- tax paid cash / tax paid ITC

Output:
- summary-bucket items

## Matching Utility Layer

Introduce reusable helpers:
- `normalize_invoice_number()`
- `normalize_gstin()`
- `compare_date_with_tolerance()`
- `compare_decimal_with_tolerance()`
- `build_match_key()`
- `derive_reason_codes()`

This should replace direct one-off matching logic over time, especially in [purchase_gstr2b_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_gstr2b_service.py).

## Import Pipeline Design

### Step 1: Upload

API accepts file metadata and payload source.

Store:
- raw file
- raw payload JSON
- parser version

### Step 2: Parse

Parser converts uploaded file into normalized return rows.

Parser interface:

```python
class BaseImportedReturnParser:
    return_type: str
    source_format: str

    def parse(self, file_obj) -> ParsedReturnPayload:
        ...
```

### Step 3: Validate

Validation checks:
- return period
- GSTIN structure
- mandatory columns/keys
- duplicates in imported file
- amount numeric integrity

### Step 4: Persist

Persist `GstImportedReturn` and normalized rows.

Recommended normalized-row storage:
- either child model `GstImportedReturnRow`
- or normalized JSON row store if we want faster initial rollout

For scale and queryability, prefer a child row table.

### Step 5: Create or attach run

Run creation modes:
- create new run from imported return
- attach imported return to existing draft run

## API Design

Do not change existing APIs in phase 1.

Add new version-safe endpoints under:
- `/api/gst-reconciliation/`

### Run APIs

- `POST /api/gst-reconciliation/runs/`
  - create run
- `GET /api/gst-reconciliation/runs/`
  - list runs by type/period/status
- `GET /api/gst-reconciliation/runs/<id>/`
  - run summary
- `POST /api/gst-reconciliation/runs/<id>/submit/`
- `POST /api/gst-reconciliation/runs/<id>/approve/`
- `POST /api/gst-reconciliation/runs/<id>/reject/`
- `POST /api/gst-reconciliation/runs/<id>/close/`
- `POST /api/gst-reconciliation/runs/<id>/reopen/`

### Import APIs

- `POST /api/gst-reconciliation/imports/`
  - upload/import file
- `GET /api/gst-reconciliation/imports/<id>/`
  - import detail
- `POST /api/gst-reconciliation/imports/<id>/validate/`
  - revalidate

### Matching APIs

- `POST /api/gst-reconciliation/runs/<id>/match/`
  - execute matcher
- `GET /api/gst-reconciliation/runs/<id>/items/`
  - paginated item list
- `GET /api/gst-reconciliation/runs/<id>/summary/`
  - summary cards and counts

### Review APIs

- `POST /api/gst-reconciliation/items/<id>/review/`
- `POST /api/gst-reconciliation/items/<id>/override/`
- `POST /api/gst-reconciliation/items/<id>/relink/`
- `POST /api/gst-reconciliation/items/bulk-review/`

### Audit APIs

- `GET /api/gst-reconciliation/runs/<id>/actions/`
- `GET /api/gst-reconciliation/items/<id>/actions/`

## Backward-Compatible Rollout Strategy

### Phase 1

Add new framework tables and services.

Keep existing APIs untouched:
- purchase 2B import APIs still write current `Gstr2bImportBatch` and `Gstr2bImportRow`
- GSTR-1 and GSTR-3B report APIs continue as-is

Add adapters:
- purchase 2B adapter builds reconciliation runs from current batch tables
- report adapter builds GSTR-1/GSTR-3B runs from current summary services

### Phase 2

Start routing new backend workflows through `gst_reconciliation`:
- purchase 2B match endpoint can optionally create/update a run
- GST exception dashboard can consume run summaries when available

### Phase 3

Move advanced UI and operational workflows to new APIs.

## Reuse Plan by Feature

### For GSTR-2B

Reuse:
- current batch import tables
- current row review UI/API concepts
- current ITC gating policy controls

Replace gradually:
- direct matching logic with pluggable matcher
- ad hoc row status updates with reconciliation item status

### For GSTR-1

Reuse:
- existing base queryset, summary, validations, readiness, and table views

Add:
- imported return pipeline
- books-vs-imported run builder

### For GSTR-3B

Reuse:
- [Gstr3bSummaryService](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/gstr3b/services.py)
- existing validation logic
- existing comparison service structure

Add:
- imported return model and parser
- computed-vs-imported run builder

## Performance and Scalability

### Query Strategy

- precompute item summaries on run
- page `GstReconciliationItem` by indexed status and severity
- materialize counts into `run.summary_json`
- avoid reparsing imported payload for every API call

### Storage Strategy

- use normalized row tables for imports if row counts become large
- store raw payload once, normalized rows separately
- keep summary JSON for quick dashboards

### Large Dataset Controls

- soft limit rows returned per API page
- async-ready matching service interface
- optional future batch processing by supplier/GSTIN

### Recommended Indexes

On imported row model if added:
- `(imported_return, supplier_gstin, invoice_number)`
- `(imported_return, doc_type, invoice_date)`
- `(imported_return, match_status)`

On reconciliation items:
- `(run, match_status, severity)`
- `(run, gstin, invoice_number, invoice_date)`
- `(run, is_actionable, manual_override)`

## Multi-Entity and Multi-GSTIN Safety

Every reconciliation model must carry:
- `entity`
- `entityfinid`
- `subentity`
- `gst_registration` or GSTIN-scoped equivalent

Rules:
- no cross-entity matching
- no cross-subentity matching unless explicitly configured
- no cross-GSTIN matching within multi-registration entities

## Audit Trail Principles

Every meaningful action should be logged:
- import uploaded
- import validated
- match executed
- item overridden
- run submitted
- run approved/rejected
- run closed/reopened

Audit logs should capture:
- actor
- previous and new status
- reason/comment
- request metadata if useful

## Permissions and Approval Model

Suggested new permission families:
- `gst_reconciliation.run.view`
- `gst_reconciliation.run.create`
- `gst_reconciliation.run.match`
- `gst_reconciliation.run.review`
- `gst_reconciliation.run.approve`
- `gst_reconciliation.run.close`
- `gst_reconciliation.import.manage`

Backwards-compatible mapping:
- users with current GST reporting permissions can still use old reports
- new reconciliation operations can be introduced separately

## Open Design Decisions

1. Should `gst_reconciliation` be a standalone app or live under `reports`?
   - recommended: standalone app

2. Should imported rows be stored in normalized relational tables or JSON only?
   - recommended: relational rows for scale and filtering

3. Should run approval be mandatory for all tenants?
   - recommended: policy-driven

4. Should GSTR-3B stay bucket-level only?
   - recommended: yes for phase 1

## Recommended Rollout Plan

### Phase 1: Core Framework

- create models
- create run service
- create action log service
- add matcher interfaces
- add purchase 2B adapter

### Phase 2: Import and Matching

- add imported return ingestion
- add GSTR-2B parser
- add GSTR-1 parser
- add GSTR-3B parser
- add item review APIs

### Phase 3: Report Integration

- feed GST exception dashboard from run summaries
- add run-based drilldowns
- add reconciliation history APIs

### Phase 4: Advanced Controls

- maker-checker
- close/reopen
- bulk review actions
- assignment and SLA flows

## Final Recommendation

Do not replace current `purchase` and `reports` GST features directly.

Instead:
- keep current services as trusted source builders
- add `gst_reconciliation` as orchestration and persistence layer
- migrate purchase `2B` first
- then add imported `GSTR-1`
- then add imported `GSTR-3B`

This gives Finacc a scalable reconciliation framework without destabilizing the current report stack.
