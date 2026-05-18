from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from payroll.models import PayrollComponent, SalaryStructureLine, StatutoryRule, StatutoryScheme
from payroll.services.entity_statutory_registration_service import EntityStatutoryRegistrationService
from payroll.services.payroll_tds_engine import PayrollTDSEngine
from payroll.services.statutory_rule_service import StatutoryRuleService
from payroll.services.statutory_scheme_service import StatutorySchemeService
from payroll.services.statutory_slab_service import StatutorySlabService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollStatutoryEngineError(ValueError):
    pass


@dataclass(frozen=True)
class PayrollStatutoryResult:
    amount: Decimal
    trace: dict[str, Any]


class PayrollStatutoryEngine:
    DEFAULT_PF_WAGE_CAP = Decimal("15000.00")
    DEFAULT_PF_EMPLOYEE_RATE = Decimal("12.00")
    DEFAULT_PF_EMPLOYER_RATE = Decimal("12.00")
    DEFAULT_ESI_WAGE_THRESHOLD = Decimal("21000.00")
    DEFAULT_ESI_EMPLOYEE_RATE = Decimal("0.75")
    DEFAULT_ESI_EMPLOYER_RATE = Decimal("3.25")

    SCHEME_CODE_BY_SEMANTIC = {
        PayrollComponent.SemanticCode.PF_EMPLOYEE: "PF",
        PayrollComponent.SemanticCode.PF_EMPLOYER: "PF",
        PayrollComponent.SemanticCode.ESI_EMPLOYEE: "ESI",
        PayrollComponent.SemanticCode.ESI_EMPLOYER: "ESI",
        PayrollComponent.SemanticCode.PT: "PT",
        PayrollComponent.SemanticCode.LWF_EMPLOYEE: "LWF",
        PayrollComponent.SemanticCode.LWF_EMPLOYER: "LWF",
        PayrollComponent.SemanticCode.TDS: "TDS",
    }
    SCHEME_TYPE_BY_SEMANTIC = {
        PayrollComponent.SemanticCode.PF_EMPLOYEE: StatutoryScheme.SchemeType.PF,
        PayrollComponent.SemanticCode.PF_EMPLOYER: StatutoryScheme.SchemeType.PF,
        PayrollComponent.SemanticCode.ESI_EMPLOYEE: StatutoryScheme.SchemeType.ESI,
        PayrollComponent.SemanticCode.ESI_EMPLOYER: StatutoryScheme.SchemeType.ESI,
        PayrollComponent.SemanticCode.PT: StatutoryScheme.SchemeType.PT,
        PayrollComponent.SemanticCode.LWF_EMPLOYEE: StatutoryScheme.SchemeType.LWF,
        PayrollComponent.SemanticCode.LWF_EMPLOYER: StatutoryScheme.SchemeType.LWF,
        PayrollComponent.SemanticCode.TDS: StatutoryScheme.SchemeType.TDS,
    }
    FLAG_BY_SCHEME_TYPE = {
        StatutoryScheme.SchemeType.PF: "pf_applicable",
        StatutoryScheme.SchemeType.ESI: "esi_applicable",
        StatutoryScheme.SchemeType.PT: "pt_applicable",
        StatutoryScheme.SchemeType.TDS: "tds_applicable",
        StatutoryScheme.SchemeType.LWF: "lwf_applicable",
    }
    SUPPORTED_SEMANTICS = set(SCHEME_TYPE_BY_SEMANTIC.keys())

    @classmethod
    def supports_component(cls, component: PayrollComponent | None) -> bool:
        semantic_code = str(getattr(component, "semantic_code", "") or "").strip()
        return semantic_code in cls.SUPPORTED_SEMANTICS

    @classmethod
    def calculate_component(
        cls,
        *,
        component: PayrollComponent,
        line: SalaryStructureLine,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent] | None,
        calculation_input,
        policy: dict[str, Any] | None,
        profile,
        current_earning_total: Decimal,
        payroll_date,
    ) -> PayrollStatutoryResult:
        semantic_code = str(getattr(component, "semantic_code", "") or "").strip()
        if semantic_code not in cls.SUPPORTED_SEMANTICS:
            raise PayrollStatutoryEngineError(f"Unsupported statutory semantic '{semantic_code}'.")

        scheme_type = cls.SCHEME_TYPE_BY_SEMANTIC[semantic_code]
        rule_context = cls._resolve_rule_context(
            semantic_code=semantic_code,
            scheme_type=scheme_type,
            component=component,
            calculation_input=calculation_input,
            policy=policy,
            payroll_date=payroll_date,
        )
        trace = cls._base_trace(
            component=component,
            scheme_type=scheme_type,
            rule_context=rule_context,
            profile=profile,
        )
        if not rule_context["is_applicable"]:
            trace["applicability_decision"] = rule_context["applicability_reason"]
            trace["final_amount"] = "0.00"
            return PayrollStatutoryResult(amount=ZERO2, trace=trace)

        if semantic_code in {PayrollComponent.SemanticCode.PF_EMPLOYEE, PayrollComponent.SemanticCode.PF_EMPLOYER}:
            return cls._calculate_pf(
                semantic_code=semantic_code,
                line=line,
                resolved=resolved,
                policy=policy,
                rule_context=rule_context,
                trace=trace,
            )
        if semantic_code in {PayrollComponent.SemanticCode.ESI_EMPLOYEE, PayrollComponent.SemanticCode.ESI_EMPLOYER}:
            return cls._calculate_esi(
                semantic_code=semantic_code,
                current_earning_total=current_earning_total,
                policy=policy,
                rule_context=rule_context,
                trace=trace,
            )
        if semantic_code == PayrollComponent.SemanticCode.PT:
            return cls._calculate_pt(
                current_earning_total=current_earning_total,
                policy=policy,
                rule_context=rule_context,
                trace=trace,
            )
        if semantic_code in {PayrollComponent.SemanticCode.LWF_EMPLOYEE, PayrollComponent.SemanticCode.LWF_EMPLOYER}:
            return cls._calculate_lwf(
                semantic_code=semantic_code,
                current_earning_total=current_earning_total,
                policy=policy,
                rule_context=rule_context,
                payroll_date=payroll_date,
                trace=trace,
            )
        return cls._calculate_tds_projection(
            policy=policy,
            rule_context=rule_context,
            calculation_input=calculation_input,
            profile=profile,
            resolved=resolved,
            component_map=component_map or {},
            trace=trace,
        )

    @classmethod
    def _base_trace(
        cls,
        *,
        component: PayrollComponent,
        scheme_type: str,
        rule_context: dict[str, Any],
        profile,
    ) -> dict[str, Any]:
        return {
            "engine": "payroll_statutory_engine",
            "component_semantic_code": getattr(component, "semantic_code", ""),
            "scheme": rule_context.get("scheme_snapshot") or {"scheme_type": scheme_type},
            "registration": rule_context.get("registration_snapshot") or {},
            "rule": rule_context.get("rule_snapshot") or {},
            "slab": {},
            "wage_base": None,
            "rate_or_amount": None,
            "cap_or_ceiling": None,
            "applicability_decision": rule_context.get("applicability_reason"),
            "rounding_trace": {"mode": "ROUND_HALF_UP", "quantize": "0.01"},
            "employee_code": getattr(profile, "employee_code", ""),
        }

    @classmethod
    def _resolve_rule_context(
        cls,
        *,
        semantic_code: str,
        scheme_type: str,
        component: PayrollComponent,
        calculation_input,
        policy: dict[str, Any] | None,
        payroll_date,
    ) -> dict[str, Any]:
        statutory_flags = getattr(calculation_input, "statutory_flags", None) or {}
        flag_name = cls.FLAG_BY_SCHEME_TYPE.get(scheme_type)
        flag_value = bool(statutory_flags.get(flag_name, False)) if flag_name else True
        if not flag_value:
            return {
                "is_applicable": False,
                "applicability_reason": f"{flag_name or scheme_type} flag is disabled",
                "scheme": None,
                "rule": None,
                "slabs": [],
                "registration": None,
                "override_rule_json": {},
            }

        profile_snapshot = cls._find_statutory_profile_snapshot(
            calculation_input=calculation_input,
            scheme_type=scheme_type,
            semantic_code=semantic_code,
        )
        if profile_snapshot and profile_snapshot.get("is_applicable") is False:
            return {
                "is_applicable": False,
                "applicability_reason": "contract statutory profile is marked not applicable",
                "scheme": None,
                "rule": None,
                "slabs": [],
                "registration": None,
                "override_rule_json": profile_snapshot.get("override_rule_json") or {},
                "scheme_snapshot": profile_snapshot,
            }

        scheme = cls._resolve_scheme(
            scheme_type=scheme_type,
            component=component,
            calculation_input=calculation_input,
            profile_snapshot=profile_snapshot,
        )
        registration = None
        rules: list[StatutoryRule] = []
        slabs: list[Any] = []
        rule = None
        if scheme is not None:
            registration = cls._resolve_registration(
                scheme=scheme,
                calculation_input=calculation_input,
                payroll_date=payroll_date,
            )
            rules = list(
                StatutoryRuleService.resolve_rules(
                    entity_id=getattr(calculation_input.contract_payroll_profile, "entity_id", None),
                    scheme=scheme,
                    rule_date=payroll_date,
                    state_code=registration.registration_state if registration else getattr(scheme, "state_code", ""),
                )
            )
            rule = rules[0] if rules else None
            slabs = list(StatutorySlabService.list_slabs(rule=rule, is_active=True)) if rule else []

        has_policy_fallback = cls._has_policy_fallback(scheme_type=scheme_type, policy=policy or {})
        if scheme is None and not has_policy_fallback:
            raise PayrollStatutoryEngineError(
                f"Missing statutory scheme/profile for applicable component {component.code} ({scheme_type})."
            )

        return {
            "is_applicable": True,
            "applicability_reason": "applicable",
            "scheme": scheme,
            "scheme_snapshot": profile_snapshot
            or (
                {
                    "scheme_id": str(scheme.id),
                    "scheme_code": scheme.code,
                    "scheme_name": scheme.name,
                    "scheme_type": scheme.scheme_type,
                }
                if scheme
                else {}
            ),
            "registration": registration,
            "registration_snapshot": (
                {
                    "registration_number": registration.registration_number,
                    "registration_state": registration.registration_state,
                    "scheme_code": registration.scheme.code,
                }
                if registration
                else {}
            ),
            "rule": rule,
            "rule_snapshot": (
                {
                    "id": str(rule.id),
                    "rule_code": rule.rule_code,
                    "rule_name": rule.rule_name,
                    "rule_type": rule.rule_type,
                    "rule_json": rule.rule_json or {},
                    "applicability_json": rule.applicability_json or {},
                }
                if rule
                else {}
            ),
            "slabs": slabs,
            "override_rule_json": (profile_snapshot or {}).get("override_rule_json") or {},
            "policy_fallback_enabled": has_policy_fallback,
        }

    @classmethod
    def _has_policy_fallback(cls, *, scheme_type: str, policy: dict[str, Any]) -> bool:
        if scheme_type == StatutoryScheme.SchemeType.PF:
            return bool(policy.get("pf_wage_cap") or policy.get("statutory_policy", {}).get("pf"))
        if scheme_type == StatutoryScheme.SchemeType.ESI:
            return bool(policy.get("esi_wage_threshold") or policy.get("statutory_policy", {}).get("esi"))
        if scheme_type == StatutoryScheme.SchemeType.PT:
            return bool(policy.get("professional_tax_amount") or policy.get("statutory_policy", {}).get("professional_tax"))
        if scheme_type == StatutoryScheme.SchemeType.LWF:
            return bool(policy.get("statutory_policy", {}).get("lwf") or policy.get("lwf_employee_amount") or policy.get("lwf_employer_amount"))
        if scheme_type == StatutoryScheme.SchemeType.TDS:
            return True
        return False

    @classmethod
    def _find_statutory_profile_snapshot(cls, *, calculation_input, scheme_type: str, semantic_code: str) -> dict[str, Any] | None:
        expected_scheme_code = cls.SCHEME_CODE_BY_SEMANTIC.get(semantic_code)
        for item in getattr(calculation_input, "statutory_profile_snapshots", []) or []:
            if item.get("scheme_type") == scheme_type:
                return item
            if expected_scheme_code and item.get("scheme_code") == expected_scheme_code:
                return item
        return None

    @classmethod
    def _resolve_scheme(cls, *, scheme_type: str, component: PayrollComponent, calculation_input, profile_snapshot: dict[str, Any] | None):
        scheme_id = (profile_snapshot or {}).get("scheme_id")
        if scheme_id:
            try:
                return StatutoryScheme.objects.get(id=scheme_id)
            except Exception:
                pass
        scheme_code = (profile_snapshot or {}).get("scheme_code") or cls.SCHEME_CODE_BY_SEMANTIC.get(
            str(getattr(component, "semantic_code", "") or "").strip()
        )
        country_code = getattr(component, "country_code", "") or "IN"
        state_code = getattr(component, "state_code", "")
        queryset = StatutorySchemeService.list_schemes(
            scheme_type=scheme_type,
            country_code=country_code or None,
            state_code=state_code or None,
            is_active=True,
        )
        if scheme_code:
            exact = queryset.filter(code=scheme_code).first()
            if exact:
                return exact
        return queryset.first()

    @classmethod
    def _resolve_registration(cls, *, scheme, calculation_input, payroll_date):
        entity_id = getattr(calculation_input.contract_payroll_profile, "entity_id", None)
        registration_snapshot = None
        for item in getattr(calculation_input, "statutory_registration_snapshots", []) or []:
            if item.get("scheme_id") == str(scheme.id) or item.get("scheme_code") == scheme.code:
                registration_snapshot = item
                break
        registration_state = (registration_snapshot or {}).get("registration_state") or getattr(scheme, "state_code", "")
        registration = EntityStatutoryRegistrationService.resolve_active_registration(
            entity_id=entity_id,
            scheme=scheme,
            registration_date=payroll_date,
            registration_state=registration_state,
        )
        if registration:
            return registration
        if registration_state:
            return EntityStatutoryRegistrationService.resolve_active_registration(
                entity_id=entity_id,
                scheme=scheme,
                registration_date=payroll_date,
                registration_state="",
            )
        return None

    @classmethod
    def _calculate_pf(
        cls,
        *,
        semantic_code: str,
        line: SalaryStructureLine,
        resolved: dict[int, Decimal],
        policy: dict[str, Any] | None,
        rule_context: dict[str, Any],
        trace: dict[str, Any],
    ) -> PayrollStatutoryResult:
        policy = policy or {}
        basis_amount = q2(resolved.get(line.basis_component_id, ZERO2))
        if basis_amount <= ZERO2:
            raise PayrollStatutoryEngineError("PF calculation requires a resolved basis component amount.")

        rule_json = cls._merged_rule_json(rule_context=rule_context)
        cap_value = cls._decimal(
            rule_json.get("wage_cap")
            or rule_json.get("ceiling")
            or policy.get("pf_wage_cap")
            or policy.get("statutory_policy", {}).get("pf", {}).get("wage_cap")
            or cls.DEFAULT_PF_WAGE_CAP
        )
        rate_key = "employee_rate" if semantic_code == PayrollComponent.SemanticCode.PF_EMPLOYEE else "employer_rate"
        policy_rate_key = "pf_employee_rate" if rate_key == "employee_rate" else "pf_employer_rate"
        rate_value = cls._decimal(
            rule_json.get(rate_key)
            or policy.get(policy_rate_key)
            or policy.get("statutory_policy", {}).get("pf", {}).get(rate_key)
            or (cls.DEFAULT_PF_EMPLOYEE_RATE if rate_key == "employee_rate" else cls.DEFAULT_PF_EMPLOYER_RATE)
        )
        capped_basis = min(basis_amount, q2(cap_value)) if cap_value > ZERO2 else basis_amount
        amount = q2(capped_basis * rate_value / Decimal("100.00"))
        trace["wage_base"] = str(basis_amount)
        trace["cap_or_ceiling"] = str(q2(cap_value))
        trace["rate_or_amount"] = str(q2(rate_value))
        trace["final_amount"] = str(amount)
        return PayrollStatutoryResult(amount=amount, trace=trace)

    @classmethod
    def _calculate_esi(
        cls,
        *,
        semantic_code: str,
        current_earning_total: Decimal,
        policy: dict[str, Any] | None,
        rule_context: dict[str, Any],
        trace: dict[str, Any],
    ) -> PayrollStatutoryResult:
        policy = policy or {}
        rule_json = cls._merged_rule_json(rule_context=rule_context)
        threshold = cls._decimal(
            rule_json.get("wage_threshold")
            or rule_json.get("eligibility_ceiling")
            or policy.get("esi_wage_threshold")
            or policy.get("statutory_policy", {}).get("esi", {}).get("wage_threshold")
            or cls.DEFAULT_ESI_WAGE_THRESHOLD
        )
        trace["wage_base"] = str(q2(current_earning_total))
        trace["cap_or_ceiling"] = str(q2(threshold))
        if q2(current_earning_total) <= ZERO2:
            trace["applicability_decision"] = "no eligible earnings"
            trace["final_amount"] = "0.00"
            return PayrollStatutoryResult(amount=ZERO2, trace=trace)
        if threshold > ZERO2 and q2(current_earning_total) > q2(threshold):
            trace["applicability_decision"] = "earnings exceed ESI threshold"
            trace["final_amount"] = "0.00"
            return PayrollStatutoryResult(amount=ZERO2, trace=trace)

        rate_key = "employee_rate" if semantic_code == PayrollComponent.SemanticCode.ESI_EMPLOYEE else "employer_rate"
        policy_rate_key = "esi_employee_rate" if rate_key == "employee_rate" else "esi_employer_rate"
        rate_value = cls._decimal(
            rule_json.get(rate_key)
            or policy.get(policy_rate_key)
            or policy.get("statutory_policy", {}).get("esi", {}).get(rate_key)
            or (cls.DEFAULT_ESI_EMPLOYEE_RATE if rate_key == "employee_rate" else cls.DEFAULT_ESI_EMPLOYER_RATE)
        )
        amount = q2(q2(current_earning_total) * rate_value / Decimal("100.00"))
        trace["rate_or_amount"] = str(q2(rate_value))
        trace["final_amount"] = str(amount)
        return PayrollStatutoryResult(amount=amount, trace=trace)

    @classmethod
    def _calculate_pt(
        cls,
        *,
        current_earning_total: Decimal,
        policy: dict[str, Any] | None,
        rule_context: dict[str, Any],
        trace: dict[str, Any],
    ) -> PayrollStatutoryResult:
        policy = policy or {}
        slabs = rule_context.get("slabs") or []
        wage_base = q2(current_earning_total)
        trace["wage_base"] = str(wage_base)
        if slabs:
            amount, slab_trace = cls._match_slab(
                slabs=slabs,
                wage_base=wage_base,
            )
            trace["slab"] = slab_trace
            trace["rate_or_amount"] = slab_trace.get("applied_value")
            trace["final_amount"] = str(amount)
            return PayrollStatutoryResult(amount=amount, trace=trace)

        rule_json = cls._merged_rule_json(rule_context=rule_context)
        threshold = cls._decimal(
            rule_json.get("threshold")
            or policy.get("professional_tax_threshold")
            or policy.get("statutory_policy", {}).get("professional_tax", {}).get("threshold")
        )
        amount = cls._decimal(
            rule_json.get("amount")
            or policy.get("professional_tax_amount")
            or policy.get("statutory_policy", {}).get("professional_tax", {}).get("amount")
        )
        trace["cap_or_ceiling"] = str(q2(threshold))
        trace["rate_or_amount"] = str(q2(amount))
        if amount <= ZERO2:
            raise PayrollStatutoryEngineError("Missing Professional Tax amount/slab configuration.")
        if threshold > ZERO2 and wage_base < q2(threshold):
            trace["applicability_decision"] = "below Professional Tax threshold"
            trace["final_amount"] = "0.00"
            return PayrollStatutoryResult(amount=ZERO2, trace=trace)
        trace["final_amount"] = str(q2(amount))
        return PayrollStatutoryResult(amount=q2(amount), trace=trace)

    @classmethod
    def _calculate_lwf(
        cls,
        *,
        semantic_code: str,
        current_earning_total: Decimal,
        policy: dict[str, Any] | None,
        rule_context: dict[str, Any],
        payroll_date,
        trace: dict[str, Any],
    ) -> PayrollStatutoryResult:
        policy = policy or {}
        rule_json = cls._merged_rule_json(rule_context=rule_context)
        if not cls._is_lwf_due(rule_json=rule_json, payroll_date=payroll_date):
            trace["applicability_decision"] = "LWF periodicity excludes this payroll period"
            trace["final_amount"] = "0.00"
            return PayrollStatutoryResult(amount=ZERO2, trace=trace)

        slabs = rule_context.get("slabs") or []
        wage_base = q2(current_earning_total)
        trace["wage_base"] = str(wage_base)
        if slabs:
            amount, slab_trace = cls._match_slab(slabs=slabs, wage_base=wage_base)
            if semantic_code == PayrollComponent.SemanticCode.LWF_EMPLOYER and cls._decimal(rule_json.get("employer_amount")) > ZERO2:
                amount = cls._decimal(rule_json.get("employer_amount"))
                slab_trace["applied_value"] = str(q2(amount))
            elif semantic_code == PayrollComponent.SemanticCode.LWF_EMPLOYEE and cls._decimal(rule_json.get("employee_amount")) > ZERO2:
                amount = cls._decimal(rule_json.get("employee_amount"))
                slab_trace["applied_value"] = str(q2(amount))
            trace["slab"] = slab_trace
            trace["rate_or_amount"] = slab_trace.get("applied_value")
            trace["final_amount"] = str(q2(amount))
            return PayrollStatutoryResult(amount=q2(amount), trace=trace)

        amount_key = "employee_amount" if semantic_code == PayrollComponent.SemanticCode.LWF_EMPLOYEE else "employer_amount"
        amount = cls._decimal(
            rule_json.get(amount_key)
            or policy.get(f"lwf_{'employee' if amount_key == 'employee_amount' else 'employer'}_amount")
            or policy.get("statutory_policy", {}).get("lwf", {}).get(amount_key)
            or rule_json.get("amount")
        )
        if amount <= ZERO2:
            raise PayrollStatutoryEngineError("Missing LWF amount/slab configuration.")
        trace["rate_or_amount"] = str(q2(amount))
        trace["final_amount"] = str(q2(amount))
        return PayrollStatutoryResult(amount=q2(amount), trace=trace)

    @classmethod
    def _calculate_tds_projection(
        cls,
        *,
        policy: dict[str, Any] | None,
        rule_context: dict[str, Any],
        calculation_input,
        profile,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent],
        trace: dict[str, Any],
    ) -> PayrollStatutoryResult:
        policy = policy or {}
        snapshot = getattr(calculation_input, "tax_projection_snapshot", None) or {}
        result = PayrollTDSEngine.build_projection(
            contract_payroll_profile=getattr(calculation_input, "contract_payroll_profile", None),
            salary_assignment=getattr(calculation_input, "salary_assignment", None),
            tax_regime=getattr(calculation_input, "tax_regime", None) or profile.tax_regime,
            policy=policy,
            existing_snapshot=snapshot,
            payroll_period=getattr(calculation_input, "payroll_period", None),
            monthly_gross_amount=q2(getattr(calculation_input, "gross_amount", ZERO2)),
            monthly_ctc_amount=q2(getattr(calculation_input, "ctc_amount", ZERO2)),
            resolved=resolved,
            component_map=component_map,
        )
        trace["wage_base"] = result.trace.get("taxable_income")
        trace["rate_or_amount"] = result.trace.get("monthly_tds")
        trace["final_amount"] = result.trace.get("monthly_tds")
        trace["tds_projection_trace"] = result.trace
        trace["limitation"] = "TDS is projected from declaration and payroll snapshots through the dedicated payroll TDS engine."
        if result.monthly_tds <= ZERO2:
            trace["applicability_decision"] = "no projected annual tax"
        else:
            trace["applicability_decision"] = "tds projection snapshot"
        return PayrollStatutoryResult(amount=q2(result.monthly_tds), trace=trace)

    @classmethod
    def _match_slab(cls, *, slabs: list[Any], wage_base: Decimal) -> tuple[Decimal, dict[str, Any]]:
        for slab in slabs:
            lower_bound = q2(getattr(slab, "slab_from", ZERO2))
            upper_bound = getattr(slab, "slab_to", None)
            upper_bound_decimal = q2(upper_bound) if upper_bound is not None else None
            if wage_base < lower_bound:
                continue
            if upper_bound_decimal is not None and wage_base > upper_bound_decimal:
                continue
            fixed_amount = q2(getattr(slab, "amount", ZERO2))
            percentage = q2(getattr(slab, "percentage", ZERO2))
            if fixed_amount > ZERO2:
                return fixed_amount, {
                    "id": str(slab.id),
                    "slab_from": str(lower_bound),
                    "slab_to": str(upper_bound_decimal) if upper_bound_decimal is not None else None,
                    "applied_value": str(fixed_amount),
                }
            if percentage > ZERO2:
                amount = q2(wage_base * percentage / Decimal("100.00"))
                return amount, {
                    "id": str(slab.id),
                    "slab_from": str(lower_bound),
                    "slab_to": str(upper_bound_decimal) if upper_bound_decimal is not None else None,
                    "applied_value": str(q2(percentage)),
                }
            raise PayrollStatutoryEngineError(f"Unable to interpret statutory slab {slab.id}.")
        return ZERO2, {}

    @classmethod
    def _is_lwf_due(cls, *, rule_json: dict[str, Any], payroll_date) -> bool:
        applicable_months = rule_json.get("applicable_months") or rule_json.get("month_numbers") or []
        if applicable_months:
            return int(payroll_date.month) in {int(item) for item in applicable_months}
        periodicity = str(rule_json.get("periodicity") or "MONTHLY").strip().upper()
        if periodicity == "MONTHLY":
            return True
        if periodicity == "QUARTERLY":
            return payroll_date.month in {3, 6, 9, 12}
        if periodicity == "HALF_YEARLY":
            return payroll_date.month in {6, 12}
        if periodicity == "YEARLY":
            return payroll_date.month == 12
        return True

    @classmethod
    def _merged_rule_json(cls, *, rule_context: dict[str, Any]) -> dict[str, Any]:
        merged = {}
        merged.update((rule_context.get("rule_snapshot") or {}).get("rule_json") or {})
        merged.update(rule_context.get("override_rule_json") or {})
        return merged

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except Exception:
            return ZERO2

    @staticmethod
    def _normalize_tax_regime(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"new", "new_regime"}:
            return "new_regime"
        if normalized in {"old", "old_regime"}:
            return "old_regime"
        return normalized or "old_regime"

    @staticmethod
    def _policy_slabs(policy: dict | None, key: str) -> list[dict]:
        raw = (policy or {}).get(key)
        if not isinstance(raw, list):
            return []
        normalized = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                rate = Decimal(str(item.get("rate") or "0"))
            except Exception:
                continue
            upto_raw = item.get("upto")
            upto = None
            if upto_raw not in (None, ""):
                try:
                    upto = Decimal(str(upto_raw))
                except Exception:
                    continue
            normalized.append({"upto": upto, "rate": rate})
        return normalized

    @classmethod
    def _resolve_policy_slabs(cls, *, tax_regime: str, policy: dict | None) -> list[dict]:
        if tax_regime == "new_regime":
            return cls._policy_slabs(policy, "tds_new_regime_slabs")
        return cls._policy_slabs(policy, "tds_old_regime_slabs")

    @staticmethod
    def _compute_tax_from_slabs(*, taxable_income: Decimal, slabs: list[dict]) -> Decimal:
        if taxable_income <= ZERO2 or not slabs:
            return ZERO2
        previous_limit = ZERO2
        annual_tax = ZERO2
        for slab in slabs:
            upper_limit = slab.get("upto")
            rate = q2(slab.get("rate"))
            if rate <= ZERO2 and upper_limit is None:
                continue
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
        policy: dict | None,
    ) -> Decimal:
        threshold_key = "tds_rebate_threshold_new_regime" if tax_regime == "new_regime" else "tds_rebate_threshold_old_regime"
        max_key = "tds_rebate_max_new_regime" if tax_regime == "new_regime" else "tds_rebate_max_old_regime"
        rebate_threshold = cls._decimal((policy or {}).get(threshold_key))
        rebate_max = cls._decimal((policy or {}).get(max_key))
        if rebate_threshold <= ZERO2 or rebate_max <= ZERO2 or projected_taxable_income > q2(rebate_threshold):
            return annual_tax
        return max(q2(annual_tax - min(annual_tax, rebate_max)), ZERO2)

    @classmethod
    def _resolve_surcharge_bracket(cls, *, projected_taxable_income: Decimal, tax_regime: str, policy: dict | None) -> dict:
        if projected_taxable_income <= ZERO2:
            return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}
        slabs = cls._policy_slabs(policy, "tds_new_regime_surcharge_slabs" if tax_regime == "new_regime" else "tds_old_regime_surcharge_slabs")
        if not slabs:
            return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}
        previous_rate = ZERO2
        previous_upper_limit = ZERO2
        for slab in slabs:
            upper_limit = slab.get("upto")
            rate = q2(slab.get("rate"))
            if upper_limit is None:
                return {"rate": rate, "threshold_income": previous_upper_limit, "previous_rate": previous_rate}
            if projected_taxable_income <= q2(upper_limit):
                return {"rate": rate, "threshold_income": previous_upper_limit, "previous_rate": previous_rate}
            previous_rate = rate
            previous_upper_limit = q2(upper_limit)
        return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}

    @classmethod
    def _apply_marginal_relief(
        cls,
        *,
        subtotal_with_surcharge: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict | None,
    ) -> Decimal:
        if subtotal_with_surcharge <= ZERO2:
            return ZERO2
        raw_flag = (policy or {}).get("tds_apply_marginal_relief", True)
        if isinstance(raw_flag, bool):
            apply_flag = raw_flag
        else:
            apply_flag = str(raw_flag).strip().lower() in {"1", "true", "yes", "y", "on"}
        if not apply_flag:
            return subtotal_with_surcharge
        surcharge_bracket = cls._resolve_surcharge_bracket(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        current_rate = q2(surcharge_bracket.get("rate"))
        previous_rate = q2(surcharge_bracket.get("previous_rate"))
        threshold_income = q2(surcharge_bracket.get("threshold_income"))
        if current_rate <= previous_rate or threshold_income <= ZERO2 or projected_taxable_income <= threshold_income:
            return subtotal_with_surcharge
        slabs = cls._resolve_policy_slabs(tax_regime=tax_regime, policy=policy)
        if not slabs:
            return subtotal_with_surcharge
        threshold_tax = cls._compute_tax_from_slabs(taxable_income=threshold_income, slabs=slabs)
        threshold_tax = cls._apply_regime_rebate(
            annual_tax=threshold_tax,
            projected_taxable_income=threshold_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        threshold_subtotal = q2(threshold_tax + q2(threshold_tax * previous_rate / Decimal("100.00")))
        max_subtotal = q2(threshold_subtotal + q2(projected_taxable_income - threshold_income))
        return min(subtotal_with_surcharge, max_subtotal)

    @classmethod
    def _apply_surcharge_and_cess(
        cls,
        *,
        annual_tax: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict | None,
    ) -> Decimal:
        if annual_tax <= ZERO2:
            return ZERO2
        surcharge_bracket = cls._resolve_surcharge_bracket(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        surcharge_rate = q2(surcharge_bracket.get("rate"))
        surcharge_amount = q2(annual_tax * surcharge_rate / Decimal("100.00")) if surcharge_rate > ZERO2 else ZERO2
        subtotal = q2(annual_tax + surcharge_amount)
        subtotal = cls._apply_marginal_relief(
            subtotal_with_surcharge=subtotal,
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        cess_rate = cls._decimal((policy or {}).get("tds_health_education_cess_rate"))
        if cess_rate <= ZERO2:
            return subtotal
        return q2(subtotal + q2(subtotal * cess_rate / Decimal("100.00")))

    @classmethod
    def _resolve_standard_deduction(cls, *, tax_regime: str, policy: dict | None) -> Decimal:
        key = "tds_standard_deduction_new_regime" if tax_regime == "new_regime" else "tds_standard_deduction_old_regime"
        return cls._decimal((policy or {}).get(key) or Decimal("50000.00"))

    @classmethod
    def _estimate_annual_component_amount(
        cls,
        *,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent],
        semantic_code: str,
    ) -> Decimal:
        for component_id, amount in resolved.items():
            component = component_map.get(component_id)
            if component and getattr(component, "semantic_code", "") == semantic_code:
                return q2(q2(amount) * Decimal("12.00"))
        return ZERO2

    @classmethod
    def _resolve_hra_exemption_amount(
        cls,
        *,
        snapshot: dict[str, Any],
        policy: dict | None,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent],
    ) -> Decimal:
        declared_hra = q2(snapshot.get("hra_exemption"))
        annual_hra_received = cls._estimate_annual_component_amount(
            resolved=resolved,
            component_map=component_map,
            semantic_code=PayrollComponent.SemanticCode.HRA,
        )
        annual_basic = cls._estimate_annual_component_amount(
            resolved=resolved,
            component_map=component_map,
            semantic_code=PayrollComponent.SemanticCode.BASIC_PAY,
        )
        rent_paid_annual = q2(snapshot.get("hra_rent_paid_annual"))
        metro_flag = snapshot.get("hra_is_metro_city")
        if annual_hra_received <= ZERO2 or annual_basic <= ZERO2 or rent_paid_annual <= ZERO2 or metro_flag is None:
            return declared_hra
        rent_months = q2(snapshot.get("hra_rent_months"))
        if Decimal("1.00") <= rent_months <= Decimal("12.00"):
            month_multiplier = (rent_months / Decimal("12.00")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            annual_hra_received = q2(annual_hra_received * month_multiplier)
            annual_basic = q2(annual_basic * month_multiplier)
        city_basic_percent = Decimal("0.50") if bool(metro_flag) else Decimal("0.40")
        rent_minus_basic_threshold = max(q2(rent_paid_annual - q2(annual_basic * Decimal("0.10"))), ZERO2)
        city_cap = q2(annual_basic * city_basic_percent)
        derived_cap = min(annual_hra_received, rent_minus_basic_threshold, city_cap)
        return min(declared_hra, derived_cap) if declared_hra > ZERO2 else derived_cap

    @classmethod
    def _resolve_declared_deductions(
        cls,
        *,
        snapshot: dict[str, Any],
        tax_regime: str,
        policy: dict | None,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent],
    ) -> Decimal:
        if tax_regime == "new_regime":
            return ZERO2
        generic_declared = q2(snapshot.get("other_old_regime_deductions") or snapshot.get("declared_deductions"))
        deduction_80c = ZERO2
        deduction_80d = ZERO2
        hra_exemption = ZERO2
        if str((policy or {}).get("tds_allow_80c_old_regime", True)).lower() not in {"false", "0", "no", "off"}:
            deduction_80c = min(q2(snapshot.get("deduction_80c")), cls._decimal((policy or {}).get("tds_80c_cap") or Decimal("150000.00")))
        if str((policy or {}).get("tds_allow_80d_old_regime", True)).lower() not in {"false", "0", "no", "off"}:
            deduction_80d = min(q2(snapshot.get("deduction_80d")), cls._decimal((policy or {}).get("tds_80d_cap") or Decimal("25000.00")))
        if str((policy or {}).get("tds_allow_hra_exemption_old_regime", True)).lower() not in {"false", "0", "no", "off"}:
            hra_exemption = cls._resolve_hra_exemption_amount(
                snapshot=snapshot,
                policy=policy,
                resolved=resolved,
                component_map=component_map,
            )
        return q2(generic_declared + deduction_80c + deduction_80d + hra_exemption)

    @classmethod
    def _resolve_projected_taxable_income(
        cls,
        *,
        profile,
        policy: dict | None,
        calculation_input,
        resolved: dict[int, Decimal],
        component_map: dict[int, PayrollComponent],
    ) -> Decimal:
        snapshot = getattr(calculation_input, "tax_projection_snapshot", None) or {}
        explicit_taxable_income = q2(snapshot.get("projected_taxable_income") or snapshot.get("annual_taxable_income"))
        if explicit_taxable_income > ZERO2:
            return explicit_taxable_income
        manual_input_snapshot = getattr(calculation_input, "manual_input_snapshot", None) or {}
        annual_salary_basis = q2(manual_input_snapshot.get("fixed_salary"))
        if annual_salary_basis <= ZERO2:
            annual_salary_basis = q2(getattr(calculation_input, "gross_amount", ZERO2)) or q2(getattr(calculation_input, "ctc_amount", ZERO2)) or q2(q2(profile.ctc_annual) / Decimal("12.00"))
        annualized_current_salary = q2(annual_salary_basis * Decimal("12.00"))
        other_income = q2(snapshot.get("other_income"))
        previous_employer_taxable_income = q2(snapshot.get("previous_employer_taxable_income") or snapshot.get("previous_employer_income"))
        tax_regime = cls._normalize_tax_regime(getattr(calculation_input, "tax_regime", None) or profile.tax_regime)
        standard_deduction = cls._resolve_standard_deduction(tax_regime=tax_regime, policy=policy)
        declared_deductions = cls._resolve_declared_deductions(
            snapshot=snapshot,
            tax_regime=tax_regime,
            policy=policy,
            resolved=resolved,
            component_map=component_map,
        )
        return max(q2(annualized_current_salary + other_income + previous_employer_taxable_income - standard_deduction - declared_deductions), ZERO2)
