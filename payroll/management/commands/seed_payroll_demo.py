# payroll/management/commands/seed_payroll_demo.py
from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from typing import Dict, Any, Optional

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, models
from django.utils import timezone

from payroll.models import (
    ComponentFamily, PayrollComponentGlobal, PayrollComponentCap,
    SlabGroup, Slab, CityCategory,
    PayStructure, PayStructureComponent, EntityPayrollComponent,
)
from payroll.services import apply_structure_to_entity

# ---- constants (match your enums) ----
RATE_AMOUNT = "amount"
RATE_PERCENT = "percent"
CYCLE_MONTHLY = "monthly"; CYCLE_YEARLY = "yearly"; CYCLE_HALF_YEARLY = "half_yearly"
CALC_PERCENT = "percent"; CALC_FLAT = "flat"; CALC_SLAB = "slab"; CALC_FORMULA = "formula"
TYPE_EARNING = "earning"; TYPE_DEDUCTION = "deduction"
FREQ_MONTHLY = "monthly"; ROUND_NEAREST = "nearest"; TAX_TAXABLE = "taxable"
PERIODICITY_MONTHLY = "monthly"
PAYSLIP_EARN = "earnings"; PAYSLIP_DED = "deductions"

EFFECTIVE_START = date(2025, 10, 1)
EFFECTIVE_END: Optional[date] = None

# ---------- helpers ----------
def aware(dt_or_date):
    if isinstance(dt_or_date, date) and not isinstance(dt_or_date, datetime):
        dt_or_date = datetime.combine(dt_or_date, time.min)
    return timezone.make_aware(dt_or_date, timezone.get_current_timezone()) if timezone.is_naive(dt_or_date) else dt_or_date

def ef(model_cls, d: date | datetime) -> date | datetime:
    f = model_cls._meta.get_field("effective_from")
    return aware(d) if isinstance(f, models.DateTimeField) else d

def et(model_cls, d: Optional[date | datetime]) -> Optional[date | datetime]:
    if d is None: return None
    f = model_cls._meta.get_field("effective_to")
    return aware(d) if isinstance(f, models.DateTimeField) else d

def choice(model_cls, field_name: str, *labels: str) -> str:
    field = model_cls._meta.get_field(field_name)
    keys = [c[0] for c in field.choices]
    def norm(x): return str(x).strip().lower().replace("-", "_")
    for want in labels:
        for k in keys:
            if norm(k) == norm(want):
                return k
    alias_map = {
        "custom": ("other","misc","custom"),
        "professional_tax": ("professional_tax","pt"),
        "labour_welfare_tax": ("labour_welfare_tax","lwf"),
        "bonus": ("bonus",),
    }
    for want in labels:
        for alias in alias_map.get(norm(want), ()):
            for k in keys:
                if norm(k) == norm(alias):
                    return k
    return keys[0] if keys else labels[0]

def upsert(model, lookup: Dict[str, Any], defaults: Optional[Dict[str, Any]] = None):
    obj = model.objects.filter(**lookup).first()
    if obj:
        changed = False
        for k, v in (defaults or {}).items():
            if getattr(obj, k) != v:
                setattr(obj, k, v); changed = True
        if changed:
            obj.full_clean(); obj.save()
        return obj, False
    data = {**lookup, **(defaults or {})}
    obj = model(**data); obj.full_clean(); obj.save()
    return obj, True

def get_family(code: str, name: str):
    return upsert(ComponentFamily, {"code": code.upper()}, {"display_name": name})[0]

def ensure_city_categories():
    eff_is_dt = isinstance(CityCategory._meta.get_field("effective_from"), models.DateTimeField)
    rows = [("BLR","Bengaluru","METRO"),("MUM","Mumbai","METRO"),("PUN","Pune","NON_METRO")]
    def pick_cat(lbl):
        field = CityCategory._meta.get_field("category")
        for k,_ in field.choices:
            if str(k).lower().replace("-","_")==str(lbl).lower().replace("-","_"): return k
        for k,_ in field.choices:
            if str(lbl).upper()=="METRO" and str(k).lower() in {"metro","m"}: return k
            if str(lbl).upper() in {"NON_METRO","NONMETRO"} and str(k).lower() in {"non_metro","non-metro","nonmetro","n"}: return k
        return field.choices[0][0]
    for code, name, lbl in rows:
        upsert(
            CityCategory,
            {"city_code": code, "effective_from": aware(EFFECTIVE_START) if eff_is_dt else EFFECTIVE_START},
            {"city_name": name, "category": pick_cat(lbl), "effective_to": None},
        )

def ensure_entities(*, a_id: int, b_id: Optional[int]):
    Entity = apps.get_model("entity","Entity")
    try: org_a = Entity.objects.get(pk=a_id)
    except Entity.DoesNotExist: raise CommandError(f"Entity id={a_id} not found.")
    org_b = None
    if b_id is not None:
        try: org_b = Entity.objects.get(pk=b_id)
        except Entity.DoesNotExist: raise CommandError(f"Entity id={b_id} not found.")
    return org_a, org_b

def ensure_slab_groups_and_slabs():
    # SlabGroup.type and Slab.cycle values
    sg_type_custom = choice(SlabGroup, "type", "custom")
    sg_type_pt = choice(SlabGroup, "type", "professional_tax")
    sg_type_lwf = choice(SlabGroup, "type", "labour_welfare_tax")
    sg_type_bonus = choice(SlabGroup, "type", "bonus")

    cy_monthly = choice(Slab, "cycle", "monthly", "MONTHLY")
    cy_yearly  = choice(Slab, "cycle", "yearly", "annual", "annually")
    cy_half    = choice(
        Slab, "cycle",
        "half_yearly", "halfyearly", "half-yearly", "semiannual", "semi_annual",
        "semi-annual", "biannual", "bi-annual", "half_yeraly", "half-yeraly"
    )

    # ---------- Earnings/allowance slabs ----------
    g_basic, _ = upsert(
        SlabGroup,
        {"group_key": "BASIC_BY_CTC_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Basic by Monthly CTC (2025)", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_basic, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT,
        "scope_json": {"ctc_annual_max": 180000},
    }, {"value": Decimal("100.0"), "percent_of": "CTC_MONTHLY", "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_basic, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT,
        "scope_json": {"ctc_annual_min": 180000.01, "emp_grade_in": ["G1","G2"]},
    }, {"value": Decimal("30.0"), "percent_of": "CTC_MONTHLY", "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_basic, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT,
        "scope_json": {"ctc_annual_min": 180000.01, "emp_grade_in": ["G3","G4"]},
    }, {"value": Decimal("40.0"), "percent_of": "CTC_MONTHLY", "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_basic, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT,
        "scope_json": {"ctc_annual_min": 180000.01, "emp_grade_not_in": ["G1","G2","G3","G4"]},
    }, {"value": Decimal("50.0"), "percent_of": "CTC_MONTHLY", "cycle": cy_monthly, "months": ""})

    g_hra, _ = upsert(
        SlabGroup,
        {"group_key": "HRA_BY_CITY_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "HRA by City Category (2025)", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_hra, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT,
        "scope_json": {"city_category": "METRO"},
    }, {"value": Decimal("50.0"), "percent_of": "BASIC", "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_hra, "from_amount": Decimal("0.00"), "to_amount": None,
        "effective_from": ef(Slab, EFFECTIVE_START), "rate_type": RATE_PERCENT, "scope_json": {},
    }, {"value": Decimal("40.0"), "percent_of": "BASIC", "cycle": cy_monthly, "months": ""})

    g_conv, _ = upsert(
        SlabGroup,
        {"group_key": "CONV_BY_GRADE_CTC_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Conveyance by Grade & CTC (2025)", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_conv, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {"emp_grade_in":["G1","G2"], "ctc_annual_min": 180000.01},
    }, {"value": Decimal("1600.00"), "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_conv, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {"emp_grade_in":["G3","G4"], "ctc_annual_min": 180000.01},
    }, {"value": Decimal("2400.00"), "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_conv, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("1000.00"), "cycle": cy_monthly, "months": ""})

    g_phone, _ = upsert(
        SlabGroup,
        {"group_key": "PHONE_BY_STATE_RANK_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Phone by State & Rank (2025)", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_phone, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {"state_in":["KA"], "emp_rank_in":["M1","M2"]},
    }, {"value": Decimal("1000.00"), "cycle": cy_monthly})
    upsert(Slab, {
        "group": g_phone, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {"state_in":["KA"], "emp_rank_not_in":["M1","M2"]},
    }, {"value": Decimal("500.00"), "cycle": cy_monthly})
    upsert(Slab, {
        "group": g_phone, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {"state_in":["MH"], "emp_rank_in":["M1","M2"]},
    }, {"value": Decimal("1200.00"), "cycle": cy_monthly})
    upsert(Slab, {
        "group": g_phone, "effective_from": ef(Slab, EFFECTIVE_START), "from_amount": 0, "to_amount": None,
        "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("300.00"), "cycle": cy_monthly})

    g_fuel, _ = upsert(
        SlabGroup,
        {"group_key": "FUEL_BY_GRADE_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Fuel / Car Allowance by Grade (2025)", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    for grades, val in [(["G1","G2"], Decimal("2500.00")), (["G3","G4"], Decimal("3500.00"))]:
        upsert(Slab, {
            "group": g_fuel, "effective_from": ef(Slab, EFFECTIVE_START),
            "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT,
            "scope_json": {"emp_grade_in": grades},
        }, {"value": val, "cycle": cy_monthly, "months": ""})
    upsert(Slab, {
        "group": g_fuel, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("1500.00"), "cycle": cy_monthly, "months": ""})

    g_bonus, _ = upsert(
        SlabGroup,
        {"group_key": "BONUS_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Bonus 2025", "type": sg_type_bonus, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_bonus, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_PERCENT, "scope_json": {},
    }, {"value": Decimal("8.33"), "percent_of": "GROSS", "cycle": cy_yearly, "months": "Dec"})

    # ---------- PT slabs (combined + per state for engine) ----------
    g_pt, _ = upsert(
        SlabGroup,
        {"group_key": "PT_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "Professional Tax 2025", "type": sg_type_pt, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    for frm, to, val, state in [
        (0, Decimal("12500.00"), Decimal("0.00"), "KA"),
        (Decimal("12500.01"), Decimal("20000.00"), Decimal("200.00"), "KA"),
        (Decimal("20000.01"), None, Decimal("300.00"), "KA"),
        (0, Decimal("10000.00"), Decimal("0.00"), "MH"),
        (Decimal("10000.01"), Decimal("20000.00"), Decimal("175.00"), "MH"),
        (Decimal("20000.01"), None, Decimal("300.00"), "MH"),
    ]:
        upsert(Slab, {
            "group": g_pt, "effective_from": ef(Slab, EFFECTIVE_START),
            "from_amount": Decimal(str(frm)), "to_amount": to, "rate_type": RATE_AMOUNT,
            "scope_json": {"state_in":[state]},
        }, {"value": val, "cycle": cy_monthly})

    pt_ka, _ = upsert(
        SlabGroup,
        {"group_key": "PT_KA", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "PT Karnataka", "type": sg_type_pt, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    for frm, to, val in [
        (0, Decimal("12500.00"), Decimal("0.00")),
        (Decimal("12500.01"), Decimal("20000.00"), Decimal("200.00")),
        (Decimal("20000.01"), None, Decimal("300.00")),
    ]:
        upsert(Slab, {
            "group": pt_ka, "effective_from": ef(Slab, EFFECTIVE_START),
            "from_amount": Decimal(str(frm)), "to_amount": to, "rate_type": RATE_AMOUNT, "scope_json": {},
        }, {"value": val, "cycle": cy_monthly})

    pt_mh, _ = upsert(
        SlabGroup,
        {"group_key": "PT_MH", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "PT Maharashtra", "type": sg_type_pt, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    for frm, to, val in [
        (0, Decimal("10000.00"), Decimal("0.00")),
        (Decimal("10000.01"), Decimal("20000.00"), Decimal("175.00")),
        (Decimal("20000.01"), None, Decimal("300.00")),
    ]:
        upsert(Slab, {
            "group": pt_mh, "effective_from": ef(Slab, EFFECTIVE_START),
            "from_amount": Decimal(str(frm)), "to_amount": to, "rate_type": RATE_AMOUNT, "scope_json": {},
        }, {"value": val, "cycle": cy_monthly})

    # ---------- LWF (combined for UI + per-state split, no JSON) ----------
    g_lwf, _ = upsert(
        SlabGroup,
        {"group_key": "LWF_2025", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "LWF 2025", "type": sg_type_lwf, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": g_lwf, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT,
        "scope_json": {"state_in":["KA"]},
    }, {"value": Decimal("20.00"), "cycle": cy_half, "months": "Jun, Dec"})
    upsert(Slab, {
        "group": g_lwf, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT,
        "scope_json": {"state_in":["MH"]},
    }, {"value": Decimal("12.00"), "cycle": cy_half, "months": "Jun, Dec"})

    # Employee/company split groups (read by PolicyRepo)
    lwf_emp_ka, _ = upsert(
        SlabGroup,
        {"group_key": "LWF_EMP_KA", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "LWF Employee (KA)", "type": sg_type_lwf, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": lwf_emp_ka, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("20.00"), "cycle": cy_half, "months": "Jun, Dec"})

    lwf_comp_ka, _ = upsert(
        SlabGroup,
        {"group_key": "LWF_COMP_KA", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "LWF Company (KA)", "type": sg_type_lwf, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": lwf_comp_ka, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("0.00"), "cycle": cy_half, "months": "Jun, Dec"})

    lwf_emp_mh, _ = upsert(
        SlabGroup,
        {"group_key": "LWF_EMP_MH", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "LWF Employee (MH)", "type": sg_type_lwf, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": lwf_emp_mh, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("12.00"), "cycle": cy_half, "months": "Jun, Dec"})

    lwf_comp_mh, _ = upsert(
        SlabGroup,
        {"group_key": "LWF_COMP_MH", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "LWF Company (MH)", "type": sg_type_lwf, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": lwf_comp_mh, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("36.00"), "cycle": cy_half, "months": "Jun, Dec"})

    # ---------- Policy/config groups (numeric slabs; no FormulaConfig) ----------
    def upsert_cfg_decimal(key: str, val: Decimal):
        grp, _ = upsert(
            SlabGroup,
            {"group_key": key, "effective_from": ef(SlabGroup, EFFECTIVE_START)},
            {"name": key.replace("_"," ").title(), "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
        )
        upsert(Slab, {
            "group": grp, "effective_from": ef(Slab, EFFECTIVE_START),
            "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
        }, {"value": val, "cycle": cy_monthly})
        return grp

    cfg_pf_empr = upsert_cfg_decimal("PF_RATE_EMPLOYER", Decimal("12"))
    cfg_pf_emp  = upsert_cfg_decimal("PF_RATE_EMPLOYEE", Decimal("12"))
    cfg_pf_cap  = upsert_cfg_decimal("PF_BASE_CAP", Decimal("15000"))
    cfg_grat    = upsert_cfg_decimal("GRATUITY_RATE", Decimal("4.83"))  # % of BASIC if you use it
    cfg_insur   = upsert_cfg_decimal("INSURANCE_RATE", Decimal("0"))     # % of GROSS

    # HRA CAP: 50% METRO, 40% NON_METRO (percent of BASIC)
    cap_hra, _ = upsert(
        SlabGroup,
        {"group_key": "CAP_HRA", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "HRA Cap Percent", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": cap_hra, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT,
        "scope_json": {"city_category": "METRO"},
    }, {"value": Decimal("50.0"), "cycle": cy_monthly})
    upsert(Slab, {
        "group": cap_hra, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("40.0"), "cycle": cy_monthly})

    # ESI config (numeric groups instead of JSON)
    esi_threshold, _ = upsert(
        SlabGroup,
        {"group_key": "ESI_THRESHOLD", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "ESI Threshold", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": esi_threshold, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("21000"), "cycle": cy_monthly})

    esi_rate_emp, _ = upsert(
        SlabGroup,
        {"group_key": "ESI_RATE_EMPLOYEE", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "ESI Employee %", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": esi_rate_emp, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("0.75"), "cycle": cy_monthly})

    esi_rate_empr, _ = upsert(
        SlabGroup,
        {"group_key": "ESI_RATE_EMPLOYER", "effective_from": ef(SlabGroup, EFFECTIVE_START)},
        {"name": "ESI Employer %", "type": sg_type_custom, "effective_to": et(SlabGroup, EFFECTIVE_END)},
    )
    upsert(Slab, {
        "group": esi_rate_empr, "effective_from": ef(Slab, EFFECTIVE_START),
        "from_amount": 0, "to_amount": None, "rate_type": RATE_AMOUNT, "scope_json": {},
    }, {"value": Decimal("3.25"), "cycle": cy_monthly})

    return {
        # used by PCGs/UI
        "BASIC_BY_CTC_2025": g_basic, "HRA_BY_CITY_2025": g_hra, "CONV_BY_GRADE_CTC_2025": g_conv,
        "PHONE_BY_STATE_RANK_2025": g_phone, "BONUS_2025": g_bonus, "FUEL_BY_GRADE_2025": g_fuel,
        "PT_2025": g_pt, "PT_KA": pt_ka, "PT_MH": pt_mh,
        "LWF_2025": g_lwf, "LWF_EMP_KA": lwf_emp_ka, "LWF_COMP_KA": lwf_comp_ka,
        "LWF_EMP_MH": lwf_emp_mh, "LWF_COMP_MH": lwf_comp_mh,
        # policy/config keys for PolicyRepo
        "PF_RATE_EMPLOYER": cfg_pf_empr, "PF_RATE_EMPLOYEE": cfg_pf_emp, "PF_BASE_CAP": cfg_pf_cap,
        "GRATUITY_RATE": cfg_grat, "INSURANCE_RATE": cfg_insur, "CAP_HRA": cap_hra,
        "ESI_THRESHOLD": esi_threshold, "ESI_RATE_EMPLOYEE": esi_rate_emp, "ESI_RATE_EMPLOYER": esi_rate_empr,
    }

def ensure_families_and_pcg(groups: Dict[str, SlabGroup], org_b):
    BASIC = get_family("BASIC","Basic"); HRA = get_family("HRA","House Rent Allowance")
    CONV = get_family("CONV","Conveyance Allowance"); PHONE = get_family("PHONE","Phone Allowance")
    PF_EMP = get_family("PF_EMP","PF Employee"); PF_EMPR = get_family("PF_EMPR","PF Employer")
    ESI_EMP = get_family("ESI_EMP","ESI Employee"); ESI_EMPR = get_family("ESI_EMPR","ESI Employer")
    PT = get_family("PT","Professional Tax"); LWF = get_family("LWF","Labour Welfare Fund")
    BONUS = get_family("BONUS","Bonus"); LTA = get_family("LTA","Leave Travel Allowance")
    SPECIAL = get_family("SPECIAL","Special Allowance"); GRATUITY = get_family("GRATUITY_ACCR","Gratuity Accrual")
    FUEL = get_family("FUEL","Fuel / Car Allowance")

    def pcg(fam, **kwargs):
        return upsert(
            PayrollComponentGlobal,
            {"family": fam, "code": fam.code, "effective_from": ef(PayrollComponentGlobal, EFFECTIVE_START), **kwargs.get("lookup", {})},
            {k:v for k,v in kwargs.items() if k!="lookup"}
        )

    # BASIC is PF-base -> pf_include=True
    pcg(BASIC, name="Basic by CTC & Grade", type=TYPE_EARNING, calc_method=CALC_SLAB,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=10, is_proratable=True, taxability=TAX_TAXABLE,
        slab_group=groups["BASIC_BY_CTC_2025"], slab_base="CTC_MONTHLY", slab_percent_basis="CTC_MONTHLY",
        slab_scope_field="entity.state_code", payslip_group=PAYSLIP_EARN, display_order=10, show_on_payslip=True,
        pf_include=True)

    pcg(HRA, name="HRA by city category", type=TYPE_EARNING, calc_method=CALC_SLAB,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=20,
        slab_group=groups["HRA_BY_CITY_2025"], slab_base="BASIC", slab_percent_basis="BASIC",
        payslip_group=PAYSLIP_EARN, display_order=20, show_on_payslip=True)

    if org_b:
        pcg(HRA, lookup={"entity": org_b}, name="HRA Flat (Org B policy)", type=TYPE_EARNING, calc_method=CALC_FLAT,
            frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=20,
            payslip_group=PAYSLIP_EARN, display_order=20, show_on_payslip=True)

    pcg(CONV, name="Conveyance by Grade & CTC", type=TYPE_EARNING, calc_method=CALC_SLAB,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=30,
        slab_group=groups["CONV_BY_GRADE_CTC_2025"], slab_base="CTC_MONTHLY",
        payslip_group=PAYSLIP_EARN, display_order=30, show_on_payslip=True)

    pcg(PHONE, name="Phone by State & Rank", type=TYPE_EARNING, calc_method=CALC_SLAB,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=40,
        slab_group=groups["PHONE_BY_STATE_RANK_2025"], slab_base="CTC_MONTHLY",
        payslip_group=PAYSLIP_EARN, display_order=40, show_on_payslip=True)

    pf_emp, _ = pcg(PF_EMP, name="PF Employee", type=TYPE_DEDUCTION, calc_method=CALC_PERCENT,
        percent_basis="BASIC", basis_cap_amount=Decimal("15000.00"), basis_cap_periodicity=PERIODICITY_MONTHLY,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=90, pf_include=False,
        payslip_group=PAYSLIP_DED, display_order=90, show_on_payslip=True)

    pcg(PF_EMPR, name="PF Employer", type=TYPE_DEDUCTION, calc_method=CALC_PERCENT,
        percent_basis="BASIC", basis_cap_amount=Decimal("15000.00"), basis_cap_periodicity=PERIODICITY_MONTHLY,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=91, pf_include=False,
        payslip_group=PAYSLIP_DED, display_order=91, show_on_payslip=True)

    upsert(PayrollComponentCap, {
        "component": pf_emp, "cap_type": "amount_max",
        "cap_value": Decimal("1800.00"), "periodicity": PERIODICITY_MONTHLY
    }, {"sort_order": 1, "notes": "Illustrative cap"})

    pcg(ESI_EMP, name="ESI Employee", type=TYPE_DEDUCTION, calc_method=CALC_PERCENT,
        percent_basis="GROSS", basis_cap_amount=Decimal("21000.00"), basis_cap_periodicity=PERIODICITY_MONTHLY,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=95,
        payslip_group=PAYSLIP_DED, display_order=95, show_on_payslip=True)

    pcg(ESI_EMPR, name="ESI Employer", type=TYPE_DEDUCTION, calc_method=CALC_PERCENT,
        percent_basis="GROSS", basis_cap_amount=Decimal("21000.00"), basis_cap_periodicity=PERIODICITY_MONTHLY,
        frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=96,
        payslip_group=PAYSLIP_DED, display_order=96, show_on_payslip=True)

    pcg(PT, name="Professional Tax", type=TYPE_DEDUCTION, calc_method=CALC_SLAB,
        slab_group=groups["PT_2025"], slab_base="GROSS", frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST,
        priority=110, payslip_group=PAYSLIP_DED, display_order=110, show_on_payslip=True)

    pcg(LWF, name="Labour Welfare Fund", type=TYPE_DEDUCTION, calc_method=CALC_SLAB,
        slab_group=groups["LWF_2025"], slab_base="GROSS", frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST,
        priority=111, payslip_group=PAYSLIP_DED, display_order=111, show_on_payslip=True)

    pcg(BONUS, name="Bonus (yearly)", type=TYPE_EARNING, calc_method=CALC_SLAB,
        slab_group=groups["BONUS_2025"], slab_base="GROSS", frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST,
        priority=200, payslip_group=PAYSLIP_EARN, display_order=200, show_on_payslip=True)

    pcg(LTA, name="LTA (accrual on BASIC)", type=TYPE_EARNING, calc_method=CALC_PERCENT,
        percent_basis="BASIC", frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=50,
        payout_policy="accrue_and_pay_on_months", payout_months="Mar, Sep",
        payslip_group=PAYSLIP_EARN, display_order=50, show_on_payslip=True)

    pcg(SPECIAL, name="Special Allowance (balancing)", type=TYPE_EARNING, calc_method=CALC_FORMULA,
        formula_text="max(0, CTC_MONTHLY - (BASIC + HRA + CONV + PHONE + LTA))",
        default_params={}, frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=80,
        allow_negative=False, payslip_group=PAYSLIP_EARN, display_order=80, show_on_payslip=True)

    pcg(GRATUITY, name="Gratuity Accrual (4.81% of BASIC)", type=TYPE_EARNING, calc_method=CALC_PERCENT,
        percent_basis="BASIC", frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=85,
        payslip_group=PAYSLIP_EARN, display_order=300, show_on_payslip=False)

    pcg(FUEL, name="Fuel / Car Allowance by Grade", type=TYPE_EARNING, calc_method=CALC_SLAB,
        slab_group=groups["FUEL_BY_GRADE_2025"], slab_base="CTC_MONTHLY", frequency=FREQ_MONTHLY,
        rounding=ROUND_NEAREST, priority=35, payslip_group=PAYSLIP_EARN, display_order=35, show_on_payslip=True)

    if org_b:
        pcg(FUEL, lookup={"entity": org_b}, name="Fuel by Grade (Org B override)",
            type=TYPE_EARNING, calc_method=CALC_SLAB, slab_group=groups["FUEL_BY_GRADE_2025"],
            frequency=FREQ_MONTHLY, rounding=ROUND_NEAREST, priority=35,
            payslip_group=PAYSLIP_EARN, display_order=35, show_on_payslip=True)

    return {"BASIC":BASIC,"HRA":HRA,"CONV":CONV,"PHONE":PHONE,"PF_EMP":PF_EMP,"PF_EMPR":PF_EMPR,
            "ESI_EMP":ESI_EMP,"ESI_EMPR":ESI_EMPR,"PT":PT,"LWF":LWF,"BONUS":BONUS,"LTA":LTA,
            "SPECIAL":SPECIAL,"GRATUITY_ACCR":GRATUITY,"FUEL":FUEL}

def ensure_pay_structure(families: Dict[str, ComponentFamily]):

    ps, _ = upsert(
        PayStructure,
        {"code": "STD_STAFF_2025_10", "entity": None, "effective_from": ef(PayStructure, EFFECTIVE_START)},
        {
            "name": "Standard Staff (2025 Oct)",
            "status": "active",
            "rounding": ROUND_NEAREST,
            "proration_method": "calendar_days",
            "notes": "Demo template",
            "effective_to": et(PayStructure, EFFECTIVE_END),
            "config_json": {                     # <— add this block
                "balancer_code": "SPECIAL",
                "balancer_allow_negative": False,
                "ctc_includes": ["PF_EMPR", "GRATUITY_ACCR", "FUEL"]
            },
        }
    )
    ps, _ = upsert(
        PayStructure,
        {"code": "STD_STAFF_2025_10", "entity": None, "effective_from": ef(PayStructure, EFFECTIVE_START)},
        {"name": "Standard Staff (2025 Oct)", "status": "active", "rounding": ROUND_NEAREST,
         "proration_method": "calendar_days", "notes": "Demo template",
         "effective_to": et(PayStructure, EFFECTIVE_END)}
    )
    def add(fam, **kw):
        upsert(PayStructureComponent, {"template": ps, "family": fam}, {"priority": 50, "enabled": True, **kw})
    add(families["BASIC"], priority=10); add(families["HRA"], priority=20)
    add(families["CONV"], priority=30); add(families["PHONE"], priority=40); add(families["FUEL"], priority=35)
    add(families["LTA"], priority=50, default_percent=Decimal("8.330"))
    add(families["SPECIAL"], priority=80); add(families["GRATUITY_ACCR"], priority=85, default_percent=Decimal("4.810"))
    add(families["PF_EMP"], priority=90, default_percent=Decimal("12.000"))
    add(families["PF_EMPR"], priority=91, default_percent=Decimal("12.000"))
    add(families["ESI_EMP"], priority=95, default_percent=Decimal("0.750"))
    add(families["ESI_EMPR"], priority=96, default_percent=Decimal("3.250"))
    add(families["PT"], priority=110); add(families["LWF"], priority=111); add(families["BONUS"], priority=200)
    return ps

def apply_to_entities(ps: PayStructure, org_a, org_b):
    eff = ef(EntityPayrollComponent, EFFECTIVE_START)
    _ = apply_structure_to_entity(structure=ps, entity_id=org_a.id, eff_from=eff, dry_run=True)
    if org_b: _ = apply_structure_to_entity(structure=ps, entity_id=org_b.id, eff_from=eff, dry_run=True)
    res_a = apply_structure_to_entity(structure=ps, entity_id=org_a.id, eff_from=eff, dry_run=False)
    res_b = None
    if org_b:
        res_b = apply_structure_to_entity(structure=ps, entity_id=org_b.id, eff_from=eff, dry_run=False)
        hra = (EntityPayrollComponent.objects
               .filter(entity=org_b, family__code="HRA", effective_from=eff)
               .order_by("-id").first())
        if hra and hra.default_amount is None:
            hra.default_amount = Decimal("12000.00"); hra.save()
    return res_a, res_b

# ---------- command ----------
class Command(BaseCommand):
    help = "Seed a rich, India-style payroll demo: families, PCGs, slabs, template, and EPCs."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", dest="entity_id", type=int, required=True,
                            help="Existing Entity ID to seed demo policies for (Org A).")
        parser.add_argument("--entity-b-id", dest="entity_b_id", type=int, default=None,
                            help="Optional second Entity ID (Org B) to demo entity overrides.")

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding payroll demo data..."))
        org_a, org_b = ensure_entities(a_id=opts["entity_id"], b_id=opts.get("entity_b_id"))
        ensure_city_categories()
        groups = ensure_slab_groups_and_slabs()
        self.stdout.write(self.style.SUCCESS(f"Slab groups ready: {', '.join(groups.keys())}"))
        fams = ensure_families_and_pcg(groups, org_b)
        self.stdout.write(self.style.SUCCESS("Families & PCGs ready."))
        ps = ensure_pay_structure(fams)
        self.stdout.write(self.style.SUCCESS(f"PayStructure ready: {ps.code}"))
        res_a, res_b = apply_to_entities(ps, org_a, org_b)
        self.stdout.write(self.style.HTTP_INFO(f"Applied to Org A: {res_a}"))
        if res_b is not None:
            self.stdout.write(self.style.HTTP_INFO(f"Applied to Org B: {res_b}"))
        self.stdout.write(self.style.SUCCESS("✅ Payroll demo seeded successfully."))
