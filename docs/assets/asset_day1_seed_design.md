# Asset Day-1 Seed Design

## Purpose

This document defines how the Asset module should be seeded so a new customer can start using fixed assets on day 1 with correct default accounting selections.

The goal is not to fully lock the customer from changing mappings later.

The goal is:

- preload the most useful Indian-standard asset categories
- preload the required fixed asset ledgers
- map each category to the correct ledgers by default
- auto-select safe defaults in the UI and API
- reduce wrong ledger selection as much as possible

## Current State

The current asset seed already has a working base:

- `AssetSettings` can be seeded per entity
- `AssetCategory` already supports ledger mapping fields
- `AssetSeedService` already exists
- `FinancialSeedService` already seeds the `indian_accounting_final` chart

Relevant code:

- [assets/seeding.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/seeding.py:26)
- [assets/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/models.py:91)
- [assets/views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/views.py:361)
- [financial/seeding.py](/Users/ansh/finacc-angular/finacc-django/Finacc/financial/seeding.py:25)

### Current seed limitations

Today the asset seed creates only:

- `COMPUTER`
- `PERIPHERAL`

and only a very small ledger set around them.

That is not enough for real day-1 onboarding.

## Design Principles

1. Seed the maximum useful starter set, not every possible category.
2. Follow common Indian accounting expectations.
3. Prefer shared control ledgers where separate ledgers are not materially necessary.
4. Use category-level defaults so the first selection is correct.
5. Keep customer editability, but make the seeded mapping the recommended path.
6. Support tangible, intangible, right-of-use, and CWIP from day 1.
7. Keep the seed idempotent and safe to rerun.

## Day-1 Customer Outcome

After onboarding and seed:

- asset settings already exist
- asset categories already exist for common asset classes
- ledgers required for capitalization, depreciation, impairment, disposal, and CWIP already exist
- each seeded category already points to the correct ledgers
- user can create an asset without manually figuring out accounting structure first

## Proposed Seed Scope

## 1. Asset settings

Seed one entity-level default `AssetSettings` row with:

- `default_doc_code_asset = FA`
- `default_doc_code_disposal = FAD`
- `default_workflow_action = draft`
- `default_depreciation_method = SLM`
- `default_useful_life_months = 60`
- `default_residual_value_percent = 5.0000`
- `depreciation_posting_day = 30`
- `allow_multiple_asset_books = False`
- `auto_post_depreciation = False`
- `auto_number_assets = True`
- `require_asset_tag = False`
- `enable_component_accounting = False`
- `enable_impairment_tracking = True`
- `capitalization_threshold = 0.00`

### Suggested policy controls

- `capitalization_basis = manual_or_posting`
- `capitalization_threshold_rule = warn`
- `depreciation_proration = daily`
- `depreciation_posting_mode = manual_run`
- `depreciation_lock_rule = hard`
- `backdated_capitalization_rule = warn`
- `backdated_disposal_rule = hard`
- `negative_nbv_rule = block`
- `component_accounting = off`
- `allow_manual_depreciation_override = warn`
- `allow_posting_without_tag = on`
- `multi_book_mode = single`

## 2. Ledger backbone

We should not create a separate P&L and reserve structure for every micro-category.

The better default is:

- category-specific asset ledgers for major asset classes
- shared contra ledgers
- shared depreciation / impairment / disposal outcome ledgers
- a dedicated amortization track for intangibles
- a dedicated CWIP track

### Proposed default ledgers

| Ledger | Suggested purpose |
| --- | --- |
| Land | Freehold / leasehold land |
| Building | Office / factory / warehouse building |
| Leasehold Improvements | Fit-outs and improvements |
| Plant and Machinery | Production assets |
| Furniture and Fixtures | Furniture and fittings |
| Office Equipment | General office equipment |
| Computers and IT Equipment | Laptops, desktops, servers |
| Printers and Peripherals | Printers, scanners, accessories |
| Vehicles | Cars, trucks, commercial vehicles |
| Electrical Installations | Panels, wiring, electrical systems |
| Air Conditioners and HVAC | AC and cooling infrastructure |
| Tools and Equipment | Operational tools |
| Security and Surveillance Equipment | CCTV, access devices |
| Medical / Laboratory Equipment | Sector-specific asset class |
| Intangible Assets - Software | Purchased software |
| Intangible Assets - Licenses | Business licenses, software licenses |
| Right-of-Use Assets | Lease assets |
| Capital Work-in-Progress | Assets under installation or completion |
| Accumulated Depreciation - Tangible Assets | Common contra for most owned tangible assets |
| Accumulated Depreciation - Vehicles | Optional separate vehicle contra |
| Accumulated Amortization - Intangible Assets | Contra for intangibles |
| Accumulated Depreciation - ROU Assets | Contra for lease assets |
| Impairment Reserve - Assets | Common impairment reserve |
| Depreciation Expense | Common depreciation expense |
| Amortization Expense | Expense for intangibles |
| Depreciation Expense - ROU | Optional separate ROU depreciation bucket |
| Impairment Expense | Common impairment expense |
| Gain on Sale of Asset | Common disposal gain ledger |
| Loss on Sale of Asset | Common disposal loss ledger |

## 3. Category pack

The system should seed a standard starter category library like this.

### Tangible assets

| Code | Category | Nature | Useful life months | Residual % | Asset ledger |
| --- | --- | --- | ---: | ---: | --- |
| LAND | Land | TANGIBLE | 9999 | 0.0000 | Land |
| BUILDING | Building | TANGIBLE | 720 | 5.0000 | Building |
| LEASEHOLD_IMPROVEMENT | Leasehold Improvement | TANGIBLE | 120 | 5.0000 | Leasehold Improvements |
| PLANT_MACHINERY | Plant and Machinery | TANGIBLE | 180 | 5.0000 | Plant and Machinery |
| FURNITURE_FIXTURE | Furniture and Fixture | TANGIBLE | 120 | 5.0000 | Furniture and Fixtures |
| OFFICE_EQUIPMENT | Office Equipment | TANGIBLE | 60 | 5.0000 | Office Equipment |
| COMPUTER | Computers | TANGIBLE | 36 | 5.0000 | Computers and IT Equipment |
| PERIPHERAL | Printers and Peripherals | TANGIBLE | 24 | 5.0000 | Printers and Peripherals |
| SERVER_NETWORK | Servers and Network Equipment | TANGIBLE | 36 | 5.0000 | Computers and IT Equipment |
| VEHICLE | Vehicles | TANGIBLE | 96 | 5.0000 | Vehicles |
| ELECTRICAL | Electrical Installations | TANGIBLE | 120 | 5.0000 | Electrical Installations |
| HVAC | Air Conditioners and HVAC | TANGIBLE | 84 | 5.0000 | Air Conditioners and HVAC |
| TOOLS_EQUIPMENT | Tools and Equipment | TANGIBLE | 60 | 5.0000 | Tools and Equipment |
| SECURITY_EQUIPMENT | Security Equipment | TANGIBLE | 60 | 5.0000 | Security and Surveillance Equipment |
| LAB_MEDICAL | Laboratory / Medical Equipment | TANGIBLE | 120 | 5.0000 | Medical / Laboratory Equipment |

### Intangible assets

| Code | Category | Nature | Useful life months | Residual % | Asset ledger |
| --- | --- | --- | ---: | ---: | --- |
| SOFTWARE | Software | INTANGIBLE | 36 | 0.0000 | Intangible Assets - Software |
| LICENSE | Licenses | INTANGIBLE | 36 | 0.0000 | Intangible Assets - Licenses |
| WEBSITE_DIGITAL | Website / Digital Assets | INTANGIBLE | 36 | 0.0000 | Intangible Assets - Software |

### Lease and construction classes

| Code | Category | Nature | Useful life months | Residual % | Asset ledger |
| --- | --- | --- | ---: | ---: | --- |
| ROU_ASSET | Right-of-Use Asset | ROU | 60 | 0.0000 | Right-of-Use Assets |
| CWIP_GENERAL | Capital Work-in-Progress | CWIP | 9999 | 0.0000 | Capital Work-in-Progress |

## 4. Ledger mapping rules by category type

### Standard tangible asset categories

- `asset_ledger` -> class-specific asset ledger
- `accumulated_depreciation_ledger` -> Accumulated Depreciation - Tangible Assets
- `depreciation_expense_ledger` -> Depreciation Expense
- `impairment_expense_ledger` -> Impairment Expense
- `impairment_reserve_ledger` -> Impairment Reserve - Assets
- `gain_on_sale_ledger` -> Gain on Sale of Asset
- `loss_on_sale_ledger` -> Loss on Sale of Asset
- `cwip_ledger` -> Capital Work-in-Progress

### Vehicle category

Same as standard tangible, but optionally:

- `accumulated_depreciation_ledger` -> Accumulated Depreciation - Vehicles

### Intangible categories

- `asset_ledger` -> relevant intangible asset ledger
- `accumulated_depreciation_ledger` -> Accumulated Amortization - Intangible Assets
- `depreciation_expense_ledger` -> Amortization Expense
- `impairment_expense_ledger` -> Impairment Expense
- `impairment_reserve_ledger` -> Impairment Reserve - Assets
- `gain_on_sale_ledger` -> Gain on Sale of Asset
- `loss_on_sale_ledger` -> Loss on Sale of Asset
- `cwip_ledger` -> null by default

### Right-of-use category

- `asset_ledger` -> Right-of-Use Assets
- `accumulated_depreciation_ledger` -> Accumulated Depreciation - ROU Assets
- `depreciation_expense_ledger` -> Depreciation Expense - ROU
- `impairment_expense_ledger` -> Impairment Expense
- `impairment_reserve_ledger` -> Impairment Reserve - Assets
- `gain_on_sale_ledger` -> Gain on Sale of Asset
- `loss_on_sale_ledger` -> Loss on Sale of Asset

### CWIP category

- `asset_ledger` -> final target class is decided later
- `cwip_ledger` -> Capital Work-in-Progress
- `accumulated_depreciation_ledger` -> null
- `depreciation_expense_ledger` -> null
- `impairment ledgers` -> optional, usually seeded but unused until capitalization
- disposal ledgers -> seeded but rarely used pre-capitalization

## 5. First-selection behavior

The first user experience should behave like this:

### When category is selected on asset master

Auto-fill:

- depreciation method
- useful life
- residual value
- default ledger
- category traceability rules

If asset ledger is empty at asset level:

- auto-set from category

If user changes category:

- show a warning before replacing accounting defaults if the asset already has custom selections

### When capitalization happens

The posting should primarily trust category-level mapping.

The asset-level `ledger` should be either:

- auto-derived from category, or
- validated against category recommendation

### UI guidance

In `asset meta`, ledgers should be enriched with recommendation semantics, not only raw ledger rows.

Current meta response only returns:

- all categories
- all ledgers

from [assets/views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/views.py:365)

That is too open-ended for guided onboarding.

We should eventually add:

- recommended ledgers by role
- category default mapping payload
- maybe allowed ledger subsets by category nature

## 6. What should be seeded automatically

These should be created automatically during entity onboarding when `seed_financial` is on:

- financial chart using `indian_accounting_final`
- posting static accounts
- asset settings
- asset ledgers
- asset categories

The asset seed should be part of normal onboarding-ready bootstrap, not just a manual repair command.

Today the asset seed exists only as a standalone command:

- [seed_asset_module.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/management/commands/seed_asset_module.py:8)

That is useful for repair and backfill, but not enough for guaranteed day-1 readiness.

## 7. What should remain customer-editable

Editable later:

- category names
- useful life
- residual values
- capitalization threshold
- asset ledger mapping
- depreciation ledger mapping
- impairment and disposal mappings

Not recommended to freely modify without warning:

- seeded system ledgers
- category codes
- seeded category accounting controls

Recommended product behavior:

- allow edits
- show warning if seeded mapping is being changed
- show seeded recommendation beside the chosen value

## 8. Categories we should not try to pre-create

We should avoid trying to seed ultra-specific niche categories such as:

- aircraft assets
- telecom tower infrastructure
- mining rigs
- cinema projection systems
- hotel kitchen specialty machinery
- oil and gas field equipment

These can be added by the customer later.

The seed should focus on high-frequency Indian business categories.

## 9. Implementation phases

### Phase A: Expand seed catalog

- extend `AssetSeedService` category library
- add full ledger backbone
- add category-to-ledger mapping pack

### Phase B: Improve onboarding integration

- call asset seed automatically during entity bootstrap
- keep command for backfill / repair

### Phase C: Improve meta/defaulting

- return recommended mappings in asset meta
- auto-fill asset form from selected category

### Phase D: Add safeguards

- warning on custom ledger override
- validation for missing required mapped ledgers by category nature

## 10. Proposed implementation decision summary

1. Seed a broad starter asset category pack based on Indian common usage.
2. Seed a disciplined ledger pack, not one ledger for every tiny category.
3. Use shared depreciation / impairment / disposal ledgers where practical.
4. Give intangibles, ROU, and CWIP separate accounting treatment from day 1.
5. Auto-select category mappings first; customer can still override.
6. Move asset seeding into onboarding-ready bootstrap flow.

## 11. Immediate coding target

If we proceed to implementation, the first code changes should be:

1. Refactor [assets/seeding.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/seeding.py:26) into a declarative seed catalog instead of hardcoded two-category logic.
2. Add a richer seeded category map and ledger map.
3. Integrate asset seeding into onboarding flow after financial seed completes.
4. Extend asset meta so frontend can default more intelligently.

## Final conclusion

The asset module already has the right architecture for day-1 seed readiness.

What is missing is not structural capability.
What is missing is the size and quality of the seeded starter pack.

Once the proposed starter catalog and ledger map are implemented, the Asset module can open much more safely for a new customer on the first day of go-live.
