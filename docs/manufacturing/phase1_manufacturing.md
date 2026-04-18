# Manufacturing Phase 1

## Purpose

This document explains the current manufacturing module implemented in `Finacc` for Phase 1.

Phase 1 is intentionally focused on the **foundation layer**:

- Bill of Material management
- Draft manufacturing work orders
- BOM-based material explosion
- Manual material and output capture
- Posting inventory consumption and finished goods receipt
- Unpost and cancel lifecycle
- Angular workspace screens for BOM, work order, and settings

This phase is designed to support the first practical set of use cases:

- repacking
- simple assembly
- single-output manufacturing
- stock transformation from raw or semi-finished material to finished goods

It is not yet a full multi-step routing or costing engine. Those are later phases.

---

## Scope Summary

### Included in Phase 1

- `ManufacturingBOM`
- `ManufacturingBOMMaterial`
- `ManufacturingSettings`
- `ManufacturingWorkOrder`
- `ManufacturingWorkOrderMaterial`
- `ManufacturingWorkOrderOutput`
- work-order numbering
- inventory posting integration
- batch and expiry validation hooks
- negative-stock control
- Angular operational screens

### Not Included Yet

- routing
- operation steps
- machine / work-center planning
- QC stages
- partial operation execution by stage
- co-products or by-products
- multi-output support
- costing variance engine
- WIP accounting
- subcontracting / job work
- MRP and planning

---

## Design Principles

The manufacturing phase-1 implementation follows these architectural principles:

### 1. Keep manufacturing inside Finacc, not as a separate project

Manufacturing depends on:

- products
- UOM
- godowns
- entity / subentity / financial year scope
- numbering
- posting
- inventory movement
- RBAC

Because these already exist in `Finacc`, the module is implemented as a new domain area inside the same platform.

### 2. Keep manufacturing separate from sales and retail

Manufacturing is responsible for **stock transformation**.

It should not be mixed into:

- sales invoice logic
- retail session logic
- promotion logic

Those areas will reuse finished goods later, but the manufacturing module remains focused on production and repacking.

### 3. Reuse posting infrastructure

Manufacturing does not create a parallel stock engine.

Instead it reuses:

- `PostingService`
- `Entry`
- `InventoryMove`
- `TxnType`

This keeps inventory behavior consistent across modules.

### 4. Build scalable structure, but keep Phase 1 lean

The current schema is future-ready enough to grow into:

- routing
- costing
- batch traceability
- repacking policies
- retail integration

But only the essential operational slice is implemented now.

---

## Backend App Structure

The backend manufacturing app currently contains:

- [manufacturing/apps.py](C:/educure/finacc_new/Finacc/manufacturing/apps.py:1)
- [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:1)
- [manufacturing/serializers.py](C:/educure/finacc_new/Finacc/manufacturing/serializers.py:1)
- [manufacturing/services.py](C:/educure/finacc_new/Finacc/manufacturing/services.py:1)
- [manufacturing/views.py](C:/educure/finacc_new/Finacc/manufacturing/views.py:1)
- [manufacturing/urls.py](C:/educure/finacc_new/Finacc/manufacturing/urls.py:1)
- [manufacturing/tests.py](C:/educure/finacc_new/Finacc/manufacturing/tests.py:1)

The app is registered in Django settings and exposed through:

- `/api/manufacturing/`

---

## Domain Model

## 1. ManufacturingBOM

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:13).

Represents a recipe for manufacturing one finished product.

Key fields:

- `entity`
- `subentity`
- `code`
- `name`
- `description`
- `finished_product`
- `output_qty`
- `output_uom`
- `is_active`

Important notes:

- BOM code is unique within entity + subentity scope.
- Root-level and subentity-level uniqueness are handled separately.
- A BOM is scoped to one finished product.
- Phase 1 assumes one primary output product per BOM.

Example:

`SUGAR-1KG`

- Finished product: Sugar 1kg Pack
- Output qty: 1.0000
- Materials:
  - Sugar Bulk 1.0000 kg
  - Pouch 1
  - Label 1

## 2. ManufacturingBOMMaterial

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:47).

Represents one input line inside a BOM.

Key fields:

- `bom`
- `line_no`
- `material_product`
- `qty`
- `uom`
- `waste_percent`
- `note`

This is a recipe line, not a transaction line.

`waste_percent` is currently stored for future use and visibility, but Phase 1 posting does not apply a full costing or wastage formula using this field.

## 3. ManufacturingSettings

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:77).

Holds scope-level manufacturing behavior.

Key fields:

- `default_doc_code_work_order`
- `default_workflow_action`
- `policy_controls`

Current policy controls:

- `auto_explode_materials_from_bom`
- `allow_manual_material_override`
- `require_batch_for_batch_managed_items`
- `require_expiry_when_expiry_tracked`
- `block_negative_stock`
- `default_output_batch_mode`

## 4. ManufacturingWorkOrder

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:103).

Represents the execution document.

Key fields:

- `entity`
- `entityfin`
- `subentity`
- `work_order_no`
- `production_date`
- `bom`
- `source_location`
- `destination_location`
- `reference_no`
- `narration`
- `status`
- `posting_entry_id`

Status values:

- `DRAFT`
- `POSTED`
- `CANCELLED`

## 5. ManufacturingWorkOrderMaterial

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:137).

Represents material consumption lines on the work order.

Key fields:

- `material_product`
- `required_qty`
- `actual_qty`
- `unit_cost`
- `waste_qty`
- `batch_number`
- `manufacture_date`
- `expiry_date`
- `note`

Important behavior:

- `required_qty` is usually BOM-derived.
- `actual_qty` is the quantity actually issued / consumed.
- `waste_qty` is separately captured for visibility.
- posting issues inventory based on `actual_qty`.

## 6. ManufacturingWorkOrderOutput

Defined in [manufacturing/models.py](C:/educure/finacc_new/Finacc/manufacturing/models.py:163).

Represents finished goods output lines.

Key fields:

- `finished_product`
- `planned_qty`
- `actual_qty`
- `unit_cost`
- `batch_number`
- `manufacture_date`
- `expiry_date`
- `note`

Phase 1 rule:

- exactly one output line is supported

This keeps the first release operationally simple and posting-safe.

---

## Service Layer

Main orchestration happens in [manufacturing/services.py](C:/educure/finacc_new/Finacc/manufacturing/services.py:1).

The central class is:

- `ManufacturingWorkOrderService`

## Core Responsibilities

### 1. Normalize dates and quantities

Utility helpers:

- `_normalize_doc_date`
- `_q4`
- `_q4_or_none`

These ensure quantities and dates remain consistent before posting.

### 2. Scope-safe product and BOM loading

Helpers:

- `_load_product_for_scope`
- `_load_bom`

These ensure:

- the selected products belong to the correct entity
- the BOM belongs to the same scope

### 3. BOM explosion

Helper:

- `_explode_bom_materials`

If a BOM is selected and explicit material lines are not provided, the service explodes BOM materials proportionally based on requested output quantity.

Formula:

`required material = bom material qty * target output qty / bom output qty`

### 4. Batch and expiry validation

Helper:

- `_extract_batch_fields`

Validation behavior depends on `ManufacturingSettings.policy_controls`.

Current rules:

- batch-managed products can require batch numbers
- expiry-tracked products can require expiry dates
- non-batch-managed products cannot accept batch metadata

### 5. Negative stock enforcement

Helpers:

- `_available_base_qty`
- `_assert_stock_available`

If `block_negative_stock` is enabled, posting checks available stock at:

- entity
- product
- location
- batch

and blocks over-issue.

### 6. Default issue cost derivation

Helpers:

- `_available_value_totals`
- `_derive_issue_unit_cost`
- `_default_unit_cost`

Material issue valuation is derived from available stock value where possible.

Fallback behavior:

- use average available value / available quantity
- else fallback to product purchase rate
- else fallback to product selling price

### 7. Work-order numbering

Helpers:

- `_doc_type_for_work_order`
- `_allocate_work_order_no`

If `entityfinid` exists, numbering goes through the numbering service.

If it does not exist, a UUID-based fallback number is generated.

### 8. Posting

Manufacturing posting is handled through `PostingService.post()`.

Current posting behavior:

- material lines create `OUT` inventory movements from source location
- output line creates `IN` inventory movement into destination location
- transaction type is `TxnType.MANUFACTURING_WORK_ORDER`
- movement nature is `PRODUCTION`

There are no journal lines yet in Phase 1.

This means Phase 1 is currently an **inventory transformation document**, not yet a full financial manufacturing valuation engine.

---

## Work Order Lifecycle

## 1. Create Draft

The user creates a work order with:

- date
- BOM or manual lines
- source location
- destination location
- materials
- output

The work order is saved as `DRAFT`.

## 2. Update Draft

Draft work orders can be updated:

- change BOM
- change quantities
- change batch data
- change narration
- change locations

## 3. Post

Posting performs:

- stock validation
- cost derivation
- inventory issue creation
- inventory receipt creation
- posting entry linkage
- status update to `POSTED`

## 4. Unpost

Unposting:

- reverses manufacturing inventory effect using posting infrastructure
- resets work-order status back from posted state
- preserves audit trail in posting entries

## 5. Cancel

Draft work orders can be cancelled and marked `CANCELLED`.

Phase 1 keeps cancel simple and operational.

---

## API Endpoints

Defined in [manufacturing/urls.py](C:/educure/finacc_new/Finacc/manufacturing/urls.py:1).

## Meta

- `GET /api/manufacturing/meta/settings/`
- `GET /api/manufacturing/meta/bom-form/`
- `GET /api/manufacturing/meta/work-order-form/`

## Settings

- `GET /api/manufacturing/settings/`
- `PATCH /api/manufacturing/settings/`

## BOM

- `GET /api/manufacturing/boms/`
- `POST /api/manufacturing/boms/`
- `GET /api/manufacturing/boms/<pk>/`
- `PATCH /api/manufacturing/boms/<pk>/`
- `DELETE /api/manufacturing/boms/<pk>/`

## Work Order

- `GET /api/manufacturing/work-orders/`
- `POST /api/manufacturing/work-orders/`
- `GET /api/manufacturing/work-orders/<pk>/`
- `PATCH /api/manufacturing/work-orders/<pk>/`
- `POST /api/manufacturing/work-orders/<pk>/post/`
- `POST /api/manufacturing/work-orders/<pk>/unpost/`
- `POST /api/manufacturing/work-orders/<pk>/cancel/`

---

## API Behavior Notes

## BOM Form Meta

The BOM form meta API returns:

- products
- active BOM options

This allows the frontend to build product selectors without hardcoded lists.

## Work Order Form Meta

The work-order form meta API returns:

- products
- BOMs
- godowns
- current manufacturing settings
- current document-code hint

This allows the Angular workspace to load the whole context in one request.

## Response Serializer Details

Work-order responses include:

- location IDs and names
- BOM code
- posting entry ID
- total input value
- total output quantity
- material and output lines

Location IDs were added so the frontend can reopen and edit work orders safely without guessing location IDs from names.

---

## Frontend Implementation

The Angular frontend lives in:

- `C:\educure\Finacc\accountproject`

Phase 1 manufacturing UI is intentionally modeled after the newer `inventory_ops` experience instead of the older production-order popup.

## Why This Design Was Chosen

The `inventory_ops` style is better for manufacturing because it supports:

- a full-screen operational workspace
- header + totals + status visibility
- line-heavy editing
- post/unpost/cancel workflow
- better long-term extensibility

The old popup-based `productionorder` design is not a good fit for a scalable manufacturing module.

## Angular Files Added

### Models and Service

- [manufacturing.ts](C:/educure/Finacc/accountproject/src/app/model/manufacturing.ts:1)
- [manufacturing.service.ts](C:/educure/Finacc/accountproject/src/app/service/manufacturing/manufacturing.service.ts:1)

### Work Order UI

- [manufacturing-work-order-entry.component.ts](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-entry/manufacturing-work-order-entry.component.ts:1)
- [manufacturing-work-order-entry.component.html](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-entry/manufacturing-work-order-entry.component.html:1)
- [manufacturing-work-order-entry.component.scss](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-entry/manufacturing-work-order-entry.component.scss:1)

### Work Order Browser

- [manufacturing-work-order-list.component.ts](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-list/manufacturing-work-order-list.component.ts:1)
- [manufacturing-work-order-list.component.html](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-list/manufacturing-work-order-list.component.html:1)
- [manufacturing-work-order-list.component.scss](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-work-order-list/manufacturing-work-order-list.component.scss:1)

### BOM Workspace

- [manufacturing-bom-workspace.component.ts](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-bom-workspace/manufacturing-bom-workspace.component.ts:1)
- [manufacturing-bom-workspace.component.html](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-bom-workspace/manufacturing-bom-workspace.component.html:1)
- [manufacturing-bom-workspace.component.scss](C:/educure/Finacc/accountproject/src/app/component/manufacturing/manufacturing-bom-workspace/manufacturing-bom-workspace.component.scss:1)

### Settings UI

- [manufacturing-settings.component.ts](C:/educure/Finacc/accountproject/src/app/component/admin/manufacturing-settings/manufacturing-settings.component.ts:1)
- [manufacturing-settings.component.html](C:/educure/Finacc/accountproject/src/app/component/admin/manufacturing-settings/manufacturing-settings.component.html:1)
- [manufacturing-settings.component.scss](C:/educure/Finacc/accountproject/src/app/component/admin/manufacturing-settings/manufacturing-settings.component.scss:1)

### Routing and Config

- [config.service.ts](C:/educure/Finacc/accountproject/src/app/service/config/config.service.ts:1333)
- [app-routing.module.ts](C:/educure/Finacc/accountproject/src/app/app-routing.module.ts:108)

## Frontend Routes

The following routes are available:

- `/productionorder`
- `/manufacturing-work-order-entry`
- `/manufacturing-work-order-list`
- `/manufacturing-boms`
- `/manufacturingsettings`

`/productionorder` now points to the new manufacturing work-order screen so the old entry point still works.

---

## Operational Example

## Example 1: Repacking Sugar Bulk to 1kg Packs

### Master Setup

Products:

- `Sugar Bulk`
- `Sugar 1kg Pack`
- `Pouch`
- `Label`

Locations:

- `Bulk Store`
- `Finished Goods Store`

### BOM

Code: `SUGAR-1KG`

Finished product:

- `Sugar 1kg Pack`

Output qty:

- `1.0000`

Materials:

- Sugar Bulk: `1.0000`
- Pouch: `1.0000`
- Label: `1.0000`

### Work Order

User enters:

- production date
- BOM: `SUGAR-1KG`
- planned output qty: `100`
- source location: `Bulk Store`
- destination location: `Finished Goods Store`

The system explodes materials to:

- Sugar Bulk: `100`
- Pouch: `100`
- Label: `100`

The user may adjust:

- actual consumed qty
- waste qty
- batch data

On post:

- source stock goes out
- 100 finished packs come in
- output unit cost is derived from total issue value / total output qty

## Example 2: Simple Assembly

Finished product:

- `Gift Hamper`

Materials:

- Tea pack x 1
- Mug x 1
- Box x 1

Phase 1 can handle this as a BOM and work order in the same flow.

---

## Settings Behavior

Current settings shape is exposed through:

- [manufacturing/views.py](C:/educure/finacc_new/Finacc/manufacturing/views.py:28)

Supported editable settings:

- `default_doc_code_work_order`
- `default_workflow_action`
- `auto_explode_materials_from_bom`
- `allow_manual_material_override`
- `require_batch_for_batch_managed_items`
- `require_expiry_when_expiry_tracked`
- `block_negative_stock`
- `default_output_batch_mode`

Important note:

The backend currently persists the settings object, but Phase 1 does not yet support full editing of numbering rows themselves. The UI shows numbering information for visibility, but direct numbering-row persistence is still a later enhancement.

---

## RBAC Permissions

The module expects manufacturing-specific permissions such as:

### Settings

- `manufacturing.settings.view`

### BOM

- `manufacturing.bom.view`
- `manufacturing.bom.create`
- `manufacturing.bom.update`
- `manufacturing.bom.delete`

### Work Order

- `manufacturing.workorder.view`
- `manufacturing.workorder.create`
- `manufacturing.workorder.update`
- `manufacturing.workorder.post`
- `manufacturing.workorder.unpost`
- `manufacturing.workorder.cancel`

These permissions are already used by the backend views and Angular workspace visibility logic.

---

## Testing

Backend test coverage currently exists in:

- [manufacturing/tests.py](C:/educure/finacc_new/Finacc/manufacturing/tests.py:1)

Phase 1 tests validate:

- BOM CRUD and meta
- work-order create/post/unpost/cancel flow
- settings/meta behavior
- negative-stock validation

## Commands Used

### Backend tests

```powershell
$env:DEBUG='False'; python manage.py test manufacturing.tests --keepdb --noinput
```

### Backend compile check

```powershell
python -m compileall manufacturing
```

### Angular build

```powershell
npm.cmd run build:dev -- --no-progress
```

---

## Current Limitations

Phase 1 is production-foundation focused, so these constraints are intentional:

- one output line only
- no routing / steps
- no work center planning
- no operation-level scrap
- no costing variance engine
- no multiple output or byproduct handling
- no full numbering-row edit persistence
- no accounting journal generation for manufacturing cost absorption

These are not design failures. They are phase boundaries.

---

## How This Scales Into Later Phases

This phase was designed to support future manufacturing maturity without rewriting the module.

## Phase 2

Planned direction:

- routing
- operation steps
- sequential process execution
- step-level status and output

## Phase 3

Planned direction:

- batch traceability
- expiry-sensitive output handling
- stricter repacking control

## Phase 4

Planned direction:

- costing
- variance
- planned vs actual consumption analytics

## Phase 5 and Later

Planned direction:

- retail and commerce integration
- finished pack barcode selling
- promotion-aware sale of manufactured goods

---

## Final Summary

Manufacturing Phase 1 gives `Finacc` a proper stock-transformation base.

It supports:

- defining BOMs
- creating work orders
- exploding materials from BOM
- issuing stock from source location
- receiving finished goods into destination location
- post / unpost / cancel lifecycle
- Angular workspaces for day-to-day operations

This phase is the right foundation for:

- repacking
- simple manufacturing
- assembly
- later routing
- later costing
- later retail integration

It is intentionally practical, operational, and extensible.
