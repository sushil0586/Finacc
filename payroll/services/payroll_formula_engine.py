from __future__ import annotations

import ast
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollFormulaEngineError(ValueError):
    pass


class UnknownPayrollFormulaVariableError(PayrollFormulaEngineError):
    pass


class UnsafePayrollFormulaError(PayrollFormulaEngineError):
    pass


class PayrollFormulaEngine:
    ALLOWED_BINARY_OPERATORS = {
        ast.Add: lambda left, right: left + right,
        ast.Sub: lambda left, right: left - right,
        ast.Mult: lambda left, right: left * right,
        ast.Div: lambda left, right: left / right,
        ast.Mod: lambda left, right: left % right,
    }
    ALLOWED_UNARY_OPERATORS = {
        ast.UAdd: lambda value: value,
        ast.USub: lambda value: -value,
    }

    @classmethod
    def evaluate(cls, *, formula: str, variables: dict[str, Any]) -> Decimal:
        normalized_formula = str(formula or "").strip()
        if not normalized_formula:
            raise UnsafePayrollFormulaError("Formula cannot be blank.")

        try:
            tree = ast.parse(normalized_formula, mode="eval")
        except SyntaxError as exc:
            raise UnsafePayrollFormulaError(f"Invalid formula syntax: {exc.msg}.") from exc

        normalized_variables = {
            str(key): value
            for key, value in (variables or {}).items()
        }
        try:
            return q2(cls._evaluate_node(tree.body, normalized_variables))
        except PayrollFormulaEngineError:
            raise
        except ZeroDivisionError as exc:
            raise UnsafePayrollFormulaError("Division by zero is not allowed in payroll formulas.") from exc
        except Exception as exc:
            raise UnsafePayrollFormulaError(f"Unsupported formula execution error: {exc}") from exc

    @classmethod
    def _evaluate_node(cls, node: ast.AST, variables: dict[str, Decimal]) -> Decimal:
        if isinstance(node, ast.BinOp):
            operator = cls.ALLOWED_BINARY_OPERATORS.get(type(node.op))
            if operator is None:
                raise UnsafePayrollFormulaError(
                    f"Operator {type(node.op).__name__} is not allowed in payroll formulas."
                )
            return operator(cls._evaluate_node(node.left, variables), cls._evaluate_node(node.right, variables))

        if isinstance(node, ast.UnaryOp):
            operator = cls.ALLOWED_UNARY_OPERATORS.get(type(node.op))
            if operator is None:
                raise UnsafePayrollFormulaError(
                    f"Unary operator {type(node.op).__name__} is not allowed in payroll formulas."
                )
            return operator(cls._evaluate_node(node.operand, variables))

        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise UnknownPayrollFormulaVariableError(
                    f"Unknown payroll formula variable '{node.id}'."
                )
            return cls._coerce_value(variables[node.id])

        if isinstance(node, ast.Constant):
            return cls._coerce_value(node.value)

        raise UnsafePayrollFormulaError(
            f"Formula node {type(node).__name__} is not allowed in payroll formulas."
        )

    @staticmethod
    def _coerce_value(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            return Decimal("1") if value else Decimal("0")
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise UnsafePayrollFormulaError(f"Unable to coerce value '{value}' into Decimal.") from exc
