from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollRuleEngineError(ValueError):
    pass


@dataclass(frozen=True)
class PayrollRuleApplicationResult:
    amount: Decimal
    trace: dict[str, Any]


class PayrollRuleEngine:
    @classmethod
    def apply(
        cls,
        *,
        amount: Decimal,
        rule_json: dict[str, Any] | None,
        variables: dict[str, Any] | None,
    ) -> PayrollRuleApplicationResult:
        normalized_rule_json = rule_json if isinstance(rule_json, dict) else {}
        normalized_variables = dict(variables or {})
        current_amount = q2(amount)
        if not normalized_rule_json:
            return PayrollRuleApplicationResult(amount=current_amount, trace={})

        trace: dict[str, Any] = {
            "input_amount": str(current_amount),
            "rule_json": normalized_rule_json,
            "steps": [],
        }

        if not cls._is_applicable(normalized_rule_json, normalized_variables):
            trace["applicability"] = "not_applicable"
            return PayrollRuleApplicationResult(amount=ZERO2, trace=trace)
        trace["applicability"] = "applied"

        percentage_config = cls._percentage_config(normalized_rule_json)
        if percentage_config:
            basis_value = cls._resolve_basis_value(
                basis=percentage_config.get("basis"),
                variables=normalized_variables,
                fallback=current_amount,
            )
            percentage_value = cls._decimal(
                percentage_config.get("rate")
                or percentage_config.get("percentage")
                or normalized_rule_json.get("percentage")
            )
            current_amount = q2(basis_value * percentage_value / Decimal("100.00"))
            trace["steps"].append(
                {
                    "type": "percentage",
                    "basis": percentage_config.get("basis"),
                    "basis_value": str(q2(basis_value)),
                    "percentage": str(q2(percentage_value)),
                    "result": str(current_amount),
                }
            )

        slabs = cls._slabs(normalized_rule_json)
        if slabs:
            slab_basis = cls._resolve_basis_value(
                basis=normalized_rule_json.get("slab_basis") or normalized_rule_json.get("basis"),
                variables=normalized_variables,
                fallback=current_amount,
            )
            current_amount = cls._apply_slabs(slabs=slabs, basis_value=slab_basis)
            trace["steps"].append(
                {
                    "type": "slab",
                    "basis_value": str(q2(slab_basis)),
                    "result": str(current_amount),
                }
            )

        if current_amount <= ZERO2:
            fallback_amount = cls._decimal(
                normalized_rule_json.get("fixed_amount_fallback")
                or normalized_rule_json.get("fallback_amount")
                or normalized_rule_json.get("default_amount")
            )
            if fallback_amount > ZERO2:
                current_amount = fallback_amount
                trace["steps"].append(
                    {
                        "type": "fixed_fallback",
                        "result": str(current_amount),
                    }
                )

        min_amount = cls._decimal(
            normalized_rule_json.get("min_amount") or normalized_rule_json.get("minimum")
        )
        if min_amount > ZERO2 and current_amount < min_amount:
            current_amount = min_amount
            trace["steps"].append({"type": "min_cap", "result": str(current_amount)})

        max_amount = cls._decimal(
            normalized_rule_json.get("max_amount")
            or normalized_rule_json.get("maximum")
            or normalized_rule_json.get("cap_amount")
        )
        if max_amount > ZERO2 and current_amount > max_amount:
            current_amount = max_amount
            trace["steps"].append({"type": "max_cap", "result": str(current_amount)})

        return PayrollRuleApplicationResult(amount=q2(current_amount), trace=trace)

    @classmethod
    def _is_applicable(cls, rule_json: dict[str, Any], variables: dict[str, Any]) -> bool:
        condition = rule_json.get("applicability") or rule_json.get("condition") or rule_json.get("applicable_if")
        if not condition:
            return True
        return cls._evaluate_condition(condition, variables)

    @classmethod
    def _evaluate_condition(cls, condition: Any, variables: dict[str, Any]) -> bool:
        if isinstance(condition, bool):
            return condition
        if isinstance(condition, list):
            return all(cls._evaluate_condition(item, variables) for item in condition)
        if isinstance(condition, dict):
            if "all" in condition:
                return all(cls._evaluate_condition(item, variables) for item in condition.get("all", []))
            if "any" in condition:
                return any(cls._evaluate_condition(item, variables) for item in condition.get("any", []))

            variable_name = str(condition.get("variable") or condition.get("field") or "").strip()
            if not variable_name:
                raise PayrollRuleEngineError("Conditional applicability is missing a variable name.")
            if variable_name not in variables:
                raise PayrollRuleEngineError(
                    f"Conditional applicability references unknown variable '{variable_name}'."
                )
            operator = str(condition.get("operator") or "eq").strip().lower()
            left_value = variables[variable_name]
            right_value = condition.get("value")
            if operator == "truthy":
                return bool(left_value)
            if operator == "falsy":
                return not bool(left_value)

            left_decimal = cls._decimal(left_value)
            right_decimal = cls._decimal(right_value)
            if operator == "eq":
                return left_decimal == right_decimal
            if operator in {"neq", "ne"}:
                return left_decimal != right_decimal
            if operator == "gt":
                return left_decimal > right_decimal
            if operator == "gte":
                return left_decimal >= right_decimal
            if operator == "lt":
                return left_decimal < right_decimal
            if operator == "lte":
                return left_decimal <= right_decimal
            raise PayrollRuleEngineError(
                f"Conditional applicability operator '{operator}' is not supported."
            )
        raise PayrollRuleEngineError("Conditional applicability must be a boolean, list, or object.")

    @classmethod
    def _percentage_config(cls, rule_json: dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(rule_json.get("percentage"), dict):
            return rule_json.get("percentage")
        if rule_json.get("rule_type") == "percentage":
            return rule_json
        return None

    @classmethod
    def _slabs(cls, rule_json: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(rule_json.get("slabs"), list):
            return [item for item in rule_json.get("slabs", []) if isinstance(item, dict)]
        if rule_json.get("rule_type") == "slab" and isinstance(rule_json.get("slab"), list):
            return [item for item in rule_json.get("slab", []) if isinstance(item, dict)]
        return []

    @classmethod
    def _apply_slabs(cls, *, slabs: list[dict[str, Any]], basis_value: Decimal) -> Decimal:
        normalized_basis = q2(basis_value)
        for slab in slabs:
            lower_bound = cls._decimal(
                slab.get("from") if slab.get("from") not in (None, "") else slab.get("min")
            )
            upper_bound_raw = slab.get("to")
            if upper_bound_raw in (None, ""):
                upper_bound_raw = slab.get("upto")
            if upper_bound_raw in (None, ""):
                upper_bound_raw = slab.get("max")
            upper_bound = None if upper_bound_raw in (None, "") else cls._decimal(upper_bound_raw)

            if normalized_basis < lower_bound:
                continue
            if upper_bound is not None and normalized_basis > upper_bound:
                continue

            amount = cls._decimal(slab.get("amount") or slab.get("fixed_amount"))
            if amount > ZERO2:
                return amount

            percentage = cls._decimal(slab.get("percentage") or slab.get("rate"))
            if percentage > ZERO2:
                return q2(normalized_basis * percentage / Decimal("100.00"))

            return ZERO2
        return ZERO2

    @classmethod
    def _resolve_basis_value(
        cls,
        *,
        basis: Any,
        variables: dict[str, Any],
        fallback: Decimal,
    ) -> Decimal:
        if isinstance(basis, list):
            basis = basis[0] if basis else None
        if basis in (None, "", "base_amount"):
            return q2(fallback)
        basis_name = str(basis)
        if basis_name not in variables:
            raise PayrollRuleEngineError(f"Rule basis '{basis_name}' is not available in the calculation context.")
        return cls._decimal(variables[basis_name])

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except Exception as exc:
            raise PayrollRuleEngineError(f"Unable to coerce rule value '{value}' into Decimal.") from exc
