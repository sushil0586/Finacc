# payroll/repositories.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any
import re

from django.db.models import Q

from payroll.models import (
    SlabGroup, Slab,
    ComponentFamily, PayrollComponentGlobal, PayStructureComponent, PayStructure
)

# ---------- runtime context ----------
@dataclass
class RepoCtx:
    eff: any                 # aware datetime
    entity_id: Optional[int] = None
    state: Optional[str] = None
    city_category: Optional[str] = None
    emp_grade: Optional[str] = None
    emp_rank: Optional[str] = None
    month: Optional[int] = None

# ---------- helpers ----------
def _effective_qs(model, eff):
    """
    Effective-dated filter if fields exist; otherwise return all().
    Works for SlabGroup/Slab/PCG and any model with effective_* fields.
    """
    field_names = {f.name for f in model._meta.get_fields()}
    qs = model.objects.all()
    if "effective_from" in field_names:
        qs = qs.filter(effective_from__lte=eff)
    if "effective_to" in field_names:
        qs = qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=eff))
    return qs

def _scope_match(scope: Dict[str, Any], ctx: RepoCtx, ctc_annual: Decimal) -> bool:
    if not scope: return True
    def S(x): return "" if x is None else str(x)
    def _in(v, arr): return v is not None and S(v) in {S(x) for x in arr}

    if "state_in" in scope and not _in(ctx.state, scope["state_in"]): return False
    if "state_not_in" in scope and _in(ctx.state, scope["state_not_in"]): return False
    if "city_category" in scope and S(scope["city_category"]) != S(ctx.city_category): return False
    if "emp_grade_in" in scope and not _in(ctx.emp_grade, scope["emp_grade_in"]): return False
    if "emp_grade_not_in" in scope and _in(ctx.emp_grade, scope["emp_grade_not_in"]): return False
    if "emp_rank_in" in scope and not _in(ctx.emp_rank, scope["emp_rank_in"]): return False
    if "emp_rank_not_in" in scope and _in(ctx.emp_rank, scope["emp_rank_not_in"]): return False
    if "ctc_annual_min" in scope and Decimal(str(ctc_annual)) < Decimal(str(scope["ctc_annual_min"])): return False
    if "ctc_annual_max" in scope and Decimal(str(ctc_annual)) > Decimal(str(scope["ctc_annual_max"])): return False
    return True

def _pick_slab(group: SlabGroup, ctx: RepoCtx, ctc_annual: Decimal, base_value: Decimal) -> Optional[Slab]:
    """
    Pick the first effective slab whose scope matches and for which
    base_value lies in [from_amount, to_amount] (to_amount may be NULL = open-ended).
    """
    slabs = _effective_qs(Slab, ctx.eff).filter(group=group).order_by("id")
    for s in slabs:
        if not _scope_match(getattr(s, "scope_json", {}) or {}, ctx, ctc_annual):
            continue
        lo = Decimal(str(getattr(s, "from_amount", 0) or 0))
        hi = getattr(s, "to_amount", None)
        if hi is None:
            if base_value >= lo:
                return s
        else:
            if lo <= base_value <= Decimal(str(hi)):
                return s
    return None

# ---------- safe expression ----------
_ALLOWED_NAMES = {"min": min, "max": max, "Decimal": Decimal}
_METRIC_RE = re.compile(r"METRIC\(\s*'([^']+)'\s*\)")

def _eval_policy_expr(expr: str, variables: Dict[str, Decimal]) -> Decimal | bool:
    """
    Evaluate a tiny expression language over current variables.
    SECURITY: __builtins__ disabled; only min/max/Decimal + numeric variables allowed.
    Return type depends on expression (bool for zero_if rules, Decimal for caps).
    """
    code = compile(expr, "<policy-expr>", "eval")
    return eval(code, {"__builtins__": {}}, {**_ALLOWED_NAMES, **variables})

# ---------- repository ----------
class PolicyRepo:
    """
    Reads all policy knobs from:
      • SlabGroup/Slab (“metrics”) seeded by admin (e.g., ESI thresholds, HRA cap %)
      • PayStructure.config_json (caps & zero_if expressions, CTC includes/excludes)
      • PCG/PSC (include_in_ctc flags, basis caps, etc.)
    No thresholds or rates are hardcoded here.
    """

    # ---- METRIC('KEY') support (values from SlabGroup.group_key == KEY) ----
    def metric(self, key: str, ctx: RepoCtx, ctc_annual: Decimal, base_value: Decimal = Decimal("0")) -> Optional[Decimal]:
        """
        Resolve a numeric metric via slabs. E.g., METRIC('ESI_THRESHOLD_2025').
        Scope and bands (from/to) are honored against ctx and base_value.
        """
        g = _effective_qs(SlabGroup, ctx.eff).filter(group_key=key).order_by("-effective_from").first()
        if not g: return None
        s = _pick_slab(g, ctx, ctc_annual, base_value)
        if not s: return None
        try:
            return Decimal(str(s.value))
        except InvalidOperation:
            return None

    def replace_metrics(self, expr: str, ctx: RepoCtx, ctc_annual: Decimal, vars_for_pick: Dict[str, Decimal]) -> str:
        """
        Replace METRIC('KEY') with numeric literals looked up from metrics().
        Uses vars_for_pick['GROSS'] as the band base by default (sensible for PT/thresholds).
        """
        def repl(m):
            key = m.group(1)
            base = vars_for_pick.get("GROSS", Decimal("0")) or Decimal("0")
            val = self.metric(key, ctx, ctc_annual, base_value=base)
            return str(val if val is not None else "0")
        return _METRIC_RE.sub(repl, expr)

    # ---- Policy: caps & zero rules (read from PayStructure.config_json) ----
    def cap_for(self, code: str, ps: PayStructure, ctx: RepoCtx,
                ctc_annual: Decimal, variables: Dict[str, Decimal]) -> Optional[Decimal]:
        """
        ps.config_json['caps'][CODE] => expression returning a Decimal cap.
        Expression may reference variables (BASIC/GROSS/…) and METRIC('KEY').
        """
        cfg = (getattr(ps, "config_json", None) or {})
        caps = cfg.get("caps") or {}
        expr = caps.get(code)
        if not expr: return None
        expr2 = self.replace_metrics(expr, ctx, ctc_annual, variables)
        try:
            val = _eval_policy_expr(expr2, variables)
            return Decimal(str(val))
        except Exception:
            return None

    def should_zero(self, code: str, ps: PayStructure, ctx: RepoCtx,
                    ctc_annual: Decimal, variables: Dict[str, Decimal]) -> tuple[bool, Optional[str]]:
        """
        ps.config_json['zero_if'][CODE] => boolean expression.
        If True, the component is zeroed out (reason is returned for metadata).
        """
        cfg = (getattr(ps, "config_json", None) or {})
        zmap = cfg.get("zero_if") or {}
        expr = zmap.get(code)
        if not expr: return (False, None)
        expr2 = self.replace_metrics(expr, ctx, ctc_annual, variables)
        try:
            ok = bool(_eval_policy_expr(expr2, variables))
            return (ok, expr2 if ok else None)
        except Exception:
            return (False, None)

    # ---- Resolution helpers (used by engine for flags & defaults) ----
    def pcg_for(self, family, entity_id: Optional[int], eff):
        """Resolve PCG by family/entity/effective date (entity override preferred)."""
        qs = (_effective_qs(PayrollComponentGlobal, eff)
              .filter(family=family)
              .filter(Q(entity_id=entity_id) | Q(entity__isnull=True)))
        return qs.order_by("-entity_id", "priority", "id").first()

    def psc_for(self, ps: PayStructure, family):
        """Fetch structure line (PSC) for flags like include_in_ctc, default_percent, etc."""
        return PayStructureComponent.objects.filter(template=ps, family=family).first()
