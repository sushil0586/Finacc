# Purchase URD GST Test Matrix

Scope: purchases from unregistered vendors where `vendor_gstin` is blank and supplier-side GST must not be charged unless reverse charge is explicitly applicable.

## Automated coverage

- Backend purchase rules
  - Blank `vendor_gstin` disables normal ITC on non-RCM URD purchases.
  - Blank `vendor_gstin` suppresses line GST on non-RCM URD purchases.
  - Claimed ITC is rejected for non-RCM URD purchases.
- Backend reporting and reconciliation
  - GSTR-3B ITC-available section excludes non-RCM URD purchases even if bad legacy data marks them ITC eligible.
  - Purchase register preserves blank supplier GSTIN instead of backfilling from the vendor master profile.
  - GSTR-2B source-document provider excludes URD purchase invoices from reconciliation candidates.
- Frontend
  - Purchase payload normalizes blank GSTIN to `null`.
  - State selection falls back to supplier state when the entity GSTIN is blank or unavailable.

## Manual QA scenarios

1. UI validations
   - Create a purchase invoice with a vendor that has no GSTIN.
   - Confirm the GSTIN field stays blank after save, reload, edit, confirm, and post.
   - Verify GST tax rows do not populate for non-RCM URD invoices.
   - Verify ITC controls default to blocked or disabled for non-RCM URD.
   - Verify RCM toggle is the only path that allows URD GST workflow.

2. Backend validations
   - Submit API payloads with blank GSTIN plus non-zero CGST/SGST/IGST on non-RCM URD.
   - Submit blank GSTIN plus `is_itc_eligible=true` and `itc_claim_status=CLAIMED`.
   - Submit URD payloads across create, update, confirm, post, cancel, and unpost APIs.

3. Posting entries
   - Post non-RCM URD invoice and verify only base expense or inventory plus vendor payable entries exist.
   - Post URD RCM invoice and verify supplier payable excludes GST while RCM liability and any allowed input tax entries are correct.
   - Verify cancelled or reversed URD documents unwind the exact journal impact.

4. GST ledger impact
   - Non-RCM URD should not hit input GST ledgers.
   - URD with RCM should hit only RCM liability ledgers and any intended ITC treatment after payment.

5. ITC eligibility
   - Verify non-RCM URD is not claimable in header actions, statutory ITC views, and downstream controls.
   - Verify URD RCM behavior only becomes claimable in the intended workflow after the tax-payment prerequisite.

6. GSTR-3B values
   - Non-RCM URD should not inflate section 4 ITC available.
   - URD RCM should appear only in inward reverse charge buckets when applicable.
   - Check that blank-GSTIN URD does not leak into normal supplier-credit calculations.

7. Purchase register output
   - Supplier GSTIN remains blank.
   - Reverse-charge, ITC status, and grand total columns remain accurate after confirm, post, cancel, and note flows.

8. Audit and exception reports
   - URD invoices should appear in purchase register and audit history.
   - URD invoices should be absent from GSTR-2B reconciliation source candidates.
   - GST exception dashboards should not treat URD as missing-2B supplier documents unless the product team explicitly wants that.

9. Edit, cancel, reversal flows
   - Edit a draft URD invoice from blank GSTIN to a valid GSTIN and back.
   - Cancel posted URD invoices and validate journal, register, and statutory effects.
   - Reverse credit or debit notes linked to URD base documents.

10. Edge cases
   - Inclusive-rate lines on URD invoices.
   - Mixed service and goods lines.
   - Charges with GST metadata present on a URD header.
   - Imported legacy URD invoices with stale GST totals or stale ITC flags.

11. Multi-state handling
   - Intra-state URD without RCM.
   - Inter-state URD without RCM.
   - Inter-state URD with RCM.
   - Place-of-supply defaulting when entity GSTIN is unavailable or registration scope changes.

12. Financial year locking
   - Draft edit before lock, then attempt post, cancel, or unpost after books or GST lock.
   - Backdated URD posting into a closed or locked year.

13. Permission and security checks
   - Role without purchase update permission cannot modify URD ITC or RCM flags.
   - Role without statutory or reconciliation permission cannot access URD GST exception or GSTR-2B views.
   - Entity and subentity scoping prevents cross-tenant visibility for URD invoices.
