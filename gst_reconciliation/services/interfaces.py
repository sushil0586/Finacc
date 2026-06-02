from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gst_reconciliation.models import GstImportedReturn, GstReconciliationRun


class ReconciliationRunBuilder(ABC):
    @abstractmethod
    def build_run(self, **kwargs: Any) -> GstReconciliationRun:
        raise NotImplementedError


class ImportedReturnConsumer(ABC):
    @abstractmethod
    def consume(self, imported_return: GstImportedReturn, **kwargs: Any) -> GstReconciliationRun:
        raise NotImplementedError

