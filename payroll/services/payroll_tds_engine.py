from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from payroll.models import ContractTaxDeclaration, ContractTaxDeclarationLine, PayrollComponent

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass(frozen=True)
class PayrollTDSProjectionResult:
    monthly_tds: Decimal
    snapshot: dict[str, Any]
    trace: dict[str, Any]


class PayrollTDSEngine:
    DEFAULT_POLICY: dict[str, Any] = {
        "tds_default_remaining_periods": "12",
        "tds_standard_deduction_old_regime": "50000.00",
        "tds_standard_deduction_new_regime": "50000.00",
        "tds_80c_cap": "150000.00",
        "tds_80d_cap": "25000.00",
        "tds_allow_80c_old_regime": True,
        "tds_allow_80d_old_regime": True,
        "tds_allow_hra_exemption_old_regime": True,
        "tds_old_regime_slabs": [
            {"upto": "250000.00", "rate": "0.00"},
            {"upto": "500000.00", "rate": "5.00"},
            {"upto": "1000000.00", "rate": "20.00"},
            {"rate": "30.00"},
        ],
        "tds_new_regime_slabs": [
            {"upto": "400000.00", "rate": "0.00"},
            {"upto": "800000.00", "rate": "5.00"},
            {"upto": "1200000.00", "rate": "10.00"},
            {"upto": "1600000.00", "rate": "15.00"},
            {"upto": "2000000.00", "rate": "20.00"},
            {"upto": "2400000.00", "rate": "25.00"},
            {"rate": "30.00"},
        ],
        "tds_rebate_threshold_old_regime": "500000.00",
        "tds_rebate_max_old_regime": "12500.00",
        "tds_rebate_threshold_new_regime": "1200000.00",
        "tds_rebate_max_new_regime": "60000.00",
        "tds_old_regime_surcharge_slabs": [
            {"upto": "5000000.00", "rate": "0.00"},
            {"upto": "10000000.00", "rate": "10.00"},
            {"upto": "20000000.00", "rate": "15.00"},
            {"upto": "50000000.00", "rate": "25.00"},
            {"rate": "37.00"},
        ],
        "tds_new_regime_surcharge_slabs": [
            {"upto": "5000000.00", "rate": "0.00"},
            {"upto": "10000000.00", "rate": "10.00"},
            {"upto": "20000000.00", "rate": "15.00"},
            {"upto": "50000000.00", "rate": "25.00"},
            {"rate": "25.00"},
        ],
        "tds_health_education_cess_rate": "4.00",
        "tds_apply_marginal_relief": True,
    }

    @staticmethod
    def normalize_tax_regime(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"new", "new_regime"}:
            return "new_regime"
        if normalized in {"old", "old_regime"}:
            return "old_regime"
        return normalized or "old_regime"

    @staticmethod
    def infer_line_category(
        *,
        section_code: str | None,
        declaration_category: str | None = None,
    ) -> str:
        explicit = str(declaration_category or "").strip().upper()
        if explicit:
            return explicit
        section = str(section_code or "").strip().upper()
        if section == ContractTaxDeclarationLine.SectionCode.HRA:
            return ContractTaxDeclarationLine.DeclarationCategory.EXEMPTION
        if section in {
            ContractTaxDeclarationLine.SectionCode.SECTION_80C,
            ContractTaxDeclarationLine.SectionCode.SECTION_80D,
            ContractTaxDeclarationLine.SectionCode.HOME_LOAN_INTEREST,
            ContractTaxDeclarationLine.SectionCode.LTA,
            ContractTaxDeclarationLine.SectionCode.OTHER,
        }:
            return ContractTaxDeclarationLine.DeclarationCategory.DEDUCTION
        return ContractTaxDeclarationLine.DeclarationCategory.INFORMATIONAL

    @classmethod
    def infer_line_code(cls, *, line: ContractTaxDeclarationLine) -> str:
        explicit = str(getattr(line, "declaration_code", "") or "").strip().upper()
        if explicit:
            return explicit
        section = str(getattr(line, "section_code", "") or "").strip().upper()
        if section == ContractTaxDeclarationLine.SectionCode.SECTION_80C:
            return "DEDUCTION_80C"
        if section == ContractTaxDeclarationLine.SectionCode.SECTION_80D:
            return "DEDUCTION_80D"
        if section == ContractTaxDeclarationLine.SectionCode.HRA:
            return "HRA_EXEMPTION"
        if section == ContractTaxDeclarationLine.SectionCode.LTA:
            return "LTA_EXEMPTION"
        if section == ContractTaxDeclarationLine.SectionCode.HOME_LOAN_INTEREST:
            return "HOME_LOAN_INTEREST"
        return "OTHER"

    @classmethod
    def declaration_snapshot(cls, declaration: ContractTaxDeclaration | None) -> dict[str, Any]:
        if declaration is None:
            return {}
        snapshot: dict[str, Any] = {
            "annual_taxable_income": str(q2(declaration.declared_annual_income)),
            "projected_taxable_income": str(q2(declaration.projected_taxable_income)),
            "previous_employer_income": str(q2(declaration.previous_employer_income)),
            "previous_employer_taxable_income": str(q2(declaration.previous_employer_income)),
            "previous_employer_tds": str(q2(declaration.previous_employer_tds)),
            "professional_tax_declared": str(q2(declaration.professional_tax_declared)),
            "standard_deduction_amount": str(q2(declaration.standard_deduction_amount)),
            "annual_other_income": str(q2(declaration.annual_other_income)),
        }
        for line in declaration.lines.filter(is_active=True).order_by("section_code", "id"):
            metadata = line.metadata if isinstance(line.metadata, dict) else {}
            amount = q2(line.approved_amount or line.declared_amount)
            if line.section_code == line.SectionCode.SECTION_80C:
                snapshot["deduction_80c"] = str(amount)
                snapshot["deduction_80c_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
            elif line.section_code == line.SectionCode.SECTION_80D:
                snapshot["deduction_80d"] = str(amount)
                snapshot["deduction_80d_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
            elif line.section_code == line.SectionCode.HRA:
                snapshot["hra_exemption"] = str(amount)
                if metadata.get("hra_rent_paid_annual") is not None:
                    snapshot["hra_rent_paid_annual"] = metadata.get("hra_rent_paid_annual")
                if metadata.get("hra_rent_months") is not None:
                    snapshot["hra_rent_months"] = metadata.get("hra_rent_months")
                if metadata.get("hra_is_metro_city") is not None:
                    snapshot["hra_is_metro_city"] = metadata.get("hra_is_metro_city")
                snapshot["hra_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
            else:
                line_category = cls.infer_line_category(
                    section_code=line.section_code,
                    declaration_category=getattr(line, "declaration_category", ""),
                )
                if line_category == ContractTaxDeclarationLine.DeclarationCategory.OTHER_INCOME:
                    existing_other_income = q2(snapshot.get("other_income") or snapshot.get("annual_other_income"))
                    snapshot["other_income"] = str(q2(existing_other_income + amount))
                elif line_category == ContractTaxDeclarationLine.DeclarationCategory.DEDUCTION:
                    existing_other_deduction = q2(snapshot.get("other_old_regime_deductions"))
                    snapshot["other_old_regime_deductions"] = str(q2(existing_other_deduction + amount))
        return snapshot

    @classmethod
    def _policy_value(cls, policy: dict[str, Any] | None, key: str, default: Any = None) -> Any:
        policy = policy or {}
        if key in policy and policy.get(key) not in (None, ""):
            return policy.get(key)
        tax_policy = policy.get("tax_policy") if isinstance(policy.get("tax_policy"), dict) else {}
        tds_policy = tax_policy.get("tds") if isinstance(tax_policy.get("tds"), dict) else {}
        nested_key_map = {
            "tds_default_remaining_periods": "default_remaining_periods",
            "tds_projection_rate": "projection_rate",
            "tds_projection_rate_old_regime": "projection_rate_old_regime",
            "tds_projection_rate_new_regime": "projection_rate_new_regime",
            "tds_standard_deduction_old_regime": "standard_deduction_old_regime",
            "tds_standard_deduction_new_regime": "standard_deduction_new_regime",
            "tds_80c_cap": "cap_80c",
            "tds_80d_cap": "cap_80d",
            "tds_allow_80c_old_regime": "allow_80c_old_regime",
            "tds_allow_80d_old_regime": "allow_80d_old_regime",
            "tds_allow_hra_exemption_old_regime": "allow_hra_exemption_old_regime",
            "tds_old_regime_slabs": "old_regime_slabs",
            "tds_new_regime_slabs": "new_regime_slabs",
            "tds_rebate_threshold_old_regime": "rebate_threshold_old_regime",
            "tds_rebate_max_old_regime": "rebate_max_old_regime",
            "tds_rebate_threshold_new_regime": "rebate_threshold_new_regime",
            "tds_rebate_max_new_regime": "rebate_max_new_regime",
            "tds_old_regime_surcharge_slabs": "old_regime_surcharge_slabs",
            "tds_new_regime_surcharge_slabs": "new_regime_surcharge_slabs",
            "tds_health_education_cess_rate": "health_education_cess_rate",
            "tds_apply_marginal_relief": "apply_marginal_relief",
        }
        nested_key = nested_key_map.get(key)
        if nested_key and tds_policy.get(nested_key) not in (None, ""):
            return tds_policy.get(nested_key)
        return cls.DEFAULT_POLICY.get(key, default)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except Exception:
            return ZERO2

    @classmethod
    def _policy_flag(cls, policy: dict[str, Any] | None, key: str, default: bool = False) -> bool:
        raw = cls._policy_value(policy, key, default)
        if isinstance(raw, bool):
            return raw
        return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _policy_slabs(cls, policy: dict[str, Any] | None, key: str) -> list[dict[str, Decimal | None]]:
        raw = cls._policy_value(policy, key, [])
        if not isinstance(raw, list):
            return []
        normalized: list[dict[str, Decimal | None]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rate = cls._decimal(item.get("rate"))
            upto_raw = item.get("upto")
            upto = None if upto_raw in (None, "") else cls._decimal(upto_raw)
            normalized.append({"rate": rate, "upto": upto})
        return normalized

    @classmethod
    def _resolve_policy_slabs(cls, *, tax_regime: str, policy: dict[str, Any] | None) -> list[dict[str, Decimal | None]]:
        if tax_regime == "new_regime":
            return cls._policy_slabs(policy, "tds_new_regime_slabs")
        return cls._policy_slabs(policy, "tds_old_regime_slabs")

    @classmethod
    def _resolve_surcharge_slabs(cls, *, tax_regime: str, policy: dict[str, Any] | None) -> list[dict[str, Decimal | None]]:
        if tax_regime == "new_regime":
            return cls._policy_slabs(policy, "tds_new_regime_surcharge_slabs")
        return cls._policy_slabs(policy, "tds_old_regime_surcharge_slabs")

    @classmethod
    def _compute_tax_from_slabs(cls, *, taxable_income: Decimal, slabs: list[dict[str, Decimal | None]]) -> Decimal:
        if taxable_income <= ZERO2 or not slabs:
            return ZERO2
        previous_limit = ZERO2
        annual_tax = ZERO2
        for slab in slabs:
            upper_limit = slab.get("upto")
            rate = q2(slab.get("rate"))
            if upper_limit is None:
                taxable_slice = max(q2(taxable_income - previous_limit), ZERO2)
            else:
                taxable_slice = max(min(q2(taxable_income), q2(upper_limit)) - previous_limit, ZERO2)
            if taxable_slice > ZERO2 and rate > ZERO2:
                annual_tax = q2(annual_tax + q2(taxable_slice * rate / Decimal("100.00")))
            if upper_limit is None or q2(taxable_income) <= q2(upper_limit):
                break
            previous_limit = q2(upper_limit)
        return annual_tax

    @classmethod
    def _apply_regime_rebate(
        cls,
        *,
        annual_tax: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict[str, Any] | None,
    ) -> Decimal:
        threshold_key = "tds_rebate_threshold_new_regime" if tax_regime == "new_regime" else "tds_rebate_threshold_old_regime"
        max_key = "tds_rebate_max_new_regime" if tax_regime == "new_regime" else "tds_rebate_max_old_regime"
        threshold = cls._decimal(cls._policy_value(policy, threshold_key, ZERO2))
        rebate_max = cls._decimal(cls._policy_value(policy, max_key, ZERO2))
        if threshold <= ZERO2 or rebate_max <= ZERO2 or projected_taxable_income > q2(threshold):
            return annual_tax
        return max(q2(annual_tax - min(annual_tax, rebate_max)), ZERO2)

    @classmethod
    def _resolve_surcharge_rate(
        cls,
        *,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict[str, Any] | None,
    ) -> Decimal:
        slabs = cls._resolve_surcharge_slabs(tax_regime=tax_regime, policy=policy)
        for slab in slabs:
            upper_limit = slab.get("upto")
            if upper_limit is None or projected_taxable_income <= q2(upper_limit):
                return q2(slab.get("rate"))
        return ZERO2

    @classmethod
    def _apply_surcharge_and_cess(
        cls,
        *,
        annual_tax: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict[str, Any] | None,
    ) -> Decimal:
        if annual_tax <= ZERO2:
            return ZERO2
        surcharge_rate = cls._resolve_surcharge_rate(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        subtotal = q2(annual_tax + q2(annual_tax * surcharge_rate / Decimal("100.00")))
        cess_rate = cls._decimal(cls._policy_value(policy, "tds_health_education_cess_rate", ZERO2))
        if cess_rate <= ZERO2:
            return subtotal
        return q2(subtotal + q2(subtotal * cess_rate / Decimal("100.00")))

    @classmethod
    def _resolve_hra_exemption(
        cls,
        *,
        snapshot: dict[str, Any],
        policy: dict[str, Any] | None,
        annual_gross: Decimal,
        annual_hra_received: Decimal,
        annual_basic_received: Decimal,
    ) -> Decimal:
        if not cls._policy_flag(policy, "tds_allow_hra_exemption_old_regime", True):
            return ZERO2
        declared_hra = q2(snapshot.get("hra_exemption"))
        rent_paid_annual = q2(snapshot.get("hra_rent_paid_annual"))
        metro_flag = snapshot.get("hra_is_metro_city")
        if annual_hra_received <= ZERO2:
            annual_hra_received = declared_hra
        if annual_basic_received <= ZERO2:
            annual_basic_received = q2(annual_gross * Decimal("0.40"))
        if rent_paid_annual <= ZERO2 or metro_flag is None:
            return declared_hra
        city_basic_percent = Decimal("0.50") if bool(metro_flag) else Decimal("0.40")
        rent_minus_basic_threshold = max(q2(rent_paid_annual - q2(annual_basic_received * Decimal("0.10"))), ZERO2)
        city_cap = q2(annual_basic_received * city_basic_percent)
        derived_cap = min(annual_hra_received, rent_minus_basic_threshold, city_cap)
        return min(declared_hra, derived_cap) if declared_hra > ZERO2 else derived_cap

    @staticmethod
    def _estimate_component_annual(
        *,
        resolved: dict[int, Decimal] | None,
        component_map: dict[int, PayrollComponent] | None,
        semantic_code: str,
    ) -> Decimal:
        resolved = resolved or {}
        component_map = component_map or {}
        for component_id, amount in resolved.items():
            component = component_map.get(component_id)
            if component and getattr(component, "semantic_code", "") == semantic_code:
                return q2(q2(amount) * Decimal("12.00"))
        return ZERO2

    @staticmethod
    def _fy_remaining_months(payroll_period) -> Decimal:
        period_end = getattr(payroll_period, "period_end", None)
        if period_end is None:
            return ZERO2
        month = int(period_end.month)
        remaining = ((3 - month) % 12) + 1
        return Decimal(str(remaining))

    @classmethod
    def build_projection(
        cls,
        *,
        contract_payroll_profile=None,
        salary_assignment=None,
        declaration: ContractTaxDeclaration | None = None,
        tax_regime: str | None = None,
        policy: dict[str, Any] | None = None,
        existing_snapshot: dict[str, Any] | None = None,
        payroll_period=None,
        monthly_gross_amount: Decimal | None = None,
        monthly_ctc_amount: Decimal | None = None,
        resolved: dict[int, Decimal] | None = None,
        component_map: dict[int, PayrollComponent] | None = None,
    ) -> PayrollTDSProjectionResult:
        snapshot = {
            **cls.declaration_snapshot(declaration),
            **(existing_snapshot or {}),
        }
        regime = cls.normalize_tax_regime(tax_regime or getattr(contract_payroll_profile, "tax_regime", None) or getattr(declaration, "tax_regime", None))
        monthly_gross = q2(monthly_gross_amount)
        if monthly_gross <= ZERO2:
            monthly_gross = q2(getattr(salary_assignment, "gross_amount", ZERO2))
        monthly_ctc = q2(monthly_ctc_amount)
        if monthly_ctc <= ZERO2:
            monthly_ctc = q2(getattr(salary_assignment, "ctc_amount", ZERO2))
        annual_gross = q2(snapshot.get("annual_gross") or snapshot.get("annual_gross_projection"))
        if annual_gross <= ZERO2:
            annual_gross = q2(snapshot.get("declared_annual_income") or getattr(declaration, "declared_annual_income", ZERO2))
        if annual_gross <= ZERO2:
            annual_gross = q2(monthly_gross * Decimal("12.00"))
        if annual_gross <= ZERO2 and monthly_ctc > ZERO2:
            annual_gross = q2(monthly_ctc * Decimal("12.00"))

        annual_other_income = q2(snapshot.get("other_income") or snapshot.get("annual_other_income") or getattr(declaration, "annual_other_income", ZERO2))
        previous_employer_income = q2(snapshot.get("previous_employer_taxable_income") or snapshot.get("previous_employer_income") or getattr(declaration, "previous_employer_income", ZERO2))
        standard_deduction = q2(snapshot.get("standard_deduction_amount") or cls._policy_value(
            policy,
            "tds_standard_deduction_new_regime" if regime == "new_regime" else "tds_standard_deduction_old_regime",
            "50000.00",
        ))
        deduction_80c = ZERO2
        deduction_80d = ZERO2
        other_deductions = q2(snapshot.get("other_old_regime_deductions"))
        annual_hra = cls._estimate_component_annual(
            resolved=resolved,
            component_map=component_map,
            semantic_code=PayrollComponent.SemanticCode.HRA,
        )
        annual_basic = cls._estimate_component_annual(
            resolved=resolved,
            component_map=component_map,
            semantic_code=PayrollComponent.SemanticCode.BASIC_PAY,
        )
        hra_exemption = ZERO2
        if regime == "old_regime":
            if cls._policy_flag(policy, "tds_allow_80c_old_regime", True):
                deduction_80c = min(q2(snapshot.get("deduction_80c")), cls._decimal(cls._policy_value(policy, "tds_80c_cap", "150000.00")))
            if cls._policy_flag(policy, "tds_allow_80d_old_regime", True):
                deduction_80d = min(q2(snapshot.get("deduction_80d")), cls._decimal(cls._policy_value(policy, "tds_80d_cap", "25000.00")))
            hra_exemption = cls._resolve_hra_exemption(
                snapshot=snapshot,
                policy=policy,
                annual_gross=annual_gross,
                annual_hra_received=annual_hra,
                annual_basic_received=annual_basic,
            )
        else:
            other_deductions = ZERO2

        professional_tax = q2(snapshot.get("professional_tax_declared") or getattr(declaration, "professional_tax_declared", ZERO2))
        annual_exemptions = q2(hra_exemption)
        annual_deductions = q2(standard_deduction + deduction_80c + deduction_80d + other_deductions + professional_tax)

        explicit_taxable_income = q2(snapshot.get("projected_taxable_income"))
        projected_taxable_income = explicit_taxable_income
        if projected_taxable_income <= ZERO2:
            projected_taxable_income = max(
                q2(annual_gross + annual_other_income + previous_employer_income - annual_exemptions - annual_deductions),
                ZERO2,
            )

        explicit_annual_tax = q2(snapshot.get("annual_tax") or snapshot.get("projected_annual_tax"))
        projected_annual_tax = explicit_annual_tax
        if projected_annual_tax <= ZERO2:
            slabs = cls._resolve_policy_slabs(tax_regime=regime, policy=policy)
            if slabs:
                projected_annual_tax = cls._compute_tax_from_slabs(taxable_income=projected_taxable_income, slabs=slabs)
                projected_annual_tax = cls._apply_regime_rebate(
                    annual_tax=projected_annual_tax,
                    projected_taxable_income=projected_taxable_income,
                    tax_regime=regime,
                    policy=policy,
                )
                projected_annual_tax = cls._apply_surcharge_and_cess(
                    annual_tax=projected_annual_tax,
                    projected_taxable_income=projected_taxable_income,
                    tax_regime=regime,
                    policy=policy,
                )

        tax_paid_ytd = q2(snapshot.get("tax_paid_ytd") or snapshot.get("tds_deducted_ytd"))
        previous_employer_tds = q2(snapshot.get("previous_employer_tds") or getattr(declaration, "previous_employer_tds", ZERO2))
        already_deducted = q2(tax_paid_ytd + previous_employer_tds)
        balance_tax = max(q2(projected_annual_tax - already_deducted), ZERO2)
        remaining_periods = q2(snapshot.get("remaining_periods") or snapshot.get("months_remaining"))
        if remaining_periods <= ZERO2:
            remaining_periods = cls._fy_remaining_months(payroll_period)
        if remaining_periods <= ZERO2:
            remaining_periods = q2(cls._policy_value(policy, "tds_default_remaining_periods", "12"))
        if remaining_periods <= ZERO2:
            remaining_periods = Decimal("1.00")

        explicit_monthly_tds = q2(snapshot.get("monthly_tds") or snapshot.get("projected_monthly_tds") or snapshot.get("current_month_tds"))
        monthly_tds = explicit_monthly_tds if explicit_monthly_tds > ZERO2 else q2(balance_tax / remaining_periods)

        trace = {
            "engine": "payroll_tds_engine",
            "source_snapshot_note": "TDS projection is derived from contract-native declarations and payroll snapshots without recalculating finalized payroll runs.",
            "regime": regime,
            "annual_gross": str(annual_gross),
            "annual_other_income": str(annual_other_income),
            "previous_employer_income": str(previous_employer_income),
            "exemptions": {
                "hra": str(hra_exemption),
                "total": str(annual_exemptions),
            },
            "deductions": {
                "standard_deduction": str(standard_deduction),
                "professional_tax": str(professional_tax),
                "section_80c": str(deduction_80c),
                "section_80d": str(deduction_80d),
                "other": str(other_deductions),
                "total": str(annual_deductions),
            },
            "taxable_income": str(projected_taxable_income),
            "projected_tax": str(projected_annual_tax),
            "already_deducted": str(already_deducted),
            "balance_tax": str(balance_tax),
            "remaining_periods": str(remaining_periods),
            "monthly_tds": str(monthly_tds),
            "manual_override": explicit_monthly_tds > ZERO2,
        }
        normalized_snapshot = {
            **snapshot,
            "tax_regime": regime.upper().replace("_REGIME", ""),
            "annual_gross_projection": str(annual_gross),
            "annual_other_income": str(annual_other_income),
            "annual_exemption_total": str(annual_exemptions),
            "annual_deduction_total": str(annual_deductions),
            "projected_taxable_income": str(projected_taxable_income),
            "annual_taxable_income": str(projected_taxable_income),
            "projected_annual_tax": str(projected_annual_tax),
            "annual_tax": str(projected_annual_tax),
            "monthly_tds": str(monthly_tds),
            "projected_monthly_tds": str(monthly_tds),
            "tax_paid_ytd": str(tax_paid_ytd),
            "tax_already_deducted": str(already_deducted),
            "balance_tax": str(balance_tax),
            "remaining_periods": str(remaining_periods),
            "months_remaining": str(remaining_periods),
            "tds_trace": trace,
        }
        return PayrollTDSProjectionResult(
            monthly_tds=monthly_tds,
            snapshot=normalized_snapshot,
            trace=trace,
        )
