from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _party_name(obj: Any) -> str:
    if obj is None:
        return ""
    return _first_text(
        getattr(obj, "accountname", None),
        getattr(obj, "legalname", None),
        getattr(obj, "name", None),
        getattr(obj, "vendor_name", None),
        getattr(obj, "customer_name", None),
    )


def _product_name(line: Any) -> str:
    product = getattr(line, "product", None)
    return _first_text(
        getattr(line, "product_desc", None),
        getattr(line, "productDesc", None),
        getattr(line, "description", None),
        getattr(product, "productname", None),
        getattr(product, "sku", None),
    )


def _charge_name(charge: Any) -> str:
    return _first_text(
        getattr(charge, "description", None),
        getattr(charge, "charge_type", None),
    )


def _join_parts(*parts: str) -> str:
    return " | ".join(part for part in (_clean_text(part) for part in parts) if part)


def purchase_document_prefix(header: Any) -> str:
    doc_type = int(getattr(header, "doc_type", 1) or 1)
    doc_label = "Purchase Invoice"
    if doc_type == 2:
        doc_label = "Purchase Credit Note"
    elif doc_type == 3:
        doc_label = "Purchase Debit Note"
    vendor_name = _first_text(getattr(header, "vendor_name", None), _party_name(getattr(header, "vendor", None)))
    supplier_invoice = _first_text(getattr(header, "supplier_invoice_number", None))
    purchase_ref = _first_text(getattr(header, "purchase_number", None), getattr(header, "doc_no", None))
    return _join_parts(
        f"Vendor {vendor_name}" if vendor_name else "",
        f"{doc_label} No {supplier_invoice}" if supplier_invoice else "",
        f"Purchase Ref {purchase_ref}" if (purchase_ref and not supplier_invoice) else "",
    )


def sales_document_prefix(header: Any) -> str:
    doc_type = int(getattr(header, "doc_type", 1) or 1)
    doc_label = "Sales Invoice"
    if doc_type == 2:
        doc_label = "Sales Credit Note"
    elif doc_type == 3:
        doc_label = "Sales Debit Note"
    doc_no = _first_text(
        getattr(header, "sales_number", None),
        getattr(header, "invoice_number", None),
        getattr(header, "doc_no", None),
        getattr(header, "id", None),
    )
    customer_name = _first_text(getattr(header, "customer_name", None), _party_name(getattr(header, "customer", None)))
    return _join_parts(
        f"Customer {customer_name}" if customer_name else "",
        f"{doc_label} No {doc_no}" if doc_no else doc_label,
    )


def payment_document_prefix(header: Any) -> str:
    vendor_name = _party_name(getattr(header, "paid_to", None))
    source_name = _party_name(getattr(header, "paid_from", None))
    reference = _first_text(
        getattr(header, "reference_number", None),
        getattr(header, "instrument_no", None),
        getattr(header, "voucher_code", None),
        getattr(header, "id", None),
    )
    return _join_parts(
        f"Vendor {vendor_name}" if vendor_name else "",
        f"From {source_name}" if source_name else "",
        f"Payment Ref {reference}" if reference else "Payment Voucher",
    )


def receipt_document_prefix(header: Any) -> str:
    customer_name = _party_name(getattr(header, "received_from", None))
    target_name = _party_name(getattr(header, "received_in", None))
    reference = _first_text(
        getattr(header, "reference_number", None),
        getattr(header, "instrument_no", None),
        getattr(header, "voucher_code", None),
        getattr(header, "id", None),
    )
    return _join_parts(
        f"Customer {customer_name}" if customer_name else "",
        f"Into {target_name}" if target_name else "",
        f"Receipt Ref {reference}" if reference else "Receipt Voucher",
    )


def voucher_document_prefix(header: Any) -> str:
    voucher_type = _first_text(getattr(header, "get_voucher_type_display", lambda: "")())
    reference = _first_text(getattr(header, "reference_number", None))
    narration = _first_text(getattr(header, "narration", None))
    return _join_parts(
        voucher_type or "Voucher",
        f"Ref {reference}" if reference else "",
        narration,
    )


def opening_stock_prefix(*, product: Any, branch_name: str = "", location_name: str = "", voucher_no: str = "") -> str:
    product_name = _first_text(getattr(product, "productname", None), getattr(product, "sku", None), getattr(product, "id", None))
    return _join_parts(
        "Opening Stock",
        f"Product {product_name}" if product_name else "",
        _join_parts(branch_name, location_name),
    )


def payroll_prefix(run: Any) -> str:
    period = getattr(getattr(run, "payroll_period", None), "period_end", None)
    return _join_parts(
        f"Payroll Run {_first_text(getattr(run, 'run_number', None), getattr(run, 'id', None))}",
        f"Period {period}" if period else "",
    )


def purchase_line_description(header: Any, line: Any) -> str:
    line_no = getattr(line, "line_no", None)
    product_name = _product_name(line)
    return _join_parts(purchase_document_prefix(header), f"Item {product_name}" if product_name else "", f"Line {line_no}" if line_no else "")


def purchase_charge_description(header: Any, charge: Any) -> str:
    line_no = getattr(charge, "line_no", None)
    charge_name = _charge_name(charge)
    return _join_parts(purchase_document_prefix(header), f"Charge {charge_name}" if charge_name else "Charge", f"Line {line_no}" if line_no else "")


def sales_line_description(header: Any, line: Any) -> str:
    line_no = getattr(line, "line_no", None)
    product_name = _product_name(line)
    return _join_parts(sales_document_prefix(header), f"Item {product_name}" if product_name else "", f"Line {line_no}" if line_no else "")


def sales_charge_description(header: Any, charge: Any) -> str:
    line_no = getattr(charge, "line_no", None)
    charge_name = _charge_name(charge)
    return _join_parts(sales_document_prefix(header), f"Charge {charge_name}" if charge_name else "Charge", f"Line {line_no}" if line_no else "")
