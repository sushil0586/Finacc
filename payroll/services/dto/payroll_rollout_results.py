from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class IssueSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class IssueRecord:
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.BLOCKING
    scope: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MetricComparison:
    name: str
    legacy_value: Decimal = Decimal("0.00")
    new_value: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    tolerance: Decimal = Decimal("0.00")
    passed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "legacy_value": str(self.legacy_value),
            "new_value": str(self.new_value),
            "difference": str(self.difference),
            "tolerance": str(self.tolerance),
            "passed": self.passed,
        }


@dataclass(slots=True)
class ReconciliationBlock:
    key: str
    status: str
    metrics: list[MetricComparison] = field(default_factory=list)
    issues: list[IssueRecord] = field(default_factory=list)
    drilldown_rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "metrics": [metric.as_dict() for metric in self.metrics],
            "issues": [issue.as_dict() for issue in self.issues],
            "drilldown_rows": self.drilldown_rows,
        }


@dataclass(slots=True)
class RolloutValidationResult:
    name: str
    scope: dict[str, Any]
    issues: list[IssueRecord] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> list[IssueRecord]:
        return [issue for issue in self.issues if issue.severity == IssueSeverity.BLOCKING]

    @property
    def warnings(self) -> list[IssueRecord]:
        return [issue for issue in self.issues if issue.severity == IssueSeverity.WARNING]

    @property
    def passed(self) -> bool:
        return not self.blocking_issues

    def add_issue(self, code: str, message: str, *, severity: IssueSeverity = IssueSeverity.BLOCKING, detail: dict[str, Any] | None = None) -> None:
        self.issues.append(IssueRecord(code=code, message=message, severity=severity, scope=self.scope, detail=detail or {}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scope": self.scope,
            "passed": self.passed,
            "summary": self.summary,
            "checks": self.checks,
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(slots=True)
class ShadowRunValidationResult(RolloutValidationResult):
    payroll_run_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        data = RolloutValidationResult.as_dict(self)
        data["payroll_run_id"] = self.payroll_run_id
        return data


@dataclass(slots=True)
class ReconciliationResult:
    name: str
    scope: dict[str, Any]
    blocks: list[ReconciliationBlock] = field(default_factory=list)
    issues: list[IssueRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> list[IssueRecord]:
        return [issue for issue in self.issues if issue.severity == IssueSeverity.BLOCKING]

    @property
    def passed(self) -> bool:
        return not self.blocking_issues and all(block.status == "pass" for block in self.blocks)

    def add_issue(self, code: str, message: str, *, severity: IssueSeverity = IssueSeverity.BLOCKING, detail: dict[str, Any] | None = None) -> None:
        self.issues.append(IssueRecord(code=code, message=message, severity=severity, scope=self.scope, detail=detail or {}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scope": self.scope,
            "passed": self.passed,
            "metadata": self.metadata,
            "issues": [issue.as_dict() for issue in self.issues],
            "blocks": [block.as_dict() for block in self.blocks],
        }
