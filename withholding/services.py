from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from django.db.models import Q, Sum
from django.utils import timezone

from withholding.models import (
    EntityTcsThresholdOpening,
    EntityPartyTaxProfile,
    TcsComputation,
    WithholdingSection,
    WithholdingTaxType,
    EntityWithholdingConfig,
    PartyTaxProfile,
    ResidencyStatus,
    WithholdingBaseRule,
)
try:
    from financial.models import AccountComplianceProfile
    from financial.models import AccountAddress
except Exception:  # pragma: no cover - keeps withholding module resilient if financial app is unavailable.
    AccountComplianceProfile = None
    AccountAddress = None

ZERO2 = Decimal("0.00")

def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


def _is_legacy_206c1h_section(section: WithholdingSection | None) -> bool:
    code = (getattr(section, "section_code", "") or "").strip().upper()
    return code in {"206C(1H)", "206C1H"}


def _threshold_policy(section: WithholdingSection | None) -> dict:
    policy = getattr(section, "applicability_json", None)
    if not isinstance(policy, dict):
        policy = {}
    mode = str(policy.get("threshold_mode") or "single_txn").strip().lower()
    if mode not in {"single_txn", "cumulative"}:
        mode = "single_txn"
    return {"mode": mode}


def _cumulative_206c1h_base_before_doc(
    *,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    section_id: int | None,
    party_account_id: int | None,
    doc_date: date,
    exclude_doc: tuple[str, str, int] | None = None,
) -> Decimal:
    if not party_account_id:
        return ZERO2
    fy, _, _ = determine_fy_quarter(doc_date)
    qs = TcsComputation.objects.filter(
        entity_id=entity_id,
        party_account_id=party_account_id,
        fiscal_year=fy,
        section__section_code__in=["206C(1H)", "206C1H"],
    ).exclude(status=TcsComputation.Status.REVERSED)
    if exclude_doc:
        mod, dtype, did = exclude_doc
        qs = qs.exclude(module_name=mod, document_type=dtype, document_id=did)
    total = qs.aggregate(v=Sum("tcs_base_amount")).get("v") or ZERO2
    opening_qs = EntityTcsThresholdOpening.objects.filter(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        party_account_id=party_account_id,
        is_active=True,
    )
    if subentity_id is not None:
        opening_qs = opening_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    else:
        opening_qs = opening_qs.filter(subentity__isnull=True)
    if section_id:
        opening_qs = opening_qs.filter(section_id=section_id)
    opening_qs = opening_qs.filter(effective_from__lte=doc_date)
    opening = opening_qs.aggregate(v=Sum("opening_base_amount")).get("v") or ZERO2
    return q2(total + q2(opening))


def _apply_section_threshold(
    *,
    section: WithholdingSection,
    base_amount: Decimal,
    doc_date: date,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    party_account_id: int | None,
    exclude_doc: tuple[str, str, int] | None = None,
) -> tuple[Decimal, str | None, str | None]:
    """
    Returns (taxable_base_after_threshold, reason, reason_code).
    Backward compatible default is single-transaction threshold.
    For 206C(1H), supports cumulative mode via applicability_json.threshold_mode="cumulative".
    """
    threshold = q2(getattr(section, "threshold_default", None) or ZERO2)
    if threshold <= ZERO2:
        return q2(base_amount), None, None

    current = q2(base_amount)
    policy = _threshold_policy(section)
    if not _is_legacy_206c1h_section(section) or policy["mode"] != "cumulative":
        if current < threshold:
            return ZERO2, f"Below threshold ({threshold})", "BELOW_THRESHOLD"
        return current, None, None

    previous = _cumulative_206c1h_base_before_doc(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        section_id=getattr(section, "id", None),
        party_account_id=party_account_id,
        doc_date=doc_date,
        exclude_doc=exclude_doc,
    )
    cumulative = q2(previous + current)
    if previous >= threshold:
        return current, "Threshold already crossed in FY (cumulative mode).", "THRESHOLD_ALREADY_CROSSED"
    if cumulative <= threshold:
        return ZERO2, f"Below cumulative threshold ({threshold})", "BELOW_THRESHOLD_CUMULATIVE"
    taxable = q2(cumulative - threshold)
    return taxable, "Threshold crossed in current transaction (cumulative mode).", "THRESHOLD_CROSSED_CUMULATIVE"

@dataclass(frozen=True)
class WithholdingResult:
    enabled: bool
    section: Optional[WithholdingSection]
    rate: Decimal
    base_amount: Decimal
    amount: Decimal
    reason: Optional[str] = None
    reason_code: Optional[str] = None
    no_pan_applied: bool = False
    sec_206ab_applied: bool = False
    lower_rate_applied: bool = False


@dataclass(frozen=True)
class RateResolution:
    rate: Decimal
    reason: Optional[str]
    reason_code: Optional[str]
    no_pan_applied: bool = False
    sec_206ab_applied: bool = False
    lower_rate_applied: bool = False


class WithholdingResolver:
    @staticmethod
    def _as_lower_set(value) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            return {str(v).strip().lower() for v in value if str(v).strip()}
        raw = str(value).strip()
        return {raw.lower()} if raw else set()

    @staticmethod
    def resolve_party_country_code(*, party_account_id: int | None) -> Optional[str]:
        if not party_account_id or AccountAddress is None:
            return None
        country_code = (
            AccountAddress.objects.filter(account_id=party_account_id, isactive=True)
            .order_by("-isprimary", "-id")
            .values_list("country__countrycode", flat=True)
            .first()
        )
        cc = str(country_code or "").strip().upper()
        return cc or None

    @staticmethod
    def resolve_party_residency(*, party_account_id: int | None, resident_country_codes=None) -> str:
        resident_codes = WithholdingResolver._as_lower_set(resident_country_codes or ["IN"])
        country_code = WithholdingResolver.resolve_party_country_code(party_account_id=party_account_id)
        if not country_code:
            return "unknown"
        return "resident" if country_code.lower() in resident_codes else "non_resident"

    @staticmethod
    def resolve_party_profile(
        *,
        party_account_id: int | None,
        entity_id: int | None = None,
        subentity_id: int | None = None,
    ) -> Optional[PartyTaxProfile]:
        """
        Resolve withholding profile with backward-compatible PAN fallback:
        1) PartyTaxProfile (primary source)
        2) AccountComplianceProfile.pan (normalized profile maintained in financial module)
        """
        if not party_account_id:
            return None

        profile = PartyTaxProfile.objects.filter(party_account_id=party_account_id).first()
        entity_profile = None
        if entity_id:
            scoped_qs = EntityPartyTaxProfile.objects.filter(
                entity_id=int(entity_id),
                party_account_id=party_account_id,
                is_active=True,
            )
            if subentity_id is not None:
                entity_profile = (
                    scoped_qs.filter(subentity_id=int(subentity_id))
                    .order_by("-id")
                    .first()
                )
            if not entity_profile:
                entity_profile = (
                    scoped_qs.filter(subentity__isnull=True)
                    .order_by("-id")
                    .first()
                )

        def _apply_entity_overrides(base_obj):
            if not base_obj or not entity_profile:
                return base_obj
            payload = dict(getattr(base_obj, "__dict__", {}))
            payload.update(
                {
                    "is_exempt_withholding": bool(getattr(entity_profile, "is_exempt_withholding", False)),
                    "is_specified_person_206ab": bool(getattr(entity_profile, "is_specified_person_206ab", False)),
                    "specified_person_valid_from": getattr(entity_profile, "specified_person_valid_from", None),
                    "specified_person_valid_to": getattr(entity_profile, "specified_person_valid_to", None),
                    "lower_deduction_rate": getattr(entity_profile, "lower_deduction_rate", None),
                    "lower_deduction_valid_from": getattr(entity_profile, "lower_deduction_valid_from", None),
                    "lower_deduction_valid_to": getattr(entity_profile, "lower_deduction_valid_to", None),
                    "residency_status": getattr(entity_profile, "residency_status", None),
                    "tax_identifier": getattr(entity_profile, "tax_identifier", None),
                    "declaration_reference": getattr(entity_profile, "declaration_reference", None),
                    "treaty_article": getattr(entity_profile, "treaty_article", None),
                    "treaty_rate": getattr(entity_profile, "treaty_rate", None),
                    "treaty_valid_from": getattr(entity_profile, "treaty_valid_from", None),
                    "treaty_valid_to": getattr(entity_profile, "treaty_valid_to", None),
                    "surcharge_rate": getattr(entity_profile, "surcharge_rate", None),
                    "cess_rate": getattr(entity_profile, "cess_rate", None),
                }
            )
            return SimpleNamespace(**payload)

        if profile:
            # Keep explicit profile settings, but allow PAN fallback from normalized compliance profile.
            has_pan_in_party_profile = bool((getattr(profile, "pan", None) or "").strip()) or bool(
                getattr(profile, "is_pan_available", False)
            )
            if not has_pan_in_party_profile and AccountComplianceProfile is not None:
                compliance_pan = (
                    AccountComplianceProfile.objects.filter(account_id=party_account_id)
                    .values_list("pan", flat=True)
                    .first()
                )
                if compliance_pan and str(compliance_pan).strip():
                    payload = dict(getattr(profile, "__dict__", {}))
                    payload["pan"] = str(compliance_pan).strip()
                    payload["is_pan_available"] = True
                    shadow = SimpleNamespace(**payload)
                    return _apply_entity_overrides(shadow)
            return _apply_entity_overrides(profile)

        if AccountComplianceProfile is None:
            return None

        compliance_pan = (
            AccountComplianceProfile.objects.filter(account_id=party_account_id).values_list("pan", flat=True).first()
        )
        if not compliance_pan or not str(compliance_pan).strip():
            return None

        # Minimal synthetic profile for rate resolution where only PAN availability is known.
        synthetic = SimpleNamespace(
            party_account_id=party_account_id,
            pan=str(compliance_pan).strip(),
            is_pan_available=True,
            is_exempt_withholding=False,
            is_specified_person_206ab=False,
            specified_person_valid_from=None,
            specified_person_valid_to=None,
            lower_deduction_rate=None,
            lower_deduction_valid_from=None,
            lower_deduction_valid_to=None,
            residency_status=ResidencyStatus.UNKNOWN,
            tax_identifier=None,
            declaration_reference=None,
            treaty_article=None,
            treaty_rate=None,
            treaty_valid_from=None,
            treaty_valid_to=None,
            surcharge_rate=None,
            cess_rate=None,
        )
        return _apply_entity_overrides(synthetic)

    @staticmethod
    def _within_window(*, doc_date: date, start_date: date | None, end_date: date | None) -> bool:
        if start_date and doc_date < start_date:
            return False
        if end_date and doc_date > end_date:
            return False
        return True

    @staticmethod
    def validate_section_195_requirements(
        *,
        section: WithholdingSection,
        party_profile,
        party_account_id: int | None,
        doc_date: date,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        code = (section.section_code or "").strip().upper()
        if code != "195":
            return True, None, None

        declared_residency = str(getattr(party_profile, "residency_status", "") or "").strip().lower()
        if declared_residency not in {"resident", "non_resident"}:
            declared_residency = WithholdingResolver.resolve_party_residency(
                party_account_id=party_account_id,
                resident_country_codes=(section.applicability_json or {}).get("resident_country_codes")
                if isinstance(section.applicability_json, dict)
                else None,
            )
        if declared_residency != "non_resident":
            return False, "Section 195 requires non-resident party profile.", "SEC195_NON_RESIDENT_REQUIRED"

        declaration_reference = str(getattr(party_profile, "declaration_reference", "") or "").strip()
        tax_identifier = str(getattr(party_profile, "tax_identifier", "") or "").strip()
        has_pan = bool((getattr(party_profile, "pan", None) or "").strip()) or bool(
            getattr(party_profile, "is_pan_available", False)
        )
        if not (has_pan or tax_identifier):
            return False, "Missing PAN / Tax Identifier for section 195.", "SEC195_TAX_ID_REQUIRED"

        treaty_rate = getattr(party_profile, "treaty_rate", None)
        if treaty_rate is not None:
            valid = WithholdingResolver._within_window(
                doc_date=doc_date,
                start_date=getattr(party_profile, "treaty_valid_from", None),
                end_date=getattr(party_profile, "treaty_valid_to", None),
            )
            if valid and not declaration_reference:
                return False, "Treaty rate configured but declaration reference is missing.", "SEC195_DECLARATION_REQUIRED"

        return True, None, None

    @staticmethod
    def evaluate_section_applicability(*, section: WithholdingSection, party_account_id: int | None) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Config-driven applicability hook from section.applicability_json.
        Supported keys:
          - resident_status: "resident" | "non_resident" | ["resident", ...]
          - resident_country_codes: ["IN", ...] (default: ["IN"])
          - party_country_codes: ["IN", "AE", ...]
        """
        policy = section.applicability_json if isinstance(section.applicability_json, dict) else {}
        if not policy:
            return True, None, None

        allowed_residency = WithholdingResolver._as_lower_set(policy.get("resident_status"))
        if allowed_residency:
            residency = WithholdingResolver.resolve_party_residency(
                party_account_id=party_account_id,
                resident_country_codes=policy.get("resident_country_codes"),
            )
            if residency != "unknown" and residency not in allowed_residency:
                return False, f"Section not applicable for party residency '{residency}'", "NOT_APPLICABLE_RESIDENCY"

        allowed_country_codes = {c.upper() for c in WithholdingResolver._as_lower_set(policy.get("party_country_codes"))}
        if allowed_country_codes:
            country_code = WithholdingResolver.resolve_party_country_code(party_account_id=party_account_id)
            if country_code and country_code.upper() not in allowed_country_codes:
                return False, f"Section not applicable for country '{country_code}'", "NOT_APPLICABLE_COUNTRY"

        return True, None, None

    @staticmethod
    def get_entity_config(*, entity_id: int, entityfin_id: int, subentity_id: int | None, doc_date: date) -> Optional[EntityWithholdingConfig]:
        qs = EntityWithholdingConfig.objects.filter(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            effective_from__lte=doc_date,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True).order_by("-effective_from", "-id")
        else:
            # Prefer subentity-specific config; fallback to entity-level (subentity NULL).
            qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True)).order_by(
                "-subentity_id", "-effective_from", "-id"
            )
        return qs.first()

    @staticmethod
    def resolve_section(*, tax_type: int, explicit_section_id: int | None, cfg: Optional[EntityWithholdingConfig], doc_date: date) -> Optional[WithholdingSection]:
        if explicit_section_id:
            sec = WithholdingSection.objects.filter(id=explicit_section_id, tax_type=tax_type, is_active=True).first()
            if sec:
                if sec.effective_from and sec.effective_from > doc_date:
                    return None
                if sec.effective_to and sec.effective_to < doc_date:
                    return None
                return sec

        if not cfg:
            return None

        sec = cfg.default_tds_section if tax_type == WithholdingTaxType.TDS else cfg.default_tcs_section
        if not sec:
            return None

        # Ensure section is valid for doc_date
        if sec.effective_from and sec.effective_from > doc_date:
            return None
        if sec.effective_to and sec.effective_to < doc_date:
            return None

        return sec

    @staticmethod
    def _is_206ab_applicable(*, party_profile: Optional[PartyTaxProfile], doc_date: date) -> bool:
        if not party_profile or not bool(getattr(party_profile, "is_specified_person_206ab", False)):
            return False
        valid_from = getattr(party_profile, "specified_person_valid_from", None)
        valid_to = getattr(party_profile, "specified_person_valid_to", None)
        if valid_from and doc_date < valid_from:
            return False
        if valid_to and doc_date > valid_to:
            return False
        return True

    @staticmethod
    def resolve_rate(*, section: WithholdingSection, party_profile: Optional[PartyTaxProfile], doc_date: date) -> RateResolution:
        # Exempt?
        if party_profile and party_profile.is_exempt_withholding:
            return RateResolution(
                rate=Decimal("0.0000"),
                reason="Party exempt from withholding",
                reason_code="EXEMPT",
            )

        # Lower deduction certificate?
        if party_profile and party_profile.lower_deduction_rate is not None:
            vf = party_profile.lower_deduction_valid_from
            vt = party_profile.lower_deduction_valid_to
            if (vf is None or vf <= doc_date) and (vt is None or doc_date <= vt):
                return RateResolution(
                    rate=Decimal(party_profile.lower_deduction_rate or 0),
                    reason="Lower deduction certificate",
                    reason_code="LOWER_CERT",
                    lower_rate_applied=True,
                )

        base_rate = Decimal(section.rate_default or 0)
        no_pan_applied = False
        sec_206ab_applied = False
        reasons: list[str] = []
        reason_codes: list[str] = []

        if section.requires_pan:
            pan_ok = bool(party_profile and party_profile.is_pan_available)
            if not pan_ok and section.higher_rate_no_pan is not None:
                base_rate = max(base_rate, Decimal(section.higher_rate_no_pan or 0))
                no_pan_applied = True
                reasons.append("Higher rate (PAN missing)")
                reason_codes.append("NO_PAN_206AA")

        if WithholdingResolver._is_206ab_applicable(party_profile=party_profile, doc_date=doc_date):
            higher_rate_206ab = getattr(section, "higher_rate_206ab", None)
            if higher_rate_206ab is not None:
                base_rate = max(base_rate, Decimal(higher_rate_206ab or 0))
                sec_206ab_applied = True
                reasons.append("Higher rate (specified person 206AB)")
                reason_codes.append("SEC_206AB")

        if no_pan_applied and sec_206ab_applied:
            reason = "Higher of 206AA/206AB applied"
            reason_code = "NO_PAN_206AA_AND_SEC_206AB"
        elif reasons:
            reason = "; ".join(reasons)
            reason_code = reason_codes[-1]
        else:
            reason = None
            reason_code = None

        return RateResolution(
            rate=base_rate,
            reason=reason,
            reason_code=reason_code,
            no_pan_applied=no_pan_applied,
            sec_206ab_applied=sec_206ab_applied,
            lower_rate_applied=False,
        )


def compute_base_amount_excl_gst(*, taxable_total: Decimal) -> Decimal:
    return q2(taxable_total)

def compute_base_amount_incl_gst(*, gross_total: Decimal) -> Decimal:
    return q2(gross_total)


def determine_fy_quarter(doc_date: date) -> tuple[str, int, str]:
    year = doc_date.year
    if doc_date.month < 4:
        fy_start = year - 1
        fy_end = year
    else:
        fy_start = year
        fy_end = year + 1
    fy = f"{fy_start}-{str(fy_end)[-2:]}"

    if doc_date.month in (4, 5, 6):
        quarter = "Q1"
    elif doc_date.month in (7, 8, 9):
        quarter = "Q2"
    elif doc_date.month in (10, 11, 12):
        quarter = "Q3"
    else:
        quarter = "Q4"

    return fy, doc_date.month, quarter


def compute_withholding_preview(
    *,
    entity_id: int,
    entityfin_id: int,
    subentity_id: int | None,
    party_account_id: int | None,
    tax_type: int,
    explicit_section_id: int | None,
    doc_date: date,
    taxable_total: Decimal,
    gross_total: Decimal,
    allowed_base_rules: list[int] | tuple[int, ...] | None = None,
    module_name: str | None = None,
    document_type: str | None = None,
    document_id: int | None = None,
) -> WithholdingResult:
    cfg = WithholdingResolver.get_entity_config(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        doc_date=doc_date,
    )

    if tax_type == WithholdingTaxType.TCS and (not cfg or not cfg.enable_tcs):
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TCS disabled in entity config", "DISABLED")
    if tax_type == WithholdingTaxType.TDS and (not cfg or not cfg.enable_tds):
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TDS disabled in entity config", "DISABLED")

    sec = WithholdingResolver.resolve_section(
        tax_type=tax_type,
        explicit_section_id=explicit_section_id,
        cfg=cfg,
        doc_date=doc_date,
    )
    if not sec:
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No section resolved", "NO_SECTION")

    if sec.effective_from and sec.effective_from > doc_date:
        return WithholdingResult(False, sec, Decimal("0.0000"), ZERO2, ZERO2, "Section not effective on doc date", "NOT_EFFECTIVE")
    if sec.effective_to and sec.effective_to < doc_date:
        return WithholdingResult(False, sec, Decimal("0.0000"), ZERO2, ZERO2, "Section expired on doc date", "EXPIRED")

    if allowed_base_rules:
        allowed = {int(x) for x in allowed_base_rules}
        if int(sec.base_rule) not in allowed:
            return WithholdingResult(
                True,
                sec,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "Selected section is not valid for this workflow base.",
                "INVALID_BASE_RULE",
            )

    applicable, applicability_reason, applicability_reason_code = WithholdingResolver.evaluate_section_applicability(
        section=sec,
        party_account_id=party_account_id,
    )
    if not applicable:
        return WithholdingResult(
            True,
            sec,
            Decimal("0.0000"),
            ZERO2,
            ZERO2,
            applicability_reason,
            applicability_reason_code,
        )

    if sec.section_code and sec.section_code.strip().upper() in {"206C(1H)", "206C1H"}:
        # Config-driven gate: never force-disable with a hardcoded date.
        if not bool(getattr(cfg, "apply_tcs_206c1h", False)):
            return WithholdingResult(
                True,
                sec,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "206C(1H) disabled in withholding configuration",
                "DISABLED_206C_1H_BY_CONFIG",
            )
        limit = q2(getattr(cfg, "tcs_206c1h_turnover_limit", ZERO2) or ZERO2)
        prev_turnover = q2(getattr(cfg, "tcs_206c1h_prev_fy_turnover", ZERO2) or ZERO2)
        force_eligible = getattr(cfg, "tcs_206c1h_force_eligible", None)
        if force_eligible is None:
            eligible = bool(limit <= ZERO2 or prev_turnover >= limit)
        else:
            eligible = bool(force_eligible)
        if not eligible:
            return WithholdingResult(
                True,
                sec,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "206C(1H) turnover eligibility not met for this entity config.",
                "NOT_ELIGIBLE_TURNOVER_GATE",
            )

    p = WithholdingResolver.resolve_party_profile(
        party_account_id=party_account_id,
        entity_id=entity_id,
        subentity_id=subentity_id,
    )
    sec195_ok, sec195_reason, sec195_reason_code = WithholdingResolver.validate_section_195_requirements(
        section=sec,
        party_profile=p,
        party_account_id=party_account_id,
        doc_date=doc_date,
    )
    if not sec195_ok:
        return WithholdingResult(
            True,
            sec,
            Decimal("0.0000"),
            ZERO2,
            ZERO2,
            sec195_reason,
            sec195_reason_code,
        )
    rate_resolution = WithholdingResolver.resolve_rate(section=sec, party_profile=p, doc_date=doc_date)

    if sec.base_rule == WithholdingBaseRule.INVOICE_VALUE_INCL_GST:
        base = compute_base_amount_incl_gst(gross_total=q2(gross_total or ZERO2))
    else:
        base = compute_base_amount_excl_gst(taxable_total=q2(taxable_total or ZERO2))

    exclude_doc = None
    if module_name and document_type and document_id:
        exclude_doc = ((module_name or "").strip().lower(), (document_type or "").strip().lower(), int(document_id))
    effective_base, threshold_reason, threshold_reason_code = _apply_section_threshold(
        section=sec,
        base_amount=base,
        doc_date=doc_date,
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        party_account_id=party_account_id,
        exclude_doc=exclude_doc,
    )
    if effective_base <= ZERO2:
        return WithholdingResult(
            True,
            sec,
            rate_resolution.rate,
            q2(base),
            ZERO2,
            threshold_reason or f"Below threshold ({getattr(sec, 'threshold_default', 0)})",
            threshold_reason_code or "BELOW_THRESHOLD",
            no_pan_applied=rate_resolution.no_pan_applied,
            sec_206ab_applied=rate_resolution.sec_206ab_applied,
            lower_rate_applied=rate_resolution.lower_rate_applied,
        )

    effective_rate = Decimal(rate_resolution.rate or 0)
    code = (sec.section_code or "").strip().upper()
    treaty_rate = getattr(p, "treaty_rate", None) if p else None
    if code == "195" and treaty_rate is not None:
        valid = WithholdingResolver._within_window(
            doc_date=doc_date,
            start_date=getattr(p, "treaty_valid_from", None),
            end_date=getattr(p, "treaty_valid_to", None),
        )
        if valid and str(getattr(p, "declaration_reference", "") or "").strip():
            effective_rate = min(effective_rate, Decimal(treaty_rate))
            surcharge_rate = Decimal(getattr(p, "surcharge_rate", 0) or 0)
            cess_rate = Decimal(getattr(p, "cess_rate", 0) or 0)
            if surcharge_rate > 0:
                effective_rate = effective_rate + surcharge_rate
            if cess_rate > 0:
                effective_rate = effective_rate + ((effective_rate * cess_rate) / Decimal("100.0"))
            effective_rate = effective_rate.quantize(Decimal("0.0001"))

    amount = q2((q2(effective_base) * Decimal(effective_rate or 0)) / Decimal("100.0"))
    return WithholdingResult(
        True,
        sec,
        Decimal(effective_rate or 0),
        q2(effective_base),
        q2(amount),
        threshold_reason or rate_resolution.reason,
        threshold_reason_code or rate_resolution.reason_code,
        no_pan_applied=rate_resolution.no_pan_applied,
        sec_206ab_applied=rate_resolution.sec_206ab_applied,
        lower_rate_applied=rate_resolution.lower_rate_applied,
    )


def upsert_tcs_computation(
    *,
    module_name: str,
    document_type: str,
    document_id: int,
    document_no: str,
    doc_date: date,
    entity_id: int,
    entityfin_id: int,
    subentity_id: int | None,
    party_account_id: int | None,
    preview: WithholdingResult,
    status: str = TcsComputation.Status.CONFIRMED,
    trigger_basis: str = "INVOICE",
    override_reason: str = "",
    overridden_by=None,
) -> TcsComputation:
    fy, _, quarter = determine_fy_quarter(doc_date)

    defaults = {
        "doc_date": doc_date,
        "document_no": (document_no or "").strip(),
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "party_account_id": party_account_id,
        "section": preview.section,
        "applicability_status": "APPLICABLE" if preview.enabled else "NOT_APPLICABLE",
        "trigger_basis": (trigger_basis or "INVOICE").upper(),
        "taxable_base": q2(preview.base_amount),
        "excluded_base": ZERO2,
        "tcs_base_amount": q2(preview.base_amount),
        "rate": Decimal(preview.rate or 0),
        "tcs_amount": q2(preview.amount),
        "no_pan_applied": bool(preview.no_pan_applied),
        "lower_rate_applied": bool(preview.lower_rate_applied),
        "override_reason": (override_reason or "").strip(),
        "fiscal_year": fy,
        "quarter": quarter,
        "status": status,
        "rule_snapshot_json": {
            "reason": preview.reason,
            "reason_code": preview.reason_code,
            "section_code": preview.section.section_code if preview.section else "",
            "section_id": preview.section.id if preview.section else None,
            "sec_206ab_applied": bool(preview.sec_206ab_applied),
        },
        "computation_json": {
            "enabled": preview.enabled,
            "base_amount": str(q2(preview.base_amount)),
            "rate": str(Decimal(preview.rate or 0)),
            "amount": str(q2(preview.amount)),
            "reason": preview.reason,
            "reason_code": preview.reason_code,
            "no_pan_applied": bool(preview.no_pan_applied),
            "sec_206ab_applied": bool(preview.sec_206ab_applied),
            "lower_rate_applied": bool(preview.lower_rate_applied),
        },
    }
    if overridden_by:
        defaults["overridden_by"] = overridden_by
        defaults["overridden_at"] = timezone.now()

    obj, _ = TcsComputation.objects.update_or_create(
        module_name=module_name,
        document_type=document_type,
        document_id=document_id,
        defaults=defaults,
    )
    return obj
