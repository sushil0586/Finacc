# payroll/compensation_engine.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple, Iterable, Optional

from django.db.models import Q
from django.utils.timezone import make_aware

from payroll.models import (
    PayStructure,
    PayStructureComponent,
    PayrollComponentGlobal,
    Slab,
    CompensationDraft,
    CompensationDraftLine,
)

# ---- repositories (policy is data-driven) ----
try:
    from payroll.repositories import PolicyRepo, RepoCtx
except Exception:  # pragma: no cover
    @dataclass
    class RepoCtx:
        eff: datetime
        state: Optional[str] = None
        city_category: Optional[str] = None
        emp_grade: Optional[str] = None
        emp_rank: Optional[str] = None
        month: Optional[int] = None
    class PolicyRepo:
        def cap_for(self, *a, **kw): return None
        def should_zero(self, *a, **kw): return (False, None)

# ----------------- utils -----------------
ROUND = lambda x: Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@dataclass
class Ctx:
    eff: datetime
    entity_id: int
    state: Optional[str]
    city_category: Optional[str]
    emp_grade: Optional[str]
    emp_rank: Optional[str]
    is_metro: bool
    month: int

def _effective_qs(model, eff):
    """Field-aware effective filter (used where models have effective_* fields)."""
    names = {f.name for f in model._meta.get_fields()}
    qs = model.objects.all()
    if "effective_from" in names:
        qs = qs.filter(effective_from__lte=eff)
    if "effective_to" in names:
        qs = qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=eff))
    return qs

def _parse_months_str(s: str) -> set[int]:
    if not s: return set()
    MONTHS = {"jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,"may":5,
              "jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,"september":9,
              "oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12}
    out=set()
    for tok in str(s).replace("/",",").replace(";",",").split(","):
        t=tok.strip()
        if not t: continue
        if t.isdigit():
            m=int(t); 
            if 1<=m<=12: out.add(m)
        else:
            m=MONTHS.get(t.lower())
            if m: out.add(m)
    return out

def _occurrences_per_year(pcg, slab) -> int:
    # explicit months first
    if slab and getattr(slab, "months", None):
        return max(1, len(_parse_months_str(slab.months)))
    if getattr(pcg, "payout_months", None):
        return max(1, len(_parse_months_str(pcg.payout_months)))
    # cycles
    cyc = getattr(slab, "cycle", None)
    if cyc in {"monthly","MONTHLY"}: return 12
    if cyc in {"yearly","YEARLY"}: return 1
    if cyc in {"half_yearly","HALF_YEARLY","semi_annual","SEMI_ANNUAL"}: return 2
    return 12

# very small safe eval for formulas like "max(0, CTC_MONTHLY - (BASIC + HRA))"
def _safe_eval(expr: str, vars_map: Dict[str, Decimal]) -> Decimal:
    allowed_names = {"min": min, "max": max, "Decimal": Decimal}
    local = {k: Decimal(str(v)) for k, v in vars_map.items()}
    return Decimal(str(eval(expr, {"__builtins__": {}}, {**allowed_names, **local})))  # noqa: S307

def _pcg_for(family, entity_id: int, eff: datetime) -> PayrollComponentGlobal:
    """Pick entity override PCG if present else global; both effective-dated."""
    qs = (_effective_qs(PayrollComponentGlobal, eff)
          .filter(family=family)
          .filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
          .order_by("-entity_id", "priority", "id"))
    return qs.first()

def _scope_match(scope: dict, ctx: Ctx, ctc_annual: Decimal) -> bool:
    if not scope: return True
    def S(x): return ("" if x is None else str(x))
    if scope.get("city_category") and S(scope["city_category"]).upper() != S(ctx.city_category).upper(): return False
    if scope.get("emp_grade_in") and S(ctx.emp_grade) not in {S(x) for x in scope["emp_grade_in"]}: return False
    if scope.get("emp_grade_not_in") and S(ctx.emp_grade) in {S(x) for x in scope["emp_grade_not_in"]}: return False
    if scope.get("emp_rank_in") and S(ctx.emp_rank) not in {S(x) for x in scope["emp_rank_in"]}: return False
    if scope.get("emp_rank_not_in") and S(ctx.emp_rank) in {S(x) for x in scope["emp_rank_not_in"]}: return False
    if scope.get("state_in") and S(ctx.state) not in {S(x) for x in scope["state_in"]}: return False
    if scope.get("state_not_in") and S(ctx.state) in {S(x) for x in scope["state_not_in"]}: return False
    if "ctc_annual_min" in scope and Decimal(str(ctc_annual)) < Decimal(str(scope["ctc_annual_min"])): return False
    if "ctc_annual_max" in scope and Decimal(str(ctc_annual)) > Decimal(str(scope["ctc_annual_max"])): return False
    return True

def _pick_slab(group, ctc_annual: Decimal, ctx: Ctx, band_base_value: Decimal) -> Optional[Slab]:
    """
    Pick first effective slab whose scope_json matches and whose [from_amount, to_amount]
    includes the provided band_base_value.
    """
    slabs = (_effective_qs(Slab, ctx.eff).filter(group=group).order_by("id"))
    for s in slabs:
        if not _scope_match(getattr(s, "scope_json", {}) or {}, ctx, ctc_annual):
            continue
        lo = Decimal(str(getattr(s, "from_amount", 0) or 0))
        hi = getattr(s, "to_amount", None)
        if hi is None:
            if band_base_value >= lo: return s
        else:
            if lo <= band_base_value <= Decimal(str(hi)): return s
    return None

# ---------- inclusion helper (CTC composition) ----------
def _flag_include_in_ctc(ps: PayStructure, line: CompensationDraftLine, pcg: PayrollComponentGlobal) -> bool:
    """
    Resolution order:
      1) PayStructureComponent.include_in_ctc if set
      2) PCG.include_in_ctc if set
      3) config_json.ctc_includes / ctc_excludes
      4) default: include earnings, exclude deductions
    """
    psc = PayStructureComponent.objects.filter(template=ps, family=line.family_id).only("include_in_ctc").first()
    if psc and psc.include_in_ctc is not None:
        return bool(psc.include_in_ctc)
    if getattr(pcg, "include_in_ctc", None) is not None:
        return bool(pcg.include_in_ctc)
    cfg = (getattr(ps, "config_json", None) or {})
    inc = set(cfg.get("ctc_includes") or [])
    exc = set(cfg.get("ctc_excludes") or [])
    if line.code in inc: return True
    if line.code in exc: return False
    return line.component_type == "earning"

# ----------------- ENGINE -----------------
class CompensationEngine:
    def calculate(
        self,
        draft: CompensationDraft,
        overrides: Optional[dict] = None,   # normalized by serializer: {CODE: {"mode":"amount"/"percent", ...}}
    ) -> Tuple[Decimal, Dict[str, Decimal]]:
        ps: PayStructure = draft.pay_structure
        eff_dt = make_aware(datetime.combine(draft.effective_from, datetime.min.time()))

        ctx = Ctx(
            eff=eff_dt, entity_id=draft.entity_id,
            state=(draft.context or {}).get("state"),
            city_category=((draft.context or {}).get("city_category") or ("METRO" if (draft.context or {}).get("is_metro") else "NON_METRO")),
            emp_grade=(draft.context or {}).get("emp_grade"),
            emp_rank=(draft.context or {}).get("emp_rank"),
            is_metro=bool((draft.context or {}).get("is_metro")),
            month=draft.effective_from.month,
        )

        policy = PolicyRepo()
        repo_ctx = RepoCtx(
            eff=eff_dt,
            state=ctx.state,
            city_category=ctx.city_category,
            emp_grade=ctx.emp_grade,
            emp_rank=ctx.emp_rank,
            month=ctx.month,
        )

        overrides = overrides or {}

        # PayStructureComponent is usually NOT effective-dated
        scs: Iterable[PayStructureComponent] = (
            PayStructureComponent.objects
            .filter(template=ps, enabled=True)
            .select_related("family")
            .order_by("priority", "id")
        )

        # running vars exposed to formulas/percent-of: start with CTC_MONTHLY and GROSS
        vars: Dict[str, Decimal] = {"CTC_MONTHLY": draft.ctc_monthly, "GROSS": draft.ctc_monthly}

        existing = {l.family_id: l for l in draft.lines.all()}
        out_lines: list[CompensationDraftLine] = []

        for sc in scs:
            fam = sc.family
            code = fam.code
            pcg = _pcg_for(fam, ctx.entity_id, ctx.eff)
            name = getattr(pcg, "name", fam.display_name or code)
            ctype = getattr(pcg, "type", "earning")
            calc_method = getattr(pcg, "calc_method", getattr(sc, "calc_method", "flat"))
            priority = sc.priority

            amount = Decimal("0.00")
            meta: dict = {}
            slab: Optional[Slab] = None

            def basis_value(label: Optional[str]) -> Decimal:
                return vars.get(label or "", Decimal("0"))

            # ---------- compute by method ----------
            if calc_method == "slab" and getattr(pcg, "slab_group_id", None):
                # choose base for band/range selection (even for flat slabs like PT)
                select_label = getattr(pcg, "slab_percent_basis", None) or getattr(pcg, "slab_base", None) or "GROSS"
                band_base = basis_value(select_label)

                slab = _pick_slab(pcg.slab_group, draft.ctc_annual, ctx, band_base)
                if slab:
                    if slab.rate_type == "percent":
                        base_label = getattr(pcg, "slab_percent_basis", None) or getattr(pcg, "slab_base", None) or "GROSS"
                        base = basis_value(base_label)
                        amount = ROUND(base * Decimal(slab.value) / Decimal("100"))
                        meta.update({"slab_id": slab.id, "percent": str(slab.value), "percent_of": base_label})
                    else:
                        amount = ROUND(Decimal(slab.value))
                        meta.update({"slab_id": slab.id, "flat": str(slab.value)})

                    meta["raw_amount"] = str(amount)

                    # month gating from slab.months
                    mset = _parse_months_str(getattr(slab, "months", "") or "")
                    if mset and (ctx.month not in mset):
                        amount = Decimal("0.00")
                        meta["off_cycle"] = "true"

            elif calc_method == "percent":
                # fully seed-driven: use SC default_percent (or 0)
                pct = getattr(sc, "default_percent", None) or Decimal("0")
                base_label = getattr(pcg, "percent_basis", None) or getattr(sc, "percent_basis", None) or "GROSS"
                base = basis_value(base_label)

                # apply basis cap if present on PCG (e.g., PF @ 15k)
                cap = getattr(pcg, "basis_cap_amount", None)
                if cap and base_label in {"BASIC", "DA", "PF_WAGE"}:
                    base = min(base, Decimal(cap))
                    meta["basis_cap"] = str(cap)

                amount = ROUND(Decimal(base) * Decimal(pct) / Decimal("100"))
                meta.update({"percent": str(pct), "percent_of": base_label})
                meta["raw_amount"] = str(amount)

                # optional month gating via pcg.payout_months
                pm = _parse_months_str(getattr(pcg, "payout_months", "") or "")
                if pm and (ctx.month not in pm):
                    amount = Decimal("0.00")
                    meta["off_cycle"] = "true"

            elif calc_method == "formula":
                expr = getattr(pcg, "formula_text", None) or getattr(sc, "formula_text", None) or "0"
                amount = ROUND(_safe_eval(expr, vars))
                meta["formula"] = expr
                meta["raw_amount"] = str(amount)

            else:  # flat
                flat = getattr(sc, "default_amount", None) or Decimal("0")
                amount = ROUND(flat)
                meta["flat"] = str(flat)
                meta["raw_amount"] = str(amount)
                pm = _parse_months_str(getattr(pcg, "payout_months", "") or "")
                if pm and (ctx.month not in pm):
                    amount = Decimal("0.00")
                    meta["off_cycle"] = "true"

            # ---------- overrides (amount or percent), then policy guards ----------
            ov = overrides.get(code)
            override_amount = None

            if ov:
                if ov.get("mode") == "amount":
                    override_amount = ROUND(Decimal(str(ov["value"])))
                    meta["override_type"] = "amount"
                elif ov.get("mode") == "percent":
                    basis_label = (
                        ov.get("basis")
                        or getattr(pcg, "percent_basis", None)
                        or (getattr(slab, "percent_of", None) if slab else None)
                        or "GROSS"
                    )
                    basis_val = vars.get(basis_label, Decimal("0"))
                    override_amount = ROUND(basis_val * Decimal(str(ov["value"])) / Decimal("100"))
                    meta.update({"override_type": "percent", "override_percent": str(ov["value"]), "override_basis": basis_label})

            provisional = override_amount if ov else amount

            # policy-driven caps / zeroing from config_json + metric slabs
            cap_amt = policy.cap_for(code, ps, repo_ctx, draft.ctc_annual, vars)
            if cap_amt is not None and provisional > cap_amt:
                provisional = cap_amt
                meta["capped_at"] = str(cap_amt)

            must_zero, reason = policy.should_zero(code, ps, repo_ctx, draft.ctc_annual, vars)
            if must_zero:
                provisional = Decimal("0.00")
                if reason: meta["skipped_by_policy"] = reason

            # ---------- persist & publish ----------
            line = existing.get(sc.family_id) or CompensationDraftLine(draft=draft, family=fam)
            line.code = code
            line.name = name
            line.component_type = ctype
            line.calc_method = calc_method
            line.priority = priority
            line.calc_amount = amount
            line.override_amount = override_amount
            line.final_amount = provisional
            line.metadata = meta
            line.save()

            out_lines.append(line)
            vars[code] = provisional  # downstream formulas use final numbers

        # ---------- CTC reconciliation (config + flags) ----------
        cfg = (getattr(ps, "config_json", None) or {})
        balancer_code = cfg.get("balancer_code") or "SPECIAL"
        allow_neg = bool(cfg.get("balancer_allow_negative", False))

        bal_line = draft.lines.filter(code=balancer_code).first()
        if bal_line:
            lines_now = list(draft.lines.all())

            # include lines per flags, but NEVER include the balancer in pre-sum
            included_inputs = []
            for l in lines_now:
                if l.code == balancer_code:  # avoid circular math
                    continue
                pcg_l = _pcg_for(l.family, ctx.entity_id, ctx.eff)
                if _flag_include_in_ctc(ps, l, pcg_l):
                    included_inputs.append(l)

            sum_inputs = sum(l.final_amount for l in included_inputs)
            residual = (draft.ctc_monthly - sum_inputs).quantize(Decimal("0.01"))
            if not allow_neg and residual < Decimal("0.00"):
                residual = Decimal("0.00")

            bal_line.calc_amount = residual
            if bal_line.override_amount is None:
                bal_line.final_amount = residual

            meta = bal_line.metadata or {}
            meta["reconciled"] = str(residual)
            bal_line.metadata = meta
            bal_line.save()
            vars[balancer_code] = bal_line.final_amount

        # ---------- Annualization (optional, helps CTC view) ----------
        if (cfg.get("enable_annual_summary", True)):
            lines_now = list(draft.lines.all())
            annual_totals: Dict[str, Decimal] = {}
            offcycle_earn_annual = Decimal("0.00")

            for l in lines_now:
                pcg_l = _pcg_for(l.family, ctx.entity_id, ctx.eff)
                slab = None
                slab_id = (l.metadata or {}).get("slab_id")
                if slab_id:
                    try: slab = Slab.objects.get(id=slab_id)
                    except Exception: slab = None

                occ = _occurrences_per_year(pcg_l, slab)
                try:
                    unit_amt = Decimal((l.metadata or {}).get("raw_amount", str(l.final_amount)))
                except Exception:
                    unit_amt = l.final_amount

                annual_amt = (unit_amt * occ).quantize(Decimal("0.01"))

                meta = l.metadata or {}
                meta["annual_occurrences"] = occ
                meta["annual_amount"] = str(annual_amt)
                l.metadata = meta
                l.save(update_fields=["metadata"])
                annual_totals[l.code] = annual_amt

                has_months = bool((slab and getattr(slab, "months", None)) or getattr(pcg_l, "payout_months", None))
                if l.component_type == "earning" and has_months and l.code != balancer_code:
                    offcycle_earn_annual += annual_amt

            # adjust SPECIAL annual so total annual matches CTC
            bal_line = next((x for x in lines_now if x.code == balancer_code), None)
            if bal_line:
                base_special = bal_line.final_amount
                special_annual = (base_special * Decimal("12") - offcycle_earn_annual).quantize(Decimal("0.01"))
                meta = bal_line.metadata or {}
                meta["annual_amount"] = str(special_annual)
                meta["annual_adjusted_for_offcycle"] = str(offcycle_earn_annual)
                bal_line.metadata = meta
                bal_line.save(update_fields=["metadata"])
                annual_totals[balancer_code] = special_annual

            # Build annual CTC = sum of lines included in CTC (using same flag logic)
            annual_ctc_from_breakup = Decimal("0.00")
            for l in lines_now:
                pcg_l = _pcg_for(l.family, ctx.entity_id, ctx.eff)
                if _flag_include_in_ctc(ps, l, pcg_l):
                    annual_ctc_from_breakup += annual_totals.get(l.code, Decimal("0.00"))

            ctx_json = draft.context or {}
            ctx_json["__annual_summary__"] = {
                "annual_from_breakup": str(annual_ctc_from_breakup.quantize(Decimal("0.01"))),
                "ctc_annual_input": str(draft.ctc_annual),
                "delta": str((Decimal(str(draft.ctc_annual)) - annual_ctc_from_breakup).quantize(Decimal("0.01")))
            }
            draft.context = ctx_json
            draft.save(update_fields=["context"])

        return draft.ctc_monthly, {l.code: l.final_amount for l in out_lines}
