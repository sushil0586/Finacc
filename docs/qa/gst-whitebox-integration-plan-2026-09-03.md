# GST Whitebox Integration Plan

Date: 2026-09-03

## Objective

Use the Whitebox GST APIs for portal filing while keeping Finacc as the source of truth for invoice data, return calculations, validations, user permissions, and audit trails.

## Current Code Position

- GSTR-1 is report/export ready. The current `gstn_json` export is a Finacc filing-prep payload, not a direct Whitebox save payload.
- GSTR-3B is summary/export ready. It maps naturally to Whitebox `sup_details`, `inter_sup`, `itc_elg`, and `inward_sup`; POS-wise section 3.2 breakup is now included in the Whitebox preview path.
- GSTR-9 already has a simulated/manual filing gateway pattern, but Whitebox needs a richer multi-step lifecycle: OTP, save, summary, offset/proceed, EVC, file, and status polling.
- GST filing scope must be GSTIN-level. If multiple branches share one GSTIN, portal filing should aggregate all those branches instead of filing only the selected branch.

## Whitebox Launch Scope

Phase 1 returns:

- GSTR-1 save, optional summary, proceed-to-file, EVC file, status.
- GSTR-3B save, summary, offset, file, EVC file, status.
- GSTR-2B generate/fetch for purchase ITC verification.

Deferred returns:

- GSTR-7/TDS.
- GSTR-9/9C direct Whitebox filing.
- GSTR-1A and advanced amendment/e-commerce flows unless required for launch tenant.

## Backend Design

New code area:

- `reports.gst_portal.whitebox.WhiteboxGstClient`
- `reports.gst_portal.payloads.Gstr1WhiteboxPayloadBuilder`
- `reports.gst_portal.payloads.Gstr3bWhiteboxPayloadBuilder`
- `reports.gst_portal.scope.resolve_gst_portal_registration_scope`
- `reports.gst_portal.services.GstPortalService`
- `reports.gst_portal.views` internal API endpoints
- `reports.models.GstPortalProfile` stores GST portal filing identity per provider + entity + GSTIN

Required next backend work:

- Add persistent filing/session models for GST portal runs, separate from the simpler annual-report `ReportFilingRun`. Completed for first slice.
- Add API endpoints under our backend, not direct browser calls to Whitebox. Completed for prepare/status/request OTP/verify OTP/save.
- Add GSTIN profile API so the browser can auto-populate GST portal username and avoid repeated operator entry. Completed.
- Add GSTR-1/GSTR-3B "prepare portal payload" endpoints. Completed.
- Add "save to GSTN", "fetch portal summary", "proceed-to-file", "request EVC", "file with EVC", and "poll status" endpoints. Completed for GSTR-1/GSTR-3B lifecycle surface where provider-supported; live execution remains blocked until Whitebox credentials are configured.
- Add backend permission checks for file actions, ideally separate from report-view permissions.
- Enforce explicit live-write feature flags before Save/File calls. Completed for GSTR-1 and GSTR-3B.

## Backend Credential Contract

WhiteBooks credentials are backend-only. The browser must never receive or submit WhiteBooks app credentials.

Primary deployment settings:

- `WHITEBOOKS_BASE_URL`
- `WHITEBOOKS_API_KEY`
- `WHITEBOOKS_API_SECRET`
- `WHITEBOOKS_CONTACT_EMAIL`
- `WHITEBOOKS_GST_USERNAME` as an optional global fallback
- `WHITEBOOKS_STATE_CODE` as an optional fallback; branch registration state remains preferred
- `WHITEBOOKS_IP_ADDRESS` as an optional server-public-IP default
- `WHITEBOOKS_TIMEOUT_SECONDS`
- `WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE`
- `WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE`
- `WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE`
- `WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE`
- `WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE`

`save` and `file` actions are blocked unless their exact live flag is enabled after approval. Preview/status and local payload preparation remain available without live-write flags.

Compatibility aliases exist for the earlier Finacc adapter naming:

- `WHITEBOX_GST_BASE_URL`
- `WHITEBOX_GST_CLIENT_ID`
- `WHITEBOX_GST_CLIENT_SECRET`
- `WHITEBOX_GST_CONTACT_EMAIL`
- `WHITEBOX_GST_USERNAME`
- `WHITEBOX_GST_STATE_CODE`
- `WHITEBOX_GST_IP_ADDRESS`
- `WHITEBOX_GST_TIMEOUT_SECONDS`

## Filing Scope Rule

Final GST filing is always per:

- GSTIN
- return period
- return type

Subentity/branch selection can be used for review and filtering, but if the selected branch shares its GSTIN with other branches, portal filing must aggregate all same-GSTIN branches.

Launch rule:

- Single branch GSTIN: selected branch can map one-to-one to portal payload.
- Shared GSTIN across branches: backend resolves filing subentity scope to all same-GSTIN branches and returns a warning.
- Missing branch GSTIN: backend falls back to active entity GST registration.
- Missing GST registration: block portal filing.

## Frontend Status

Added a "GST Portal Filing" workspace on GSTR-1 and GSTR-3B pages:

- Period and scope-aware status strip.
- High-level actions: Prepare Payload, Review Warnings, File Return, Check Status.
- File Return opens a guided modal instead of exposing raw API fields on the report page.
- GST username is auto-populated from `GstPortalProfile`; backend `WHITEBOOKS_GST_USERNAME` remains a fallback only.
- Optional registered phone/email fields are captured for operator confirmation on the GSTIN profile.
- WhiteBooks contact email is resolved by the backend from `WHITEBOOKS_CONTACT_EMAIL`.
- GSTR-1 modal steps: prepare payload, request/verify GST auth OTP, save to GSTN, optionally check portal summary, proceed to file, request EVC, file with EVC, poll final status.
- Filing is visually blocked while report readiness has unresolved warnings/blockers.
- Unexpected HTML/500 responses are sanitized into a readable message instead of showing raw markup.

Remaining frontend polish:

- Show a compact latest filing-run history/status list.
- Add dedicated preview JSON/download affordance separate from legacy `gstn_json`.
- Add GSTR-3B offset UI once the backend offset endpoint is enabled for the launch path.

Keep offline export separate:

- Rename current GSTR-1 `gstn_json` export to avoid implying it is directly portal-submittable.
- Add a new portal-preview JSON once payload builders are wired into the report APIs.

## Security And Audit Requirements

- Whitebox `client_id` and `client_secret` must stay server-side in environment/settings.
- Never log OTP, EVC OTP, client secret, auth token, SEK, or encrypted payloads.
- Every portal call should record redacted request/response metadata.
- Use generated `txn` IDs for traceability and idempotency.
- Add explicit timeouts and safe error handling for all Whitebox calls.

## Known Gaps Before Live Filing

- Whitebox sandbox credentials are verified through the backend adapter. OTP request/auth and GSTR-1 draft save succeeded against the sandbox test GSTIN on 2026-09-04.
- Whitebox `email` is treated as backend-configured WhiteBooks contact email. Sandbox testing showed the GSP contact email must match the WhiteBooks-enabled account; otherwise WhiteBooks returns an invalid credential/account response even when the GST username and GSTIN are correct.
- Need final production confirmation for `ip_address`: default to backend/server public IP unless WhiteBooks requires a different value.
- GSTR-3B section 3.2 POS-wise breakup is now available for Whitebox preview payloads.
- GSTR-1 advanced tables 11, 14, 14A, 15, 15A need final Whitebox schema mapping before being enabled for portal save.
- GSTR-1 direct `retfile` uses a different payload shape from `retsave`: `gstin`, `ret_period`, `chksum`, `newSumFlag`, and `sec_sum`. Finacc now has a deterministic backend helper to derive this structure from the saved draft payload, including legitimate negative credit-note/amendment totals.
- WhiteBooks DOCX/Postman review confirms `retevcfile` is query-param based with no request body, while direct DSC-style `retfile` requires the checksum/section-summary body. The current launch UI should keep EVC filing as the simple path and keep direct `retfile` as a backend-ready extension.
- WhiteBooks documentation names both legacy and newer lifecycle endpoints. The adapter now uses `newproceedfile/newretstatus` first, with conservative fallback to `proceedfile/retstatus` only when the primary endpoint itself is unavailable.
- Filing run persistence is implemented for prepare/save/summary/proceed/EVC/file/status lifecycle.
- Initial GSTR-1/GSTR-3B frontend portal panel is implemented; live filing still depends on stage Whitebox credentials and sandbox confirmation.
- Sandbox GSTR-1 proceed-to-file for August 2026 was blocked by GSTN rule `RET192409` because the prior July 2026 GSTR-3B was not filed. This is expected statutory behavior; the UI/backend should show the provider blocker and keep the run in failed/blocker state rather than advancing to EVC.
- Sandbox GSTR-3B save for August 2026 was blocked because GSTR-1 for the same tax period had not been filed first. This confirms launch workflow ordering must be GSTR-1 completion before GSTR-3B finalization.
- WhiteBooks sandbox default OTP `575757` works for auth-token verification. EVC OTP should also be operator-entered in the UI, but sandbox EVC filing cannot be completed until the selected GSTIN/period passes proceed-to-file prerequisites.
- For return period `082026`, sandbox logout cleanup, auth OTP request, auth verification, and GSTR-1 nil save succeeded. GSTR-1 proceed-to-file was correctly blocked by GSTN `RET192409` because July 2026 GSTR-3B is not filed. GSTR-1 portal summary returned `AUTH143`; keep portal summary optional/non-blocking until WhiteBooks confirms the accepted summary parameters for sandbox.

## Test Evidence Added

Focused backend tests added in `reports.tests_gst_portal`:

- Return-period conversion to GST `MMYYYY` format.
- GSTR-1 core table conversion to Whitebox-style payload.
- GSTR-3B summary conversion to Whitebox-style payload.
- Warning when GSTR-3B POS-wise breakup is missing in low-level builder input.
- Real GSTR-3B preview includes POS-wise interstate breakup from posted sales invoices.
- Shared-GSTIN branch scope resolution.
- Entity GST fallback when branch GST is missing.
- Whitebox client required headers and redacted sensitive data.
- Backend `WHITEBOOKS_*` credential contract with legacy `WHITEBOX_GST_*` aliases.
- Clean provider error handling for non-JSON/HTML provider responses and `status_cd=0` payloads.
- Missing Whitebox credentials block outbound calls.
- Internal prepare/status/request OTP/save endpoints.
- GST portal profile save/fetch endpoint and profile-driven username auto-resolution.
- Internal portal summary/proceed/request EVC/file with EVC/poll status endpoints.
- Mocked Whitebox happy-path lifecycle through internal APIs.
- WhiteBooks adapter falls back from `newproceedfile` to `proceedfile`, and from `newretstatus` to `retstatus`, only for endpoint-unavailable responses.
- Direct sandbox adapter evidence: logout cleanup, OTP request, OTP verification, and GSTR-1 nil draft save succeeded; GSTR-1 proceed and GSTR-3B save correctly returned statutory/provider blockers.
- EVC filing contract coverage confirms `575757` or any entered EVC OTP is sent as WhiteBooks `evcotp` query param with no JSON body for `gstr1/retevcfile`.
- Sandbox `082026` evidence confirms auth and save are operational; final EVC filing remains blocked by GSTN prior-period compliance, not by Finacc request construction.
- GSTR-1 `retfile` payload helper derives deterministic `sec_sum` totals/checksums and preserves valid negative credit-note totals.

Focused frontend tests/checks added:

- Report service contract coverage for GST portal profile, prepare, status, OTP, save, summary, proceed, EVC, file, and poll APIs.
- EVC file calls send `evc_otp` to match the backend contract.
- Notification service sanitizes unexpected HTML server-error responses.
- Targeted GSTR-1/GSTR-3B component specs pass with the guided filing modal.
- Angular strict typecheck and development build pass with the portal panel enabled.
