from __future__ import annotations

from typing import Dict

from gst_reconciliation.models import GstReconciliationRun
from gst_reconciliation.services.matching.base import BaseReconciliationMatcher


class MatcherRegistry:
    _registry: Dict[str, BaseReconciliationMatcher] = {}

    @classmethod
    def register(cls, matcher: BaseReconciliationMatcher) -> None:
        cls._registry[matcher.code] = matcher

    @classmethod
    def get(cls, code: str) -> BaseReconciliationMatcher:
        matcher = cls._registry.get(code or "default") or cls._registry.get("default")
        if matcher is None:
            raise KeyError(f"No GST reconciliation matcher registered for code '{code}'.")
        return matcher

    @classmethod
    def get_for_run(cls, run: GstReconciliationRun) -> BaseReconciliationMatcher:
        matcher = cls.get(run.match_strategy_code)
        if not matcher.supports(run):
            raise ValueError(
                f"Matcher '{matcher.code}' does not support reconciliation type '{run.reconciliation_type}'."
            )
        return matcher

