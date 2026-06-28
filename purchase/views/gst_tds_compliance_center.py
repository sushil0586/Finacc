from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.utils import timezone
from rest_framework.response import Response

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.profile_access import account_gstno
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.models.purchase_statutory import (
    PurchaseStatutoryChallan,
    PurchaseStatutoryChallanLine,
    PurchaseStatutoryReturn,
)
from purchase.services.purchase_statutory_service import PurchaseStatutoryService
from purchase.views.purchase_statutory import _require_any_permission
from purchase.views.tds_compliance_center import (
    PurchaseTdsComplianceCenterAPIView,
    PurchaseTdsComplianceCenterExportAPIView,
    ZERO2,
)


class PurchaseGstTdsComplianceCenterAPIView(PurchaseTdsComplianceCenterAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        _require_any_permission(
            request,
            entity_id,
            [
                "reports.financial_hub.gst_tds_compliance_center.view",
                "reports.gst.view",
                "purchase.statutory.view",
                "purchase.statutory.manage",
                "purchase.statutory.approve",
                "reports.financial_hub.tds_compliance_center.view",
            ],
        )

        financial_year = EntityFinancialYear.objects.filter(
            pk=entityfinid_id,
            entity_id=entity_id,
        ).only("id", "desc", "finstartyear", "finendyear").first()
        if financial_year is None:
            return Response({"detail": "Financial year not found for the selected entity."}, status=404)

        period_from, period_to, quarter_code = self._resolve_period(
            request=request,
            financial_year=financial_year,
        )

        entity = Entity.objects.filter(pk=entity_id).only("entityname").first()
        subentity = (
            SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).only("id", "subentityname").first()
            if subentity_id is not None
            else None
        )

        posted_headers_qs = (
            PurchaseInvoiceHeader.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                status=PurchaseInvoiceHeader.Status.POSTED,
                bill_date__gte=period_from,
                bill_date__lte=period_to,
                gst_tds_amount__gt=ZERO2,
            )
            .select_related("vendor", "subentity", "created_by")
            .order_by("-bill_date", "-id")
        )
        if subentity_id is not None:
            posted_headers_qs = posted_headers_qs.filter(subentity_id=subentity_id)
        headers = list(posted_headers_qs)

        challans_qs = (
            PurchaseStatutoryChallan.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
                challan_date__gte=period_from,
                challan_date__lte=period_to,
            )
            .prefetch_related("lines__header", "lines__section")
            .order_by("-challan_date", "-id")
        )
        if subentity_id is not None:
            challans_qs = challans_qs.filter(subentity_id=subentity_id)
        challans = list(challans_qs)

        returns_qs = (
            PurchaseStatutoryReturn.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                tax_type=PurchaseStatutoryReturn.TaxType.GST_TDS,
                period_to__gte=period_from,
                period_from__lte=period_to,
            )
            .prefetch_related("lines__header", "lines__challan")
            .order_by("-period_to", "-id")
        )
        if subentity_id is not None:
            returns_qs = returns_qs.filter(subentity_id=subentity_id)
        returns = list(returns_qs)

        challan_lines_all = list(
            PurchaseStatutoryChallanLine.objects.filter(
                challan__entity_id=entity_id,
                challan__entityfinid_id=entityfinid_id,
                challan__tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
            )
            .exclude(challan__status=PurchaseStatutoryChallan.Status.CANCELLED)
            .select_related("challan", "header", "section")
            .order_by("-challan__challan_date", "-id")
        )
        if subentity_id is not None:
            challan_lines_all = [line for line in challan_lines_all if line.challan.subentity_id == subentity_id]

        summary = PurchaseStatutoryService.reconciliation_summary(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
            date_from=period_from,
            date_to=period_to,
        )

        header_mapping = self._build_header_mapping(challan_lines_all)
        header_rows = self._build_deduction_rows(headers, header_mapping)
        section_rows = self._build_section_summary_rows(
            headers=headers,
            challan_lines=challan_lines_all,
            period_from=period_from,
        )
        deductee_rows = self._build_deductee_summary_rows(headers=headers, header_mapping=header_mapping)
        monthly_rows = self._build_monthly_summary_rows(
            headers=headers,
            challan_lines=challan_lines_all,
            returns=returns,
        )
        challan_rows = self._build_payment_register_rows(challans)
        challan_mapping_rows = self._build_challan_mapping_rows(headers, header_mapping)
        pending_rows = self._build_pending_payment_rows(headers, header_mapping)
        vendor_rows = self._build_vendor_compliance_rows(headers, header_mapping)
        filing_rows = self._build_return_rows(returns)
        audit_rows = self._build_audit_rows(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            period_from=period_from,
            period_to=period_to,
            challans=challans,
            returns=returns,
        )

        warnings = self._build_warning_chips(
            vendor_rows=vendor_rows,
            challan_mapping_rows=challan_mapping_rows,
            pending_rows=pending_rows,
            filing_rows=filing_rows["gstr7"],
        )

        payload = {
            "pageTitle": "GST-TDS Compliance Center",
            "meta": {
                "entityId": entity_id,
                "entityLabel": getattr(entity, "entityname", None) or f"Entity {entity_id}",
                "branchLabel": getattr(subentity, "subentityname", None) or "All subentities",
                "financialYears": self._normalize_financial_years(self._financial_years(entity_id)),
                "subentities": self._subentities(entity_id),
                "quarters": self._quarter_options(),
                "voucherTypes": [
                    {"value": "purchase_invoice", "label": "Purchase Invoice"},
                    {"value": "purchase_credit_note", "label": "Purchase Credit Note"},
                    {"value": "purchase_debit_note", "label": "Purchase Debit Note"},
                ],
                "paymentStatuses": [
                    {"value": "pending", "label": "Pending"},
                    {"value": "paid", "label": "Paid"},
                    {"value": "overdue", "label": "Overdue"},
                    {"value": "partially_mapped", "label": "Partially Mapped"},
                ],
                "challanStatuses": [
                    {"value": "unmapped", "label": "Unmapped"},
                    {"value": "partially_mapped", "label": "Partially Mapped"},
                    {"value": "mapped", "label": "Mapped"},
                    {"value": "deposited", "label": "Deposited"},
                ],
                "returnStatuses": [
                    {"value": "draft", "label": "Draft"},
                    {"value": "approval_submitted", "label": "Approval Submitted"},
                    {"value": "approved_draft", "label": "Approved Draft"},
                    {"value": "rejected_draft", "label": "Rejected Draft"},
                    {"value": "filed", "label": "Filed"},
                    {"value": "revised", "label": "Revised"},
                    {"value": "validated", "label": "Validated"},
                ],
                "tdsSections": [],
            },
            "tabs": self._tabs(),
            "returnTabs": self._return_tabs(),
            "headerChips": [
                {"label": getattr(entity, "entityname", None) or f"Entity {entity_id}"},
                {"label": self._financial_year_label(financial_year)},
                {"label": self._quarter_label(quarter_code)},
                {"label": getattr(subentity, "subentityname", None) or "All subentities"},
                {"label": f"{self._display_date(period_from)} to {self._display_date(period_to)}", "tone": "info"},
            ],
            "kpis": self._build_kpis(summary, vendor_rows, filing_rows, challan_mapping_rows),
            "warnings": warnings,
            "dashboard": self._build_dashboard(monthly_rows, section_rows, deductee_rows, pending_rows, audit_rows),
            "filters": {
                "financialYearId": entityfinid_id,
                "quarter": quarter_code,
                "fromDate": period_from.isoformat(),
                "toDate": period_to.isoformat(),
                "vendorId": None,
                "vendorLabel": "",
                "pan": "",
                "tdsSectionId": None,
                "expenseLedgerLabel": "",
                "voucherType": "",
                "paymentStatus": "",
                "challanStatus": "",
                "returnStatus": "",
                "minAmount": None,
                "maxAmount": None,
                "branchId": subentity_id,
                "entityId": entity_id,
                "searchText": request.query_params.get("search") or "",
            },
            "datasets": {
                "dashboard": self._dataset(
                    columns=[
                        {"key": "month", "label": "Month", "type": "text"},
                        {"key": "tdsDeducted", "label": "GST-TDS Deducted", "type": "currency", "align": "right"},
                        {"key": "deposited", "label": "Deposited", "type": "currency", "align": "right"},
                        {"key": "pending", "label": "Pending Liability", "type": "currency", "align": "right"},
                        {"key": "returnStatus", "label": "Status", "type": "status"},
                    ],
                    rows=monthly_rows,
                    totals={
                        "primaryLabel": "Period Deducted",
                        "primaryValue": self._money(summary["deducted"]),
                        "secondaryLabel": "Pending Deposit",
                        "secondaryValue": self._money(summary["pending_deposit"]),
                    },
                ),
                "deduction-register": self._dataset(
                    columns=[
                        {"key": "date", "label": "Date", "type": "date"},
                        {"key": "voucherNo", "label": "Voucher No", "type": "text"},
                        {"key": "voucherType", "label": "Voucher Type", "type": "text"},
                        {"key": "deductee", "label": "Vendor", "type": "text"},
                        {"key": "pan", "label": "GSTIN", "type": "text"},
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "taxableAmount", "label": "Taxable Amount", "type": "currency", "align": "right"},
                        {"key": "tdsAmount", "label": "GST-TDS Amount", "type": "currency", "align": "right"},
                        {"key": "status", "label": "Status", "type": "status"},
                        {"key": "actions", "label": "Actions", "type": "actions", "sortable": False},
                    ],
                    rows=header_rows,
                    totals={"primaryLabel": "GST-TDS Total", "primaryValue": self._money(summary["deducted"])},
                ),
                "payable-report": self._dataset(
                    columns=[
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "openingBalance", "label": "Opening Balance", "type": "currency", "align": "right"},
                        {"key": "currentDeduction", "label": "Current Deduction", "type": "currency", "align": "right"},
                        {"key": "deposited", "label": "Deposited", "type": "currency", "align": "right"},
                        {"key": "interest", "label": "Interest", "type": "currency", "align": "right"},
                        {"key": "closingBalance", "label": "Closing Balance", "type": "currency", "align": "right"},
                        {"key": "status", "label": "Status", "type": "status"},
                        {"key": "actions", "label": "Actions", "type": "actions", "sortable": False},
                    ],
                    rows=section_rows,
                    totals={
                        "primaryLabel": "Closing Balance",
                        "primaryValue": self._money(sum((self._decimal(row.get("closingBalance")) for row in section_rows), ZERO2)),
                        "secondaryLabel": "Interest",
                        "secondaryValue": self._money(sum((self._decimal(row.get("interest")) for row in section_rows), ZERO2)),
                    },
                ),
                "payment-register": self._dataset(
                    columns=[
                        {"key": "challanNo", "label": "Challan No", "type": "text"},
                        {"key": "cin", "label": "CIN", "type": "text"},
                        {"key": "bank", "label": "Bank", "type": "text"},
                        {"key": "depositDate", "label": "Deposit Date", "type": "date"},
                        {"key": "amount", "label": "Amount", "type": "currency", "align": "right"},
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "status", "label": "Status", "type": "status"},
                        {"key": "actions", "label": "Actions", "type": "actions", "sortable": False},
                    ],
                    rows=challan_rows,
                ),
                "challan-mapping": self._dataset(
                    columns=[
                        {"key": "voucherNo", "label": "Voucher No", "type": "text"},
                        {"key": "deductee", "label": "Vendor", "type": "text"},
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "tdsAmount", "label": "GST-TDS Amount", "type": "currency", "align": "right"},
                        {"key": "mappedChallan", "label": "Mapped Challan", "type": "text"},
                        {"key": "remainingAmount", "label": "Remaining Amount", "type": "currency", "align": "right"},
                        {"key": "mappingStatus", "label": "Mapping Status", "type": "status"},
                        {"key": "actions", "label": "Actions", "type": "actions", "sortable": False},
                    ],
                    rows=challan_mapping_rows,
                ),
                "section-wise-summary": self._dataset(
                    columns=[
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "nature", "label": "Classification", "type": "text"},
                        {"key": "transactions", "label": "Transactions", "type": "number", "align": "right"},
                        {"key": "taxableAmount", "label": "Taxable Amount", "type": "currency", "align": "right"},
                        {"key": "tdsAmount", "label": "GST-TDS Amount", "type": "currency", "align": "right"},
                        {"key": "pendingAmount", "label": "Pending Amount", "type": "currency", "align": "right"},
                    ],
                    rows=section_rows,
                ),
                "deductee-wise-summary": self._dataset(
                    columns=[
                        {"key": "deductee", "label": "Vendor", "type": "text"},
                        {"key": "pan", "label": "GSTIN", "type": "text"},
                        {"key": "transactions", "label": "Transactions", "type": "number", "align": "right"},
                        {"key": "taxableAmount", "label": "Taxable Amount", "type": "currency", "align": "right"},
                        {"key": "tdsAmount", "label": "GST-TDS Amount", "type": "currency", "align": "right"},
                        {"key": "pending", "label": "Pending", "type": "currency", "align": "right"},
                        {"key": "complianceStatus", "label": "Compliance", "type": "status"},
                    ],
                    rows=deductee_rows,
                ),
                "monthly-summary": self._dataset(
                    columns=[
                        {"key": "month", "label": "Month", "type": "text"},
                        {"key": "taxableAmount", "label": "Taxable Amount", "type": "currency", "align": "right"},
                        {"key": "tdsDeducted", "label": "GST-TDS Deducted", "type": "currency", "align": "right"},
                        {"key": "deposited", "label": "Deposited", "type": "currency", "align": "right"},
                        {"key": "pending", "label": "Pending", "type": "currency", "align": "right"},
                        {"key": "returnStatus", "label": "Return Status", "type": "status"},
                    ],
                    rows=monthly_rows,
                ),
                "pending-payment": self._dataset(
                    columns=[
                        {"key": "dueDate", "label": "Due Date", "type": "date"},
                        {"key": "section", "label": "Contract / Scope", "type": "text"},
                        {"key": "deductee", "label": "Vendor", "type": "text"},
                        {"key": "tdsAmount", "label": "GST-TDS Amount", "type": "currency", "align": "right"},
                        {"key": "delayDays", "label": "Delay Days", "type": "number", "align": "right"},
                        {"key": "interest", "label": "Interest", "type": "currency", "align": "right"},
                        {"key": "status", "label": "Status", "type": "status"},
                    ],
                    rows=pending_rows,
                ),
                "vendor-compliance": self._dataset(
                    columns=[
                        {"key": "deductee", "label": "Vendor", "type": "text"},
                        {"key": "pan", "label": "GSTIN", "type": "text"},
                        {"key": "panStatus", "label": "GSTIN Status", "type": "status"},
                        {"key": "defaultSection", "label": "Contract Ref", "type": "text"},
                        {"key": "certificate", "label": "GST-TDS Setup", "type": "text"},
                        {"key": "validity", "label": "Last Activity", "type": "date"},
                        {"key": "complianceStatus", "label": "Compliance", "type": "status"},
                    ],
                    rows=vendor_rows,
                ),
                "return-filing": self._dataset(
                    columns=self._return_columns("gstr7"),
                    rows=filing_rows["gstr7"],
                    return_tab="gstr7",
                ),
                "audit-trail": self._dataset(
                    columns=[
                        {"key": "dateTime", "label": "Date Time", "type": "date"},
                        {"key": "user", "label": "User", "type": "text"},
                        {"key": "action", "label": "Action", "type": "text"},
                        {"key": "voucherNo", "label": "Voucher No", "type": "text"},
                        {"key": "field", "label": "Field", "type": "text"},
                        {"key": "oldValue", "label": "Old Value", "type": "text"},
                        {"key": "newValue", "label": "New Value", "type": "text"},
                        {"key": "remarks", "label": "Remarks", "type": "text"},
                        {"key": "ipAddress", "label": "IP Address", "type": "text"},
                    ],
                    rows=audit_rows,
                ),
            },
            "returnDatasets": {
                "gstr7": self._dataset(
                    columns=self._return_columns("gstr7"),
                    rows=filing_rows["gstr7"],
                    return_tab="gstr7",
                ),
            },
        }
        return Response(payload)

    def _build_header_mapping(self, challan_lines: Iterable[PurchaseStatutoryChallanLine]) -> dict[int, dict[str, object]]:
        mapping = super()._build_header_mapping(challan_lines)
        for bucket in mapping.values():
            sections = bucket.get("sections")
            if isinstance(sections, set) and not sections:
                sections.add("GST-TDS")
        return mapping

    def _build_deduction_rows(self, headers: list[PurchaseInvoiceHeader], mapping: dict[int, dict[str, object]]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for header in headers:
            row_mapping = mapping.get(int(header.id), {})
            gst_tds_amount = self._decimal(getattr(header, "gst_tds_amount", ZERO2))
            deposited = self._decimal(row_mapping.get("deposited"))
            gstin = account_gstno(header.vendor)
            rows.append(
                {
                    "id": int(header.id),
                    "date": self._iso(header.bill_date),
                    "voucherNo": self._voucher_label(header),
                    "voucherType": self._voucher_type_label(header.doc_type),
                    "deductee": header.vendor_name or getattr(header.vendor, "accountname", "") or "-",
                    "pan": gstin or "-",
                    "section": self._gst_scope_label(header),
                    "taxableAmount": self._money(getattr(header, "gst_tds_base_amount", ZERO2)),
                    "tdsAmount": self._money(gst_tds_amount),
                    "status": self._header_status_badge(tds_amount=gst_tds_amount, deposited_amount=deposited, pan=gstin),
                    "actions": self._actions("Voucher", "Vendor"),
                }
            )
        return rows

    def _build_section_summary_rows(
        self,
        *,
        headers: list[PurchaseInvoiceHeader],
        challan_lines: list[PurchaseStatutoryChallanLine],
        period_from: date,
    ) -> list[dict[str, object]]:
        scope_map: dict[str, dict[str, object]] = {}

        prior_headers = (
            PurchaseInvoiceHeader.objects.filter(
                entity_id=headers[0].entity_id if headers else None,
                entityfinid_id=headers[0].entityfinid_id if headers else None,
                status=PurchaseInvoiceHeader.Status.POSTED,
                bill_date__lt=period_from,
                gst_tds_amount__gt=ZERO2,
            )
            if headers
            else PurchaseInvoiceHeader.objects.none()
        )
        if headers and headers[0].subentity_id is not None:
            prior_headers = prior_headers.filter(subentity_id=headers[0].subentity_id)
        for header in prior_headers:
            code = self._gst_scope_label(header)
            bucket = scope_map.setdefault(code, self._new_section_bucket(header))
            bucket["opening"] += self._decimal(getattr(header, "gst_tds_amount", ZERO2))

        for line in challan_lines:
            challan = line.challan
            section_code = self._gst_scope_label(line.header)
            bucket = scope_map.setdefault(section_code, self._new_section_bucket(line.header))
            amount = self._decimal(line.amount)
            if challan.challan_date < period_from and int(challan.status) == int(PurchaseStatutoryChallan.Status.DEPOSITED):
                bucket["opening"] -= amount
            elif challan.challan_date >= period_from and int(challan.status) == int(PurchaseStatutoryChallan.Status.DEPOSITED):
                bucket["deposited"] += amount
                bucket["interest"] += self._section_share(
                    amount=amount,
                    total=self._decimal(challan.amount),
                    distributed=self._decimal(challan.interest_amount),
                )

        for header in headers:
            section_code = self._gst_scope_label(header)
            bucket = scope_map.setdefault(section_code, self._new_section_bucket(header))
            bucket["transactions"] += 1
            bucket["taxable"] += self._decimal(getattr(header, "gst_tds_base_amount", ZERO2))
            bucket["current"] += self._decimal(getattr(header, "gst_tds_amount", ZERO2))

        rows: list[dict[str, object]] = []
        for section_code, bucket in sorted(scope_map.items(), key=lambda item: item[0]):
            closing = bucket["opening"] + bucket["current"] - bucket["deposited"]
            rows.append(
                {
                    "id": section_code.lower().replace("/", "-").replace(" ", "-"),
                    "section": section_code,
                    "nature": bucket["nature"] or "GST-TDS Scope",
                    "transactions": int(bucket["transactions"]),
                    "taxableAmount": self._money(bucket["taxable"]),
                    "tdsAmount": self._money(bucket["current"]),
                    "pendingAmount": self._money(max(closing, ZERO2)),
                    "openingBalance": self._money(bucket["opening"]),
                    "currentDeduction": self._money(bucket["current"]),
                    "deposited": self._money(bucket["deposited"]),
                    "interest": self._money(bucket["interest"]),
                    "closingBalance": self._money(closing),
                    "status": self._balance_status(closing, bucket["interest"]),
                    "actions": self._actions("Scope View", "Monthly Drilldown"),
                }
            )
        return rows

    def _build_deductee_summary_rows(
        self,
        *,
        headers: list[PurchaseInvoiceHeader],
        header_mapping: dict[int, dict[str, object]],
    ) -> list[dict[str, object]]:
        buckets: dict[str, dict[str, object]] = {}
        for header in headers:
            vendor_key = header.vendor_name or getattr(header.vendor, "accountname", "") or f"Vendor {header.vendor_id or header.id}"
            bucket = buckets.setdefault(
                vendor_key,
                {
                    "deductee": vendor_key,
                    "pan": account_gstno(header.vendor) or "-",
                    "transactions": 0,
                    "taxableAmount": ZERO2,
                    "tdsAmount": ZERO2,
                    "pending": ZERO2,
                    "missing_pan": False,
                },
            )
            bucket["transactions"] += 1
            bucket["taxableAmount"] += self._decimal(getattr(header, "gst_tds_base_amount", ZERO2))
            bucket["tdsAmount"] += self._decimal(getattr(header, "gst_tds_amount", ZERO2))
            row_mapping = header_mapping.get(int(header.id), {})
            pending = max(self._decimal(getattr(header, "gst_tds_amount", ZERO2)) - self._decimal(row_mapping.get("deposited")), ZERO2)
            bucket["pending"] += pending
            bucket["missing_pan"] = bucket["missing_pan"] or not bool((account_gstno(header.vendor) or "").strip())

        rows: list[dict[str, object]] = []
        for index, bucket in enumerate(sorted(buckets.values(), key=lambda item: (-item["tdsAmount"], item["deductee"])), start=1):
            compliance = (
                self._badge("Missing GSTIN", "danger")
                if bucket["missing_pan"]
                else self._badge("Pending Deposit", "warning")
                if bucket["pending"] > ZERO2
                else self._badge("Compliant", "success")
            )
            rows.append(
                {
                    "id": index,
                    "deductee": bucket["deductee"],
                    "pan": bucket["pan"],
                    "transactions": int(bucket["transactions"]),
                    "taxableAmount": self._money(bucket["taxableAmount"]),
                    "tdsAmount": self._money(bucket["tdsAmount"]),
                    "pending": self._money(bucket["pending"]),
                    "complianceStatus": compliance,
                }
            )
        return rows

    def _build_monthly_summary_rows(
        self,
        *,
        headers: list[PurchaseInvoiceHeader],
        challan_lines: list[PurchaseStatutoryChallanLine],
        returns: list[PurchaseStatutoryReturn],
    ) -> list[dict[str, object]]:
        buckets: dict[str, dict[str, object]] = {}
        for header in headers:
            month_key = header.bill_date.strftime("%Y-%m")
            bucket = buckets.setdefault(
                month_key,
                {"label": header.bill_date.strftime("%b %Y"), "taxable": ZERO2, "deducted": ZERO2, "deposited": ZERO2, "returnStatus": self._badge("Draft", "warning")},
            )
            bucket["taxable"] += self._decimal(getattr(header, "gst_tds_base_amount", ZERO2))
            bucket["deducted"] += self._decimal(getattr(header, "gst_tds_amount", ZERO2))

        for line in challan_lines:
            if int(line.challan.status) != int(PurchaseStatutoryChallan.Status.DEPOSITED):
                continue
            month_key = line.challan.challan_date.strftime("%Y-%m")
            bucket = buckets.setdefault(
                month_key,
                {"label": line.challan.challan_date.strftime("%b %Y"), "taxable": ZERO2, "deducted": ZERO2, "deposited": ZERO2, "returnStatus": self._badge("Draft", "warning")},
            )
            bucket["deposited"] += self._decimal(line.amount)

        for filing in returns:
            filing_month = filing.period_to.strftime("%Y-%m")
            bucket = buckets.setdefault(
                filing_month,
                {"label": filing.period_to.strftime("%b %Y"), "taxable": ZERO2, "deducted": ZERO2, "deposited": ZERO2, "returnStatus": self._badge("Draft", "warning")},
            )
            bucket["returnStatus"] = self._return_status_badge(filing)

        rows: list[dict[str, object]] = []
        for month_key in sorted(buckets.keys()):
            bucket = buckets[month_key]
            pending = max(bucket["deducted"] - bucket["deposited"], ZERO2)
            rows.append(
                {
                    "id": month_key,
                    "month": bucket["label"],
                    "taxableAmount": self._money(bucket["taxable"]),
                    "tdsDeducted": self._money(bucket["deducted"]),
                    "deposited": self._money(bucket["deposited"]),
                    "pending": self._money(pending),
                    "returnStatus": bucket["returnStatus"],
                }
            )
        return rows

    def _build_payment_register_rows(self, challans: list[PurchaseStatutoryChallan]) -> list[dict[str, object]]:
        rows = super()._build_payment_register_rows(challans)
        for row in rows:
            if row.get("section") in ("", "-", "UNSPECIFIED"):
                row["section"] = "GST-TDS"
        return rows

    def _build_challan_mapping_rows(
        self,
        headers: list[PurchaseInvoiceHeader],
        header_mapping: dict[int, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for header in headers:
            row_mapping = header_mapping.get(int(header.id), {})
            gst_tds_amount = self._decimal(getattr(header, "gst_tds_amount", ZERO2))
            mapped = self._decimal(row_mapping.get("mapped"))
            remaining = max(gst_tds_amount - mapped, ZERO2)
            mapped_challan = ", ".join(sorted(row_mapping.get("challan_nos", set()))) or "-"
            rows.append(
                {
                    "id": int(header.id),
                    "voucherNo": self._voucher_label(header),
                    "deductee": header.vendor_name or getattr(header.vendor, "accountname", "") or "-",
                    "section": self._gst_scope_label(header),
                    "tdsAmount": self._money(gst_tds_amount),
                    "mappedChallan": mapped_challan,
                    "remainingAmount": self._money(remaining),
                    "mappingStatus": (
                        self._badge("Mapped", "success")
                        if remaining <= ZERO2
                        else self._badge("Partially Mapped", "warning")
                        if mapped > ZERO2
                        else self._badge("Unmapped", "danger")
                    ),
                    "actions": self._actions("Voucher", "Mapping Detail"),
                }
            )
        return rows

    def _build_pending_payment_rows(
        self,
        headers: list[PurchaseInvoiceHeader],
        header_mapping: dict[int, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        today = timezone.localdate()
        for header in headers:
            row_mapping = header_mapping.get(int(header.id), {})
            remaining = max(self._decimal(getattr(header, "gst_tds_amount", ZERO2)) - self._decimal(row_mapping.get("deposited")), ZERO2)
            if remaining <= ZERO2:
                continue
            due_date = self._deposit_due_date(header.bill_date)
            delay_days = max((today - due_date).days, 0)
            rows.append(
                {
                    "id": int(header.id),
                    "dueDate": self._iso(due_date),
                    "section": self._gst_scope_label(header),
                    "deductee": header.vendor_name or getattr(header.vendor, "accountname", "") or "-",
                    "tdsAmount": self._money(remaining),
                    "delayDays": delay_days,
                    "interest": self._money(self._interest_estimate(remaining, delay_days)),
                    "status": self._badge("Overdue", "danger") if delay_days > 0 else self._badge("Pending", "warning"),
                }
            )
        rows.sort(key=lambda row: (row["dueDate"], row["section"], row["deductee"]))
        return rows

    def _build_vendor_compliance_rows(
        self,
        headers: list[PurchaseInvoiceHeader],
        header_mapping: dict[int, dict[str, object]],
    ) -> list[dict[str, object]]:
        buckets: dict[str, dict[str, object]] = {}
        for header in headers:
            key = header.vendor_name or getattr(header.vendor, "accountname", "") or f"Vendor {header.vendor_id or header.id}"
            bucket = buckets.setdefault(
                key,
                {
                    "id": key,
                    "deductee": key,
                    "pan": account_gstno(header.vendor) or "-",
                    "defaultSection": (getattr(header, "gst_tds_contract_ref", None) or "").strip() or "GST-TDS",
                    "certificate": "Configured" if bool(getattr(header, "gst_tds_enabled", False)) else "Review setup",
                    "validity": self._iso(header.bill_date),
                    "pending": ZERO2,
                },
            )
            row_mapping = header_mapping.get(int(header.id), {})
            bucket["pending"] += max(
                self._decimal(getattr(header, "gst_tds_amount", ZERO2)) - self._decimal(row_mapping.get("deposited")),
                ZERO2,
            )

        rows: list[dict[str, object]] = []
        for bucket in sorted(buckets.values(), key=lambda item: item["deductee"]):
            has_gstin = bool((bucket["pan"] or "").strip() and bucket["pan"] != "-")
            rows.append(
                {
                    "id": bucket["id"],
                    "deductee": bucket["deductee"],
                    "pan": bucket["pan"],
                    "panStatus": self._badge("Valid", "success") if has_gstin else self._badge("Missing GSTIN", "danger"),
                    "defaultSection": bucket["defaultSection"],
                    "certificate": bucket["certificate"],
                    "validity": bucket["validity"],
                    "complianceStatus": (
                        self._badge("Review Required", "danger")
                        if not has_gstin
                        else self._badge("Pending Deposit", "warning")
                        if bucket["pending"] > ZERO2
                        else self._badge("Compliant", "success")
                    ),
                }
            )
        return rows

    def _build_return_rows(self, returns: list[PurchaseStatutoryReturn]) -> dict[str, list[dict[str, object]]]:
        rows = {"gstr7": []}
        for filing in returns:
            code = (filing.return_code or "").strip().upper()
            if code != "GSTR7":
                continue
            line_items = list(filing.lines.all())
            deductee_count = len({(line.header_id or idx) for idx, line in enumerate(line_items, start=1)})
            total_taxable = sum((self._decimal(getattr(line.header, "gst_tds_base_amount", ZERO2)) for line in line_items), ZERO2)
            row = {
                "id": int(filing.id),
                "quarter": self._quarter_for_date(filing.period_from, filing.period_from, filing.period_to),
                "returnType": "GSTR-7 Return",
                "transactions": len(line_items),
                "deductees": deductee_count,
                "totalTaxableAmount": self._money(total_taxable),
                "totalTds": self._money(filing.amount),
                "validationErrors": 0,
                "warnings": 0,
                "fvuStatus": self._badge("Validated", "success"),
                "returnStatus": self._return_status_badge(filing),
                "tokenNumber": filing.arn_no or filing.ack_no or "-",
                "filingDate": self._iso(filing.filed_on),
                "actions": self._actions(self._return_primary_action_label(filing), "Validation"),
            }
            rows["gstr7"].append(row)
        return rows

    def _build_warning_chips(
        self,
        *,
        vendor_rows: list[dict[str, object]],
        challan_mapping_rows: list[dict[str, object]],
        pending_rows: list[dict[str, object]],
        filing_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        missing_gstin = sum(1 for row in vendor_rows if self._status_label(row.get("panStatus")) == "Missing GSTIN")
        unmapped = sum(1 for row in challan_mapping_rows if self._status_label(row.get("mappingStatus")) == "Unmapped")
        overdue = sum(1 for row in pending_rows if self._status_label(row.get("status")) == "Overdue")
        pending_returns = sum(1 for row in filing_rows if self._status_label(row.get("returnStatus")) not in {"Filed", "Revised"})
        chips: list[dict[str, object]] = []
        if missing_gstin:
            chips.append({"label": f"Missing GSTIN {missing_gstin}", "tone": "danger"})
        if unmapped:
            chips.append({"label": f"Unmapped Challans {unmapped}", "tone": "warning"})
        if overdue:
            chips.append({"label": f"Pending Deposit {overdue}", "tone": "warning"})
        if pending_returns:
            chips.append({"label": f"GSTR-7 Pending {pending_returns}", "tone": "warning"})
        if not chips:
            chips.append({"label": "Real Data Synced", "tone": "success"})
        return chips

    def _build_kpis(
        self,
        summary: dict[str, str],
        vendor_rows: list[dict[str, object]],
        filing_rows: dict[str, list[dict[str, object]]],
        challan_mapping_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        missing_gstin = sum(1 for row in vendor_rows if self._status_label(row.get("panStatus")) == "Missing GSTIN")
        pending_challans = sum(1 for row in challan_mapping_rows if self._status_label(row.get("mappingStatus")) != "Mapped")
        pending_returns = sum(
            1 for row in filing_rows["gstr7"] if self._status_label(row.get("returnStatus")) not in {"Filed", "Revised"}
        )
        return [
            {"code": "total_deducted", "label": "Total GST-TDS Deducted", "value": self._money(summary["deducted"]), "tone": "info", "hint": "Selected period"},
            {"code": "total_deposited", "label": "Total GST-TDS Deposited", "value": self._money(summary["deposited"]), "tone": "success", "hint": "Deposited challans"},
            {"code": "pending_liability", "label": "Pending Liability", "value": self._money(summary["pending_deposit"]), "tone": "warning", "hint": "Deducted but not deposited"},
            {"code": "interest_payable", "label": "Interest Payable", "value": self._money(summary["deposited_interest"]), "tone": "danger", "hint": "Deposited interest in period"},
            {"code": "pending_challans", "label": "Pending Challans", "value": str(pending_challans), "tone": "warning", "hint": "Unmapped or partial"},
            {"code": "vendors_missing_pan", "label": "Vendors Missing GSTIN", "value": str(missing_gstin), "tone": "danger", "hint": "Needs master cleanup"},
            {"code": "returns_pending", "label": "Returns Pending", "value": str(pending_returns), "tone": "warning", "hint": "Draft or not filed"},
            {"code": "short_deduction_cases", "label": "Validation Cases", "value": "0", "tone": "info", "hint": "GSTR-7 review queue"},
        ]

    def _tabs(self) -> list[dict[str, str]]:
        return [
            {"id": "dashboard", "label": "Dashboard", "shortLabel": "Dashboard"},
            {"id": "deduction-register", "label": "Deduction Register", "shortLabel": "Deduction"},
            {"id": "payable-report", "label": "Payable Report", "shortLabel": "Payable"},
            {"id": "payment-register", "label": "Payment Register", "shortLabel": "Payment"},
            {"id": "challan-mapping", "label": "Challan Mapping", "shortLabel": "Mapping"},
            {"id": "section-wise-summary", "label": "Contract Wise Summary", "shortLabel": "Contracts"},
            {"id": "deductee-wise-summary", "label": "Vendor Wise Summary", "shortLabel": "Vendors"},
            {"id": "monthly-summary", "label": "Monthly Summary", "shortLabel": "Monthly"},
            {"id": "pending-payment", "label": "Pending Payment", "shortLabel": "Pending"},
            {"id": "vendor-compliance", "label": "Vendor Compliance", "shortLabel": "Compliance"},
            {"id": "return-filing", "label": "Return Filing", "shortLabel": "Returns"},
            {"id": "audit-trail", "label": "Audit Trail", "shortLabel": "Audit"},
        ]

    def _return_tabs(self) -> list[dict[str, str]]:
        return [{"id": "gstr7", "label": "GSTR-7 Return", "shortLabel": "GSTR-7"}]

    def _return_columns(self, return_tab: str) -> list[dict[str, object]]:
        return [
            {"key": "quarter", "label": "Quarter", "type": "text"},
            {"key": "returnType", "label": "Return Type", "type": "text"},
            {"key": "transactions", "label": "Transactions", "type": "number", "align": "right"},
            {"key": "deductees", "label": "Vendors", "type": "number", "align": "right"},
            {"key": "totalTaxableAmount", "label": "Total Taxable Amount", "type": "currency", "align": "right"},
            {"key": "totalTds", "label": "Total GST-TDS", "type": "currency", "align": "right"},
            {"key": "validationErrors", "label": "Validation Errors", "type": "number", "align": "right"},
            {"key": "warnings", "label": "Warnings", "type": "number", "align": "right"},
            {"key": "fvuStatus", "label": "Validation Status", "type": "status"},
            {"key": "returnStatus", "label": "Return Status", "type": "status"},
            {"key": "tokenNumber", "label": "ARN / Token", "type": "text"},
            {"key": "filingDate", "label": "Filing Date", "type": "date"},
            {"key": "actions", "label": "Actions", "type": "actions", "sortable": False},
        ]

    def _new_section_bucket(self, header: PurchaseInvoiceHeader) -> dict[str, object]:
        contract_ref = (getattr(header, "gst_tds_contract_ref", None) or "").strip()
        return {
            "nature": "Contract-linked GST-TDS" if contract_ref else "GST-TDS",
            "opening": ZERO2,
            "current": ZERO2,
            "deposited": ZERO2,
            "interest": ZERO2,
            "transactions": 0,
            "taxable": ZERO2,
        }

    def _return_type_label(self, code: str) -> str:
        return "GSTR-7 Return" if code == "GSTR7" else code

    def _header_status_badge(self, *, tds_amount: Decimal, deposited_amount: Decimal, pan: Optional[str]) -> dict[str, str]:
        if not (pan or "").strip():
            return self._badge("Missing GSTIN", "danger")
        if deposited_amount >= tds_amount > ZERO2:
            return self._badge("Paid", "success")
        if deposited_amount > ZERO2:
            return self._badge("Partially Mapped", "warning")
        return self._badge("Pending Deposit", "warning")

    def _return_primary_action_label(self, filing: PurchaseStatutoryReturn) -> str:
        if int(filing.status) == int(PurchaseStatutoryReturn.Status.CANCELLED):
            return "Audit only"
        if int(filing.status) in (int(PurchaseStatutoryReturn.Status.FILED), int(PurchaseStatutoryReturn.Status.REVISED)):
            return "Filing follow-up"
        approval_state = PurchaseStatutoryService._approval_state(getattr(filing, "filed_payload_json", None))
        approval_code = str(approval_state.get("status") or "DRAFT").upper()
        if approval_code == "SUBMITTED":
            return "Approve draft"
        if approval_code == "APPROVED":
            return "File"
        if approval_code == "REJECTED":
            return "Review rejected"
        return "Review draft"

    def _deposit_due_date(self, bill_date: date) -> date:
        if bill_date.month == 12:
            next_month = date(bill_date.year + 1, 1, 1)
        else:
            next_month = date(bill_date.year, bill_date.month + 1, 1)
        return next_month + timedelta(days=9)

    def _gst_scope_label(self, header: PurchaseInvoiceHeader) -> str:
        contract_ref = (getattr(header, "gst_tds_contract_ref", None) or "").strip()
        return contract_ref or "GST-TDS"


class PurchaseGstTdsComplianceCenterExportAPIView(PurchaseTdsComplianceCenterExportAPIView):
    def get(self, request):
        if not request.query_params.get("return_tab"):
            mutable = request.query_params.copy()
            mutable["return_tab"] = "gstr7"
            request._request.GET = mutable
            request._full_data = mutable
        return super().get(request)

    def _resolve_export_title(self, payload: dict[str, object], tab_id: str, return_tab: str) -> str:
        if tab_id == "return-filing":
            for tab in list(payload.get("returnTabs") or []):
                if str(tab.get("id") or "").lower() == return_tab:
                    return f"GST-TDS Compliance Center - {tab.get('label') or return_tab.upper()}"
        for tab in list(payload.get("tabs") or []):
            if str(tab.get("id") or "") == tab_id:
                return f"GST-TDS Compliance Center - {tab.get('label') or tab_id}"
        return "GST-TDS Compliance Center"

    def _resolve_export_filename(self, payload: dict[str, object], tab_id: str, return_tab: str) -> str:
        quarter = str(payload.get("filters", {}).get("quarter") or "scope")  # type: ignore[union-attr]
        tab_token = f"{tab_id}-{return_tab}" if tab_id == "return-filing" else tab_id
        from reports.api.receivables_views import _safe_filename

        return _safe_filename(f"gst_tds_compliance_{tab_token}_{quarter}")
