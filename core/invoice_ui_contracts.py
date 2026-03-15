from __future__ import annotations


def purchase_invoice_ui_contract() -> dict:
    """Machine-readable frontend contract for purchase invoice form behavior."""
    return {
        "version": 1,
        "save_reload": {
            "use_save_response_as_truth": True,
            "reload_detail_after_save": False,
            "note": "Replace local draft values with the saved response immediately after create/update.",
        },
        "header_fields": {
            "posting_date": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "defaulted_and_validated",
                "helper_text": "If blank, backend defaults to bill date. Backend rejects posting dates before bill date.",
            },
            "due_date": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "derived_or_validated",
                "helper_text": "If blank, backend derives from bill date + credit days. Backend rejects due dates before bill date.",
            },
            "tax_regime": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "derived_when_vendor_and_place_of_supply_are_known",
                "helper_text": "Treat as backend-derived from vendor/place-of-supply state. Reload saved value after save.",
            },
            "is_igst": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "paired_with_tax_regime",
                "helper_text": "Backend determines whether invoice is inter-state or intra-state.",
            },
            "is_reverse_charge": {
                "ui_state": "editable",
                "backend_authoritative": False,
                "save_behavior": "suppresses_gst_components_on_lines",
                "helper_text": "When enabled, backend suppresses GST amounts on invoice lines even if UI draft showed tax.",
            },
            "is_itc_eligible": {
                "ui_state": "editable",
                "backend_authoritative": True,
                "save_behavior": "validated_for_legality",
                "helper_text": "Backend enforces ITC legality for exempt/nil-rated/non-GST and reverse-charge scenarios.",
            },
            "itc_claim_status": {
                "ui_state": "editable",
                "backend_authoritative": True,
                "save_behavior": "validated_for_legality",
                "helper_text": "Claim status may be rejected if the invoice is not legally ITC-claimable.",
            },
            "itc_block_reason": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "auto_filled_or_normalized",
                "helper_text": "Backend may auto-fill a block reason when ITC is not eligible.",
            },
            "total_taxable": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "recomputed_on_save",
                "helper_text": "Derived from saved lines and charges.",
            },
            "total_cgst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_sgst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_igst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_cess": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_gst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "grand_total": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
        },
        "line_fields": {
            "taxable_value": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "recomputed_on_save",
                "helper_text": "Preview only. Backend recalculates from qty, rate, discount, taxability, and regime.",
            },
            "cgst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "sgst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "igst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "cess_amount": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "recomputed_on_save",
                "helper_text": "Backend computes cess from cess percent; manual cess edits should not be treated as authoritative.",
            },
            "line_total": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
        },
    }


def sales_invoice_ui_contract() -> dict:
    """Machine-readable frontend contract for sales invoice form behavior."""
    return {
        "version": 1,
        "save_reload": {
            "use_save_response_as_truth": True,
            "reload_detail_after_save": False,
            "note": "Replace local draft values with the saved response immediately after create/update.",
        },
        "header_fields": {
            "posting_date": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "derived_on_save",
                "helper_text": "Backend defaults posting date to bill date.",
            },
            "due_date": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "derived_on_save",
                "helper_text": "Backend derives due date from bill date + credit days.",
            },
            "tax_regime": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "derived_on_save",
                "helper_text": "Backend derives tax regime from seller state and place of supply.",
            },
            "is_igst": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "derived_on_save",
                "helper_text": "Backend determines IGST vs CGST/SGST split.",
            },
            "total_taxable_value": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_cgst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_sgst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_igst": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_cess": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "total_discount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "round_off": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "grand_total": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
        },
        "line_fields": {
            "taxable_value": {
                "ui_state": "read_only",
                "backend_authoritative": True,
                "save_behavior": "recomputed_on_save",
                "helper_text": "Preview only. Backend recalculates from qty, rate, discount, and regime.",
            },
            "cgst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "sgst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "igst_amount": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
            "cess_amount": {
                "ui_state": "provisional",
                "backend_authoritative": True,
                "save_behavior": "manual_only_when_cess_percent_is_zero",
                "helper_text": "If cess percent is greater than zero, backend recomputes cess. Manual cess only survives when cess percent is zero.",
            },
            "line_total": {"ui_state": "read_only", "backend_authoritative": True, "save_behavior": "recomputed_on_save"},
        },
    }
