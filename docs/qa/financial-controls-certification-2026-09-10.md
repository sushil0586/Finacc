# Financial Controls Certification

Date: 10 September 2026

## Scope

This certificate covers the three Financial Controls workspaces:

- Control Center: `/reports/controls/phase-one`
- Posting Setup: `/reports/controls/posting-setup`
- Year-End Close: `/reports/controls/year-end-close`

The review included API contracts, authorization, entity/FY/subentity scope propagation, business-state presentation, navigation, responsive behavior, keyboard access, automated WCAG A/AA checks, failure recovery, and landing-page performance.

## Certification Result

**Local release recommendation: Ready for staging validation with conditions.**

Confidence is **97% locally** for the reviewed surfaces. The core workflows, scope handling, action authorization, UI behavior, accessibility automation, cross-browser presentation, and disposable-database destructive cycles are covered. Final production sign-off remains conditional on repeating the destructive actions in staging and completing manual assistive-technology review.

## Corrective Work

- Added separate permissions for opening-policy updates, opening generation and rollback, posting-setup application, and year-close execution and rollback.
- Corrected the opening-policy PATCH endpoint and removed the misplaced PATCH implementation from opening preview.
- Enforced action permissions in both backend APIs and frontend controls.
- Replaced expensive live compliance reconstruction on Control Center load with a bounded persisted reconciliation snapshot and direct links to full GST/TDS/TCS reports.
- Improved labels and accessible names for posting ledger inputs, selectors, and enablement controls.
- Made year-close opening asset and liability lists keyboard reachable.
- Corrected low-contrast text in Control Center and Year-End Close.
- Stabilized Posting Setup tables on mobile with deliberate horizontal scrolling and fixed minimum table widths.
- Corrected year-close lock dates to use the financial-year closing date instead of the date on which the operator executes the close.
- Excluded disabled Posting Setup targets from provisioned and touched results while reporting them separately as skipped.
- Fixed posting test data isolation so tests do not depend on pre-existing static-account records.

## Evidence

| Layer | Result | Coverage |
| --- | ---: | --- |
| Django focused suite | 77 passed | Controls services, APIs, permissions, posting, year close, persisted snapshot, destructive cycles |
| Django destructive suite | 3 passed | Real balanced close/opening postings, duplicate rejection, rollback purge and state restoration, disabled setup targets |
| Angular focused suite | 53 passed | All three components, permission states, interaction and rendering contracts |
| Angular production build | Passed | AOT production compilation and asset generation |
| Playwright certification | 45/45 effective pass | Chromium, Firefox, WebKit; desktop, tablet, mobile; workflow, recovery, scope and WCAG |
| Playwright rerun | 2 passed | Firefox setup plus isolated WCAG Control Center retry after one transient `ECONNRESET` |
| Post-fix Playwright regression | 15 passed | Chromium rerun of the complete control certificate after destructive-path corrections |
| Django system checks | Passed | `manage.py check` and migration drift check |
| Diff integrity | Passed | No whitespace errors in backend or frontend changes |

The initial full Playwright invocation reported 44 passed and one Firefox infrastructure failure while fetching workspace entities. The failed accessibility case passed immediately in isolation, with no accessibility assertion failure. This is classified as local transport noise, not a product defect.

## Control Matrix

| Area | Certified checks | Status |
| --- | --- | --- |
| Control Center | Scoped load, actionable cards, cross-workspace navigation, API failure recovery, bounded response time, responsive views, WCAG A/AA | Pass |
| Posting Setup | Scoped preview, editable target review, reset behavior, action RBAC, confirmation guard, mobile table usability, accessible labels, WCAG A/AA | Pass |
| Year-End Close | FY/subentity scope, preview refresh, readiness presentation, action RBAC, confirmation guard, keyboard lists, responsive views, WCAG A/AA | Pass |
| Authorization | View-only access separated from six financial-control mutations; administrator grants migrated | Pass |
| Scope integrity | Entity, financial year, and available subentity parameters verified in browser requests | Pass |
| Close execution | Balanced journal persisted, FY-end locks applied, duplicate rejected, rollback purged entry and restored original state | Pass |
| Opening generation | Balanced carry-forward persisted, duplicate rejected, rollback purged entry, metadata and active FY restored | Pass |
| Posting setup selection | Disabled targets excluded from applied/touched output and reported as skipped | Pass |
| Recovery | One-shot API 500 produces useful feedback and succeeds after reload | Pass |
| Performance | Control Center landing response held below the 10-second certificate threshold in browser testing | Pass |

## Residual Gates

- Repeat close, rollback, opening generation, opening rollback, and auto-provision against a disposable staging entity. Local database certification executes the posting and rollback services; browser certification deliberately verifies confirmation and request guards without changing shared developer books.
- Run VoiceOver or NVDA manual review for announcements, reading order, and confirmation-dialog context. Automated WCAG checks are complete but do not replace this review.
- Verify migration `0144_add_financial_control_action_permissions` is applied before testing administrator actions in staging.
- Validate the persisted GST reconciliation card against a freshly completed staging reconciliation run. The card intentionally shows the latest saved run rather than rebuilding all compliance reports during page load.
- Approve staging screenshots for business-facing visual baselines and test print output where operator print dialogs are involved.

## Staging Sign-Off Script

1. Open all three routes as an administrator and as a view-only user.
2. Confirm the view-only user can inspect previews but cannot invoke any mutation.
3. Use a disposable entity to apply Posting Setup and verify the resulting ledger mappings.
4. Generate and roll back opening entries, checking journal balances and idempotency.
5. Execute and roll back year close, checking status, retained earnings, lock state, and audit history.
6. Complete a GST reconciliation run and verify the Control Center snapshot and deep links.
7. Repeat the critical path in desktop Chrome and one mobile browser before production approval.
