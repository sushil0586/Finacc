from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class PreparedWhiteboxPayload:
    return_type: str
    gstin: str
    ret_period: str
    payload: dict
    warnings: tuple[dict, ...] = ()


def ret_period_from_scope(scope) -> str:
    from_date = getattr(scope, "from_date", None)
    if not from_date:
        return ""
    return f"{from_date.month:02d}{from_date.year}"


def ret_period_from_date(value: date | datetime | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        parsed = date.fromisoformat(value[:10])
    elif isinstance(value, datetime):
        parsed = value.date()
    else:
        parsed = value
    return f"{parsed.month:02d}{parsed.year}"


class Gstr1WhiteboxPayloadBuilder:
    """
    Adapter from Finacc filing-prep GSTR-1 JSON to the Whitebox/GSTN save payload.

    This intentionally covers the launch-safe core tables first. Advanced tables
    remain explicit warnings until the corresponding report rows have full
    Whitebox field coverage.
    """

    def build(
        self,
        *,
        filing_prep_payload: dict,
        gstin: str | None = None,
        aggregate_turnover: Decimal | int | float | str = ZERO,
        current_turnover: Decimal | int | float | str = ZERO,
    ) -> PreparedWhiteboxPayload:
        tables = filing_prep_payload.get("tables") or {}
        taxpayer = (tables.get("1_2_3") or [{}])[0] if tables.get("1_2_3") else {}
        resolved_gstin = _clean_gstin(gstin or taxpayer.get("gstin"))
        ret_period = str(filing_prep_payload.get("ret_period") or "")
        warnings: list[dict] = []

        payload = {
            "gstin": resolved_gstin,
            "fp": ret_period,
            "gt": _amount(aggregate_turnover or taxpayer.get("previous_financial_year_aggregate_turnover")),
            "cur_gt": _amount(current_turnover),
        }

        b2b = self._build_b2b(tables.get("4") or [])
        if b2b:
            payload["b2b"] = b2b

        b2cl = self._build_b2cl(tables.get("5") or [])
        if b2cl:
            payload["b2cl"] = b2cl

        b2cs = self._build_b2cs(tables.get("7") or [])
        if b2cs:
            payload["b2cs"] = b2cs

        exp = self._build_exp(tables.get("6") or [])
        if exp:
            payload["exp"] = exp

        cdnr = self._build_cdnr(tables.get("9") or [])
        if cdnr:
            payload["cdnr"] = cdnr

        cdnur = self._build_cdnur(tables.get("10") or [])
        if cdnur:
            payload["cdnur"] = cdnur

        nil = self._build_nil(tables.get("8") or [])
        if nil:
            payload["nil"] = nil

        hsnsum = self._build_hsnsum(tables.get("12") or [])
        if hsnsum:
            payload["hsnsum"] = hsnsum

        dociss = self._build_dociss(tables.get("13") or [])
        if dociss:
            payload["doc_issue"] = dociss

        unsupported_counts = {
            "advances_table_11": len(tables.get("11") or []),
            "ecommerce_table_14": len(tables.get("14") or []),
            "ecommerce_amendment_table_14a": len(tables.get("14A") or []),
            "operator_table_15": len(tables.get("15") or []),
            "operator_amendment_table_15a": len(tables.get("15A") or []),
        }
        for code, count in unsupported_counts.items():
            if count:
                warnings.append(
                    {
                        "code": "WHITEBOX_GSTR1_TABLE_PENDING",
                        "severity": "warning",
                        "message": f"{code} has {count} row(s); portal adapter mapping is pending for this table.",
                    }
                )

        return PreparedWhiteboxPayload(
            return_type="gstr1",
            gstin=resolved_gstin,
            ret_period=ret_period,
            payload=payload,
            warnings=tuple(warnings),
        )

    def _build_b2b(self, rows: list[dict]) -> list[dict]:
        grouped = _group_invoice_rows(rows, "customer_gstin", "invoice_id")
        payload = []
        for ctin, invoices in grouped.items():
            inv_payload = []
            for _, invoice_rows in invoices.items():
                first = invoice_rows[0]
                inv_payload.append(
                    {
                        "inum": _document_number(first, "invoice"),
                        "idt": _gstn_date(first.get("invoice_date")),
                        "val": _amount(first.get("grand_total")),
                        "pos": _state_code(first.get("place_of_supply_state_code")),
                        "rchrg": _reverse_charge_flag(first),
                        "inv_typ": "R",
                        "itms": _line_items(invoice_rows),
                    }
                )
            payload.append({"ctin": _clean_gstin(ctin), "inv": inv_payload})
        return payload

    def _build_b2cl(self, rows: list[dict]) -> list[dict]:
        by_pos: dict[str, list[dict]] = {}
        for row in rows:
            by_pos.setdefault(_state_code(row.get("place_of_supply_state_code")), []).append(row)
        payload = []
        for pos, pos_rows in by_pos.items():
            invoices = _group_rows(pos_rows, "invoice_id")
            payload.append(
                {
                    "pos": pos,
                    "inv": [
                        {
                            "inum": _document_number(invoice_rows[0], "invoice"),
                            "idt": _gstn_date(invoice_rows[0].get("invoice_date")),
                            "val": _amount(invoice_rows[0].get("grand_total")),
                            "itms": _line_items(invoice_rows),
                        }
                        for invoice_rows in invoices.values()
                    ],
                }
            )
        return payload

    def _build_b2cs(self, rows: list[dict]) -> list[dict]:
        payload = []
        for row in rows:
            payload.append(
                _with_non_zero_tax_fields(
                    {
                        "sply_ty": "INTER" if _decimal(row.get("igst_amount")) else "INTRA",
                        "typ": "OE",
                        "pos": _state_code(row.get("place_of_supply_state_code")),
                        "rt": _rate(row.get("gst_rate")),
                        "txval": _amount(row.get("taxable_value")),
                    },
                    row,
                )
            )
        return payload

    def _build_exp(self, rows: list[dict]) -> list[dict]:
        by_type: dict[str, list[dict]] = {}
        for row in rows:
            category = str(row.get("supply_category") or "").upper()
            exp_type = "WPAY" if "WITH IGST" in category else "WOPAY"
            by_type.setdefault(exp_type, []).append(row)
        payload = []
        for exp_type, type_rows in by_type.items():
            invoices = _group_rows(type_rows, "invoice_id")
            payload.append(
                {
                    "exp_typ": exp_type,
                    "inv": [
                        {
                            "inum": _document_number(invoice_rows[0], "invoice"),
                            "idt": _gstn_date(invoice_rows[0].get("invoice_date")),
                            "val": _amount(invoice_rows[0].get("grand_total")),
                            "itms": _line_items(invoice_rows),
                        }
                        for invoice_rows in invoices.values()
                    ],
                }
            )
        return payload

    def _build_cdnr(self, rows: list[dict]) -> list[dict]:
        registered = [row for row in rows if _clean_gstin(row.get("customer_gstin"))]
        grouped = _group_invoice_rows(registered, "customer_gstin", "note_id")
        payload = []
        for ctin, notes in grouped.items():
            payload.append(
                {
                    "ctin": _clean_gstin(ctin),
                    "nt": [
                        {
                            "ntty": _note_type(note_rows[0]),
                            "nt_num": _document_number(note_rows[0], "note"),
                            "nt_dt": _gstn_date(note_rows[0].get("note_date")),
                            "val": _amount(note_rows[0].get("grand_total")),
                            "itms": _line_items(note_rows),
                        }
                        for note_rows in notes.values()
                    ],
                }
            )
        return payload

    def _build_cdnur(self, rows: list[dict]) -> list[dict]:
        grouped = _group_rows(rows, "note_id")
        return [
            {
                "typ": "B2CL",
                "ntty": _note_type(note_rows[0]),
                "nt_num": _document_number(note_rows[0], "note"),
                "nt_dt": _gstn_date(note_rows[0].get("note_date")),
                "pos": _state_code(note_rows[0].get("place_of_supply_state_code")),
                "val": _amount(note_rows[0].get("grand_total")),
                "itms": _line_items(note_rows),
            }
            for note_rows in grouped.values()
        ]

    def _build_nil(self, rows: list[dict]) -> dict:
        if not rows:
            return {}
        nil_amt = sum((_decimal(row.get("taxable_value")) for row in rows if str(row.get("taxability") or "").lower() == "nil_rated"), ZERO)
        expt_amt = sum((_decimal(row.get("taxable_value")) for row in rows if str(row.get("taxability") or "").lower() == "exempt"), ZERO)
        ngsup_amt = sum((_decimal(row.get("taxable_value")) for row in rows if str(row.get("taxability") or "").lower() == "non_gst"), ZERO)
        return {
            "inv": [
                {
                    "sply_ty": "INTRB2C",
                    "nil_amt": _amount(nil_amt),
                    "expt_amt": _amount(expt_amt),
                    "ngsup_amt": _amount(ngsup_amt),
                }
            ]
        }

    def _build_hsnsum(self, rows: list[dict]) -> dict:
        if not rows:
            return {}
        return {
            "data": [
                _with_non_zero_tax_fields(
                    {
                        "num": idx,
                        "hsn_sc": str(row.get("hsn_sac_code") or ""),
                        "uqc": "OTH" if row.get("is_service") else "NOS",
                        "qty": _amount(row.get("total_qty")),
                        "rt": _rate(row.get("gst_rate")),
                        "txval": _amount(row.get("taxable_value")),
                    },
                    row,
                )
                for idx, row in enumerate(rows, start=1)
            ]
        }

    def _build_dociss(self, rows: list[dict]) -> dict:
        if not rows:
            return {}
        return {
            "doc_det": [
                {
                    "doc_num": idx,
                    "docs": [
                        {
                            "num": idx,
                            "from": _doc_sequence_value(row.get("min_doc_no")),
                            "to": _doc_sequence_value(row.get("max_doc_no")),
                            "totnum": int(row.get("document_count") or 0),
                            "cancel": int(row.get("cancelled_count") or 0),
                            "net_issue": max(int(row.get("document_count") or 0) - int(row.get("cancelled_count") or 0), 0),
                        }
                    ],
                }
                for idx, row in enumerate(rows, start=1)
            ]
        }


class Gstr3bWhiteboxPayloadBuilder:
    """Adapter from Finacc GSTR-3B summary into the Whitebox/GSTN save payload."""

    def build(
        self,
        *,
        summary: dict,
        gstin: str,
        ret_period: str,
        interstate_breakups: dict[str, list[dict]] | None = None,
    ) -> PreparedWhiteboxPayload:
        interstate_breakups = interstate_breakups or {}
        section_31 = summary.get("section_3_1") or {}
        section_32 = summary.get("section_3_2") or {}
        section_4 = summary.get("section_4") or {}
        section_51 = summary.get("section_5_1") or {}

        warnings = []
        if section_32 and not interstate_breakups:
            warnings.append(
                {
                    "code": "WHITEBOX_GSTR3B_POS_BREAKUP_PENDING",
                    "severity": "warning",
                    "message": "GSTR-3B section 3.2 portal payload needs POS-wise breakup; current summary is aggregate-only.",
                }
            )

        itc_available = section_4.get("itc_available") or {}
        itc_reversed = section_4.get("itc_reversed") or {}
        net_itc = section_4.get("net_itc") or {}

        payload = {
            "gstin": _clean_gstin(gstin),
            "ret_period": ret_period,
            "sup_details": {
                "osup_det": _gstr3b_tax_bucket(section_31.get("outward_taxable_supplies")),
                "osup_zero": _gstr3b_tax_bucket(section_31.get("outward_zero_rated_supplies"), include_state_tax=False),
                "osup_nil_exmp": {"txval": _amount((section_31.get("outward_nil_exempt_non_gst") or {}).get("taxable_value"))},
                "isup_rev": _gstr3b_tax_bucket(section_31.get("inward_supplies_reverse_charge")),
                "osup_nongst": {"txval": _amount((section_31.get("non_gst_outward_supplies") or {}).get("taxable_value"))},
            },
            "inter_sup": {
                "unreg_details": [_gstr3b_interstate_row(row) for row in interstate_breakups.get("unregistered", [])],
                "comp_details": [_gstr3b_interstate_row(row) for row in interstate_breakups.get("composition", [])],
                "uin_details": [_gstr3b_interstate_row(row) for row in interstate_breakups.get("uin", [])],
            },
            "itc_elg": {
                "itc_avl": [_gstr3b_itc_row("OTH", itc_available)],
                "itc_rev": [_gstr3b_itc_row("OTH", itc_reversed)],
                "itc_net": _gstr3b_tax_amount_bucket(net_itc),
                "itc_inelg": [_gstr3b_itc_row("OTH", {})],
            },
            "inward_sup": {
                "isup_details": [
                    {
                        "ty": "GST",
                        "inter": _amount((section_51.get("inward_exempt_nil_non_gst") or {}).get("taxable_value")),
                        "intra": 0,
                    }
                ]
            },
        }

        return PreparedWhiteboxPayload(
            return_type="gstr3b",
            gstin=_clean_gstin(gstin),
            ret_period=ret_period,
            payload=payload,
            warnings=tuple(warnings),
        )


def build_gstr1_retfile_payload(*, save_payload: dict, gstin: str = "", ret_period: str = "") -> dict:
    """Build the WhiteBooks/GSTN GSTR-1 `retfile` payload from a saved draft payload."""
    resolved_gstin = _clean_gstin(gstin or save_payload.get("gstin"))
    resolved_ret_period = str(ret_period or save_payload.get("ret_period") or save_payload.get("fp") or "").strip()
    section_summaries = _build_gstr1_section_summaries(save_payload)
    payload = {
        "gstin": resolved_gstin,
        "ret_period": resolved_ret_period,
        "newSumFlag": True,
        "sec_sum": section_summaries,
    }
    payload["chksum"] = _checksum(payload)
    return payload


def _build_gstr1_section_summaries(save_payload: dict) -> list[dict]:
    sections = []
    for section_name, entries, builder in (
        ("B2B", save_payload.get("b2b") or [], _invoice_group_subsections),
        ("B2CL", save_payload.get("b2cl") or [], _invoice_group_subsections),
        ("B2CS", save_payload.get("b2cs") or [], _b2cs_subsections),
        ("EXP", save_payload.get("exp") or [], _invoice_group_subsections),
        ("CDNR", save_payload.get("cdnr") or [], _note_group_subsections),
        ("CDNUR", save_payload.get("cdnur") or [], _note_group_subsections),
        ("CDNRA", save_payload.get("cdnra") or [], _note_group_subsections),
        ("CDNURA", save_payload.get("cdnura") or [], _note_group_subsections),
        ("NIL", [save_payload.get("nil")] if save_payload.get("nil") else [], _nil_subsections),
        ("HSN", [save_payload.get("hsnsum")] if save_payload.get("hsnsum") else [], _hsn_subsections),
        ("DOC_ISSUE", [save_payload.get("doc_issue")] if save_payload.get("doc_issue") else [], _doc_issue_subsections),
    ):
        if not entries:
            continue
        subsections = builder(section_name, entries)
        sections.append(_section_summary(section_name, _combine_metrics(subsections), subsections))
    return sections


def _invoice_group_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    subsections = []
    for entry in entries:
        anchor = entry.get("ctin") or entry.get("pos") or entry.get("exp_typ") or "NA"
        metrics = _empty_summary_metrics()
        for invoice in entry.get("inv") or []:
            metrics["ttl_rec"] += 1
            _apply_tax_metrics(metrics, *_invoice_tax_components(invoice), is_amendment=section_name.endswith("A"))
        subsections.append(_section_summary(_safe_section_name(f"{section_name}_{anchor}"), metrics, []))
    return subsections


def _b2cs_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    subsections = []
    for entry in entries:
        anchor = f"{entry.get('pos') or '00'}_{entry.get('rt') or '0'}"
        metrics = _empty_summary_metrics()
        metrics["ttl_rec"] = 1
        _apply_tax_metrics(
            metrics,
            _decimal(entry.get("txval")),
            _decimal(entry.get("iamt")),
            _decimal(entry.get("samt")),
            _decimal(entry.get("camt")),
            _decimal(entry.get("csamt")),
            is_amendment=section_name.endswith("A"),
        )
        subsections.append(_section_summary(_safe_section_name(f"{section_name}_{anchor}"), metrics, []))
    return subsections


def _note_group_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    subsections = []
    for entry in entries:
        anchor = entry.get("ctin") or entry.get("typ") or "NA"
        metrics = _empty_summary_metrics()
        for note in entry.get("nt") or []:
            taxable, igst, sgst, cgst, cess = _note_tax_components(note)
            metrics["ttl_rec"] += 1
            _apply_tax_metrics(metrics, taxable, igst, sgst, cgst, cess, is_amendment=section_name.endswith("A"))
        subsections.append(_section_summary(_safe_section_name(f"{section_name}_{anchor}"), metrics, []))
    return subsections


def _nil_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    metrics = _empty_summary_metrics()
    nil_payload = entries[0] if entries else {}
    for row in nil_payload.get("inv") or []:
        metrics["ttl_rec"] += 1
        taxable = _decimal(row.get("nil_amt")) + _decimal(row.get("expt_amt")) + _decimal(row.get("ngsup_amt"))
        _apply_tax_metrics(metrics, taxable, ZERO, ZERO, ZERO, ZERO)
    return [_section_summary(section_name, metrics, [])] if metrics["ttl_rec"] else []


def _hsn_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    metrics = _empty_summary_metrics()
    hsn_payload = entries[0] if entries else {}
    for row in hsn_payload.get("data") or []:
        metrics["ttl_rec"] += 1
        _apply_tax_metrics(
            metrics,
            _decimal(row.get("txval")),
            _decimal(row.get("iamt")),
            _decimal(row.get("samt")),
            _decimal(row.get("camt")),
            _decimal(row.get("csamt")),
        )
    return [_section_summary(section_name, metrics, [])] if metrics["ttl_rec"] else []


def _doc_issue_subsections(section_name: str, entries: list[dict]) -> list[dict]:
    metrics = _empty_summary_metrics()
    doc_payload = entries[0] if entries else {}
    for group in doc_payload.get("doc_det") or []:
        for row in group.get("docs") or []:
            metrics["ttl_rec"] += int(row.get("net_issue") or row.get("totnum") or 0)
    return [_section_summary(section_name, metrics, [])] if metrics["ttl_rec"] else []


def _section_summary(section_name: str, metrics: dict[str, Decimal | int], subsections: list[dict]) -> dict:
    payload = {
        "sec_nm": section_name,
        "ttl_rec": int(metrics["ttl_rec"]),
        "ttl_val": _amount(metrics["ttl_val"]),
        "ttl_igst": _amount(metrics["ttl_igst"]),
        "ttl_sgst": _amount(metrics["ttl_sgst"]),
        "ttl_cgst": _amount(metrics["ttl_cgst"]),
        "ttl_cess": _amount(metrics["ttl_cess"]),
        "ttl_tax": _amount(metrics["ttl_tax"]),
        "act_tax": _amount(metrics["act_tax"]),
        "act_igst": _amount(metrics["act_igst"]),
        "act_sgst": _amount(metrics["act_sgst"]),
        "act_cgst": _amount(metrics["act_cgst"]),
        "act_val": _amount(metrics["act_val"]),
        "act_cess": _amount(metrics["act_cess"]),
    }
    if subsections:
        payload["sub_sections"] = subsections
    payload["chksum"] = _checksum(payload)
    return payload


def _invoice_tax_components(invoice: dict) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    taxable = igst = sgst = cgst = cess = ZERO
    for item in invoice.get("itms") or []:
        item_det = item.get("itm_det") if isinstance(item.get("itm_det"), dict) else {}
        taxable += _decimal(item_det.get("txval"))
        igst += _decimal(item_det.get("iamt"))
        sgst += _decimal(item_det.get("samt"))
        cgst += _decimal(item_det.get("camt"))
        cess += _decimal(item_det.get("csamt"))
    if taxable == ZERO:
        taxable = _decimal(invoice.get("val")) - (igst + sgst + cgst + cess)
    return taxable, igst, sgst, cgst, cess


def _note_tax_components(note: dict) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    taxable, igst, sgst, cgst, cess = _invoice_tax_components(note)
    if str(note.get("ntty") or "").upper() == "C":
        return -taxable, -igst, -sgst, -cgst, -cess
    return taxable, igst, sgst, cgst, cess


def _apply_tax_metrics(
    metrics: dict[str, Decimal | int],
    taxable: Decimal,
    igst: Decimal,
    sgst: Decimal,
    cgst: Decimal,
    cess: Decimal,
    *,
    is_amendment: bool = False,
) -> None:
    total_tax = igst + sgst + cgst + cess
    metrics["ttl_val"] += taxable
    metrics["ttl_igst"] += igst
    metrics["ttl_sgst"] += sgst
    metrics["ttl_cgst"] += cgst
    metrics["ttl_cess"] += cess
    metrics["ttl_tax"] += total_tax
    if is_amendment:
        metrics["act_val"] += taxable
        metrics["act_igst"] += igst
        metrics["act_sgst"] += sgst
        metrics["act_cgst"] += cgst
        metrics["act_cess"] += cess
        metrics["act_tax"] += total_tax


def _combine_metrics(summaries: list[dict]) -> dict[str, Decimal | int]:
    metrics = _empty_summary_metrics()
    for summary in summaries:
        metrics["ttl_rec"] += int(summary.get("ttl_rec") or 0)
        for key in ("ttl_val", "ttl_igst", "ttl_sgst", "ttl_cgst", "ttl_cess", "ttl_tax", "act_val", "act_igst", "act_sgst", "act_cgst", "act_cess", "act_tax"):
            metrics[key] += _decimal(summary.get(key))
    return metrics


def _empty_summary_metrics() -> dict[str, Decimal | int]:
    return {
        "ttl_rec": 0,
        "ttl_val": ZERO,
        "ttl_igst": ZERO,
        "ttl_sgst": ZERO,
        "ttl_cgst": ZERO,
        "ttl_cess": ZERO,
        "ttl_tax": ZERO,
        "act_tax": ZERO,
        "act_igst": ZERO,
        "act_sgst": ZERO,
        "act_cgst": ZERO,
        "act_val": ZERO,
        "act_cess": ZERO,
    }


def _safe_section_name(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value.upper())[:64]


def _checksum(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> float:
    if isinstance(value, Decimal):
        return _amount(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _group_invoice_rows(rows: list[dict], party_key: str, invoice_key: str) -> dict[str, dict[Any, list[dict]]]:
    grouped: dict[str, dict[Any, list[dict]]] = {}
    for row in rows:
        party = str(row.get(party_key) or "").strip().upper()
        invoice = row.get(invoice_key) or _document_number(row, "invoice")
        grouped.setdefault(party, {}).setdefault(invoice, []).append(row)
    return {party: invoices for party, invoices in grouped.items() if party}


def _group_rows(rows: list[dict], key: str) -> dict[Any, list[dict]]:
    grouped: dict[Any, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get(key) or _document_number(row, "invoice"), []).append(row)
    return grouped


def _line_items(rows: list[dict]) -> list[dict]:
    return [
        {
            "num": idx,
            "itm_det": _with_non_zero_tax_fields(
                {
                    "rt": _rate(row.get("gst_rate")),
                    "txval": _amount(row.get("taxable_amount", row.get("taxable_value"))),
                },
                row,
            ),
        }
        for idx, row in enumerate(rows, start=1)
    ]


def _with_non_zero_tax_fields(payload: dict, row: dict) -> dict:
    field_map = {
        "igst_amount": "iamt",
        "cgst_amount": "camt",
        "sgst_amount": "samt",
        "cess_amount": "csamt",
    }
    for source, target in field_map.items():
        value = _decimal(row.get(source))
        if value:
            payload[target] = _amount(value)
    return payload


def _gstr3b_tax_bucket(row: dict | None, *, include_state_tax: bool = True) -> dict:
    payload = {
        "txval": _amount((row or {}).get("taxable_value")),
        "iamt": _amount((row or {}).get("igst")),
        "csamt": _amount((row or {}).get("cess")),
    }
    if include_state_tax:
        payload["camt"] = _amount((row or {}).get("cgst"))
        payload["samt"] = _amount((row or {}).get("sgst"))
    return payload


def _gstr3b_tax_amount_bucket(row: dict | None) -> dict:
    return {
        "iamt": _amount((row or {}).get("igst")),
        "camt": _amount((row or {}).get("cgst")),
        "samt": _amount((row or {}).get("sgst")),
        "csamt": _amount((row or {}).get("cess")),
    }


def _gstr3b_itc_row(ty: str, row: dict | None) -> dict:
    return {"ty": ty, **_gstr3b_tax_amount_bucket(row)}


def _gstr3b_interstate_row(row: dict) -> dict:
    return {
        "pos": _state_code(row.get("pos") or row.get("place_of_supply_state_code")),
        "txval": _amount(row.get("taxable_value") or row.get("txval")),
        "iamt": _amount(row.get("igst") or row.get("igst_amount") or row.get("iamt")),
    }


def _document_number(row: dict, kind: str) -> str:
    return str(row.get(f"{kind}_number") or row.get("invoice_number") or row.get("note_number") or "").strip()


def _note_type(row: dict) -> str:
    label = str(row.get("note_type") or "").upper()
    return "C" if "CREDIT" in label else "D"


def _reverse_charge_flag(row: dict) -> str:
    contract = row.get("rcm_contract") or {}
    value = contract.get("is_reverse_charge") or row.get("is_reverse_charge")
    return "Y" if value else "N"


def _gstn_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        parsed = date.fromisoformat(value[:10])
    elif isinstance(value, datetime):
        parsed = value.date()
    else:
        parsed = value
    return parsed.strftime("%d-%m-%Y")


def _state_code(value: Any) -> str:
    code = str(value or "").strip()
    return code.zfill(2) if code.isdigit() else code


def _doc_sequence_value(value: Any) -> str:
    return "" if value in (None, "") else str(value)


def _clean_gstin(value: Any) -> str:
    return str(value or "").strip().upper()


def _rate(value: Any) -> float:
    return _amount(value)


def _amount(value: Any) -> float:
    value = _decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(value)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
