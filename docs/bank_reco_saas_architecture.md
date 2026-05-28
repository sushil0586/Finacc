# Bank Reconciliation SaaS Architecture

## Goal

Build a clean bank reconciliation module for Finacc that treats:

- statement imports
- reconciliation runs
- reviewable match suggestions
- confirmed matches
- voucher creation from unmatched bank lines
- audit trail

as separate concerns.

The design should be:

- entity-aware
- financial-year-aware
- subentity-aware
- bank-account-aware
- safe for multi-tenant SaaS usage
- independent from existing voucher posting logic

## Why we are rebuilding

The existing `bank_reconciliation` module mixes:

- import lifecycle
- workspace lifecycle
- statement line persistence
- matching workflow
- review workflow

inside one session-based model.

That makes it hard to support:

- duplicate import control
- overlapping statement validation
- many-to-one and partial matches
- separate validation vs reconciliation workflow
- voucher creation from unmatched lines
- bank-side and books-side reporting

## New domain model

### 1. `BankStatementImport`

Represents one imported bank statement file or normalized upload.

Responsibilities:

- file identity
- statement period
- opening/closing balance inputs
- parser format
- duplicate import protection
- validation status and summary

Key lifecycle:

- `uploaded`
- `validated`
- `ready`
- `rejected`
- `archived`

### 2. `BankStatementLine`

Represents one normalized bank statement row.

Responsibilities:

- normalized bank transaction data
- raw source payload retention
- per-line validation state
- per-line reconciliation state

Normalized line shape:

- `txn_date`
- `value_date`
- `narration`
- `reference_no`
- `cheque_no`
- `debit_amount`
- `credit_amount`
- `balance`
- `raw_data`
- `normalized_hash`

### 3. `BankReconciliationRun`

Represents one reconciliation workspace for one bank account and one import scope.

Responsibilities:

- scope and balances
- run status
- aggregate metrics
- reviewer progress
- lock/close control

Key lifecycle:

- `draft`
- `validated`
- `matching`
- `review`
- `reconciled`
- `locked`

### 4. `BankReconciliationMatch`

Represents one reviewable or confirmed reconciliation decision.

Design principle:

- match header stores decision and audit context
- allocations store actual bank-side and book-side rows

This supports:

- one-to-one
- one-to-many
- many-to-one
- many-to-many
- partial matching

Key lifecycle:

- `suggested`
- `confirmed`
- `rejected`
- `unmatched`
- `reversed`

### 5. `BankReconciliationMatchBankLine`

Stores the bank-side allocation rows belonging to a match.

### 6. `BankReconciliationMatchBookLine`

Stores the books-side allocation rows belonging to a match.

Books-side source remains:

- `posting.JournalLine`
- optional linked `posting.Entry`

No duplicate posting logic lives in reconciliation.

### 7. `BankReconciliationAuditLog`

Stores a full action log for:

- import
- validation
- auto-match suggestion
- manual match
- group match
- unmatch
- voucher creation
- lock/reopen

## Validation architecture

Validation is a separate step from import parsing.

### Import parsing

Converts source file or uploaded rows into normalized lines.

Supported now:

- `csv`
- `xlsx`

Pluggable later:

- `pdf`
- `mt940`
- `camt053`

### Import validation

Validation must produce:

- import-level errors
- import-level warnings
- line-level errors
- line-level warnings

Validation rules:

- duplicate file detection by file hash
- duplicate line detection by normalized hash
- invalid debit/credit rows
- zero-value lines
- opening/closing balance mismatch
- period overlap with prior imports
- bank account mismatch when account clues exist
- impossible date ranges

## Matching architecture

### Suggested matching

Auto-match engine must create suggestions first, not accounting entries.

Suggested matching strategies:

1. exact amount + date + reference
2. amount + reference + date tolerance
3. amount + narration similarity + date tolerance
4. rule-assisted settlement patterns

Every suggestion carries:

- confidence score
- reason codes
- explanation payload

### Confirmed matching

Manual reviewer actions confirm a suggestion or create a fresh manual/group match.

Supported reviewer actions:

- confirm suggestion
- manual one-to-one
- manual one-to-many
- manual many-to-one
- partial match
- unmatch
- reject suggestion

## Voucher creation architecture

Voucher creation must be separate from reconciliation matching.

Reconciliation may create a voucher only for unmatched bank lines that represent real direct bank activity, such as:

- bank charges
- interest received
- direct customer receipt
- direct vendor payment
- bank transfer

Rule:

- create voucher through existing voucher/posting services
- never post accounting directly from bank reconciliation models

The reconciliation module only:

- captures intent
- invokes existing voucher service
- stores created voucher references
- audits the event

## API design

Target API family:

- `POST /api/bank-reco/import/`
- `GET /api/bank-reco/imports/`
- `GET /api/bank-reco/imports/{id}/lines/`
- `POST /api/bank-reco/imports/{id}/validate/`
- `POST /api/bank-reco/imports/{id}/auto-match/`
- `GET /api/bank-reco/workspace/`
- `POST /api/bank-reco/match/`
- `POST /api/bank-reco/unmatch/`
- `POST /api/bank-reco/group-match/`
- `POST /api/bank-reco/create-voucher-from-bank-line/`
- `GET /api/bank-reco/reports/statement/`
- `GET /api/bank-reco/reports/unmatched-bank/`
- `GET /api/bank-reco/reports/unmatched-books/`
- `GET /api/bank-reco/reports/audit-trail/`

## SaaS design principles

### Tenant safety

All objects must carry:

- `entity`
- `entityfin`
- `subentity`
- `bank_account`

### Idempotency

- import dedupe by file hash
- line dedupe by normalized hash
- voucher creation guarded against duplicate voucher creation from the same bank line event

### Auditability

Every mutation must be logged with:

- actor
- action
- object type
- object id
- before/after payload where relevant

### Extensibility

Parser architecture must be pluggable by format key.

Matching architecture must be pluggable by strategy key.

Voucher creation must be pluggable by event type.

## Build phases

### Phase 1

- new app scaffold
- core models
- migration
- basic serializers

### Phase 2

- import parsing
- import validation
- import APIs

### Phase 3

- auto-match engine
- manual match
- group match
- unmatch
- audit trail

### Phase 4

- voucher creation from bank lines
- reports APIs

### Phase 5

- frontend workspace
- review UX
- exports

## Current implementation strategy

We will:

- freeze the old `bank_reconciliation` app as legacy
- build the new module in a new app: `bank_reco`
- switch routes and UI to the new module after backend completeness is sufficient

