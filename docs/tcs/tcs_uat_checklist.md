# TCS UAT Checklist

Date: 2026-05-08

## Purpose

This checklist is for validating the TCS module before go-live or business signoff.

It focuses on:
- TCS sections
- TCS config
- TCS party profiles
- TCS statutory workspace
- collection workflow
- deposit workflow
- allocation workflow
- TCS return 27EQ review

## UAT Rules

- Use one entity and one financial year for the main run.
- Use one quarter for final readiness scenarios unless a test case explicitly changes period.
- Record customer, document, collection, deposit, and return references for every test.
- Capture screenshots and exact error text for failed steps.
- If a number looks wrong, verify source transaction data before calling it a TCS defect.

## Scope

Included:
- screen access and route access
- setup screens
- workspace filters and metrics
- collection creation
- deposit creation
- allocation behavior
- quarter review and exports

Excluded:
- original sales/invoice entry UAT
- external bank integration UAT
- customer onboarding UAT
- non-TCS withholding flows

## Signoff Conditions

Mark TCS ready only if all are true:
- authorized users can open all required TCS pages
- unauthorized users are blocked
- section/config/profile setup screens behave correctly
- workspace numbers load for the correct scope
- collection and deposit flows work
- allocation logic behaves correctly
- quarter review screen works for the selected FY and quarter
- exports work in expected formats

## Suggested UAT Order

1. Access and permissions
2. Sections
3. Config
4. Party profiles
5. TCS workspace filters and metrics
6. Collection workflow
7. Deposit and allocation workflow
8. Return 27EQ review
9. Exports and evidence

## Scenario Matrix

| ID | Scenario | Steps | Expected Result | Status |
|---|---|---|---|---|
| TCS-01 | Authorized access | Login with authorized TCS user and open all TCS pages | Pages open successfully | Pending |
| TCS-02 | Unauthorized access | Login with user without TCS permission and try to open pages or APIs | Access is blocked cleanly | Pending |
| TCS-03 | Section list | Open TCS Sections | List loads correctly | Pending |
| TCS-04 | Section create/edit | Add or edit one valid TCS section | Save succeeds and list reflects changes | Pending |
| TCS-05 | Section validation | Try invalid section data | Clear validation message is shown | Pending |
| TCS-06 | Config list | Open TCS Config | Config list and posting map list load correctly | Pending |
| TCS-07 | Config add/edit | Add or edit one valid config | Save succeeds and values persist | Pending |
| TCS-08 | Posting map add/edit | Add or edit one valid posting map | Save succeeds and values persist | Pending |
| TCS-09 | Party profile list | Open TCS Party Profiles | List loads correctly | Pending |
| TCS-10 | Party profile add/edit | Add or edit one profile with PAN and residency | Save succeeds and values persist | Pending |
| TCS-11 | Party profile data quality | Save profile with edge-case fields used by business | Values persist and display correctly | Pending |
| TCS-12 | Workspace access | Open TCS Statutory workspace | Workspace loads without API errors | Pending |
| TCS-13 | Workspace scope filters | Change FY, quarter, section, and customer filters | Grid and totals refresh correctly | Pending |
| TCS-14 | Workspace quality flags | Open scope with known missing PAN / section issue | Quality chips and warnings appear correctly | Pending |
| TCS-15 | Collection create | Create one valid collection | Collection is saved and appears in workspace | Pending |
| TCS-16 | Collection validation | Try invalid collection amount/date case | Clear validation error is shown | Pending |
| TCS-17 | Deposit create | Create one valid deposit | Deposit is saved and appears in workspace | Pending |
| TCS-18 | Deposit validation | Try invalid deposit amount or duplicate challan case | Clear validation error is shown | Pending |
| TCS-19 | Deposit allocation | Allocate deposit to valid collection | Allocation succeeds and totals update | Pending |
| TCS-20 | Allocation control | Try invalid allocation case | System blocks with correct message | Pending |
| TCS-21 | Pending collection review | Open scope with incomplete collections | Pending collection metrics show correctly | Pending |
| TCS-22 | Pending deposit review | Open scope with incomplete deposits | Pending deposit metrics show correctly | Pending |
| TCS-23 | Workspace exports | Export Excel/PDF/CSV/ZIP where available | Files download and scope matches selection | Pending |
| TCS-24 | Return 27EQ access | Open TCS Return 27EQ | Screen loads correctly | Pending |
| TCS-25 | Return quarter switch | Change FY and quarter | Readiness cards and return list refresh correctly | Pending |
| TCS-26 | Return readiness warnings | Open quarter with known exceptions | Warnings show clearly | Pending |
| TCS-27 | Return list review | Review draft/validated/filed rows | Status, ack no, filed date, and notes display correctly | Pending |
| TCS-28 | Return exports | Export quarter files in available formats | Files download correctly | Pending |
| TCS-29 | Operational navigation | Use Operations / Quarter Review / Ledger actions | Navigation works as expected | Pending |
| TCS-30 | Source-of-truth boundary | Try to use TCS screen to override source transaction truth | System behavior keeps source truth outside TCS workflow | Pending |

## Validation Notes By Area

### Access

Validate:
- menu visibility
- route visibility
- action-level permission behavior

### Setup Screens

Validate:
- create
- edit
- delete where allowed
- search and filters
- modal behavior

### Workspace

Validate:
- totals
- quality flags
- row-level actions
- filter behavior
- export behavior

### Collection and Deposit

Validate:
- create flow
- validation messages
- allocation logic
- cross-check against visible totals

### Return 27EQ

Validate:
- quarter readiness display
- return row visibility
- export behavior
- review and evidence hints

## Failure Logging Template

Use this for any failed case:

- Scenario ID:
- Scope used:
- Customer / Document / Collection / Deposit / Return reference:
- User role:
- Step failed:
- Expected:
- Actual:
- Error text:
- Screenshot / payload:
- Root-cause guess:
  - access / RBAC
  - section setup
  - config setup
  - party profile
  - source transaction data
  - collection workflow
  - deposit workflow
  - allocation logic
  - return review
  - export / file

## Final Signoff

- TCS Setup Readiness: Pending
- TCS Workspace Readiness: Pending
- Collection Workflow Readiness: Pending
- Deposit Workflow Readiness: Pending
- Return 27EQ Readiness: Pending
- Export Readiness: Pending
- Business Signoff Owner: Pending
- Finance / Compliance Signoff Owner: Pending

