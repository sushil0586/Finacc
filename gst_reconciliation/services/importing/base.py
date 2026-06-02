from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

from gst_reconciliation.models import GstImportedReturn


@dataclass(frozen=True)
class ImportPipelineResult:
    imported_return: GstImportedReturn
    normalized_payload: Dict[str, Any]
    validation_summary: Dict[str, Any]


class BaseImportedReturnPipeline(ABC):
    code = "base"

    @abstractmethod
    def supports(self, imported_return: GstImportedReturn) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate(self, imported_return: GstImportedReturn) -> ImportPipelineResult:
        raise NotImplementedError

    def ingest(self, *args: Any, **kwargs: Any):
        raise NotImplementedError
