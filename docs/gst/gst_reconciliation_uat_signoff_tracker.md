# GST Reconciliation UAT Signoff Tracker

Date: 2026-05-20

Use this tracker during pilot UAT signoff.

Status values:
- `Pass`
- `Fail`
- `Blocked`
- `Not Run`

## Summary

| Area | Owner | Status | Notes |
|---|---|---|---|
| Access / Menu |  | Not Run |  |
| Import / Matching |  | Not Run |  |
| Review Workflow |  | Not Run |  |
| Bulk Actions |  | Not Run |  |
| Permissions / Scope Safety |  | Not Run |  |
| Performance / Large Run |  | Not Run |  |
| Regression On Old GST Flows |  | Not Run |  |

## Scenario Tracker

| Test Scenario | Expected Result | Actual Result | Tester | Status | Remarks |
|---|---|---|---|---|---|
| Menu visible only for authorized pilot user | GST Reconciliation menu appears only with `gst.reconciliation.view` |  |  | Not Run |  |
| Direct route denied for unauthorized user | Unauthorized user cannot use `/gst-reconciliation` |  |  | Not Run |  |
| GSTR-2B JSON import | Imported return and run are created successfully |  |  | Not Run |  |
| GSTR-2B Excel import | Imported return and run are created successfully |  |  | Not Run |  |
| Auto match execution | Run moves through match flow and items populate |  |  | Not Run |  |
| Manual match | Reviewer can link valid source document |  |  | Not Run |  |
| Manual unmatch | Manual match can be removed and item reopens |  |  | Not Run |  |
| Ignore item | Reviewer can ignore with mandatory note |  |  | Not Run |  |
| Accept mismatch | Reviewer can accept mismatch with note |  |  | Not Run |  |
| Reviewer assignment | Reviewer can be assigned correctly |  |  | Not Run |  |
| Source document search | Search returns valid scoped source documents |  |  | Not Run |  |
| Bulk assign | Selected items assign successfully |  |  | Not Run |  |
| Bulk ignore | Selected items ignore successfully |  |  | Not Run |  |
| Bulk reopen | Selected items reopen successfully |  |  | Not Run |  |
| Bulk accept mismatch | Selected items accept mismatch successfully |  |  | Not Run |  |
| Bulk unmatch | Selected items unmatch successfully |  |  | Not Run |  |
| Bulk mark reviewed | Selected items move to reviewed/resolved state correctly |  |  | Not Run |  |
| Dashboard counts | Summary values match run state |  |  | Not Run |  |
| Supplier analytics | Supplier-level mismatch stats are correct |  |  | Not Run |  |
| Reviewer queue | Queue reflects unresolved / assigned state correctly |  |  | Not Run |  |
| Closed run immutability | Closed run does not allow mutation actions |  |  | Not Run |  |
| Cross-entity denial | User cannot access another entity’s run/items |  |  | Not Run |  |
| Old purchase statutory flow | Existing purchase statutory screens still work |  |  | Not Run |  |
| Old GST reports | Existing GST reports still work |  |  | Not Run |  |
| Large-run performance | Large run pages and summaries remain usable |  |  | Not Run |  |

## Final Signoff

| Role | Name | Date | Signoff |
|---|---|---|---|
| Business Tester |  |  |  |
| Finance Reviewer |  |  |  |
| QA / Implementation |  |  |  |
| Product / Module Owner |  |  |  |
