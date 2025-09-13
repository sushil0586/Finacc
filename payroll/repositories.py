# payroll/repositories.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from django.db.models import Q

from payroll.models import SlabGroup, Slab

ROUND = lambda x: Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class RepoCtx:
    """
    Context used by PolicyRepo. You can pass values from your draft/context.
    """
    eff: datetime
    state: Optional[str] = None
    city_category: Optional[str] = None  # e.g., "METRO"/"NON_METRO"
    emp_grade: Optional[str] = None
    emp_rank: Optional[str] = None
    month: Optional[int] = None


class PolicyRepo:
    """
    Central policy access. All numbers/rates come from slabs you seeded.
    No hardcoded amounts inside the engine.
    """

    # ---------- effective-dated helpers ----------
    def _effective_qs(self, model, eff: datetime):
        return model.objects.filter(
            Q(effective_from__lte=eff) &
            (Q(effective_to__isnull=True) | Q(effective_to__gt=eff))
        )

    # ---------- scope/range matching (same semantics as engine) ----------
    def _scope_matches(self, scope: dict, ctc_annual: Decimal, ctx: RepoCtx) -> bool:
        if not scope:
            return True
        st = (ctx.state or "").upper()
        cat = (ctx.city_category or "").upper()
        grade = (ctx.emp_grade or "").upper()
        rank = (ctx.emp_rank or "").upper()

        if "state_in" in scope and st not in [str(x).upper() for x in scope["state_in"]]:
            return False
        if "emp_grade_in" in scope and grade not in [str(x).upper() for x in scope["emp_grade_in"]]:
            return False
        if "emp_rank_in" in scope and rank not in [str(x).upper() for x in scope["emp_rank_in"]]:
            return False
        if "city_category" in scope and cat != str(scope["city_category"]).upper():
            return False
        if "emp_grade_not_in" in scope and grade in [str(x).upper() for x in scope["emp_grade_not_in"]]:
            return False
        if "emp_rank_not_in" in scope and rank in [str(x).upper() for x in scope["emp_rank_not_in"]]:
            return False
        if "ctc_annual_min" in scope and Decimal(str(ctc_annual)) < Decimal(str(scope["ctc_annual_min"])):
            return False
        if "ctc_annual_max" in scope and Decimal(str(ctc_annual)) > Decimal(str(scope["ctc_annual_max"])):
            return False
        return True

    def _pick_slab(self, group_key: str, eff: datetime, ctc_annual: Decimal, ctx: RepoCtx) -> Optional[Slab]:
        sg = (self._effective_qs(SlabGroup, eff)
              .filter(group_key=group_key)
              .order_by("-effective_from")
              .first())
        if not sg:
            return None

        slabs = (self._effective_qs(Slab, eff)
                 .filter(group=sg)
                 .order_by("from_amount", "id"))

        for s in slabs:
            scope = getattr(s, "scope_json", {}) or {}
            if not self._scope_matches(scope, ctc_annual, ctx):
                continue
            fa = s.from_amount or Decimal("0")
            ta = s.to_amount
            if ta is None or (ctc_annual >= fa and ctc_annual <= ta):
                return s
        return None

    # ---------- generic readers ----------
    def read_decimal(
        self,
        group_key: str,
        eff: datetime,
        ctc_annual: Decimal,
        ctx: RepoCtx,
        default: Decimal = Decimal("0")
    ) -> Decimal:
        """Return slab.value for the effective slab in group_key (or default)."""
        s = self._pick_slab(group_key, eff, ctc_annual, ctx)
        return Decimal(s.value) if s else default

    # ---------- public hooks used by the engine ----------
    def cap_for(
        self,
        code: str,
        eff: datetime,
        ctc_annual: Decimal,
        ctx: RepoCtx,
        variables: dict
    ) -> Optional[Decimal]:
        """
        Return an absolute cap amount for a component (None if no cap applies).
        Example implemented: HRA cap via CAP_HRA slabs → (basis * pct).
        """
        if code.upper() == "HRA":
            slab = self._pick_slab("CAP_HRA", eff, ctc_annual, ctx)
            if not slab:
                return None
            pct = Decimal(slab.value)  # 50/40 etc from data
            # If your Slab model has 'percent_of' populated, you can honor it; fallback to BASIC
            basis_code = getattr(slab, "percent_of", None) or "BASIC"
            basis = Decimal(variables.get(basis_code, 0))
            return ROUND(basis * pct / Decimal(100))
        return None

    def should_zero(
        self,
        code: str,
        eff: datetime,
        ctc_annual: Decimal,
        ctx: RepoCtx,
        variables: dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Return (True, reason) when a component must be zeroed by policy.
        Example implemented: ESI zero when GROSS > ESI_THRESHOLD (from slab).
        """
        if code.upper() in {"ESI_EMP", "ESI_EMPR"}:
            thr = self.read_decimal("ESI_THRESHOLD", eff, ctc_annual, ctx, default=Decimal("21000"))
            gross = Decimal(variables.get("GROSS", 0))
            if gross > thr:
                return True, f"gross>{thr}"
        return False, None

    # ---------- optional helpers (for future use) ----------
    def percent_for(self, key, eff, ctc_annual, ctx: RepoCtx, default: Decimal) -> Decimal:
        # look up slab groups for rates (PF/ESI) by key; else return default
        return default

    def basis_cap_for(self, key, eff, ctc_annual, ctx: RepoCtx, default=None):
        return default

    def cap_for(self, code, eff, ctc_annual, ctx: RepoCtx, variables: dict):
        # HRA cap, etc. Return Decimal or None
        return None

    def should_zero(self, code, eff, ctc_annual, ctx: RepoCtx, variables: dict):
        # ESI threshold, month rules, etc. -> (True/False, reason)
        return (False, None)
