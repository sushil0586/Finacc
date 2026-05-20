from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from gst_reconciliation.models import GstReconciliationRun


@dataclass(frozen=True)
class MatchExecutionResult:
    run: GstReconciliationRun
    processed_items: int
    matched_items: int
    partial_items: int
    mismatched_items: int
    ignored_items: int = 0


class BaseReconciliationMatcher(ABC):
    code = "default"

    @abstractmethod
    def supports(self, run: GstReconciliationRun) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute(self, run: GstReconciliationRun, *, user=None) -> MatchExecutionResult:
        raise NotImplementedError

