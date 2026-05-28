# Bank Reconciliation Business Workflow

This document explains how the new `bank_reco` module is expected to work in Finacc from a finance-user and product-workflow perspective.

It is intentionally business-first, not code-first.

---

## 1. What problem this module solves

Bank reconciliation ensures that:

- transactions appearing in the bank statement
- and transactions already posted in Finacc books

are compared, matched, reviewed, and closed with a proper audit trail.

The module does **not** replace accounting.

It works **on top of** existing Finacc posting and voucher logic.

---

## 2. Core idea

The new module separates the bank reconciliation lifecycle into clean stages:

1. Import bank statement
2. Validate imported statement
3. Start reconciliation run
4. Auto-suggest possible matches
5. Review and confirm matches
6. Manually match edge cases
7. Create missing vouchers where bank moved but books did not
8. Review unmatched items
9. Lock and close the run

This is the right SaaS shape because:

- import is separate from matching
- matching is separate from accounting
- every action is auditable
- multiple users can review with controlled workflow

---

## 3. Main business objects

### 3.1 Bank Statement Import

Represents one uploaded bank statement file.

Examples:

- `HDFC_Apr_2026.csv`
- `ICICI_May_2026.xlsx`

What it stores:

- entity / FY / subentity / bank account
- statement period
- opening / closing balance
- upload metadata
- validation status

### 3.2 Bank Statement Line

Represents one row from the imported bank statement.

Examples:

- salary payment debit
- NEFT receipt credit
- bank charges debit
- interest credit

### 3.3 Reconciliation Run

Represents one working reconciliation cycle for a selected bank account and statement.

Example:

- `HDFC Main Account - April 2026 reconciliation`

### 3.4 Match

Represents a suggested or confirmed relationship between:

- one or more bank lines
- and one or more Finacc book entries

### 3.5 Audit Log

Tracks:

- who imported
- who validated
- who matched
- who unmatched
- who created vouchers
- who locked the run

---

## 4. Practical workflow

## Stage A. Upload bank statement

### User action

Finance user selects:

- Entity
- Financial year
- Subentity if applicable
- Bank account
- File type
- Statement file

### Example

User uploads:

- `HDFC_April_2026.csv`

for:

- `Arnika G`
- `FY 2026-27`
- `HDFC Current Account`

### System action

System creates:

- one `BankStatementImport`
- many `BankStatementLine` rows

System also stores:

- file hash
- raw row payload
- normalized row fields

### Output

Import status:

- `Uploaded`

---

## Stage B. Validate statement

### User action

User clicks:

- `Validate`

### System checks

The system validates:

- duplicate file import
- duplicate rows in same file
- duplicate rows across old imports
- invalid rows with both debit and credit
- invalid rows with neither debit nor credit
- opening balance mismatch
- closing balance mismatch
- overlapping statement period
- bank account mismatch if account number metadata is available

### Example 1: Invalid debit/credit row

Statement line contains:

- debit `1000`
- credit `1000`

Result:

- row is marked invalid
- import can still be reviewed
- user sees exact reason

### Example 2: Opening balance mismatch

Declared opening balance:

- `1,00,000`

But first line implies opening should be:

- `98,500`

Result:

- import-level validation error

### Output

Import status becomes:

- `Validated`, if usable
- `Rejected`, if materially broken

---

## Stage C. Start reconciliation run

### User action

User starts a reconciliation run on a validated statement import.

### Purpose

This creates a working review session for:

- matching
- exception handling
- voucher creation
- closure

### Example

Run:

- `HDFC April 2026 Run`

### Output

Run status:

- `Draft`

---

## Stage D. Auto-match suggestions

### User action

User runs:

- `Auto Match`

### Book-side source

The system uses existing Finacc book postings only.

It does **not** create new accounting during matching.

### Auto-match logic

The system suggests matches using:

1. exact amount + exact date + reference
2. amount + reference + date tolerance
3. amount + narration similarity + date tolerance

Each suggestion gets:

- confidence score
- rule code
- reason code(s)

### Example 1: Exact customer receipt

Bank line:

- `₹50,000` credit
- date `05-Apr-2026`
- ref `UTR123`

Book line:

- receipt voucher `₹50,000`
- same date
- narration contains `UTR123`

Result:

- high-confidence auto suggestion

### Example 2: Near-date vendor payment

Bank line:

- `₹18,750` debit
- date `07-Apr-2026`

Book payment:

- `₹18,750`
- posted on `06-Apr-2026`

Result:

- suggestion with date-tolerance reasoning

### Important rule

Auto-match does **not** auto-post vouchers.

Suggestions remain reviewable.

---

## Stage E. Review and confirm matches

### User action

Reviewer opens suggested matches and:

- confirms
- edits
- rejects

### Output

Match status becomes:

- `Confirmed`
- or remains `Suggested`
- or becomes `Rejected`

### Audit

Every confirmation is logged.

---

## Stage F. Manual matching

This is where the real operational depth matters.

The module must support:

- one-to-one
- one-to-many
- many-to-one
- partial match
- unmatch/rematch

### Scenario 1: One bank line to multiple book entries

Bank line:

- `₹1,00,000` credit from payment gateway

Books:

- receipt 1: `₹60,000`
- receipt 2: `₹25,000`
- receipt 3: `₹15,000`

Result:

- one bank line matched to three book lines

### Scenario 2: Multiple bank lines to one book entry

Bank:

- `₹30,000` credit
- `₹20,000` credit

Books:

- one customer receipt voucher for `₹50,000`

Result:

- many-to-one match

### Scenario 3: Partial match

Bank line:

- `₹9,800` credit

Book receipt:

- `₹10,000`

Difference:

- `₹200`

Possible meaning:

- bank charges netted off

Result:

- partial match + unmatched difference
- or manual voucher creation for bank charges

---

## Stage G. Create voucher from bank line

This is used when:

- bank statement shows a genuine transaction
- but books do not yet contain it

### Supported use cases

- bank charges
- interest received
- direct receipt
- direct payment
- bank transfer

### Example 1: Bank charges

Bank line:

- debit `₹590`
- narration `bank charges`

No book entry exists.

User action:

- `Create Voucher from Bank Line`
- select `Bank Charges`

System action:

- creates voucher through existing Finacc posting architecture
- does not duplicate business logic

### Example 2: Interest received

Bank line:

- credit `₹1,250`
- narration `interest credit`

User action:

- create voucher as `Interest Received`

### Example 3: Direct customer receipt

Bank line:

- credit `₹25,000`
- no receipt voucher exists in books

User action:

- create direct receipt voucher

### Important rule

Reconciliation can create voucher drafts or invoke existing voucher logic,
but it must not invent a separate posting engine.

---

## Stage H. Unmatch and rematch

### User action

If a match is wrong, reviewer can:

- unmatch
- rematch correctly

### Example

Wrong match:

- UTR accidentally matched to another customer receipt

Reviewer action:

- unmatch
- confirm correct candidate

### Audit

Audit log must capture:

- old match
- who removed it
- why it was removed
- new match if rematched

---

## Stage I. Review unmatched items

At the end of matching, the run should clearly show:

- unmatched bank items
- unmatched book items
- partial differences
- exceptions requiring voucher creation

### Common unmatched bank scenarios

- bank charges
- direct customer receipts
- direct vendor payments
- cheque bounce reversal
- interest credit
- UPI settlement

### Common unmatched book scenarios

- cheque issued not cleared
- cheque deposited not cleared
- receipts/payments posted in books but not yet reflected in bank

---

## Stage J. Lock and close run

### User action

Once reviewed, user locks the run.

### Purpose

This prevents accidental changes after closure.

### Output

Run status:

- `Locked`

### Audit

Lock action is recorded.

---

## 5. Real-world scenarios the module must support

## 5.1 Cheque issued not cleared

Books:

- payment posted

Bank:

- debit not yet present

Expected:

- appears in unmatched books

## 5.2 Cheque deposited not cleared

Books:

- receipt posted

Bank:

- credit not yet present

Expected:

- appears in unmatched books

## 5.3 Bank charges

Bank:

- debit exists

Books:

- no entry

Expected:

- create voucher from bank line

## 5.4 Interest credit

Bank:

- credit exists

Books:

- no entry

Expected:

- create voucher from bank line

## 5.5 Direct customer receipt

Bank:

- customer paid directly

Books:

- receipt not posted

Expected:

- create receipt voucher

## 5.6 Direct vendor payment

Bank:

- debit exists

Books:

- payment not posted

Expected:

- create payment voucher

## 5.7 UPI settlement

Bank:

- multiple UPI credits or net settlement

Books:

- separate receipts may exist

Expected:

- one-to-many or many-to-one matching

## 5.8 NEFT / RTGS / IMPS

Expected:

- amount + reference + date tolerance matching

## 5.9 Payment gateway settlement net of charges

Bank:

- net amount received

Books:

- gross receipts posted

Expected:

- grouped or partial matching
- charges voucher creation where needed

## 5.10 Reversal transaction

Expected:

- reversal line should not be silently netted
- it must be separately matched or handled

## 5.11 Cheque bounce

Expected:

- bounce debit/credit visible as separate bank line
- proper reversal or exception treatment

## 5.12 Opening unreconciled items

Expected:

- old pending items can remain unmatched into a new run
- new run should still display carry-forward exposure

---

## 6. SaaS design principles this module follows

### 6.1 Entity aware

Every import, line, run, and match belongs to:

- entity
- optionally financial year
- optionally subentity
- one bank account

### 6.2 Review first, not auto-post first

The module suggests and supports actions, but does not behave like a blind auto-posting engine.

### 6.3 Separate reconciliation from accounting

Matching is not accounting.

Voucher creation uses existing accounting workflows.

### 6.4 Strong audit trail

Every important action must be logged.

### 6.5 Import lifecycle is independent

Statement import, validation, and reconciliation are separate stages.

This prevents one overloaded object from trying to do everything.

---

## 7. Future API shape

The module is designed toward these APIs:

- `POST /bank-reco/import/`
- `GET /bank-reco/imports/`
- `GET /bank-reco/imports/{id}/lines/`
- `POST /bank-reco/imports/{id}/validate/`
- `POST /bank-reco/imports/{id}/auto-match/`
- `GET /bank-reco/workspace/`
- `POST /bank-reco/match/`
- `POST /bank-reco/unmatch/`
- `POST /bank-reco/group-match/`
- `POST /bank-reco/create-voucher-from-bank-line/`
- `GET /bank-reco/reports/statement/`
- `GET /bank-reco/reports/unmatched-bank/`
- `GET /bank-reco/reports/unmatched-books/`
- `GET /bank-reco/reports/audit-trail/`

---

## 8. What is already built in the new module

Currently implemented in the new backend:

- new SaaS-oriented data model
- import upload
- CSV/XLSX parsing
- normalized statement line creation
- duplicate file detection
- line validation
- balance checks
- overlap checks
- bank account mismatch check from metadata
- import line listing
- workspace summary
- audit logs for import/validation

---

## 9. Next implementation phases

### Phase 2

- auto-match engine
- confidence scoring
- suggestion review API

### Phase 3

- manual/group/partial matching
- unmatch/rematch workflow

### Phase 4

- create-voucher-from-bank-line

### Phase 5

- unmatched bank report
- unmatched books report
- audit trail report
- statement report

### Phase 6

- dedicated frontend reconciliation workspace

---

## 10. One-line business summary

The new bank reconciliation module will let finance teams import a bank statement, validate it, match it safely against Finacc books, create missing vouchers where needed, review all unmatched items, and close the run with a full audit trail.
