import os
import random
from typing import Any, Dict
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from locust import HttpUser, between, task, tag

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent.parent

# Prefer local perf/locust/.env, then fallback to backend root .env.
load_dotenv(CURRENT_DIR / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=False)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class FinaccDjangoUser(HttpUser):
    wait_time = between(1, 3)

    host = env("LOCUST_HOST", "")
    email = env("FINACC_USER_EMAIL", "")
    password = env("FINACC_USER_PASSWORD", "")

    entity_id = env("FINACC_ENTITY_ID", "1")
    entity_fin_id = env("FINACC_ENTITY_FIN_ID", "1")
    subentity_id = env("FINACC_SUBENTITY_ID", "")

    login_path = env("FINACC_LOGIN_PATH", "/api/auth/login")
    me_path = env("FINACC_ME_PATH", "/api/auth/me")
    sales_invoice_path = env("FINACC_SALES_INVOICE_PATH", "/api/sales/invoices/")
    sales_invoice_lookup_path = env("FINACC_SALES_INVOICE_LOOKUP_PATH", "/api/sales/invoices/lookup/")
    sales_service_invoice_path = env("FINACC_SALES_SERVICE_INVOICE_PATH", "/api/sales/service-invoices/")
    sales_service_invoice_lookup_path = env("FINACC_SALES_SERVICE_INVOICE_LOOKUP_PATH", "/api/sales/service-invoices/lookup/")
    purchase_invoice_path = env("FINACC_PURCHASE_INVOICE_PATH", "/api/purchase/purchase-invoices/")
    purchase_service_invoice_path = env("FINACC_PURCHASE_SERVICE_INVOICE_PATH", "/api/purchase/purchase-service-invoices/")
    purchase_invoice_search_path = env("FINACC_PURCHASE_INVOICE_SEARCH_PATH", "/api/purchase/purchase-invoices/search/")
    purchase_service_invoice_search_path = env("FINACC_PURCHASE_SERVICE_INVOICE_SEARCH_PATH", "/api/purchase/purchase-service-invoices/search/")
    purchase_invoice_lookup_path = env("FINACC_PURCHASE_INVOICE_LOOKUP_PATH", "/api/purchase/purchase-invoices/lookup/")
    purchase_service_invoice_lookup_path = env("FINACC_PURCHASE_SERVICE_INVOICE_LOOKUP_PATH", "/api/purchase/purchase-service-invoices/lookup/")
    purchase_invoice_detail_path_template = env("FINACC_PURCHASE_INVOICE_DETAIL_PATH_TEMPLATE", "/api/purchase/purchase-invoices/{id}/")
    purchase_service_invoice_detail_path_template = env("FINACC_PURCHASE_SERVICE_INVOICE_DETAIL_PATH_TEMPLATE", "/api/purchase/purchase-service-invoices/{id}/")
    sales_settings_path = env("FINACC_SALES_SETTINGS_PATH", "/api/sales/settings/")
    payment_voucher_path = env("FINACC_PAYMENT_VOUCHER_PATH", "/api/payments/payment-vouchers/")
    payment_voucher_lookup_path = env("FINACC_PAYMENT_VOUCHER_LOOKUP_PATH", "/api/payments/payment-vouchers/lookup/")
    payment_voucher_form_meta_path = env("FINACC_PAYMENT_VOUCHER_FORM_META_PATH", "/api/payments/meta/voucher-form/")
    payment_voucher_confirm_suffix = env("FINACC_PAYMENT_VOUCHER_CONFIRM_SUFFIX", "/confirm/")
    payment_voucher_post_suffix = env("FINACC_PAYMENT_VOUCHER_POST_SUFFIX", "/post/")
    payment_voucher_approval_suffix = env("FINACC_PAYMENT_VOUCHER_APPROVAL_SUFFIX", "/approval/")
    receipt_voucher_path = env("FINACC_RECEIPT_VOUCHER_PATH", "/api/receipts/receipt-vouchers/")
    receipt_voucher_lookup_path = env("FINACC_RECEIPT_VOUCHER_LOOKUP_PATH", "/api/receipts/receipt-vouchers/lookup/")
    receipt_voucher_form_meta_path = env("FINACC_RECEIPT_VOUCHER_FORM_META_PATH", "/api/receipts/meta/voucher-form/")
    receipt_voucher_confirm_suffix = env("FINACC_RECEIPT_VOUCHER_CONFIRM_SUFFIX", "/confirm/")
    receipt_voucher_post_suffix = env("FINACC_RECEIPT_VOUCHER_POST_SUFFIX", "/post/")
    receipt_voucher_approval_suffix = env("FINACC_RECEIPT_VOUCHER_APPROVAL_SUFFIX", "/approval/")
    payables_meta_path = env("FINACC_PAYABLES_META_PATH", "/api/reports/payables/meta/")
    ap_aging_path = env("FINACC_AP_AGING_PATH", "/api/reports/payables/aging/")
    receivables_customer_outstanding_path = env("FINACC_RECEIVABLES_CUSTOMER_OUTSTANDING_PATH", "/api/reports/receivables/customer-outstanding/")
    receivables_open_items_path = env("FINACC_RECEIVABLES_OPEN_ITEMS_PATH", "/api/reports/receivables/open-items/")
    receivables_collections_history_path = env("FINACC_RECEIVABLES_COLLECTIONS_HISTORY_PATH", "/api/reports/receivables/collections-history/")
    receivables_aging_path = env("FINACC_RECEIVABLES_AGING_PATH", "/api/reports/receivables/aging/")
    financial_meta_path = env("FINACC_FINANCIAL_META_PATH", "/api/reports/financial/meta/")
    financial_trial_balance_path = env("FINACC_FINANCIAL_TRIAL_BALANCE_PATH", "/api/reports/financial/trial-balance/")
    financial_trial_balance_excel_path = env("FINACC_FINANCIAL_TRIAL_BALANCE_EXCEL_PATH", "/api/reports/financial/trial-balance/excel/")
    financial_trial_balance_pdf_path = env("FINACC_FINANCIAL_TRIAL_BALANCE_PDF_PATH", "/api/reports/financial/trial-balance/pdf/")
    financial_trial_balance_csv_path = env("FINACC_FINANCIAL_TRIAL_BALANCE_CSV_PATH", "/api/reports/financial/trial-balance/csv/")
    financial_ledger_summary_path = env("FINACC_FINANCIAL_LEDGER_SUMMARY_PATH", "/api/reports/financial/ledger-summary/")
    financial_ledger_summary_excel_path = env("FINACC_FINANCIAL_LEDGER_SUMMARY_EXCEL_PATH", "/api/reports/financial/ledger-summary/excel/")
    financial_ledger_summary_pdf_path = env("FINACC_FINANCIAL_LEDGER_SUMMARY_PDF_PATH", "/api/reports/financial/ledger-summary/pdf/")
    financial_ledger_summary_csv_path = env("FINACC_FINANCIAL_LEDGER_SUMMARY_CSV_PATH", "/api/reports/financial/ledger-summary/csv/")
    financial_profit_loss_path = env("FINACC_FINANCIAL_PROFIT_LOSS_PATH", "/api/reports/financial/profit-loss/")
    financial_profit_loss_csv_path = env("FINACC_FINANCIAL_PROFIT_LOSS_CSV_PATH", "/api/reports/financial/profit-loss/csv/")
    financial_balance_sheet_path = env("FINACC_FINANCIAL_BALANCE_SHEET_PATH", "/api/reports/financial/balance-sheet/")
    financial_balance_sheet_csv_path = env("FINACC_FINANCIAL_BALANCE_SHEET_CSV_PATH", "/api/reports/financial/balance-sheet/csv/")
    financial_trading_account_path = env("FINACC_FINANCIAL_TRADING_ACCOUNT_PATH", "/api/reports/financial/trading-account/")
    financial_trading_account_csv_path = env("FINACC_FINANCIAL_TRADING_ACCOUNT_CSV_PATH", "/api/reports/financial/trading-account/csv/")
    financial_ledger_book_path = env("FINACC_FINANCIAL_LEDGER_BOOK_PATH", "/api/reports/financial/ledger-book/")
    financial_ledger_book_csv_path = env("FINACC_FINANCIAL_LEDGER_BOOK_CSV_PATH", "/api/reports/financial/ledger-book/csv/")
    bank_reco_meta_path = env("FINACC_BANK_RECO_META_PATH", "/api/bank-reconciliation/meta/")
    bank_reco_sessions_path = env("FINACC_BANK_RECO_SESSIONS_PATH", "/api/bank-reconciliation/sessions/")
    sales_invoice_confirm_suffix = env("FINACC_SALES_INVOICE_CONFIRM_SUFFIX", "/confirm/")
    sales_invoice_post_suffix = env("FINACC_SALES_INVOICE_POST_SUFFIX", "/post/")
    sales_invoice_reverse_suffix = env("FINACC_SALES_INVOICE_REVERSE_SUFFIX", "/reverse/")
    purchase_invoice_confirm_suffix = env("FINACC_PURCHASE_INVOICE_CONFIRM_SUFFIX", "/confirm/")
    purchase_invoice_post_suffix = env("FINACC_PURCHASE_INVOICE_POST_SUFFIX", "/post/")
    purchase_invoice_create_credit_note_suffix = env("FINACC_PURCHASE_INVOICE_CREATE_CREDIT_NOTE_SUFFIX", "/create-credit-note/")
    purchase_invoice_create_debit_note_suffix = env("FINACC_PURCHASE_INVOICE_CREATE_DEBIT_NOTE_SUFFIX", "/create-debit-note/")
    purchase_lifecycle_seed_status = env("FINACC_PURCHASE_LIFECYCLE_SEED_STATUS", "1")
    purchase_valid_doc_codes = {"PINV", "PCN", "PDN"}
    purchase_note_reasons = (
        "price_difference",
        "quantity_return",
    )
    report_as_of_date = env("FINACC_REPORT_AS_OF_DATE", "")
    ap_aging_view = env("FINACC_AP_AGING_VIEW", "summary")
    financial_report_from_date = env("FINACC_FINANCIAL_REPORT_FROM_DATE", "")
    financial_report_to_date = env("FINACC_FINANCIAL_REPORT_TO_DATE", "")

    enable_writes = env("FINACC_ENABLE_WRITE_TESTS", "false").lower() == "true"
    enable_lifecycle = env("FINACC_ENABLE_LIFECYCLE_TESTS", "false").lower() == "true"
    _seed_invoice_id: int | None = None
    _seed_service_invoice_id: int | None = None
    _seed_purchase_invoice_id: int | None = None
    _seed_purchase_service_invoice_id: int | None = None
    _last_created_purchase_invoice_id: int | None = None
    _last_created_purchase_service_invoice_id: int | None = None
    _payment_meta_cache: Dict[str, Any] | None = None
    _receipt_meta_cache: Dict[str, Any] | None = None
    _financial_meta_cache: Dict[str, Any] | None = None

    def on_start(self) -> None:
        if not self.email or not self.password:
            raise RuntimeError("Set FINACC_USER_EMAIL and FINACC_USER_PASSWORD in .env")

        payload = {"email": self.email, "password": self.password}
        with self.client.post(self.login_path, json=payload, name="auth/login", catch_response=True) as response:
            if response.status_code >= 400:
                response.failure(f"Login failed ({response.status_code}): {response.text[:2000]}")
                return

            token = self._extract_token(response)
            if not token:
                token = self._extract_cookie_token()
            if token:
                self.client.headers.update({"Authorization": f"Bearer {token}"})
            response.success()

        # Finacc may authenticate using httpOnly auth cookies even when token is
        # not included in JSON response. Validate the session either way.
        with self.client.get(self.me_path, name="auth/me", catch_response=True) as me_response:
            if me_response.status_code >= 400:
                me_response.failure(
                    f"Post-login auth validation failed ({me_response.status_code}): {me_response.text[:2000]}"
                )
            else:
                me_response.success()

    @staticmethod
    def _extract_token(response) -> str:
        try:
            data = response.json()
        except Exception:
            return ""

        if not isinstance(data, dict):
            return ""

        return str(data.get("access") or data.get("access_token") or data.get("token") or "")

    def _extract_cookie_token(self) -> str:
        try:
            return str(self.client.cookies.get("fa_access") or "").strip()
        except Exception:
            return ""

    def _scope_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "entity_id": self.entity_id,
            "entityfinid": self.entity_fin_id,
        }
        if self.subentity_id:
            params["subentity_id"] = self.subentity_id
        return params

    def _entity_scope_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "entity": self.entity_id,
            "entityfinid": self.entity_fin_id,
        }
        if self.subentity_id:
            params["subentity"] = self.subentity_id
        return params

    def _ap_aging_params(self) -> Dict[str, Any]:
        params = self._entity_scope_params()
        params["view"] = self.ap_aging_view or "summary"
        params["include_trace"] = "true"
        if self.report_as_of_date:
            params["as_of_date"] = self.report_as_of_date
        return params

    def _receivable_report_params(self) -> Dict[str, Any]:
        params = self._entity_scope_params()
        params["page"] = 1
        params["page_size"] = 100
        if self.report_as_of_date:
            params["as_of_date"] = self.report_as_of_date
            params["to_date"] = self.report_as_of_date
            params["from_date"] = self.report_as_of_date[:4] + "-04-01"
        return params

    def _receivable_aging_params(self, *, view: str = "summary") -> Dict[str, Any]:
        params = self._receivable_report_params()
        params["view"] = view
        return params

    def _financial_report_params(
        self,
        *,
        group_by: str = "ledger",
        view_type: str = "summary",
        page_size: int = 100,
        include_zero_balances: bool = False,
        posted_only: bool = True,
        search: str = "",
    ) -> Dict[str, Any]:
        params = self._entity_scope_params()
        params["scope_mode"] = "custom"
        if self.financial_report_from_date:
            params["from_date"] = self.financial_report_from_date
        elif self.report_as_of_date:
            params["from_date"] = self.report_as_of_date[:4] + "-04-01"
        if self.financial_report_to_date:
            params["to_date"] = self.financial_report_to_date
        elif self.report_as_of_date:
            params["to_date"] = self.report_as_of_date
        params["group_by"] = group_by
        params["account_group"] = group_by
        params["view_type"] = view_type
        params["posted_only"] = str(posted_only).lower()
        params["include_zero_balances"] = str(include_zero_balances).lower()
        params["include_opening"] = "true"
        params["page"] = 1
        params["page_size"] = page_size
        if search:
            params["search"] = search
        return params

    def _financial_statement_params(
        self,
        *,
        group_by: str = "accounthead",
        view_type: str = "summary",
        presentation: str = "standard",
        page_size: int = 100,
    ) -> Dict[str, Any]:
        params = self._financial_report_params(
            group_by=group_by,
            view_type=view_type,
            page_size=page_size,
            include_zero_balances=False,
            posted_only=True,
        )
        params["presentation"] = presentation
        return params

    def _get_financial_meta(self) -> Dict[str, Any]:
        if self._financial_meta_cache is not None:
            return self._financial_meta_cache
        with self.client.get(
            self.financial_meta_path,
            params=self._entity_scope_params(),
            name="reports/financial/meta [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
                return {}
            try:
                payload = response.json()
            except ValueError:
                response.failure("Financial meta returned invalid JSON")
                return {}
        self._financial_meta_cache = payload if isinstance(payload, dict) else {}
        return self._financial_meta_cache

    def _pick_financial_ledger_id(self) -> int | None:
        meta = self._get_financial_meta()
        rows = meta.get("all_accounts") if isinstance(meta, dict) else None
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                return int(row["id"])
        return None

    def _extract_invoice_id(self, payload: Any) -> int | None:
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict) and first.get("id"):
                return int(first["id"])

        if isinstance(payload, dict):
            for key in ("results", "data", "items"):
                if isinstance(payload.get(key), list) and payload[key]:
                    first = payload[key][0]
                    if isinstance(first, dict) and first.get("id"):
                        return int(first["id"])
        return None

    def _extract_lookup_invoice_id(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                return int(first["id"])
        return None

    def _extract_response_header_id(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if isinstance(data, dict) and data.get("id"):
            return int(data["id"])
        return None

    def _extract_lookup_item_id(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                return int(first["id"])
        return None

    def _is_duplicate_note_guard(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        duplicate_note_guard = payload.get("duplicate_note_guard")
        if not isinstance(duplicate_note_guard, dict):
            return False
        return str(duplicate_note_guard.get("code") or "").strip() == "purchase_duplicate_note_exists"

    def _extract_valid_purchase_lookup_invoice_id(self, payload: Any) -> int | None:
        direct_id = self._extract_lookup_invoice_id(payload)
        if direct_id:
            return direct_id
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            invoice_id = item.get("id")
            doc_code = str(item.get("doc_code") or "").strip().upper()
            try:
                grand_total = float(item.get("grand_total") or 0)
            except (TypeError, ValueError):
                grand_total = 0
            if invoice_id and doc_code in self.purchase_valid_doc_codes and grand_total > 0:
                return int(invoice_id)
        return None

    def _extract_purchase_seed_invoice_id(self, payload: Any) -> int | None:
        invoice_id = self._extract_valid_purchase_lookup_invoice_id(payload)
        if invoice_id:
            return invoice_id
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("results") or payload.get("data") or payload.get("items") or []
        else:
            rows = []
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            invoice_id = row.get("id")
            if invoice_id:
                try:
                    return int(invoice_id)
                except (TypeError, ValueError):
                    continue
        return None

    def _build_purchase_detail_path(self, invoice_id: int, *, line_mode: str) -> str:
        template = (
            self.purchase_service_invoice_detail_path_template
            if line_mode == "service"
            else self.purchase_invoice_detail_path_template
        )
        return template.format(id=invoice_id)

    def _unique_supplier_invoice_number(self, prefix: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{prefix}-{stamp}-{random.randint(100, 999)}"

    def _normalize_date_value(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return text[:10]

    def _sanitize_purchase_line_for_create(self, line: Dict[str, Any], *, line_no: int) -> Dict[str, Any]:
        current_product_desc = str(line.get("product_desc") or "").strip()
        payload: Dict[str, Any] = {
            "id": None,
            "line_no": line_no,
            "product": line.get("product"),
            "purchase_account": line.get("purchase_account"),
            "product_desc": current_product_desc[:500],
            "is_service": bool(line.get("is_service")),
            "purchase_behavior": line.get("purchase_behavior"),
            "is_rate_inclusive_of_tax": bool(line.get("is_rate_inclusive_of_tax", False)),
            "uom": line.get("uom"),
            "qty": line.get("qty"),
            "free_qty": line.get("free_qty") or "0.0000",
            "rate": line.get("rate"),
            "discount_type": line.get("discount_type") if line.get("discount_type") is not None else 0,
            "discount_percent": line.get("discount_percent") or "0.00",
            "discount_amount": line.get("discount_amount") or "0.00",
            "taxability": line.get("taxability"),
            "gst_rate": line.get("gst_rate"),
            "cgst_percent": line.get("cgst_percent") or "0.00",
            "sgst_percent": line.get("sgst_percent") or "0.00",
            "igst_percent": line.get("igst_percent") or "0.00",
            "taxable_value": line.get("taxable_value"),
            "cgst_amount": line.get("cgst_amount") or "0.00",
            "sgst_amount": line.get("sgst_amount") or "0.00",
            "igst_amount": line.get("igst_amount") or "0.00",
            "cess_percent": line.get("cess_percent") or "0.00",
            "cess_type": line.get("cess_type") or "none",
            "cess_specific_amount": line.get("cess_specific_amount") or "0.00",
            "cess_amount": line.get("cess_amount") or "0.00",
            "line_total": line.get("line_total"),
            "is_itc_eligible": bool(line.get("is_itc_eligible", True)),
        }
        if line.get("batch_number"):
            payload["batch_number"] = line.get("batch_number")
        if line.get("hsn_sac"):
            payload["hsn_sac"] = line.get("hsn_sac")
        return payload

    def _build_purchase_draft_payload_from_detail(self, detail: Dict[str, Any], *, line_mode: str) -> Dict[str, Any] | None:
        lines = detail.get("lines")
        if not isinstance(lines, list) or not lines:
            return None

        sanitized_lines = [
            self._sanitize_purchase_line_for_create(line, line_no=index)
            for index, line in enumerate(lines, start=1)
        ]
        payload: Dict[str, Any] = {
            "doc_type": detail.get("doc_type"),
            "bill_date": self._normalize_date_value(detail.get("bill_date")),
            "posting_date": self._normalize_date_value(detail.get("posting_date")),
            "supplier_invoice_number": self._unique_supplier_invoice_number(
                "LOCUST-PSVC" if line_mode == "service" else "LOCUST-PINV"
            ),
            "supplier_invoice_date": self._normalize_date_value(
                detail.get("supplier_invoice_date") or detail.get("bill_date")
            ),
            "vendor": detail.get("vendor"),
            "vendor_name": detail.get("vendor_name"),
            "vendor_gstin": detail.get("vendor_gstin"),
            "vendor_state": detail.get("vendor_state"),
            "supplier_state": detail.get("supplier_state"),
            "place_of_supply_state": detail.get("place_of_supply_state"),
            "supply_category": detail.get("supply_category"),
            "default_taxability": detail.get("default_taxability"),
            "tax_regime": detail.get("tax_regime"),
            "is_igst": detail.get("is_igst"),
            "is_reverse_charge": detail.get("is_reverse_charge"),
            "is_itc_eligible": detail.get("is_itc_eligible"),
            "itc_claim_status": detail.get("itc_claim_status"),
            "entity": detail.get("entity"),
            "entityfinid": detail.get("entityfinid"),
            "subentity": detail.get("subentity"),
            "location": detail.get("location"),
            "lines": sanitized_lines,
            "charges": detail.get("charges") if isinstance(detail.get("charges"), list) else [],
            "custom_fields": detail.get("custom_fields") if isinstance(detail.get("custom_fields"), dict) else {},
            "withholding_enabled": bool(detail.get("withholding_enabled", False)),
            "gst_tds_enabled": bool(detail.get("gst_tds_enabled", False)),
            "vendor_gst_tds_declared": bool(detail.get("vendor_gst_tds_declared", False)),
            "vendor_tds_declared": bool(detail.get("vendor_tds_declared", False)),
        }
        return payload

    def _fetch_purchase_detail_payload(self, *, line_mode: str) -> Dict[str, Any] | None:
        invoice_id = self._fetch_purchase_lookup_invoice_id(line_mode=line_mode)
        if not invoice_id:
            return None
        with self.client.get(
            self._build_purchase_detail_path(invoice_id, line_mode=line_mode),
            params=self._entity_scope_params(),
            name=f"purchase/{line_mode}-detail [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Purchase detail seed fetch failed ({response.status_code}): {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                content_type = response.headers.get("Content-Type", "")
                response.failure(
                    "Purchase detail seed fetch returned invalid JSON "
                    f"(content-type={content_type!r}, body={response.text[:500]!r})"
                )
                return None
            if not isinstance(payload, dict):
                response.failure("Purchase detail seed fetch returned non-object payload")
                return None
            response.success()
            return payload

    def _create_purchase_draft_from_seed(
        self,
        *,
        line_mode: str,
        request_name: str,
    ) -> tuple[int, Dict[str, Any]] | None:
        list_path = self.purchase_service_invoice_path if line_mode == "service" else self.purchase_invoice_path
        seed_detail = self._fetch_purchase_detail_payload(line_mode=line_mode)
        if not seed_detail:
            return None
        create_payload = self._build_purchase_draft_payload_from_detail(seed_detail, line_mode=line_mode)
        if not create_payload:
            return None

        with self.client.post(
            list_path,
            json=create_payload,
            name=request_name,
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return None
            try:
                created_body = response.json()
            except Exception:
                response.failure("Purchase draft create returned invalid JSON")
                return None
            if not isinstance(created_body, dict):
                response.failure("Purchase draft create returned non-object payload")
                return None

            created_id = None
            try:
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                created_id = self._extract_response_header_id(created_body)
            if not created_id:
                response.failure("Purchase draft create did not return an id")
                return None
            if line_mode == "service":
                self._last_created_purchase_service_invoice_id = created_id
                self._seed_purchase_service_invoice_id = created_id
            else:
                self._last_created_purchase_invoice_id = created_id
                self._seed_purchase_invoice_id = created_id
            response.success()
            return created_id, created_body

    def _build_sales_detail_path(self, invoice_id: int, *, line_mode: str) -> str:
        return (
            f"{self.sales_service_invoice_path}{invoice_id}/"
            if line_mode == "service"
            else f"{self.sales_invoice_path}{invoice_id}/"
        )

    def _sanitize_sales_line_for_create(self, line: Dict[str, Any], *, line_no: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": None,
            "line_no": line_no,
            "product": line.get("product"),
            "productDesc": line.get("productDesc") or "",
            "uom": line.get("uom"),
            "is_service": bool(line.get("is_service")),
            "qty": line.get("qty"),
            "free_qty": line.get("free_qty") or "0.00",
            "rate": line.get("rate"),
            "is_rate_inclusive_of_tax": bool(line.get("is_rate_inclusive_of_tax", False)),
            "discount_type": line.get("discount_type") if line.get("discount_type") is not None else 0,
            "discount_percent": line.get("discount_percent") or "0.00",
            "discount_amount": line.get("discount_amount") or "0.00",
            "taxability": line.get("taxability"),
            "gst_rate": line.get("gst_rate") or "0.00",
            "cess_percent": line.get("cess_percent") or "0.00",
            "cess_amount": line.get("cess_amount") or "0.00",
            "sales_account": line.get("sales_account"),
        }
        if line.get("batch_number"):
            payload["batch_number"] = line.get("batch_number")
        if line.get("hsn_sac_code"):
            payload["hsn_sac_code"] = line.get("hsn_sac_code")
        manufacture_date = self._normalize_date_value(line.get("manufacture_date"))
        expiry_date = self._normalize_date_value(line.get("expiry_date"))
        if manufacture_date:
            payload["manufacture_date"] = manufacture_date
        if expiry_date:
            payload["expiry_date"] = expiry_date
        for amount_field in (
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "line_total",
        ):
            if amount_field in line:
                payload[amount_field] = line.get(amount_field)
        return payload

    def _sanitize_sales_custom_fields_for_create(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        raw_custom_fields = detail.get("custom_fields")
        if not isinstance(raw_custom_fields, dict):
            return {}
        blocked_keys = {"correction_history", "correction_origin"}
        return {
            key: value
            for key, value in raw_custom_fields.items()
            if key not in blocked_keys
        }

    def _build_sales_draft_payload_from_detail(self, detail: Dict[str, Any], *, line_mode: str) -> Dict[str, Any] | None:
        lines = detail.get("lines")
        if not isinstance(lines, list) or not lines:
            return None

        sanitized_lines = [
            self._sanitize_sales_line_for_create(line, line_no=index)
            for index, line in enumerate(lines, start=1)
        ]
        payload: Dict[str, Any] = {
            "entity": detail.get("entity"),
            "entityfinid": detail.get("entityfinid"),
            "subentity": detail.get("subentity"),
            "location": detail.get("location"),
            "doc_type": detail.get("doc_type"),
            "doc_code": self._resolve_sales_doc_code(detail),
            "bill_date": self._normalize_date_value(detail.get("bill_date")),
            "credit_days": detail.get("credit_days") or 0,
            "customer": detail.get("customer"),
            "customer_name": detail.get("customer_name"),
            "customer_gstin": detail.get("customer_gstin") or "",
            "customer_state_code": detail.get("customer_state_code") or "",
            "is_bill_to_ship_to_same": bool(detail.get("is_bill_to_ship_to_same", True)),
            "bill_to_address1": detail.get("bill_to_address1") or "",
            "bill_to_address2": detail.get("bill_to_address2") or "",
            "bill_to_city": detail.get("bill_to_city") or "",
            "bill_to_state_code": detail.get("bill_to_state_code") or "",
            "bill_to_pincode": detail.get("bill_to_pincode") or "",
            "seller_gstin": detail.get("seller_gstin") or "",
            "ecm_gstin": detail.get("ecm_gstin") or "",
            "seller_state_code": detail.get("seller_state_code") or "",
            "place_of_supply_state_code": detail.get("place_of_supply_state_code") or "",
            "place_of_supply_pincode": detail.get("place_of_supply_pincode") or "",
            "supply_category": detail.get("supply_category"),
            "taxability": detail.get("taxability"),
            "is_reverse_charge": bool(detail.get("is_reverse_charge", False)),
            "reference": self._unique_supplier_invoice_number("LOCUST-SREF"),
            "remarks": f"Locust sales {line_mode} draft create",
            "withholding_enabled": bool(detail.get("withholding_enabled", False)),
            "lines": sanitized_lines,
            "charges": detail.get("charges") if isinstance(detail.get("charges"), list) else [],
            "custom_fields": self._sanitize_sales_custom_fields_for_create(detail),
        }
        if detail.get("shipping_detail"):
            payload["shipping_detail"] = detail.get("shipping_detail")
        if detail.get("tcs_section"):
            payload["tcs_section"] = detail.get("tcs_section")
        return payload

    def _fetch_sales_detail_payload(self, *, line_mode: str) -> Dict[str, Any] | None:
        invoice_id = self._fetch_lookup_invoice_id(line_mode=line_mode)
        if not invoice_id:
            return None
        with self.client.get(
            self._build_sales_detail_path(invoice_id, line_mode=line_mode),
            params=self._entity_scope_params(),
            name=f"sales/{line_mode}-detail [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Sales detail seed fetch failed ({response.status_code}): {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                response.failure("Sales detail seed fetch returned invalid JSON")
                return None
            if not isinstance(payload, dict):
                response.failure("Sales detail seed fetch returned non-object payload")
                return None
            response.success()
            return payload

    def _fetch_sales_settings_payload(self) -> Dict[str, Any] | None:
        cached = getattr(self, "_sales_settings_cache", None)
        if isinstance(cached, dict):
            return cached
        with self.client.get(
            self.sales_settings_path,
            params=self._scope_params(),
            name="sales/settings [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Sales settings seed fetch failed ({response.status_code}): {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                response.failure("Sales settings seed fetch returned invalid JSON")
                return None
            if not isinstance(payload, dict):
                response.failure("Sales settings seed fetch returned non-object payload")
                return None
            settings_payload = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
            if not isinstance(settings_payload, dict):
                response.failure("Sales settings seed fetch returned invalid settings payload")
                return None
            self._sales_settings_cache = settings_payload
            response.success()
            return settings_payload

    def _resolve_sales_doc_code(self, detail: Dict[str, Any]) -> str:
        explicit = str(detail.get("doc_code") or "").strip()
        if explicit:
            return explicit

        settings_payload = self._fetch_sales_settings_payload() or {}
        doc_type = detail.get("doc_type")
        if doc_type == 2:
            return str(settings_payload.get("default_doc_code_cn") or "SCN").strip()
        if doc_type == 3:
            return str(settings_payload.get("default_doc_code_dn") or "SDN").strip()
        return str(settings_payload.get("default_doc_code_invoice") or "SINV").strip()

    def _fetch_payment_meta(self) -> Dict[str, Any] | None:
        if self._payment_meta_cache is not None:
            return self._payment_meta_cache
        with self.client.get(
            self.payment_voucher_form_meta_path,
            params=self._entity_scope_params(),
            name="payments/meta/voucher-form [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Payment meta seed fetch failed ({response.status_code}): {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                response.failure("Payment meta seed fetch returned invalid JSON")
                return None
            if not isinstance(payload, dict):
                response.failure("Payment meta seed fetch returned non-object payload")
                return None
            self._payment_meta_cache = payload
            response.success()
            return payload

    def _build_payment_voucher_payload(self, meta: Dict[str, Any]) -> Dict[str, Any] | None:
        paid_from_accounts = meta.get("paid_from_accounts")
        vendors = meta.get("vendors")
        payment_modes = meta.get("payment_modes")
        settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
        if not isinstance(paid_from_accounts, list) or not paid_from_accounts:
            return None
        if not isinstance(vendors, list) or not vendors:
            return None
        if not isinstance(payment_modes, list) or not payment_modes:
            return None

        paid_from = paid_from_accounts[0]
        paid_to = next((row for row in vendors if str(row.get("partytype") or "").strip().lower() in {"vendor", "both"}), vendors[0])
        payment_mode = payment_modes[0]
        return {
            "entity": int(self.entity_id),
            "entityfinid": int(self.entity_fin_id),
            "subentity": int(self.subentity_id) if self.subentity_id else None,
            "voucher_date": datetime.now().strftime("%Y-%m-%d"),
            "doc_code": settings.get("default_doc_code_payment") or "PPV",
            "payment_type": "ADVANCE",
            "supply_type": "SERVICES",
            "paid_from": paid_from.get("id"),
            "paid_to": paid_to.get("id"),
            "payment_mode": payment_mode.get("id"),
            "cash_paid_amount": "1000.00",
            "reference_number": self._unique_supplier_invoice_number("LOCUST-PAY-REF"),
            "narration": "Locust payment voucher write test",
            "allocations": [],
            "adjustments": [],
            "advance_adjustments": [],
        }

    def _fetch_payment_lookup_voucher_id(self) -> int | None:
        with self.client.get(
            self.payment_voucher_lookup_path,
            params={**self._entity_scope_params(), "limit": 1},
            name="payments/payment-vouchers/lookup [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Payment lookup seed fetch failed ({response.status_code})")
                return None
            try:
                voucher_id = self._extract_lookup_item_id(response.json())
            except Exception:
                voucher_id = None
            if not voucher_id:
                response.failure("No payment voucher id found for lookup seed")
                return None
            response.success()
            return voucher_id

    def _fetch_receipt_meta(self) -> Dict[str, Any] | None:
        if self._receipt_meta_cache is not None:
            return self._receipt_meta_cache
        with self.client.get(
            self.receipt_voucher_form_meta_path,
            params=self._entity_scope_params(),
            name="receipts/meta/voucher-form [seed]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Receipt meta seed fetch failed ({response.status_code}): {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                response.failure("Receipt meta seed fetch returned invalid JSON")
                return None
            if not isinstance(payload, dict):
                response.failure("Receipt meta seed fetch returned non-object payload")
                return None
            self._receipt_meta_cache = payload
            response.success()
            return payload

    def _build_receipt_voucher_payload(self, meta: Dict[str, Any]) -> Dict[str, Any] | None:
        received_in_accounts = meta.get("received_in_accounts")
        customers = meta.get("customers")
        receipt_modes = meta.get("receipt_modes")
        settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
        if not isinstance(received_in_accounts, list) or not received_in_accounts:
            return None
        if not isinstance(customers, list) or not customers:
            return None
        if not isinstance(receipt_modes, list) or not receipt_modes:
            return None

        received_in = received_in_accounts[0]
        received_from = next((row for row in customers if str(row.get("partytype") or "").strip().lower() in {"customer", "both"}), customers[0])
        receipt_mode = receipt_modes[0]
        return {
            "entity": int(self.entity_id),
            "entityfinid": int(self.entity_fin_id),
            "subentity": int(self.subentity_id) if self.subentity_id else None,
            "voucher_date": datetime.now().strftime("%Y-%m-%d"),
            "doc_code": settings.get("default_doc_code_receipt") or "RV",
            "receipt_type": "ADVANCE",
            "supply_type": "SERVICES",
            "received_in": received_in.get("id"),
            "received_from": received_from.get("id"),
            "receipt_mode": receipt_mode.get("id"),
            "cash_received_amount": "1000.00",
            "reference_number": self._unique_supplier_invoice_number("LOCUST-REC-REF"),
            "narration": "Locust receipt voucher write test",
            "allocations": [],
            "adjustments": [],
            "advance_adjustments": [],
        }

    def _run_approval_action(self, detail_base: str, suffix: str, *, name: str, params: Dict[str, Any], action: str, remarks: str) -> bool:
        with self.client.post(
            f"{detail_base}{suffix}",
            params=params,
            json={"action": action, "remarks": remarks},
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return False
            response.success()
            return True

    def _run_approval_action_with_body(
        self,
        detail_base: str,
        suffix: str,
        *,
        name: str,
        params: Dict[str, Any],
        action: str,
        remarks: str,
    ) -> Dict[str, Any] | None:
        with self.client.post(
            f"{detail_base}{suffix}",
            params=params,
            json={"action": action, "remarks": remarks},
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return None
            try:
                payload = response.json()
            except Exception:
                response.failure("Approval action returned invalid JSON")
                return None
            if not isinstance(payload, dict):
                response.failure("Approval action returned non-object payload")
                return None
            response.success()
            return payload

    def _expect_approval_feedback(
        self,
        payload: Dict[str, Any] | None,
        *,
        expected_message: str,
        expected_status: str,
    ) -> bool:
        if not isinstance(payload, dict):
            return False
        message = str(payload.get("message") or "").strip()
        approval_status = str(payload.get("approval_status") or "").strip().upper()
        if message != expected_message or approval_status != expected_status.upper():
            return False
        return True

    def _fetch_any_invoice_id(self) -> int | None:
        if self._seed_invoice_id:
            return self._seed_invoice_id
        with self.client.get(
            self.sales_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 1, "include_total": "false"},
            name="sales/invoices [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Invoice seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_lookup_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if not invoice_id:
                response.failure("No invoice id found for lifecycle test")
                return None
            self._seed_invoice_id = invoice_id
            response.success()
            return invoice_id

    def _fetch_lookup_invoice_id(self, *, line_mode: str = "goods") -> int | None:
        cache_attr = "_seed_service_invoice_id" if line_mode == "service" else "_seed_invoice_id"
        cached_id = getattr(self, cache_attr, None)
        if cached_id:
            return cached_id

        path = self.sales_service_invoice_lookup_path if line_mode == "service" else self.sales_invoice_lookup_path
        with self.client.get(
            path,
            params={**self._entity_scope_params(), "limit": 1, "include_total": "false"},
            name=f"sales/{line_mode}-lookup [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Lookup seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_lookup_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if not invoice_id:
                response.failure("No invoice id found for lookup/navigation seed")
                return None
            setattr(self, cache_attr, invoice_id)
            response.success()
            return invoice_id

    def _fetch_purchase_lookup_invoice_id(self, *, line_mode: str = "goods") -> int | None:
        cache_attr = "_seed_purchase_service_invoice_id" if line_mode == "service" else "_seed_purchase_invoice_id"
        last_created_attr = (
            "_last_created_purchase_service_invoice_id" if line_mode == "service" else "_last_created_purchase_invoice_id"
        )
        cached_id = getattr(self, cache_attr, None)
        if cached_id:
            return cached_id
        last_created_id = getattr(self, last_created_attr, None)
        if last_created_id:
            setattr(self, cache_attr, last_created_id)
            return last_created_id

        path = self.purchase_service_invoice_lookup_path if line_mode == "service" else self.purchase_invoice_lookup_path
        with self.client.get(
            path,
            params={
                **self._entity_scope_params(),
                "limit": 5,
                "status": self.purchase_lifecycle_seed_status,
                "include_total": "false",
            },
            name=f"purchase/{line_mode}-lookup [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Purchase lookup seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_purchase_seed_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if invoice_id:
                setattr(self, cache_attr, invoice_id)
                response.success()
                return invoice_id
            response.success()

        fallback_path = self.purchase_service_invoice_path if line_mode == "service" else self.purchase_invoice_path
        with self.client.get(
            fallback_path,
            params=self._entity_scope_params(),
            name=f"purchase/{line_mode}-list [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code < 400:
                try:
                    invoice_id = self._extract_purchase_seed_invoice_id(response.json())
                except Exception:
                    invoice_id = None
                if invoice_id:
                    setattr(self, cache_attr, invoice_id)
                    response.success()
                    return invoice_id
            response.success()

        legacy_path = self.purchase_service_invoice_search_path if line_mode == "service" else self.purchase_invoice_search_path
        with self.client.get(
            legacy_path,
            params=self._entity_scope_params(),
            name=f"purchase/{line_mode}-search [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code < 400:
                try:
                    invoice_id = self._extract_purchase_seed_invoice_id(response.json())
                except Exception:
                    invoice_id = None
                if invoice_id:
                    setattr(self, cache_attr, invoice_id)
                    response.success()
                    return invoice_id
            response.success()

        last_created_id = getattr(self, last_created_attr, None)
        if last_created_id:
            setattr(self, cache_attr, last_created_id)
            return last_created_id

        with self.client.get(
            path,
            params={
                **self._entity_scope_params(),
                "limit": 5,
                "status": self.purchase_lifecycle_seed_status,
                "include_total": "false",
            },
            name=f"purchase/{line_mode}-lookup [seed-id]",
            catch_response=True,
        ) as response:
            response.failure("No valid purchase invoice id found for lookup/navigation seed")
            return None

    @tag("read")
    @task(5)
    def list_sales_invoices(self) -> None:
        with self.client.get(
            self.sales_invoice_path,
            params=self._scope_params(),
            name="sales/invoices [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("auth-bootstrap", "auth-health")
    @task(1)
    def auth_me_health(self) -> None:
        with self.client.get(
            self.me_path,
            name="auth/me [health]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("read", "read-modern", "sales-modern", "sales-mixed")
    @task(4)
    def lookup_sales_invoices(self) -> None:
        with self.client.get(
            self.sales_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="sales/invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern", "sales-modern", "sales-mixed")
    @task(2)
    def lookup_service_invoices(self) -> None:
        with self.client.get(
            self.sales_service_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="sales/service-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern", "sales-modern", "sales-mixed")
    @task(2)
    def cross_mode_navigation_from_goods(self) -> None:
        invoice_id = self._fetch_lookup_invoice_id(line_mode="goods")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.sales_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "service", "direction": "next"},
            name="sales/invoices/cross-mode-nav [goods->service]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern", "sales-modern", "sales-mixed")
    @task(2)
    def cross_mode_navigation_from_service(self) -> None:
        invoice_id = self._fetch_lookup_invoice_id(line_mode="service")
        if not invoice_id:
            return
        with self.client.get(
            f"/api/sales/service-invoices/{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "goods", "direction": "next"},
            name="sales/service-invoices/cross-mode-nav [service->goods]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "sales-modern", "sales-mixed")
    @task(3)
    def get_sales_settings(self) -> None:
        with self.client.get(
            self.sales_settings_path,
            params=self._scope_params(),
            name="sales/settings [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(4)
    def lookup_purchase_invoices(self) -> None:
        with self.client.get(
            self.purchase_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="purchase/purchase-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-legacy")
    @task(4)
    def search_purchase_invoices_legacy(self) -> None:
        with self.client.get(
            self.purchase_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-invoices/search [legacy]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-legacy")
    @task(3)
    def search_purchase_service_invoices_legacy(self) -> None:
        with self.client.get(
            self.purchase_service_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-service-invoices/search [legacy]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-legacy-mix")
    @task(7)
    def purchase_legacy_mix(self) -> None:
        # Keep a single explicit tagged entrypoint for the legacy search profile so
        # headless filtered runs always dispatch the intended legacy workload.
        if random.random() < (4 / 7):
            self.search_purchase_invoices_legacy()
        else:
            self.search_purchase_service_invoices_legacy()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def lookup_purchase_service_invoices(self) -> None:
        with self.client.get(
            self.purchase_service_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="purchase/purchase-service-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def cross_mode_navigation_from_purchase_goods(self) -> None:
        invoice_id = self._fetch_purchase_lookup_invoice_id(line_mode="goods")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.purchase_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "service", "direction": "next"},
            name="purchase/purchase-invoices/cross-mode-nav [goods->service]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def cross_mode_navigation_from_purchase_service(self) -> None:
        invoice_id = self._fetch_purchase_lookup_invoice_id(line_mode="service")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.purchase_service_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "goods", "direction": "next"},
            name="purchase/purchase-service-invoices/cross-mode-nav [service->goods]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-mixed")
    @task(8)
    def purchase_mixed(self) -> None:
        weighted_tasks = [
            self.lookup_purchase_invoices,
            self.lookup_purchase_invoices,
            self.lookup_purchase_service_invoices,
            self.cross_mode_navigation_from_purchase_goods,
            self.cross_mode_navigation_from_purchase_service,
        ]
        if self.enable_lifecycle:
            weighted_tasks.extend(
                [
                    self.purchase_invoice_lifecycle_optional,
                    self.purchase_note_lifecycle_optional,
                ]
            )
        if self.enable_writes or self.enable_lifecycle:
            weighted_tasks.append(self.purchase_draft_create_save_optional)
        random.choice(weighted_tasks)()

    @tag("read", "report-heavy", "report-write-mix", "ap-ar-reports", "payables-reports")
    @task(2)
    def get_payables_meta(self) -> None:
        with self.client.get(
            self.payables_meta_path,
            params=self._entity_scope_params(),
            name="reports/payables/meta [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "report-write-mix", "ap-ar-reports", "payables-reports")
    @task(3)
    def get_ap_aging(self) -> None:
        with self.client.get(
            self.ap_aging_path,
            params=self._ap_aging_params(),
            name="reports/payables/aging [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "receivables-reports", "report-write-mix", "ap-ar-reports")
    @task(2)
    def get_customer_outstanding(self) -> None:
        with self.client.get(
            self.receivables_customer_outstanding_path,
            params=self._receivable_report_params(),
            name="reports/receivables/customer-outstanding [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "receivables-reports", "report-write-mix", "ap-ar-reports")
    @task(2)
    def get_receivable_aging_summary(self) -> None:
        with self.client.get(
            self.receivables_aging_path,
            params=self._receivable_aging_params(view="summary"),
            name="reports/receivables/aging [summary]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "receivables-reports", "report-write-mix", "ap-ar-reports")
    @task(1)
    def get_receivable_aging_invoice(self) -> None:
        with self.client.get(
            self.receivables_aging_path,
            params=self._receivable_aging_params(view="invoice"),
            name="reports/receivables/aging [invoice]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "receivables-reports", "ap-ar-reports")
    @task(1)
    def get_receivables_open_items(self) -> None:
        with self.client.get(
            self.receivables_open_items_path,
            params=self._receivable_report_params(),
            name="reports/receivables/open-items [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "receivables-reports", "ap-ar-reports")
    @task(1)
    def get_receivables_collections_history(self) -> None:
        with self.client.get(
            self.receivables_collections_history_path,
            params=self._receivable_report_params(),
            name="reports/receivables/collections-history [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "report-write-mix")
    @task(2)
    def get_bank_reconciliation_meta(self) -> None:
        with self.client.get(
            self.bank_reco_meta_path,
            params=self._entity_scope_params(),
            name="bank-reconciliation/meta [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "report-write-mix")
    @task(2)
    def list_bank_reconciliation_sessions(self) -> None:
        with self.client.get(
            self.bank_reco_sessions_path,
            params=self._entity_scope_params(),
            name="bank-reconciliation/sessions [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "trial-balance")
    @task(2)
    def get_financial_trial_balance(self) -> None:
        with self.client.get(
            self.financial_trial_balance_path,
            params=self._financial_report_params(group_by="ledger", view_type="summary", page_size=100),
            name="reports/financial/trial-balance [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "trial-balance")
    @task(1)
    def get_financial_trial_balance_grouped(self) -> None:
        with self.client.get(
            self.financial_trial_balance_path,
            params=self._financial_report_params(group_by=random.choice(["accounthead", "accounttype"]), view_type="detailed", page_size=50),
            name="reports/financial/trial-balance [grouped]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "trial-balance", "report-exports")
    @task(1)
    def export_financial_trial_balance_csv(self) -> None:
        with self.client.get(
            self.financial_trial_balance_csv_path,
            params=self._financial_report_params(group_by="ledger", view_type="summary", page_size=100),
            name="reports/financial/trial-balance/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "ledger-summary")
    @task(2)
    def get_financial_ledger_summary(self) -> None:
        with self.client.get(
            self.financial_ledger_summary_path,
            params=self._financial_report_params(group_by="ledger", view_type="summary", page_size=100),
            name="reports/financial/ledger-summary [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "ledger-summary")
    @task(1)
    def get_financial_ledger_summary_grouped(self) -> None:
        with self.client.get(
            self.financial_ledger_summary_path,
            params=self._financial_report_params(group_by=random.choice(["accounthead", "accounttype"]), view_type="detailed", page_size=50),
            name="reports/financial/ledger-summary [grouped]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-reports", "financial-reports-r1", "ledger-summary", "report-exports")
    @task(1)
    def export_financial_ledger_summary_csv(self) -> None:
        with self.client.get(
            self.financial_ledger_summary_csv_path,
            params=self._financial_report_params(group_by="ledger", view_type="summary", page_size=100),
            name="reports/financial/ledger-summary/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "profit-loss")
    @task(2)
    def get_financial_profit_loss(self) -> None:
        with self.client.get(
            self.financial_profit_loss_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="standard", page_size=100),
            name="reports/financial/profit-loss [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "profit-loss")
    @task(1)
    def get_financial_profit_loss_grouped(self) -> None:
        with self.client.get(
            self.financial_profit_loss_path,
            params=self._financial_statement_params(
                group_by=random.choice(["accounthead", "accounttype"]),
                view_type="detailed",
                presentation="statement",
                page_size=50,
            ),
            name="reports/financial/profit-loss [grouped]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "profit-loss", "report-exports")
    @task(1)
    def export_financial_profit_loss_csv(self) -> None:
        with self.client.get(
            self.financial_profit_loss_csv_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="standard", page_size=100),
            name="reports/financial/profit-loss/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "balance-sheet")
    @task(2)
    def get_financial_balance_sheet(self) -> None:
        with self.client.get(
            self.financial_balance_sheet_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="standard", page_size=100),
            name="reports/financial/balance-sheet [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "balance-sheet")
    @task(1)
    def get_financial_balance_sheet_grouped(self) -> None:
        with self.client.get(
            self.financial_balance_sheet_path,
            params=self._financial_statement_params(
                group_by=random.choice(["accounthead", "accounttype"]),
                view_type="detailed",
                presentation="statement",
                page_size=50,
            ),
            name="reports/financial/balance-sheet [grouped]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "balance-sheet", "report-exports")
    @task(1)
    def export_financial_balance_sheet_csv(self) -> None:
        with self.client.get(
            self.financial_balance_sheet_csv_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="standard", page_size=100),
            name="reports/financial/balance-sheet/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "trading-account")
    @task(2)
    def get_financial_trading_account(self) -> None:
        with self.client.get(
            self.financial_trading_account_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="statement", page_size=100),
            name="reports/financial/trading-account [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "trading-account")
    @task(1)
    def get_financial_trading_account_grouped(self) -> None:
        with self.client.get(
            self.financial_trading_account_path,
            params=self._financial_statement_params(
                group_by=random.choice(["accounthead", "accounttype"]),
                view_type="detailed",
                presentation="statement",
                page_size=50,
            ),
            name="reports/financial/trading-account [grouped]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "trading-account", "report-exports")
    @task(1)
    def export_financial_trading_account_csv(self) -> None:
        with self.client.get(
            self.financial_trading_account_csv_path,
            params=self._financial_statement_params(group_by="accounthead", view_type="summary", presentation="statement", page_size=100),
            name="reports/financial/trading-account/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "ledger-book")
    @task(2)
    def get_financial_ledger_book(self) -> None:
        ledger_id = self._pick_financial_ledger_id()
        if not ledger_id:
            return
        params = self._financial_statement_params(group_by="ledger", view_type="detailed", presentation="standard", page_size=100)
        params["ledger"] = ledger_id
        with self.client.get(
            self.financial_ledger_book_path,
            params=params,
            name="reports/financial/ledger-book [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "report-heavy", "financial-statements", "financial-reports-r2", "ledger-book", "report-exports")
    @task(1)
    def export_financial_ledger_book_csv(self) -> None:
        ledger_id = self._pick_financial_ledger_id()
        if not ledger_id:
            return
        params = self._financial_statement_params(group_by="ledger", view_type="detailed", presentation="standard", page_size=100)
        params["ledger"] = ledger_id
        with self.client.get(
            self.financial_ledger_book_csv_path,
            params=params,
            name="reports/financial/ledger-book/csv [export]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("write", "sales-write", "sales-mixed")
    @task(1)
    def patch_sales_settings_optional(self) -> None:
        if not self.enable_writes:
            return

        payload = {
            "settings": {
                "workflow_mode": random.choice(["STRICT", "RELAXED"]),
                "allow_negative_stock": random.choice([True, False]),
            }
        }
        self.client.patch(
            self.sales_settings_path,
            params=self._scope_params(),
            json=payload,
            name="sales/settings [patch]",
        )

    @tag("lifecycle", "write", "sales-lifecycle", "sales-write", "sales-mixed")
    @task(1)
    def invoice_lifecycle_optional(self) -> None:
        if not self.enable_lifecycle:
            return

        invoice_id = self._fetch_any_invoice_id()
        if not invoice_id:
            return

        base = f"{self.sales_invoice_path}{invoice_id}"

        with self.client.post(
            f"{base}{self.sales_invoice_confirm_suffix}",
            name="sales/invoices [confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{base}{self.sales_invoice_post_suffix}",
            name="sales/invoices [post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{base}{self.sales_invoice_reverse_suffix}",
            json={"reason": "Locust lifecycle perf test"},
            name="sales/invoices [reverse]",
            catch_response=True,
        ) as response:
            if response.status_code < 400:
                response.success()
                return
            body = response.text[:2000]
            if (
                response.status_code == 400
                and "Only posted invoices can be reversed." in body
            ):
                response.success()
                return
            response.failure(f"{response.status_code}: {body}")

    @tag("purchase-write", "lifecycle", "write")
    @task(1)
    def purchase_invoice_lifecycle_optional(self) -> None:
        if not self.enable_lifecycle:
            return

        line_mode = random.choice(["goods", "service"])
        created = self._create_purchase_draft_from_seed(
            line_mode=line_mode,
            request_name=(
                "purchase/service-invoices [draft create]"
                if line_mode == "service"
                else "purchase/invoices [draft create]"
            ),
        )
        if not created:
            return
        invoice_id, _ = created

        base_path = self.purchase_service_invoice_path if line_mode == "service" else self.purchase_invoice_path
        invoice_name = "purchase/service-invoices" if line_mode == "service" else "purchase/invoices"
        base = f"{base_path}{invoice_id}"
        params = self._entity_scope_params()

        with self.client.post(
            f"{base}{self.purchase_invoice_confirm_suffix}",
            params=params,
            name=f"{invoice_name} [confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

        with self.client.post(
            f"{base}{self.purchase_invoice_post_suffix}",
            params=params,
            name=f"{invoice_name} [post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("purchase-write", "purchase-note-write", "lifecycle", "write")
    @task(1)
    def purchase_note_lifecycle_optional(self) -> None:
        if not self.enable_lifecycle:
            return

        line_mode = random.choice(["goods", "service"])
        note_mode = random.choice(["credit", "debit"])
        created = self._create_purchase_draft_from_seed(
            line_mode=line_mode,
            request_name=(
                "purchase/service-invoices [draft create]"
                if line_mode == "service"
                else "purchase/invoices [draft create]"
            ),
        )
        if not created:
            return
        invoice_id, _ = created

        base_path = self.purchase_service_invoice_path if line_mode == "service" else self.purchase_invoice_path
        invoice_name = "purchase/service-invoices" if line_mode == "service" else "purchase/invoices"
        create_suffix = (
            self.purchase_invoice_create_credit_note_suffix
            if note_mode == "credit"
            else self.purchase_invoice_create_debit_note_suffix
        )
        params = self._entity_scope_params()
        note_reason = random.choice(self.purchase_note_reasons)
        note_id: int | None = None
        invoice_base = f"{base_path}{invoice_id}"

        with self.client.post(
            f"{invoice_base}{self.purchase_invoice_confirm_suffix}",
            params=params,
            name=f"{invoice_name} [confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{invoice_base}{self.purchase_invoice_post_suffix}",
            params=params,
            name=f"{invoice_name} [post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{base_path}{invoice_id}{create_suffix}",
            params=params,
            json={
                "note_reason": note_reason,
                "reason": f"Locust {note_mode} note lifecycle perf test",
            },
            name=f"{invoice_name} [{note_mode}-note create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                retry_with_duplicate_override = False
                try:
                    retry_with_duplicate_override = (
                        response.status_code == 400 and self._is_duplicate_note_guard(response.json())
                    )
                except Exception:
                    retry_with_duplicate_override = False
                if not retry_with_duplicate_override:
                    response.failure(f"{response.status_code}: {response.text[:2000]}")
                    return
                response.success()
            else:
                try:
                    note_id = self._extract_response_header_id(response.json())
                except Exception:
                    note_id = None
                if not note_id:
                    response.failure("No purchase note id found in create response")
                    return
                response.success()

        if not note_id:
            with self.client.post(
                f"{base_path}{invoice_id}{create_suffix}",
                params=params,
                json={
                    "note_reason": note_reason,
                    "reason": f"Locust {note_mode} note lifecycle perf test",
                    "allow_duplicate": True,
                },
                name=f"{invoice_name} [{note_mode}-note create override]",
                catch_response=True,
            ) as response:
                if response.status_code >= 400:
                    response.failure(f"{response.status_code}: {response.text[:2000]}")
                    return
                try:
                    note_id = self._extract_response_header_id(response.json())
                except Exception:
                    note_id = None
                if not note_id:
                    response.failure("No purchase note id found in duplicate override create response")
                    return
                response.success()

        note_base = f"{base_path}{note_id}"

        with self.client.post(
            f"{note_base}{self.purchase_invoice_confirm_suffix}",
            params=params,
            name=f"{invoice_name} [{note_mode}-note confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

        with self.client.post(
            f"{note_base}{self.purchase_invoice_post_suffix}",
            params=params,
            name=f"{invoice_name} [{note_mode}-note post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("purchase-write", "purchase-draft-write", "write", "report-write-mix")
    @task(1)
    def purchase_draft_create_save_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        line_mode = random.choice(["goods", "service"])
        invoice_name = "purchase/service-invoices" if line_mode == "service" else "purchase/invoices"
        created = self._create_purchase_draft_from_seed(
            line_mode=line_mode,
            request_name=f"{invoice_name} [draft create]",
        )
        if not created:
            return
        created_id, created_body = created

        created_lines = created_body.get("lines") if isinstance(created_body, dict) else None
        if not isinstance(created_lines, list) or not created_lines:
            return

        first_line = dict(created_lines[0])
        first_line["line_no"] = first_line.get("line_no") or 1
        current_product_desc = str(first_line.get("product_desc") or "Locust purchase").strip() or "Locust purchase"
        # Stay comfortably below the serializer ceiling so seed data with unusual spacing
        # or downstream normalization does not create false stress failures.
        trimmed_product_desc = current_product_desc[:460].rstrip()
        first_line["product_desc"] = f"{trimmed_product_desc} save"[:480]

        patch_payload = {
            "supplier_invoice_number": self._unique_supplier_invoice_number(
                "LOCUST-PSAVE-SVC" if line_mode == "service" else "LOCUST-PSAVE"
            ),
            "lines": [self._sanitize_purchase_line_for_create(first_line, line_no=int(first_line["line_no"]))],
        }
        patch_payload["lines"][0]["id"] = first_line.get("id")

        with self.client.patch(
            self._build_purchase_detail_path(created_id, line_mode=line_mode),
            params=self._entity_scope_params(),
            json=patch_payload,
            name=f"{invoice_name} [draft save]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("sales-write", "sales-draft-write", "write", "report-write-mix", "sales-mixed")
    @task(1)
    def sales_draft_create_save_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        line_mode = random.choice(["goods", "service"])
        list_path = self.sales_service_invoice_path if line_mode == "service" else self.sales_invoice_path
        invoice_name = "sales/service-invoices" if line_mode == "service" else "sales/invoices"
        seed_detail = self._fetch_sales_detail_payload(line_mode=line_mode)
        if not seed_detail:
            return
        create_payload = self._build_sales_draft_payload_from_detail(seed_detail, line_mode=line_mode)
        if not create_payload:
            return

        created_body: Dict[str, Any] | None = None
        created_id: int | None = None
        with self.client.post(
            list_path,
            json=create_payload,
            name=f"{invoice_name} [draft create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
            except Exception:
                response.failure("Sales draft create returned invalid JSON")
                return
            try:
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Sales draft create did not return an id")
                return
            response.success()

        created_lines = created_body.get("lines") if isinstance(created_body, dict) else None
        if not isinstance(created_lines, list) or not created_lines:
            return

        first_line = dict(created_lines[0])
        first_line["line_no"] = first_line.get("line_no") or 1
        current_product_desc = str(first_line.get("productDesc") or "Locust sales").strip()
        if not current_product_desc:
            current_product_desc = "Locust sales"
        trimmed_product_desc = current_product_desc[:195].rstrip()
        first_line["productDesc"] = f"{trimmed_product_desc} save"[:200]

        patch_payload = {
            "reference": self._unique_supplier_invoice_number(
                "LOCUST-SSAVE-SVC" if line_mode == "service" else "LOCUST-SSAVE"
            ),
            "remarks": f"Locust sales {line_mode} draft save mutation",
            "lines": [self._sanitize_sales_line_for_create(first_line, line_no=int(first_line["line_no"]))],
        }
        patch_payload["lines"][0]["id"] = first_line.get("id")

        with self.client.patch(
            self._build_sales_detail_path(created_id, line_mode=line_mode),
            params=self._entity_scope_params(),
            json=patch_payload,
            name=f"{invoice_name} [draft save]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("payment-write", "write", "report-write-mix", "voucher-mixed")
    @task(1)
    def payment_voucher_lifecycle_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_payment_meta()
        if not meta:
            return
        create_payload = self._build_payment_voucher_payload(meta)
        if not create_payload:
            return

        created_body: Dict[str, Any] | None = None
        created_id: int | None = None
        with self.client.post(
            self.payment_voucher_path,
            json=create_payload,
            name="payments/payment-vouchers [draft create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
            except Exception:
                response.failure("Payment voucher create returned invalid JSON")
                return
            try:
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Payment voucher create did not return an id")
                return
            response.success()

        patch_payload = {
            "reference_number": self._unique_supplier_invoice_number("LOCUST-PAY-SAVE"),
            "narration": "Locust payment voucher save mutation",
        }
        detail_path = f"{self.payment_voucher_path}{created_id}/"
        detail_base = detail_path.rstrip("/")
        params = self._entity_scope_params()

        with self.client.patch(
            detail_path,
            params=params,
            json=patch_payload,
            name="payments/payment-vouchers [draft save]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{detail_base}{self.payment_voucher_confirm_suffix}",
            params=params,
            name="payments/payment-vouchers [confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{detail_base}{self.payment_voucher_post_suffix}",
            params=params,
            name="payments/payment-vouchers [post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("receipt-write", "write", "report-write-mix", "voucher-mixed")
    @task(1)
    def receipt_voucher_lifecycle_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_receipt_meta()
        if not meta:
            return
        create_payload = self._build_receipt_voucher_payload(meta)
        if not create_payload:
            return

        created_body: Dict[str, Any] | None = None
        created_id: int | None = None
        with self.client.post(
            self.receipt_voucher_path,
            json=create_payload,
            name="receipts/receipt-vouchers [draft create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
            except Exception:
                response.failure("Receipt voucher create returned invalid JSON")
                return
            try:
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Receipt voucher create did not return an id")
                return
            response.success()

        patch_payload = {
            "reference_number": self._unique_supplier_invoice_number("LOCUST-REC-SAVE"),
            "narration": "Locust receipt voucher save mutation",
        }
        detail_path = f"{self.receipt_voucher_path}{created_id}/"
        detail_base = detail_path.rstrip("/")
        params = self._entity_scope_params()

        with self.client.patch(
            detail_path,
            params=params,
            json=patch_payload,
            name="receipts/receipt-vouchers [draft save]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{detail_base}{self.receipt_voucher_confirm_suffix}",
            params=params,
            name="receipts/receipt-vouchers [confirm]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            response.success()

        with self.client.post(
            f"{detail_base}{self.receipt_voucher_post_suffix}",
            params=params,
            name="receipts/receipt-vouchers [post]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
            else:
                response.success()

    @tag("payment-approval", "write", "voucher-mixed")
    @task(1)
    def payment_voucher_approval_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_payment_meta()
        if not meta:
            return
        create_payload = self._build_payment_voucher_payload(meta)
        if not create_payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.payment_voucher_path,
            json=create_payload,
            name="payments/payment-vouchers [approval draft create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_id = int(response.json().get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Payment approval seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.payment_voucher_path}{created_id}".rstrip("/")
        params = self._entity_scope_params()
        if not self._run_approval_action(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [submit]",
            params=params,
            action="submit",
            remarks="Locust submit approval path",
        ):
            return
        self._run_approval_action(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [approve]",
            params=params,
            action="approve",
            remarks="Locust approve approval path",
        )

    @tag("receipt-approval", "write", "voucher-mixed")
    @task(1)
    def receipt_voucher_approval_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_receipt_meta()
        if not meta:
            return
        create_payload = self._build_receipt_voucher_payload(meta)
        if not create_payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.receipt_voucher_path,
            json=create_payload,
            name="receipts/receipt-vouchers [approval draft create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_id = int(response.json().get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Receipt approval seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.receipt_voucher_path}{created_id}".rstrip("/")
        params = self._entity_scope_params()
        if not self._run_approval_action(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [submit]",
            params=params,
            action="submit",
            remarks="Locust submit approval path",
        ):
            return
        self._run_approval_action(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [approve]",
            params=params,
            action="approve",
            remarks="Locust approve approval path",
        )

    @tag("payment-approval-conflict", "stale-conflict", "write", "voucher-mixed")
    @task(1)
    def payment_voucher_stale_conflict_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_payment_meta()
        if not meta:
            return
        payload = self._build_payment_voucher_payload(meta)
        if not payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.payment_voucher_path,
            json=payload,
            name="payments/payment-vouchers [stale seed create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Payment stale conflict seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.payment_voucher_path}{created_id}"
        params = self._entity_scope_params()

        if not self._run_approval_action(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [stale submit]",
            params=params,
            action="submit",
            remarks="Locust stale submit baseline",
        ):
            return

        stale_submit_payload = self._run_approval_action_with_body(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [stale submit repeat]",
            params=params,
            action="submit",
            remarks="Locust stale submit repeat",
        )
        if not self._expect_approval_feedback(
            stale_submit_payload,
            expected_message="Already submitted.",
            expected_status="SUBMITTED",
        ):
            raise AssertionError("Payment stale submit did not return expected already-submitted feedback")

        if not self._run_approval_action(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [stale approve]",
            params=params,
            action="approve",
            remarks="Locust stale approve baseline",
        ):
            return

        stale_approve_payload = self._run_approval_action_with_body(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [stale approve repeat]",
            params=params,
            action="approve",
            remarks="Locust stale approve repeat",
        )
        if not self._expect_approval_feedback(
            stale_approve_payload,
            expected_message="Already approved.",
            expected_status="APPROVED",
        ):
            raise AssertionError("Payment stale approve did not return expected already-approved feedback")

    @tag("payment-approval-conflict", "stale-conflict", "write", "voucher-mixed")
    @task(1)
    def payment_voucher_reject_conflict_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_payment_meta()
        if not meta:
            return
        payload = self._build_payment_voucher_payload(meta)
        if not payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.payment_voucher_path,
            json=payload,
            name="payments/payment-vouchers [reject seed create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Payment reject conflict seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.payment_voucher_path}{created_id}"
        params = self._entity_scope_params()
        if not self._run_approval_action(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [reject]",
            params=params,
            action="reject",
            remarks="Locust reject baseline",
        ):
            return

        stale_reject_payload = self._run_approval_action_with_body(
            detail_base,
            self.payment_voucher_approval_suffix,
            name="payments/payment-vouchers [reject repeat]",
            params=params,
            action="reject",
            remarks="Locust reject repeat",
        )
        if not self._expect_approval_feedback(
            stale_reject_payload,
            expected_message="Already rejected.",
            expected_status="REJECTED",
        ):
            raise AssertionError("Payment stale reject did not return expected already-rejected feedback")

    @tag("receipt-approval-conflict", "stale-conflict", "write", "voucher-mixed")
    @task(1)
    def receipt_voucher_stale_conflict_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_receipt_meta()
        if not meta:
            return
        payload = self._build_receipt_voucher_payload(meta)
        if not payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.receipt_voucher_path,
            json=payload,
            name="receipts/receipt-vouchers [stale seed create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Receipt stale conflict seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.receipt_voucher_path}{created_id}"
        params = self._entity_scope_params()

        if not self._run_approval_action(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [stale submit]",
            params=params,
            action="submit",
            remarks="Locust stale submit baseline",
        ):
            return

        stale_submit_payload = self._run_approval_action_with_body(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [stale submit repeat]",
            params=params,
            action="submit",
            remarks="Locust stale submit repeat",
        )
        if not self._expect_approval_feedback(
            stale_submit_payload,
            expected_message="Already submitted.",
            expected_status="SUBMITTED",
        ):
            raise AssertionError("Receipt stale submit did not return expected already-submitted feedback")

        if not self._run_approval_action(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [stale approve]",
            params=params,
            action="approve",
            remarks="Locust stale approve baseline",
        ):
            return

        stale_approve_payload = self._run_approval_action_with_body(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [stale approve repeat]",
            params=params,
            action="approve",
            remarks="Locust stale approve repeat",
        )
        if not self._expect_approval_feedback(
            stale_approve_payload,
            expected_message="Already approved.",
            expected_status="APPROVED",
        ):
            raise AssertionError("Receipt stale approve did not return expected already-approved feedback")

    @tag("receipt-approval-conflict", "stale-conflict", "write", "voucher-mixed")
    @task(1)
    def receipt_voucher_reject_conflict_optional(self) -> None:
        if not (self.enable_writes or self.enable_lifecycle):
            return

        meta = self._fetch_receipt_meta()
        if not meta:
            return
        payload = self._build_receipt_voucher_payload(meta)
        if not payload:
            return

        created_id: int | None = None
        with self.client.post(
            self.receipt_voucher_path,
            json=payload,
            name="receipts/receipt-vouchers [reject seed create]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:2000]}")
                return
            try:
                created_body = response.json()
                created_id = int(created_body.get("id"))
            except Exception:
                created_id = None
            if not created_id:
                response.failure("Receipt reject conflict seed create did not return an id")
                return
            response.success()

        detail_base = f"{self.receipt_voucher_path}{created_id}"
        params = self._entity_scope_params()
        if not self._run_approval_action(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [reject]",
            params=params,
            action="reject",
            remarks="Locust reject baseline",
        ):
            return

        stale_reject_payload = self._run_approval_action_with_body(
            detail_base,
            self.receipt_voucher_approval_suffix,
            name="receipts/receipt-vouchers [reject repeat]",
            params=params,
            action="reject",
            remarks="Locust reject repeat",
        )
        if not self._expect_approval_feedback(
            stale_reject_payload,
            expected_message="Already rejected.",
            expected_status="REJECTED",
        ):
            raise AssertionError("Receipt stale reject did not return expected already-rejected feedback")
