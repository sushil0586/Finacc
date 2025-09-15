from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional
from typing import Dict, Any, Optional, Tuple, Sequence

from django.apps import apps
from django.db import transaction
from django.db.models import Q
from .models import SlabGroup, Slab
from decimal import Decimal, InvalidOperation
from .models import RateType, SlabCycle  # adjust import paths if different
from django.utils import timezone
from payroll.models import EntityPayStructure
from uuid import uuid4


@dataclass
class DiffRow:
    family_id: int
    family_code: str
    action: str  # "create" | "noop" | "skip_disabled" | "warn"
    old_id: Optional[int]
    new_payload: Dict[str, Any]

def _resolve_global_for_item(item, eff_from: date):
    if item.pinned_global_component_id:
        return item.pinned_global_component
    PCG = apps.get_model(item._meta.app_label, "PayrollComponentGlobal")
    return (PCG.objects
            .filter(family=item.family, effective_from__lte=eff_from)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=eff_from))
            .order_by("-effective_from")
            .first())

def _epc_component_fk_is_pcg(EPC_model):
    try:
        f = EPC_model._meta.get_field("component")
        return f.remote_field.model._meta.object_name == "PayrollComponentGlobal"
    except Exception:
        return False

def _payload_from_item(item, g, entity_id: int, eff_from: date, eff_to: Optional[date], pin: bool) -> Dict[str, Any]:
    EPC = apps.get_model(item._meta.app_label, "EntityPayrollComponent")
    payload = dict(
        entity_id=entity_id,
        family_id=item.family_id,
        effective_from=eff_from,
        effective_to=eff_to,
        enabled=True,
        default_percent=item.default_percent,
        default_amount=item.default_amount,
        param_overrides=item.param_overrides or {},
        slab_scope_value=item.slab_scope_value,
        allow_emp_override=item.allow_emp_override,
        emp_min_percent=item.emp_min_percent,
        emp_max_percent=item.emp_max_percent,
        notes=f"Applied from PayStructure {item.template.code}",
    )
    if pin and _epc_component_fk_is_pcg(EPC):
        payload["component_id"] = g.id
    return payload

def _same_config(epc, payload: Dict[str, Any]) -> bool:
    fields = [
        "enabled", "default_percent", "default_amount",
        "param_overrides", "slab_scope_value",
        "allow_emp_override", "emp_min_percent", "emp_max_percent",
    ]
    for f in fields:
        if getattr(epc, f) != payload.get(f):
            return False
    if hasattr(epc, "component_id") and "component_id" in payload:
        if getattr(epc, "component_id") != payload["component_id"]:
            return False
    return True

def diff_structure_for_entity(*, structure, entity_id: int, eff_from: date, eff_to: Optional[date] = None) -> List[DiffRow]:
    EPC = apps.get_model(structure._meta.app_label, "EntityPayrollComponent")
    diffs: List[DiffRow] = []
    items = structure.items.select_related("family", "pinned_global_component").order_by("priority", "id")

    for item in items:
        fam = item.family
        if not item.enabled:
            diffs.append(DiffRow(family_id=fam.id, family_code=fam.code, action="skip_disabled", old_id=None, new_payload={}))
            continue

        g = _resolve_global_for_item(item, eff_from)
        if not g:
            diffs.append(DiffRow(family_id=fam.id, family_code=fam.code, action="warn", old_id=None,
                                 new_payload={"warning": "No active global version found"}))
            continue

        payload = _payload_from_item(item, g, entity_id, eff_from, eff_to, pin=bool(item.pinned_global_component_id))

        current = (EPC.objects
                   .filter(entity_id=entity_id, family_id=fam.id, effective_to__isnull=True)
                   .order_by("-effective_from")
                   .first())

        if current and _same_config(current, payload):
            diffs.append(DiffRow(family_id=fam.id, family_code=fam.code, action="noop", old_id=current.id, new_payload=payload))
        else:
            diffs.append(DiffRow(family_id=fam.id, family_code=fam.code, action="create",
                                 old_id=current.id if current else None, new_payload=payload))
    return diffs

def _model_has_field(model, field_name: str) -> bool:
    return any(f.name == field_name for f in model._meta.get_fields())

@transaction.atomic
def apply_structure_to_entity(
    *, structure, entity_id: int, eff_from: date, eff_to: Optional[date] = None,
    replace: bool = True, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Materialize PayStructure into EntityPayrollComponent from eff_from.

    Key changes to avoid join errors:
      - Resolve PayStructureComponent (PSC) ids for this structure up front.
      - Scope end-dating and lookups with component_id__in=<PSC ids> instead of joins.
      - Ensure payload has component_id for linkage.
      - Stamp applied_at / applied_run_id if those fields exist.
    """
    app_label = structure._meta.app_label
    EPC = apps.get_model(app_label, "EntityPayrollComponent")
    PSC = apps.get_model(app_label, "PayStructureComponent")

    # Compute the diffs
    diffs = diff_structure_for_entity(structure=structure, entity_id=entity_id, eff_from=eff_from, eff_to=eff_to)
    if dry_run:
        return {"dry_run": True, "diff": [d.__dict__ for d in diffs]}

    # Run metadata
    run_id = uuid4().hex[:12]
    now = timezone.now()
    has_applied_at = _model_has_field(EPC, "applied_at")
    has_applied_run_id = _model_has_field(EPC, "applied_run_id")

    created_ids: List[int] = []
    updated_ids: List[int] = []

    # Families that will have rows at eff_from
    affected_family_ids = {d.family_id for d in diffs if d.action in ("create", "noop")}

    # Map family_id -> PSC.id for this structure (no joins later)
    psc_qs = PSC.objects.filter(template_id=getattr(structure, "id"))
    if affected_family_ids:
        psc_qs = psc_qs.filter(family_id__in=list(affected_family_ids))
    psc_by_family: Dict[int, int] = dict(psc_qs.values_list("family_id", "id"))
    psc_ids: List[int] = list(psc_by_family.values())

    # End-date open rows from THIS structure only (via PSC ids)
    if replace and psc_ids:
        (EPC.objects
            .filter(
                entity_id=entity_id,
                component_id__in=psc_ids,
                effective_to__isnull=True,
            )
            .update(effective_to=eff_from))

    for d in diffs:
        if d.action not in ("create", "noop"):
            continue

        payload = d.new_payload.copy()
        payload.setdefault("entity_id", entity_id)

        # Ensure component_id present for the EPC row linkage
        psc_id = psc_by_family.get(d.family_id)
        if psc_id and "component_id" not in payload and "component" not in payload:
            payload["component_id"] = psc_id

        # Stamp run metadata if columns exist
        if has_applied_at:
            payload["applied_at"] = now
        if has_applied_run_id:
            payload["applied_run_id"] = run_id

        # Same-day row produced by THIS structure (filter by component_id if available)
        same_day_filter = {
            "entity_id": entity_id,
            "family_id": d.family_id,
            "effective_from": eff_from,
        }
        if psc_id:
            same_day_filter["component_id"] = psc_id

        existing_same_day = (
            EPC.objects
            .filter(**same_day_filter)
            .order_by("-id")
            .first()
        )

        if existing_same_day and _same_config(existing_same_day, payload):
            touched = False
            if has_applied_at and getattr(existing_same_day, "applied_at", None) != now:
                existing_same_day.applied_at = now; touched = True
            if has_applied_run_id and getattr(existing_same_day, "applied_run_id", None) != run_id:
                existing_same_day.applied_run_id = run_id; touched = True
            if touched:
                existing_same_day.save(update_fields=[
                    *(["applied_at"] if has_applied_at else []),
                    *(["applied_run_id"] if has_applied_run_id else []),
                ])
                updated_ids.append(existing_same_day.id)
            continue

        if existing_same_day:
            for k, v in payload.items():
                setattr(existing_same_day, k, v)
            existing_same_day.save()
            created_ids.append(existing_same_day.id)
            updated_ids.append(existing_same_day.id)
            continue

        obj = EPC.objects.create(**payload)
        created_ids.append(obj.id)

    return {
        "dry_run": False,
        "applied_run_id": run_id,
        "created_epc_ids": created_ids,
        "updated_epc_ids": updated_ids,
        "diff": [d.__dict__ for d in diffs],
    }

def record_pay_structure_assignment(*, entity_id: int, pay_structure, eff_from, status: str = "active", note: str = ""):
    """
    Create or update an assignment row for reporting/discovery.
    eff_from can be date or aware datetime; store as aware datetime.
    """
    from datetime import datetime, time
    from django.db import models as djm

    # Normalize to aware datetime
    if isinstance(eff_from, datetime):
        eff = eff_from
    else:
        eff = timezone.make_aware(datetime.combine(eff_from, time.min), timezone.get_current_timezone())

    obj, created = EntityPayStructure.objects.get_or_create(
        entity_id=entity_id,
        pay_structure=pay_structure,
        effective_from=eff,
        defaults={"status": status, "note": note},
    )
    if not created:
        changed = False
        if obj.status != status:
            obj.status = status; changed = True
        if note and obj.note != note:
            obj.note = note; changed = True
        if changed: obj.save(update_fields=["status", "note"])
    return obj

@dataclass
class SlabResolution:
    group: SlabGroup
    slab: Slab
    reason: str
    score: int

def get_active_slab_group(group_key: str, on: date) -> Optional[SlabGroup]:
    """Resolve the SlabGroup version active on 'on'."""
    return (SlabGroup.objects
            .filter(group_key=group_key, effective_from__lte=on)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on))
            .order_by("-effective_from")
            .first())

def resolve_slab(
    *,
    group: SlabGroup | None = None,
    group_key: str | None = None,
    on: date,
    band_value: Decimal,
    context: Dict[str, Any],
) -> Optional[SlabResolution]:
    """
    Pick the best slab row inside a group for a given 'band_value' and 'context'.

    - 'group' OR 'group_key' must be provided.
    - 'band_value' is the numeric used against from_amount/to_amount (e.g., CTC_MONTHLY, BASIC, etc.),
      chosen earlier by your PCG.slab_base.
    - 'context' is any info used by scopes, e.g. {"state":"KA","emp_grade":"G3","city_category":"METRO","ctc_annual":1200000}.
    """
    if group is None:
        if not group_key:
            raise ValueError("Provide either group or group_key.")
        group = get_active_slab_group(group_key, on)
        if not group:
            return None

    # Candidates: effective on date + band matches + month is applicable
    cands: list[Slab] = []
    for s in (group.slabs
              .filter(effective_from__lte=on)
              .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on))):
        if not _band_matches(s, band_value):
            continue
        if not _cycle_month_applicable(s, on):
            continue
        if not _scope_matches(s.scope_json or {}, context):
            continue
        cands.append(s)

    if not cands:
        return None

    # Rank: most-specific scope wins, then newer version, then higher from_amount
    cands.sort(
        key=lambda s: (
            _specificity_score(s.scope_json or {}),
            s.effective_from or date.min,
            s.from_amount or Decimal("0"),
        ),
        reverse=True,
    )
    top = cands[0]
    return SlabResolution(group=group, slab=top, reason="best_match", score=_specificity_score(top.scope_json or {}))

def compute_slab_amount(
    slab: Slab,
    bases: Dict[str, Decimal],
) -> Decimal:
    """
    Turn a slab row into a money amount given 'bases' (e.g. {"CTC_MONTHLY": 100000, "BASIC": 40000}).
    - PERCENT: uses slab.percent_of to pick basis; returns (value % of basis)
    - AMOUNT / MONTHLY: returns slab.value as-is (you can post-adjust for cycle if you need)
    """
    if slab.rate_type == RateType.PERCENT:
        basis_name = (slab.percent_of or "").strip()
        if not basis_name:
            raise ValueError("percent_of is required for PERCENT slabs.")
        try:
            basis = Decimal(str(bases[basis_name]))
        except KeyError:
            raise KeyError(f"Missing basis '{basis_name}' in bases.")
        return (Decimal(slab.value) / Decimal("100")) * basis

    # Treat other rate types as fixed amounts (extend if you have more)
    return Decimal(slab.value)


# --- internals: band, month/cycle, scopes, specificity -----------------------

def _to_dec(x) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError):
        return None

def _band_matches(s: Slab, v: Decimal) -> bool:
    v = Decimal(str(v))
    lo = s.from_amount
    hi = s.to_amount if s.to_amount is not None else v  # open-ended: treat as >= lo
    return not (v < lo or hi < v)  # closed interval [lo, hi]

_MONTHS = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}
def _month_name(d: date) -> str:
    return d.strftime("%b")  # 'Jan', 'Feb', ...

def _parse_months_field(months: str) -> set[str]:
    if not months:
        return set()
    return {m.strip() for m in months.split(",") if m.strip()}

def _cycle_month_applicable(s: Slab, on: date) -> bool:
    wanted = _parse_months_field(s.months)
    if s.cycle == SlabCycle.MONTHLY:
        # If months listed, honor them as "book only in these months"
        return (not wanted) or (_month_name(on) in wanted)
    if s.cycle in (SlabCycle.YEARLY, SlabCycle.HALF_YEARLY):
        # If months listed, require match; else allow all months (you can tighten as needed)
        return (not wanted) or (_month_name(on) in wanted)
    return True

def _as_set(v) -> Optional[set[str]]:
    if v is None:
        return None
    if isinstance(v, (list, tuple, set)):
        return set(map(str, v))
    return {str(v)}

def _collect_range(scope: dict, base: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    mn = mx = None
    nested = scope.get(base)
    if isinstance(nested, dict):
        mn = _to_dec(nested.get("min"))
        mx = _to_dec(nested.get("max"))
    if mn is None:
        mn = _to_dec(scope.get(f"{base}_min"))
    if mx is None:
        mx = _to_dec(scope.get(f"{base}_max"))
    return mn, mx

def _intervals_disjoint(a_min, a_max, b_min, b_max) -> bool:
    lo1 = a_min if a_min is not None else Decimal("-Infinity")
    hi1 = a_max if a_max is not None else Decimal("Infinity")
    lo2 = b_min if b_min is not None else Decimal("-Infinity")
    hi2 = b_max if b_max is not None else Decimal("Infinity")
    return hi1 < lo2 or hi2 < lo1

def _scope_key_matches_eq(key: str, expected: Any, ctx: Dict[str, Any]) -> bool:
    # equality: ctx[key] must equal expected (string-wise)
    ctx_val = ctx.get(key, None)
    if ctx_val is None:
        return False
    return str(ctx_val) == str(expected)

def _scope_key_matches_in(base: str, allowed: Sequence[Any], ctx: Dict[str, Any]) -> bool:
    ctx_val = ctx.get(base, None)
    if ctx_val is None:
        return False
    return str(ctx_val) in set(map(str, allowed))

def _scope_key_matches_not_in(base: str, banned: Sequence[Any], ctx: Dict[str, Any]) -> bool:
    ctx_val = ctx.get(base, None)
    if ctx_val is None:
        return True  # missing value does not violate a NOT IN constraint
    return str(ctx_val) not in set(map(str, banned))

def _scope_key_matches_range(base: str, mn: Optional[Decimal], mx: Optional[Decimal], ctx: Dict[str, Any]) -> bool:
    v = _to_dec(ctx.get(base))
    if v is None:
        return False
    if mn is not None and v < mn:
        return False
    if mx is not None and v > mx:
        return False
    return True

def _scope_matches(scope: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    """
    A scope matches the context if ALL constraints hold.
    Supports:
      - equality:      {"city_category": "METRO"}
      - membership:    {"emp_grade_in": ["G3","G4"]}, {"dept_not_in": ["FIN"]}
      - numeric:       {"ctc_annual_min": 0, "ctc_annual_max": 180000}
                       {"ctc_annual": {"min":0, "max":180000}}
      - mirrored state: {"state_in":["KA"]} if you kept state_scope
    """
    if not scope:
        return True  # catch-all

    for key, val in scope.items():
        if key.endswith("_in"):
            base = key[:-3]
            if not _scope_key_matches_in(base, val, ctx):
                return False
        elif key.endswith("_not_in"):
            base = key[:-7]
            if not _scope_key_matches_not_in(base, val, ctx):
                return False
        elif key.endswith("_min") or key.endswith("_max") or (isinstance(val, dict) and {"min","max"} & set(val.keys())):
            base = key.split("_")[0] if key.endswith(("_min","_max")) else key
            mn, mx = _collect_range(scope, base)
            if not _scope_key_matches_range(base, mn, mx, ctx):
                return False
        else:
            # equality
            if not _scope_key_matches_eq(key, val, ctx):
                return False
    return True

def _specificity_score(scope: Dict[str, Any]) -> int:
    """
    Higher = more specific.
    - +20 per constrained key
    - +len(set) for *_in values
    - +5 for equality key
    - +3 if a key has numeric bounds
    """
    if not scope:
        return 0
    score = 0
    for k, v in scope.items():
        score += 20
        if k.endswith("_in"):
            score += len(_as_set(v) or [])
        elif k.endswith("_not_in"):
            score += len(_as_set(v) or []) // 2  # weaker than IN
        elif k.endswith("_min") or k.endswith("_max") or (isinstance(v, dict) and {"min","max"} & set(v.keys())):
            score += 3
        else:
            score += 5  # equality
    return score
