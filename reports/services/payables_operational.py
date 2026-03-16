from __future__ import annotations

from decimal import Decimal

from financial.models import account
from purchase.models.purchase_core import PurchaseInvoiceHeader
from reports.services.financial.ledger_book import build_ledger_book
from reports.services.payables_config import (
    get_close_pack_section_codes,
    resolve_close_pack_sections,
)
from reports.services.payables import (
    _drilldown_item,
    _paginate,
    _report_meta_payload,
    _row_with_meta,
    _sort_rows,
    _stringify_amount_fields,
    _trace_payload,
    _vendor_meta,
    build_ap_aging_report,
    build_payables_dashboard_summary,
    build_vendor_outstanding_report,
)
from reports.services.payables_control import (
    build_ap_gl_reconciliation_report,
    build_payables_close_readiness_summary,
    build_payables_close_validation,
    build_vendor_balance_exception_report,
)
from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import note_register_queryset, q2, settlement_history_queryset, vendor_queryset

ZERO = Decimal("0.00")


def _resolve_vendor(entity_id, vendor_id):
    vendor = vendor_queryset(entity_id=entity_id, vendor_id=vendor_id).first()
    if not vendor:
        raise ValueError({"vendor": ["Vendor is not available in the selected entity scope."]})
    if not getattr(vendor, "ledger_id", None):
        raise ValueError({"vendor": ["Vendor does not have a mapped ledger for statement reporting."]})
    return vendor


def _note_signed_amount(header, field_name):
    value = q2(getattr(header, field_name, ZERO) or ZERO)
    if header.doc_type == PurchaseInvoiceHeader.DocType.CREDIT_NOTE:
        return q2(-abs(value))
    return q2(abs(value))


def build_vendor_settlement_history_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    vendor_id=None,
    from_date=None,
    to_date=None,
    settlement_type=None,
    include_unapplied=True,
    include_trace=True,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
):
    """Build a vendor settlement history from posted/draft settlement headers and lines."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    settlements = settlement_history_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        vendor_id=vendor_id,
        from_date=from_date,
        to_date=to_date,
        settlement_type=settlement_type,
    )

    rows = []
    total_settled = ZERO
    total_unapplied = ZERO
    settlement_count = 0
    for settlement in settlements.iterator(chunk_size=500):
        settlement_count += 1
        line_rows = list(settlement.lines.all())
        line_total = q2(sum((q2(line.amount) for line in line_rows), ZERO))
        unapplied_amount = q2(settlement.total_amount - line_total)
        vendor = settlement.vendor
        base_trace = _trace_payload(
            source_model="purchase.VendorSettlement",
            source_id=settlement.id,
            source_document_number=settlement.reference_no or settlement.external_voucher_no or f"SET-{settlement.id}",
            vendor_id=settlement.vendor_id,
            settlement_id=settlement.id,
            settlement_type=settlement.settlement_type,
            settlement_date=str(settlement.settlement_date),
            posted_at=settlement.posted_at.isoformat() if settlement.posted_at else None,
            created_at=settlement.created_at.isoformat() if getattr(settlement, "created_at", None) else None,
            updated_at=settlement.updated_at.isoformat() if getattr(settlement, "updated_at", None) else None,
            derived_from=["purchase.VendorSettlement", "purchase.VendorSettlementLine", "purchase.VendorBillOpenItem"],
        )
        for line in line_rows:
            open_item = line.open_item
            header = getattr(open_item, "header", None)
            applied_amount = q2(line.amount)
            total_settled = q2(total_settled + applied_amount)
            drilldown = {
                "document": _drilldown_item(
                    label="Purchase Document Detail",
                    target="purchase_document_detail",
                    params={"id": open_item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                ),
                "vendor_outstanding": _drilldown_item(
                    label="Vendor Outstanding",
                    target="vendor_outstanding",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "to_date": to_date or settlement.settlement_date, "vendor": settlement.vendor_id},
                ),
                "ap_aging": _drilldown_item(
                    label="AP Aging",
                    target="ap_aging",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": to_date or settlement.settlement_date, "vendor": settlement.vendor_id, "view": "invoice"},
                ),
                "vendor_ledger_statement": _drilldown_item(
                    label="Vendor Ledger Statement",
                    target="vendor_ledger_statement",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": settlement.vendor_id, "from_date": from_date, "to_date": to_date or settlement.settlement_date},
                ),
                "settlement_detail": _drilldown_item(
                    label="Settlement Detail",
                    target="purchase_ap_settlements",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": settlement.vendor_id, "settlement": settlement.id},
                ),
            }
            rows.append(
                {
                    **_row_with_meta(
                        {
                            **_vendor_meta(vendor, subentity_name=getattr(settlement.subentity, "subentityname", None)),
                            "settlement_id": settlement.id,
                            "settlement_number": settlement.reference_no or settlement.external_voucher_no or f"SET-{settlement.id}",
                            "settlement_date": settlement.settlement_date,
                            "settlement_type": settlement.settlement_type,
                            "settlement_type_name": settlement.get_settlement_type_display(),
                            "status": settlement.status,
                            "status_name": settlement.get_status_display(),
                            "posted": settlement.status == settlement.Status.POSTED,
                            "reference_number": settlement.reference_no,
                            "remarks": settlement.remarks,
                            "external_voucher_no": settlement.external_voucher_no,
                            "bill_number": open_item.purchase_number or open_item.supplier_invoice_number,
                            "bill_date": open_item.bill_date,
                            "open_item_id": open_item.id,
                            "source_document_id": open_item.header_id,
                            "applied_amount": applied_amount,
                            "unapplied_amount": ZERO,
                            "note": line.note,
                        },
                        drilldown=drilldown,
                        trace=_trace_payload(
                            **{
                                **(base_trace or {}),
                                "source_line_model": "purchase.VendorSettlementLine",
                                "settlement_line_id": line.id,
                                "open_item_id": open_item.id,
                                "source_document_id": open_item.header_id,
                                "source_document_number": open_item.purchase_number or open_item.supplier_invoice_number,
                                "source_document_type": header.get_doc_type_display() if header else None,
                                "applied_amount": f"{applied_amount:.2f}",
                            }
                        ) if include_trace else None,
                    )
                }
            )
        if include_unapplied and unapplied_amount > ZERO:
            total_unapplied = q2(total_unapplied + unapplied_amount)
            drilldown = {
                "vendor_outstanding": _drilldown_item(
                    label="Vendor Outstanding",
                    target="vendor_outstanding",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "to_date": to_date or settlement.settlement_date, "vendor": settlement.vendor_id},
                ),
                "ap_aging": _drilldown_item(
                    label="AP Aging",
                    target="ap_aging",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": to_date or settlement.settlement_date, "vendor": settlement.vendor_id, "view": "invoice"},
                ),
                "vendor_ledger_statement": _drilldown_item(
                    label="Vendor Ledger Statement",
                    target="vendor_ledger_statement",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": settlement.vendor_id, "from_date": from_date, "to_date": to_date or settlement.settlement_date},
                ),
                "settlement_detail": _drilldown_item(
                    label="Settlement Detail",
                    target="purchase_ap_settlements",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": settlement.vendor_id, "settlement": settlement.id},
                ),
            }
            rows.append(
                {
                    **_row_with_meta(
                        {
                            **_vendor_meta(vendor, subentity_name=getattr(settlement.subentity, "subentityname", None)),
                            "settlement_id": settlement.id,
                            "settlement_number": settlement.reference_no or settlement.external_voucher_no or f"SET-{settlement.id}",
                            "settlement_date": settlement.settlement_date,
                            "settlement_type": settlement.settlement_type,
                            "settlement_type_name": settlement.get_settlement_type_display(),
                            "status": settlement.status,
                            "status_name": settlement.get_status_display(),
                            "posted": settlement.status == settlement.Status.POSTED,
                            "reference_number": settlement.reference_no,
                            "remarks": settlement.remarks,
                            "external_voucher_no": settlement.external_voucher_no,
                            "bill_number": None,
                            "bill_date": None,
                            "open_item_id": None,
                            "source_document_id": None,
                            "applied_amount": ZERO,
                            "unapplied_amount": unapplied_amount,
                            "note": "Unapplied balance",
                        },
                        drilldown=drilldown,
                        trace=_trace_payload(
                            **{
                                **(base_trace or {}),
                                "source_line_model": None,
                                "unapplied_amount": f"{unapplied_amount:.2f}",
                            }
                        ) if include_trace else None,
                    )
                }
            )

    _sort_rows(rows, sort_by or "settlement_date", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("applied_amount", "unapplied_amount"))
    payload = {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": from_date,
        "to_date": to_date,
        "rows": paged_rows,
        "totals": {
            "total_settled": f"{total_settled:.2f}",
            "total_unapplied": f"{total_unapplied:.2f}",
        },
        "summary": {
            "settlement_count": settlement_count,
        },
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
    }
    payload.update(
        _report_meta_payload(
            report_code="vendor_settlement_history",
            report_name="Vendor Settlement History",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=from_date,
            to_date=to_date,
            vendor_id=vendor_id,
            required_menu_code="reports.vendorsettlementhistory",
            required_permissions=["reports.vendorsettlementhistory.view"],
            feature_state={"include_unapplied": include_unapplied, "include_trace": include_trace},
        )
    )
    return payload


def build_vendor_note_register(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    vendor_id=None,
    from_date=None,
    to_date=None,
    note_type=None,
    status=None,
    include_trace=True,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
):
    """Build a vendor debit/credit note register using existing purchase note documents."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    notes = note_register_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        vendor_id=vendor_id,
        from_date=from_date,
        to_date=to_date,
        note_type=note_type,
        status=status,
    )
    rows = []
    credit_total = ZERO
    debit_total = ZERO
    net_total = ZERO
    for header in notes.iterator(chunk_size=500):
        note_amount = _note_signed_amount(header, "grand_total")
        tax_amount = _note_signed_amount(header, "total_gst")
        taxable_amount = _note_signed_amount(header, "total_taxable")
        outstanding_amount = q2(getattr(getattr(header, "ap_open_item", None), "outstanding_amount", ZERO))
        if header.doc_type == PurchaseInvoiceHeader.DocType.CREDIT_NOTE:
            credit_total = q2(credit_total + abs(note_amount))
        else:
            debit_total = q2(debit_total + abs(note_amount))
        net_total = q2(net_total + note_amount)
        drilldown = {
            "document": _drilldown_item(
                label="Purchase Document Detail",
                target="purchase_document_detail",
                params={"id": header.id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
            ),
            "vendor_outstanding": _drilldown_item(
                label="Vendor Outstanding",
                target="vendor_outstanding",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "to_date": to_date or header.bill_date, "vendor": header.vendor_id},
            ),
            "ap_aging": _drilldown_item(
                label="AP Aging",
                target="ap_aging",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": to_date or header.bill_date, "vendor": header.vendor_id, "view": "invoice"},
            ),
            "vendor_ledger_statement": _drilldown_item(
                label="Vendor Ledger Statement",
                target="vendor_ledger_statement",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": header.vendor_id, "from_date": from_date, "to_date": to_date or header.bill_date},
            ),
        }
        rows.append(
            {
                **_row_with_meta(
                    {
                        **_vendor_meta(header.vendor, subentity_name=getattr(header.subentity, "subentityname", None)),
                        "note_id": header.id,
                        "note_number": header.purchase_number or f"{header.doc_code}-{header.doc_no}",
                        "note_date": header.bill_date,
                        "note_type": "credit" if header.doc_type == PurchaseInvoiceHeader.DocType.CREDIT_NOTE else "debit",
                        "note_type_name": header.get_doc_type_display(),
                        "linked_bill_number": getattr(getattr(header, "ref_document", None), "purchase_number", None),
                        "linked_bill_id": getattr(header, "ref_document_id", None),
                        "taxable_amount": taxable_amount,
                        "tax_amount": tax_amount,
                        "total_note_amount": note_amount,
                        "outstanding_amount": outstanding_amount,
                        "status": header.status,
                        "status_name": header.get_status_display(),
                        "posted": header.status == header.Status.POSTED,
                        "posting_status": "Posted" if header.status == header.Status.POSTED else "Unposted",
                    },
                    drilldown=drilldown,
                    trace=_trace_payload(
                        source_model="purchase.PurchaseInvoiceHeader",
                        source_id=header.id,
                        source_document_number=header.purchase_number or f"{header.doc_code}-{header.doc_no}",
                        source_document_type=header.get_doc_type_display(),
                        vendor_id=header.vendor_id,
                        open_item_id=getattr(getattr(header, "ap_open_item", None), "id", None),
                        linked_bill_id=header.ref_document_id,
                        linked_bill_number=getattr(getattr(header, "ref_document", None), "purchase_number", None),
                        created_at=header.created_at.isoformat() if getattr(header, "created_at", None) else None,
                        updated_at=header.updated_at.isoformat() if getattr(header, "updated_at", None) else None,
                        posted_at=header.posted_at.isoformat() if getattr(header, "posted_at", None) else None,
                        derived_from=["purchase.PurchaseInvoiceHeader", "purchase.VendorBillOpenItem"],
                    ) if include_trace else None,
                )
            }
        )

    _sort_rows(rows, sort_by or "note_date", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("taxable_amount", "tax_amount", "total_note_amount", "outstanding_amount"))
    payload = {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": from_date,
        "to_date": to_date,
        "rows": paged_rows,
        "totals": {
            "credit_note_total": f"{credit_total:.2f}",
            "debit_note_total": f"{debit_total:.2f}",
            "net_note_total": f"{net_total:.2f}",
        },
        "summary": {"note_count": total_rows},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
    }
    payload.update(
        _report_meta_payload(
            report_code="vendor_note_register",
            report_name="Vendor Debit/Credit Note Register",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=from_date,
            to_date=to_date,
            vendor_id=vendor_id,
            required_menu_code="reports.vendornoteregister",
            required_permissions=["reports.vendornoteregister.view"],
            feature_state={"note_type": note_type, "include_trace": include_trace},
        )
    )
    return payload


def build_vendor_ledger_statement(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    vendor_id,
    from_date=None,
    to_date=None,
    include_opening=True,
    include_running_balance=True,
    include_settlement_drilldowns=True,
    include_related_reports=True,
    include_trace=True,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    vendor = _resolve_vendor(entity_id, vendor_id)
    base = build_ledger_book(
        entity_id=entity_id,
        ledger_id=vendor.ledger_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )

    rows = []
    for row in base["rows"]:
        drilldown = {
            "source_document": _drilldown_item(
                label="Source Document",
                target=row["drilldown_target"],
                params=row["drilldown_params"],
            )
        }
        if include_related_reports:
            drilldown["vendor_outstanding"] = _drilldown_item(
                label="Vendor Outstanding",
                target="vendor_outstanding",
                report_code="vendor_outstanding",
                path="/api/reports/payables/vendor-outstanding/",
                params={
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "to_date": base["to_date"],
                    "vendor": vendor.id,
                },
            )
            drilldown["ap_aging"] = _drilldown_item(
                label="AP Aging",
                target="ap_aging",
                report_code="ap_aging",
                path="/api/reports/payables/aging/",
                params={
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": base["to_date"],
                    "vendor": vendor.id,
                    "view": "invoice",
                },
            )
        if include_settlement_drilldowns:
            drilldown["vendor_settlements"] = _drilldown_item(
                label="Vendor Settlements",
                target="purchase_ap_settlements",
                params={
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "vendor": vendor.id,
                    "from_date": base["from_date"],
                    "to_date": base["to_date"],
                },
            )

        out_row = {
            "transaction_date": row["posting_date"],
            "document_number": row["voucher_number"],
            "document_type": row["voucher_type"],
            "document_type_name": row["voucher_type_name"],
            "reference": row.get("description"),
            "debit": row["debit"],
            "credit": row["credit"],
            "running_balance": row.get("running_balance"),
            "entry_id": row["entry_id"],
            "source_txn_type": row["txn_type"],
            "source_txn_id": row["txn_id"],
            "source_detail_id": row.get("detail_id"),
            "drilldown_target": row["drilldown_target"],
            "drilldown_params": row["drilldown_params"],
            "drilldown_targets": list(drilldown.keys()),
            "_meta": {"drilldown": drilldown, "supports_drilldown": True},
        }
        trace = _trace_payload(
            source_model="posting.Entry",
            source_id=row["entry_id"],
            source_document_id=row["txn_id"],
            source_document_number=row["voucher_number"],
            source_document_type=row["voucher_type_name"],
            vendor_id=vendor.id,
            posting_entry_id=row["entry_id"],
            posting_txn_type=row["txn_type"],
            posting_txn_id=row["txn_id"],
            derived_from=["posting.Entry", "posting.JournalLine"],
        )
        if include_trace and trace:
            out_row["_trace"] = trace
        if not include_running_balance:
            out_row.pop("running_balance", None)
        rows.append(out_row)

    opening_balance = f"{-q2(base['opening_balance']):.2f}" if include_opening else None
    totals = {
        "debit": base["totals"]["debit"],
        "credit": base["totals"]["credit"],
        "closing_balance": f"{-q2(base['totals']['closing_balance']):.2f}",
    }
    for row in rows:
        if include_running_balance and row.get("running_balance") is not None:
            row["running_balance"] = f"{-q2(row['running_balance']):.2f}"
    payload = {
        "entity_id": base["entity_id"],
        "entity_name": base["entity_name"],
        "entityfin_id": base["entityfin_id"],
        "entityfin_name": base["entityfin_name"],
        "subentity_id": base["subentity_id"],
        "subentity_name": base["subentity_name"],
        "from_date": base["from_date"],
        "to_date": base["to_date"],
        "vendor": {**_vendor_meta(vendor), "ledger_id": vendor.ledger_id, "ledger_name": base["ledger"]["name"]},
        "opening_balance": opening_balance,
        "totals": totals,
        "rows": rows,
        "summary": {"transaction_count": len(rows)},
    }
    payload.update(
        _report_meta_payload(
            report_code="vendor_ledger_statement",
            report_name="Vendor Ledger Statement",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=base["from_date"],
            to_date=base["to_date"],
            vendor_id=vendor.id,
            required_menu_code="reports.vendorledgerstatement",
            required_permissions=["reports.vendorledgerstatement.view"],
            feature_state={
                "include_opening": include_opening,
                "include_running_balance": include_running_balance,
                "include_settlement_drilldowns": include_settlement_drilldowns,
                "include_related_reports": include_related_reports,
                "include_trace": include_trace,
            },
            extra_meta={"vendor_id": vendor.id, "vendor_ledger_id": vendor.ledger_id},
        )
    )
    return payload


def build_payables_close_pack(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    include_sections=None,
    include_top_vendors=True,
    include_top_exceptions=True,
    expanded_validation=False,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    sections = get_close_pack_section_codes(include_sections)

    dashboard = build_payables_dashboard_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
    )
    aging = build_ap_aging_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
        view="summary",
    )
    reconciliation = build_ap_gl_reconciliation_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
        page_size=10,
    )
    validation = build_payables_close_validation(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
    )
    close_summary = build_payables_close_readiness_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
    )
    exception_report = build_vendor_balance_exception_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
        page_size=10,
    )
    vendor_outstanding = build_vendor_outstanding_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        to_date=as_of_date,
        page_size=10,
    )

    top_overdue_vendors = sorted(
        vendor_outstanding["rows"],
        key=lambda row: q2(row.get("overdue_amount") or ZERO),
        reverse=True,
    )[:5]
    top_outstanding_vendors = sorted(
        vendor_outstanding["rows"],
        key=lambda row: q2(row.get("net_outstanding") or ZERO),
        reverse=True,
    )[:5]

    payload = {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": close_summary["as_of_date"],
        "included_sections": sections,
        "section_order": sections,
    }
    if "overview" in sections:
        payload["overview"] = {
            "total_vendor_outstanding": dashboard["totals"]["vendor_outstanding"],
            "overdue_outstanding": dashboard.get("overdue_outstanding", "0.00"),
            "open_vendor_count": close_summary["open_vendor_count"],
            "negative_balance_vendor_count": close_summary["negative_balance_vendor_count"],
            "stale_advance_count": close_summary["stale_advance_count"],
        }
    if "aging" in sections:
        payload["aging"] = {
            "totals": aging["totals"],
            "vendor_count": aging["summary"]["vendor_count"],
        }
    if "reconciliation" in sections:
        payload["reconciliation"] = {
            "subledger_balance": reconciliation["totals"]["subledger_balance"],
            "gl_balance": reconciliation["totals"]["gl_balance"],
            "difference_amount": reconciliation["totals"]["difference_amount"],
            "status": reconciliation["summary"]["overall_status"],
        }
    if "validation" in sections:
        payload["validation"] = {
            "validation_error_count": validation["summary"]["validation_error_count"],
            "validation_warning_count": validation["summary"]["validation_warning_count"],
            "top_critical_issues": close_summary["top_critical_issues"],
        }
        if expanded_validation:
            payload["validation"]["checks"] = validation["checks"]
    if "exceptions" in sections and include_top_exceptions:
        payload["exceptions"] = {
            "total_exceptions": exception_report["summary"]["total_exceptions"],
            "top_exception_rows": exception_report["rows"],
        }
    if "top_vendors" in sections and include_top_vendors:
        payload["top_vendors"] = {
            "top_overdue_vendors": top_overdue_vendors,
            "top_outstanding_vendors": top_outstanding_vendors,
        }

    payload.update(
        _report_meta_payload(
            report_code="payables_close_pack",
            report_name="Payables Close Pack",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=close_summary["as_of_date"],
            required_menu_code="reports.payablesclosepack",
            required_permissions=["reports.payablesclosepack.view"],
            feature_state={
                "include_overview": "overview" in sections,
                "include_aging": "aging" in sections,
                "include_reconciliation": "reconciliation" in sections,
                "include_validation": "validation" in sections,
                "include_exceptions": "exceptions" in sections and include_top_exceptions,
                "include_top_vendors": "top_vendors" in sections and include_top_vendors,
                "expanded_validation": expanded_validation,
            },
            extra_meta={
                "expanded_validation": expanded_validation,
                "configured_sections": resolve_close_pack_sections(sections),
            },
        )
    )
    return payload


def close_pack_export_rows(payload):
    rows = []
    for section_meta in resolve_close_pack_sections(payload.get("included_sections", [])):
        section = section_meta["code"]
        block = payload.get(section)
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if isinstance(value, list):
                rows.append([section_meta["label"], key, len(value), "list"])
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    rows.append([section_meta["label"], f"{key}.{sub_key}", sub_value, "value"])
            else:
                rows.append([section_meta["label"], key, value, "value"])
    return rows
