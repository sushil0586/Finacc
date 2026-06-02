# Seed Command Reference

## Purpose

This document is the current seed and bootstrap command inventory for the backend.

It answers three practical questions:

- what seed or bootstrap commands exist
- what each command actually seeds
- how to run each command correctly

This review is based on the current management commands and seeding services in the codebase.

## General Run Pattern

From the repository root:

```bash
./Finacc/venv/bin/python Finacc/manage.py <command> [options]
```

If your virtualenv is already activated:

```bash
python Finacc/manage.py <command> [options]
```

## Important Distinction

Not every command with similar behavior is a pure "seed" command.

There are three broad groups:

1. Seed commands
   They create default masters, catalogs, numbering, roles, or mappings.
2. Bootstrap commands
   They create and connect foundational records needed for a module to work.
3. Reconcile or repair commands
   They normalize or repair previously created data against a target catalog.

This document includes all three when they are part of setup or master-data readiness.

## Onboarding-Driven Seeding

Before the command-by-command list, one important note:

Entity onboarding itself already performs part of the setup automatically through `EntityOnboardingService`.

Current onboarding can automatically seed:

- financial chart and ledgers
- RBAC defaults
- default subentity
- default roles
- document numbering
- posting static account master

Current onboarding default seed options are exposed in [entity/onboarding_views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/entity/onboarding_views.py:187).

That means some environments may already have base setup even before any manual management command is run.

## Command Inventory

## Entity Module

### `seed_entity_master_data`

Purpose:
- seeds entity-domain base masters
- GST registration types
- entity constitutions

Scope:
- global master data
- not entity-specific operational data

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_entity_master_data
```

With actor:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_entity_master_data --actor-id 1
```

Notes:
- safe to rerun
- reactivates seeded rows when needed

## Financial Module

### `seed_indian_chart_of_accounts`

Purpose:
- seeds the final Indian chart of accounts for one entity

Scope:
- entity-specific
- chart of accounts, account types, account heads, and default accounts via `FinancialSeedService`

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_indian_chart_of_accounts --entity-id 12
```

Recommended use:
- primary command when you want the standard Indian COA for an entity

### `seed_financial_template`

Purpose:
- applies a selected financial template to an entity

Scope:
- entity-specific
- same seeding engine as above, but template-driven

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_financial_template --entity-id 12
```

With explicit template:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_financial_template --entity-id 12 --template-code indian_accounting_final
```

Recommended use:
- use this if multiple templates are expected in future
- today, `indian_accounting_final` is the important one

### `seed_common_ledgers`

Purpose:
- seeds a broad non-party ledger set for one entity

Scope:
- entity-specific
- internally uses `FinancialSeedService.seed_entity(..., template_code="indian_accounting_final")`

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_common_ledgers --entity-id 12
```

Recommended use:
- functionally overlaps with `seed_indian_chart_of_accounts`
- prefer `seed_indian_chart_of_accounts` as the clearer business-facing command

### `bootstrap_financial_foundation`

Purpose:
- bootstraps additive financial foundation data
- ensures `FinancialSettings`
- resyncs `Ledger` rows

Scope:
- all entities or one entity
- bootstrap and repair, not full COA seeding

Commands:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_financial_foundation
```

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_financial_foundation --entity-id 12
```

Recommended use:
- run when ledger foundation or `FinancialSettings` need repair
- not a replacement for COA seeding

### `reconcile_indian_chart_of_accounts`

Purpose:
- reconciles existing entity ledgers and accounts against the final Indian chart

Scope:
- one entity or all entities
- repair and normalization command

Commands:

```bash
./Finacc/venv/bin/python Finacc/manage.py reconcile_indian_chart_of_accounts --entity-id 12
```

All entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py reconcile_indian_chart_of_accounts --all
```

Recommended use:
- use after older live data drift
- use when existing ledgers need to be normalized to current COA expectations

## Posting Module

### `bootstrap_static_accounts`

Purpose:
- seeds static posting account master
- creates missing default system accounts and synced ledgers
- creates entity mappings for important posting codes

Scope:
- entity-specific
- bootstrap for posting/static-account setup

Dry run:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_static_accounts --entity-id 12
```

Apply changes:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_static_accounts --entity-id 12 --apply
```

Include sales-side mappings:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_static_accounts --entity-id 12 --include-sales --apply
```

Subentity-scoped mappings:

```bash
./Finacc/venv/bin/python Finacc/manage.py bootstrap_static_accounts --entity-id 12 --subentity-id 5 --apply
```

Recommended use:
- preferred current command for posting static-account bootstrapping

### `seed_static_accounts`

Purpose:
- seeds `StaticAccount` master
- optionally maps entity accounts through auto-map, JSON file, or copy-from-entity

Scope:
- global master and optional entity mapping

Master only:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_static_accounts --only-master
```

Auto-map for one entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_static_accounts --entity-id 12 --auto-map
```

Dry-run forced remap:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_static_accounts --entity-id 12 --auto-map --force --dry-run
```

Copy mapping from another entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_static_accounts --entity-id 12 --copy-from-entity 3
```

Recommended use:
- older or more manual mapping-oriented command
- `bootstrap_static_accounts` is usually the better operational choice now

## Numbering Module

### `seed_doc_sequences`

Purpose:
- seeds `DocumentType` and `DocumentNumberSeries` together using the current numbering schema

Scope:
- entity + financial year + optional subentity

Seed all default document types:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_doc_sequences --entity 12 --entityfinid 7
```

Seed one code only:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_doc_sequences --entity 12 --entityfinid 7 --doc-code JV
```

Custom one-off numbering seed:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_doc_sequences --entity 12 --entityfinid 7 --module custom --doc-key CUSTOM_DOC --name "Custom Document" --default-code CD
```

Default bundled doc codes currently include:

- `SINV`
- `SCN`
- `SDN`
- `PINV`
- `PCN`
- `PDN`
- `RV`
- `PV`
- `CV`
- `BV`
- `JV`
- `FA`
- `FAD`

Recommended use:
- primary generic numbering seed command

Operational note:
- the generic selector code is `PV`, but the payment voucher default document code seeded underneath is `PPV`
- this is current code behavior, so use `PV` when filtering `seed_doc_sequences`, and expect `PPV` as the seeded payment doc code

## Payments, Receipts, Vouchers Numbering

These commands seed narrower numbering use cases when you want just one domain.

### `seed_payment_numbering`

Purpose:
- seeds `PAYMENT_VOUCHER` numbering

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payment_numbering --entity 12 --entityfinid 7
```

Example with custom format knobs:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payment_numbering --entity 12 --entityfinid 7 --doc-code PPV --prefix PPV --start 1 --padding 5 --reset yearly
```

### `seed_receipt_numbering`

Purpose:
- seeds `RECEIPT_VOUCHER` numbering

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_receipt_numbering --entity 12 --entityfinid 7
```

### `seed_voucher_numbering`

Purpose:
- seeds voucher numbering for cash, bank, and journal vouchers

Seed all voucher types:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_voucher_numbering --entity 12 --entityfinid 7
```

Seed only journal vouchers:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_voucher_numbering --entity 12 --entityfinid 7 --voucher-type JOURNAL
```

Recommended use:
- use these when you want domain-specific numbering control
- use `seed_doc_sequences` when you want one general numbering command

## Asset Module

### `seed_asset_module`

Purpose:
- seeds asset settings
- seeds asset ledger backbone
- seeds asset categories with ledger mappings

Scope:
- entity-specific

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_asset_module --entity-id 12
```

Current seeded coverage:
- asset settings
- tangible asset starter pack
- intangible asset starter pack
- ROU and CWIP categories
- depreciation, amortization, impairment, and disposal ledgers

Important behavior:
- now rerun-safe
- preserves existing customer-created or customer-edited rows where codes already exist
- only backfills missing values instead of overwriting configured values

## Catalog Module

### `seed_catalog_masters`

Purpose:
- seeds basic catalog masters for products and inventory setup

Current seeded areas:
- product categories
- brands
- units of measure
- HSN/SAC
- price lists
- product attributes

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_catalog_masters --entity-id 12
```

All entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_catalog_masters
```

## Geography Module

### `seed_india_geography`

Purpose:
- seeds or repairs India country and GST state code masters

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_india_geography
```

Dry run:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_india_geography --dry-run
```

### `seed_india_district_city_sample`

Purpose:
- seeds sample districts and cities for testing

Dependency:
- run `seed_india_geography` first

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_india_district_city_sample
```

Dry run:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_india_district_city_sample --dry-run
```

Recommended use:
- testing and demos
- not a complete production district/city master

## Purchase Module

### `seed_purchase_choice_overrides`

Purpose:
- seeds supported purchase choice override rows

Current groups include:
- supply category
- taxability
- tax regime
- document type
- status
- ITC claim status
- GSTR-2B match status
- reverse charge
- service type

Entity-level:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_purchase_choice_overrides --entity 12
```

Subentity-level:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_purchase_choice_overrides --entity 12 --subentity 5
```

## Sales Module

### `seed_sales_choice_overrides`

Purpose:
- seeds supported sales choice override rows

Current groups include:
- supply category
- taxability
- tax regime
- document type
- status
- GST compliance mode
- e-invoice applicability
- e-way applicability
- bill-to / ship-to

Entity-level:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_sales_choice_overrides --entity 12
```

Subentity-level:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_sales_choice_overrides --entity 12 --subentity 5
```

### `repair_entity_bootstrap`

Purpose:
- repairs legacy entities so they receive the same baseline newer entities now get during onboarding
- gives ops/support one rerun-safe command instead of remembering many separate seeds

Included by default:
- entity policy
- static account master
- financial reconciliation and ledger resync
- RBAC seed when an actor is available
- numbering for all existing FYs and entity-level/subentity-level scopes
- catalog masters
- asset module seed
- purchase and sales choice overrides

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py repair_entity_bootstrap --entity-id 12
```

Single entity with explicit actor for RBAC ownership:

```bash
./Finacc/venv/bin/python Finacc/manage.py repair_entity_bootstrap --entity-id 12 --actor-id 5
```

All entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py repair_entity_bootstrap --all-entities
```

All entities, but skip RBAC:

```bash
./Finacc/venv/bin/python Finacc/manage.py repair_entity_bootstrap --all-entities --skip-rbac
```

Notes:
- if an entity has no `createdby` and you do not pass `--actor-id`, the command skips RBAC instead of failing
- this is the preferred repair command after new onboarding seeders are introduced

## RBAC Module

### `seed_hrms_rbac`

Purpose:
- seeds HRMS RBAC catalog
- seeds entity HRMS roles

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_hrms_rbac --entity-id 12
```

All active entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_hrms_rbac --all-entities
```

### `seed_payroll_rbac`

Purpose:
- seeds payroll RBAC catalog
- seeds payroll entity role mappings

Catalog only:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payroll_rbac --catalog-only
```

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payroll_rbac --entity-id 12
```

All active entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payroll_rbac --all-entities
```

### `seed_payables_rbac`

Purpose:
- seeds payables reporting permissions
- creates or updates the `payables_user` role

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payables_rbac --entity-id 12
```

All active entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payables_rbac --all-entities
```

### `seed_tcs_hierarchy`

Purpose:
- seeds hierarchical TCS menus
- seeds TCS permissions
- optionally replaces TCS role-permission mappings for a target role

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_tcs_hierarchy --entity-id 12
```

With explicit role code:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_tcs_hierarchy --entity-id 12 --role-code legacy_role_2
```

Replace TCS permissions for the target role:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_tcs_hierarchy --entity-id 12 --replace-role-permissions
```

## HRMS Module

### `seed_global_hrms_catalog`

Purpose:
- seeds global HRMS onboarding catalog

Current seeded areas include:
- leave types
- leave policies
- leave policy rules
- shifts
- holiday calendars
- attendance policies
- HR policies

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_hrms_catalog
```

Dry run:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_hrms_catalog --dry-run
```

Force update existing global records:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_hrms_catalog --force
```

## Payroll Module

### `seed_global_payroll_catalog`

Purpose:
- seeds global payroll component groups
- seeds global payroll components
- seeds global salary templates and template lines

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_payroll_catalog
```

Dry run:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_payroll_catalog --dry-run
```

Only components:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_payroll_catalog --only components
```

Force update existing global records:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_global_payroll_catalog --force
```

### `seed_payroll_masters`

Purpose:
- seeds entity-scoped payroll setup safely and idempotently

Current service scope includes:
- payroll components
- salary structure and version setup
- payroll ledger policy
- payment modes and supporting setup
- payroll RBAC seed integration where needed by service dependencies

All active entities:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payroll_masters
```

Single entity:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_payroll_masters --entity-id 12
```

## Withholding Module

### `seed_withholding`

Purpose:
- seeds default TDS and TCS withholding sections

Current definitions include common Indian withholding sections such as:
- `194C`
- `194J`
- `194H`
- `194I`
- `194Q`
- `194A`
- `194N`
- `195`
- `206C(1)`
- `206C(1H)`

Command:

```bash
./Finacc/venv/bin/python Finacc/manage.py seed_withholding
```

Scope:
- global withholding configuration master

## Recommended Operational Order

For a new environment, a practical order is:

1. `seed_entity_master_data`
2. `seed_india_geography`
3. create entity through onboarding or normal process
4. `seed_indian_chart_of_accounts --entity-id <id>`
5. `bootstrap_static_accounts --entity-id <id> --apply`
6. `seed_doc_sequences --entity <id> --entityfinid <fy_id>`
7. `seed_catalog_masters --entity-id <id>`
8. `seed_asset_module --entity-id <id>`
9. `seed_purchase_choice_overrides --entity <id>`
10. `seed_sales_choice_overrides --entity <id>`
11. `seed_withholding`

Then module-specific extras as needed:

- `seed_global_hrms_catalog`
- `seed_hrms_rbac`
- `seed_global_payroll_catalog`
- `seed_payroll_masters`
- `seed_payroll_rbac`
- `seed_payables_rbac`
- `seed_tcs_hierarchy`

## Commands With Overlap

These commands overlap and should be used deliberately:

- `seed_common_ledgers`
  Uses the same financial seed path as `seed_indian_chart_of_accounts`.
- `seed_financial_template`
  More generic wrapper around the same financial seeding engine.
- `seed_static_accounts`
  Older manual mapping command.
- `bootstrap_static_accounts`
  Better current command for posting static-account setup.
- `seed_doc_sequences`
  Generic numbering seeder.
- `seed_payment_numbering`, `seed_receipt_numbering`, `seed_voucher_numbering`
  Narrower numbering seeders for targeted use.

## Modules Without Dedicated Seed Commands

After reviewing current management commands, there is no dedicated seed command in these modules for broad master bootstrap:

- bank reconciliation
- subscriptions
- manufacturing
- reports
- inventory operations
- receipts reporting beyond numbering

Some of those modules still receive seeded support indirectly through:

- financial seeding
- posting static accounts
- numbering
- RBAC menu/permission migrations
- onboarding services

## Practical Recommendation

For current day-to-day setup work, the most important commands are:

- `seed_entity_master_data`
- `seed_indian_chart_of_accounts`
- `bootstrap_static_accounts`
- `seed_doc_sequences`
- `seed_catalog_masters`
- `seed_asset_module`
- `seed_purchase_choice_overrides`
- `seed_sales_choice_overrides`
- `seed_withholding`

And for HRMS / payroll rollouts:

- `seed_global_hrms_catalog`
- `seed_hrms_rbac`
- `seed_global_payroll_catalog`
- `seed_payroll_masters`
- `seed_payroll_rbac`

## Final Ownership Matrix

This is the recommended operating split after the latest review and wiring work.

| Command / Seed Path | Part of migration | Part of new entity creation | Manual / repair only | Notes |
| --- | --- | --- | --- | --- |
| `seed_entity_master_data` | Yes | No | Optional | Now suitable as global master-data migration. |
| `seed_india_geography` | No | No | Yes | Kept manual for now because many existing tests and flows still assume geography is not preseeded. |
| `seed_india_district_city_sample` | No | No | Yes | Testing/demo only. |
| `seed_withholding` | Yes | No | Optional | Now suitable as global statutory master-data migration. |
| `seed_global_hrms_catalog` | Yes | No | Optional | Global HRMS catalog belongs to platform setup. |
| `seed_global_payroll_catalog` | Yes | No | Optional | Global payroll catalog belongs to platform setup. |
| `seed_payroll_rbac --catalog-only` | Not yet wired as migration | No | Yes | Good candidate for global platform bootstrap, but not migrated in this pass. |
| `seed_static_accounts --only-master` | Superseded | No | Optional | Prefer the posting migration-backed static master path instead. |
| `StaticAccountService.seed_static_account_master()` | Yes | Implicit | Optional | Now seeded through posting migration; also still called during onboarding flow. |
| `seed_indian_chart_of_accounts` / financial seed | No | Yes | Yes | Entity-specific chart and ledgers must stay tenant-scoped. |
| `bootstrap_financial_foundation` | No | No | Yes | Repair/bootstrap only. |
| `reconcile_indian_chart_of_accounts` | No | No | Yes | Repair/normalization only. |
| `seed_common_ledgers` | No | No | Yes | Overlaps with main financial seeding; not needed in normal onboarding. |
| `seed_financial_template` | No | No | Yes | Administrative or custom-template use. |
| `seed_doc_sequences` / numbering seeding | No | Yes | Yes | Already part of onboarding when enabled. |
| `seed_payment_numbering` | No | No | Yes | Targeted numbering repair/admin use. |
| `seed_receipt_numbering` | No | No | Yes | Targeted numbering repair/admin use. |
| `seed_voucher_numbering` | No | No | Yes | Targeted numbering repair/admin use. |
| `seed_catalog_masters` / `CatalogSeedService.seed_entity()` | No | Yes | Yes | Now attached to entity onboarding. |
| `seed_asset_module` / `AssetSeedService.seed_entity()` | No | Yes | Yes | Now attached to entity onboarding. |
| `seed_purchase_choice_overrides` / `PurchaseSeedService.seed_choice_overrides()` | No | Yes | Yes | Now attached to entity onboarding. |
| `seed_sales_choice_overrides` / `SalesSeedService.seed_choice_overrides()` | No | Yes | Yes | Now attached to entity onboarding. |
| `seed_payables_rbac` | No | No | Yes | Still an explicit entity admin step. |
| `seed_hrms_rbac` | No | No | Yes | Still an explicit entity admin step. |
| `seed_payroll_rbac` | No | No | Yes | Still an explicit entity admin step. |
| `seed_tcs_hierarchy` | No | No | Yes | Role-targeted admin seed; not suitable for generic migration or automatic onboarding. |
| `seed_payroll_masters` | No | No | Yes | Entity-scoped payroll rollout step, but not auto-onboarding in this pass. |

## What Was Implemented

### Now part of migrations

- entity master catalogs
- withholding master catalog
- global HRMS catalog
- global payroll catalog
- posting static account master

### Now part of new entity creation

- financial seed
- RBAC seed
- numbering seed
- catalog masters
- asset module seed
- purchase choice overrides
- sales choice overrides

### Still manual by design

- geography seed
- reconciliation and repair commands
- targeted numbering repair commands
- TCS hierarchy seed
- payables / HRMS / payroll RBAC role seeding
- payroll entity master rollout

## Current Caveat

Geography was intentionally left out of migration-backed seeding in the final implementation.

Reason:
- a large number of existing tests and setup flows still create `India` and related geography rows explicitly
- auto-seeding geography during migration currently collides with those assumptions

So the correct operational rule right now is:

- treat geography as a required platform setup command
- do not yet force it through app migration until those test and setup assumptions are normalized
