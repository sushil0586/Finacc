# Financial Account / Ledger Governance Blueprint

## Purpose

This document defines the target behavior for:

- `Accounts`
- `Ledgers`
- quick account popups
- code / series allocation
- party vs non-party governance

It is intended to prevent hardcoded business rules from spreading across:

- Angular UI
- Django serializers
- seed scripts
- repair / reconciliation commands

The goal is to move to a **config-driven accounting governance model**.

## Implementation Status

Status as of `2026-06-01`:

- backend governance config tables are implemented
- governance seed/bootstrap is implemented
- series-based code allocation is implemented
- ledger/account save flows use governance rules
- repair/backfill command is implemented
- Angular account workspace, quick popup, and ledger page now consume governance metadata
- Django verification passed: `51` tests green
- Angular compile verification passed

This document now serves two purposes:

1. describe the intended governance model
2. record the current implemented state

---

## 1. Core Product Principle

Finacc should treat `Ledger` and `Account` as related but not identical concepts.

### 1.1 Ledger

`Ledger` is the accounting master.

It owns:

- accounting code
- debit head
- credit head
- account type
- opening balances
- posting classification

### 1.2 Account

`Account` is the business / party profile.

It owns:

- party identity
- contact details
- billing / shipping address
- GST / PAN / compliance
- commercial profile
- bank details

### 1.3 Final meaning

- non-party accounting master = `Ledger only`
- party master = `Account + linked Ledger`

This should be the steady-state behavior everywhere.

---

## 2. Current Problems To Solve

Today the system still allows mixed states such as:

- party-like ledgers created as standalone direct ledgers
- direct ledgers with no code
- account head filtering behaving differently across screens
- party defaults split between frontend guesses and backend seed logic
- code allocation using generic `max + 1` instead of domain-based series

This causes:

- inconsistent rows in Ledger list
- unclear ownership of edits
- poor reporting hygiene
- confusing user experience

---

## 3. Final Target Behavior

## 3.1 Ledger page

Ledger page should support two outcomes:

1. `Direct ledger`
2. `Auto-managed ledger`

### Direct ledger

A ledger remains `Direct` only when it is **not party-like**.

Examples:

- indirect expense
- direct expense
- income ledger
- adjustment ledger
- statutory clearing ledger
- internal control ledger
- tax input/output ledger
- pure balance-sheet accounting master

### Auto-managed ledger

A ledger becomes `Auto-managed` when it is **party-like**.

Examples:

- customer
- vendor
- both customer/vendor
- bank account treated as business counterparty
- employee settlement account
- government counterparty account

When a party-like ledger is created from the Ledger page:

1. ledger is saved
2. ledger code is allocated if blank
3. linked account is auto-created
4. row becomes `Auto-managed`
5. future edits happen from Account page

This is the chosen behavior: **Option C**

---

## 3.2 Account page

Account page is the canonical create/edit flow for party masters.

When an account is created:

1. linked ledger must exist
2. ledger code must exist
3. debit/credit heads must follow the same party/account governance rules
4. resulting ledger is always `Auto-managed`

Account page should never create a party row without a ledger.

---

## 3.3 Quick account popup

All quick account popups must behave exactly like the main Account page for:

- party type defaults
- account type suggestion
- debit/credit head filtering
- linked ledger creation
- code allocation

No invoice or voucher screen should have its own isolated behavior.

All must use the same shared rules.

---

## 4. Party vs Non-Party Decision Rule

This must not be inferred by UI labels or string matching on names.

It must come from configured rules.

### 4.1 Decision result

Every create/update flow should determine a normalized classification:

- `party_managed`
- `ledger_only`

### 4.2 Recommended decision priority

1. explicit user / payload flag
2. configured account type rule
3. configured account head rule
4. configured party type rule

### 4.3 Important product rule

If the resolved result is `party_managed`, the system must ensure:

- linked account exists
- ledger code exists
- ledger row is treated as `Auto-managed`

If the resolved result is `ledger_only`, the system must ensure:

- no linked account is required
- ledger can remain `Direct`

---

## 5. Party Type, Account Type, and Heads

These fields must each have exactly one role.

### 5.1 Party Type

`Party Type` answers:

- who is this in business terms?

Examples:

- Customer
- Vendor
- Both
- Bank
- Employee
- Government
- Other

It should drive:

- business identity
- address/compliance requirements
- default suggestions
- voucher eligibility

It should **not** be the final posting classifier.

### 5.2 Account Type

`Account Type` answers:

- where does this belong structurally in the chart?

Examples:

- Party
- Bank and Cash
- Current Liabilities
- Current Assets
- Direct Expenses
- Indirect Expenses

It should drive:

- allowed head options
- structural reporting classification
- code-series fallback when no head-specific rule is found

### 5.3 Debit Head and Credit Head

These answer:

- which posting buckets does this master actually map to?

They are the closest operational accounting mapping and should be the strongest input for series allocation.

---

## 6. Recommended Default Mapping

These are default suggestions, not immutable rules.

| Party Type | Suggested Account Type | Suggested Debit Head | Suggested Credit Head | Managed As |
| --- | --- | --- | --- | --- |
| Customer | Party | Sundry Debtors `8000` | Sundry Creditors `7000` | party_managed |
| Vendor | Party | Advance Recoverable `6100` preferred, fallback Sundry Debtors `8000` | Sundry Creditors `7000` | party_managed |
| Both | Party | Sundry Debtors `8000` | Sundry Creditors `7000` | party_managed |
| Bank | Bank and Cash | Bank `2000` | Bank `2000` | party_managed or ledger_only based on config |
| Employee | Party | Advance Recoverable `6100` preferred, fallback Sundry Debtors `8000` | Sundry Creditors `7000` | party_managed |
| Government | Current Liabilities | Duties & Taxes `5300` | Duties & Taxes `5300` | party_managed |
| Other | no forced default | no forced default | no forced default | depends on account type / head rule |

Notes:

- `Vendor` and `Employee` use a preferred debit head with fallback because older entities may still classify party settlement heads differently.
- Defaults should be configurable per entity template, not hardcoded.

---

## 7. Code Generation Policy

## 7.1 Problem with current policy

Current generic allocation:

- finds max ledger code
- adds 1

This is not sufficient because it:

- mixes unrelated families
- breaks chart readability
- weakens reporting predictability
- makes seeded control ranges harder to reason about

## 7.2 Target policy

Code allocation must be **series-based**.

Each created ledger/account should be assigned from a configured series based on its classification.

### 7.3 Allocation priority

The system should determine the code series using this order:

1. configured rule for `debit head`
2. fallback rule for `account type`
3. fallback rule for `party type`
4. default entity series

### 7.4 Why debit head first

`Debit Head` is the most reliable operational accounting signal.

It is stronger than:

- party label
- free-text name
- optional hints

### 7.5 Reserved anchor codes

Seeded control codes must remain fixed.

Examples:

- `2000` Bank control / base bank head
- `7000` Sundry Creditors control
- `8000` Sundry Debtors control

User-created masters should start after these anchor codes.

Examples:

- vendor party accounts: `7001+`
- customer party accounts: `8001+`
- bank accounts: `2001+`

---

## 8. Config-Driven Design

Implementation must not rely on scattered hardcoded `if partytype == ...` logic.

Instead, use configuration tables.

---

## 9. Config Tables

## 9.1 `financial_master_rule`

Purpose:

- define whether a master behaves as party-managed or ledger-only
- define defaults and fallbacks

### Suggested columns

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | PK | row id |
| `entity_id` | FK nullable | entity-specific override |
| `template_code` | text nullable | seeded template scope |
| `party_type` | text nullable | Customer, Vendor, etc. |
| `account_type_id` | FK nullable | structural classifier |
| `debit_head_id` | FK nullable | strongest accounting signal |
| `credit_head_id` | FK nullable | optional matching signal |
| `management_mode` | text | `party_managed` or `ledger_only` |
| `suggested_account_type_id` | FK nullable | UI default |
| `suggested_debit_head_id` | FK nullable | UI default |
| `suggested_credit_head_id` | FK nullable | UI default |
| `auto_create_account` | boolean | create linked account on ledger save |
| `allow_direct_ledger_edit` | boolean | whether ledger can remain directly editable |
| `priority` | integer | lower number = stronger match |
| `is_active` | boolean | enable/disable rule |

### Matching behavior

Rules are evaluated in priority order.

The first matching rule wins.

---

## 9.2 `financial_code_series`

Purpose:

- define code ranges and allocation policies

### Suggested columns

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | PK | row id |
| `entity_id` | FK nullable | entity-specific override |
| `template_code` | text nullable | seeded template scope |
| `series_key` | text | logical series id |
| `label` | text | human-readable name |
| `account_type_id` | FK nullable | structural match |
| `debit_head_id` | FK nullable | strongest series match |
| `credit_head_id` | FK nullable | optional refinement |
| `party_type` | text nullable | fallback match |
| `range_start` | integer | first usable code |
| `range_end` | integer | last usable code |
| `next_code` | integer | next proposed code |
| `increment_step` | integer | normally `1` |
| `is_reserved_anchor` | boolean | identifies non-user anchor row |
| `is_active` | boolean | enable/disable rule |
| `priority` | integer | lower number = stronger match |

### Allocation behavior

1. find best matching series
2. lock row / transact safely
3. allocate `next_code`
4. increment stored `next_code`
5. enforce `range_end`

### Important rule

Series state must be stored in config, not recalculated from max ledger code every time.

This avoids race conditions and keeps sequences predictable.

---

## 9.3 Optional `financial_code_series_audit`

Purpose:

- audit code allocations

### Suggested columns

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | PK | row id |
| `entity_id` | FK | entity |
| `series_id` | FK | source series |
| `allocated_code` | integer | generated code |
| `ledger_id` | FK nullable | linked ledger |
| `account_id` | FK nullable | linked account |
| `allocated_by_id` | FK nullable | actor |
| `allocated_at` | datetime | timestamp |
| `allocation_reason` | text | create, repair, migration, import |

This table is optional but strongly recommended.

---

## 10. Suggested Default Series Table

These are blueprint defaults for seeded templates.

| Series Key | Use Case | Match Basis | Range |
| --- | --- | --- | --- |
| `BANK_PARTY` | business bank accounts | debit head `2000` / account type `Bank and Cash` | `2001-2999` |
| `VENDOR_PARTY` | vendor / creditor accounts | credit head `7000` | `7001-7999` |
| `CUSTOMER_PARTY` | customer / debtor accounts | debit head `8000` | `8001-8999` |
| `PARTY_SETTLEMENT` | employee / recoverable / advances | debit head `6100` or `6000` | `6101-6999` |
| `GOVERNMENT_PARTY` | government counterparties | debit/credit head `5300` | `5301-5399` |
| `EXPENSE_DIRECT` | direct expense ledgers | account type `Direct Expenses` | `5101-5199` |
| `EXPENSE_INDIRECT` | indirect expense ledgers | account type `Indirect Expenses` | `5201-5999` |
| `INCOME_DIRECT` | direct income ledgers | account type `Direct Income` | `4101-4199` |
| `INCOME_INDIRECT` | indirect income ledgers | account type `Indirect Income` | `4201-4299` |
| `CURRENT_ASSET_MISC` | non-party current assets | account type `Current Assets` | `1101-1999` |
| `CURRENT_LIABILITY_MISC` | non-party current liabilities | account type `Current Liabilities` | `2101-2999` excluding reserved ranges |

This table should be seeded, then overridden per entity if needed.

---

## 11. Screen Behavior Rules

## 11.1 Add Ledger screen

### On load

- show ledger form
- allow blank code
- classify candidate row using config rules

### On save

1. resolve management rule
2. allocate code from series if blank
3. create ledger
4. if result is `party_managed`, auto-create linked account
5. reload ledger row as `Auto-managed`

### UI result

- party-managed save: success message should explain that linked account was created
- future edits should open account page

Suggested message:

`Ledger saved and linked account created. Future edits should be managed from Accounts.`

---

## 11.2 Account page

### On save

1. resolve defaults from config
2. filter allowed heads by account type
3. allocate code from series if missing
4. create/update linked ledger
5. result always behaves as `Auto-managed`

---

## 11.3 Quick account popup

Must use the same config service as Account page for:

- party/account/head defaults
- code series allocation
- linked ledger creation

No screen-specific duplication.

---

## 11.4 Ledger list

### Row mode

- `Auto-managed` when a linked account exists
- `Auto-managed` when governance marks the row as not directly editable, even if the linked account still needs repair
- `Direct` only when governance permits direct ledger behavior

### Row actions

- `Auto-managed` -> `Open Account`
- `Direct` -> edit/delete buttons

### Code column

- should never remain blank after a successful create unless config explicitly allows code-less ledgers

Recommended policy:

- disallow code-less ledgers entirely after this redesign

---

## 12. Migration and Backfill Plan

Existing data may contain:

- party-like direct ledgers
- blank ledger codes
- heads assigned under older account-type mapping

So rollout must include repair utilities.

### 12.1 Backfill steps

1. seed config tables
2. seed default series ranges
3. classify existing ledgers using config rules
4. assign code to blank ledgers from matching series
5. create missing linked accounts for party-managed ledgers
6. convert those rows to `Auto-managed`
7. log each repaired record

### 12.2 Conflict rules

If a row looks party-like but already has contradictory data:

- do not silently destroy data
- flag in audit / repair report
- optionally skip and require manual review

---

## 13. Implemented Service Layer

Implementation is now service-driven, though some orchestration still spans serializers/views/services.

### 13.1 Rule resolution

Implemented through:

- `financial/governance.py`
- `financial/party_accounting_defaults.py`

Responsibilities now covered:

- resolve `party_managed` vs `ledger_only`
- resolve suggested account type / debit head / credit head
- resolve whether a ledger should remain directly editable

### 13.2 Code series allocation

Implemented through:

- `financial/governance.py`
- `financial/services.py`

Responsibilities now covered:

- resolve matching code series
- allocate next code transactionally
- audit allocation
- fallback safely when no configured series exists

### 13.3 Master creation orchestration

Implemented through coordinated backend save paths:

- `financial/services.py`
- `financial/views_ledger.py`
- `financial/serializers_ledger.py`

Responsibilities now covered:

- create/update ledger
- auto-create linked account for party-managed rows
- synchronize account-ledger behavior
- return final governance state to the UI

---

## 14. API Guidance

Frontend should not hardcode:

- party type to head mapping
- account type to series mapping
- direct vs auto-managed inference

This is now implemented through backend metadata on:

- `meta/account-form/`
- `meta/ledger-form/`

These payloads now expose config-backed governance metadata such as:

- suggested account type
- suggested debit head
- suggested credit head
- party-managed account type/head sets
- direct-edit-blocked account type/head sets

Backend remains the final authority on save.

---

## 15. Non-Goals

This blueprint does not require:

- immediate full ledger-first posting migration
- removal of current `account -> ledger` compatibility logic
- redesign of all financial masters at once

It only standardizes:

- master creation
- governance
- code allocation
- party linkage behavior

---

## 16. Implementation Progress

Completed:

1. config tables
2. config seed data for default rules and series
3. backend rule-resolution service
4. backend code-series allocation service
5. account create/update governance integration
6. ledger create/update governance integration
7. quick popup governance integration
8. repair/backfill command
9. audit tracking for allocated series codes

Completed verification:

- Django tests green
- Angular compile green

Minor follow-up items can now be treated as incremental product refinement rather than core-governance work.

---

## 17. Final Decision Summary

### Governance model

- party-like master -> `Account + Ledger`
- non-party master -> `Ledger only`

### Ledger page strategy

- use Option C
- allow create from ledger page
- auto-convert party-like rows to linked account flow

### Code strategy

- do not use global `max + 1`
- allocate from config-driven series
- use debit head first, account type second, party type third

### Configuration strategy

- no scattered hardcoding
- maintain behavior through config tables + seeded defaults

---

## 18. Current Default Decisions

The current seeded defaults are:

1. `Bank` defaults to `party_managed` with bank-series allocation, but can still be overridden by config.
2. `Government` defaults to `party_managed` with `5300`-family mapping, but can be split later by additional series rules if required.
3. `Employee` defaults to `party_managed` with `6100`-family preference and configured fallback behavior.
4. Direct ledger create follows Option C:
   - save is allowed
   - governance resolves final mode
   - party-managed rows auto-convert into linked account flow

If product wants different behavior later, the config tables are now in place to support it without redesigning the architecture.
