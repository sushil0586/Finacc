"""Shared GST compliance contracts.

Phase A intentionally keeps this package calculation-free.  It gives GST
reports and future compliance-center screens one stable scope/status/deep-link
language without changing existing report endpoint behavior.
"""

from .contracts import (
    GST_COMPLIANCE_DEEP_LINKS,
    GST_COMPLIANCE_STATUS_VALUES,
    GST_COMPLIANCE_TARGETS,
    GstComplianceScope,
    build_gst_compliance_deep_link,
    parse_gst_compliance_scope,
)
from .services import GST_COMPLIANCE_CARD_DEFINITIONS, GstComplianceSnapshotService

__all__ = [
    "GST_COMPLIANCE_DEEP_LINKS",
    "GST_COMPLIANCE_STATUS_VALUES",
    "GST_COMPLIANCE_TARGETS",
    "GST_COMPLIANCE_CARD_DEFINITIONS",
    "GstComplianceScope",
    "GstComplianceSnapshotService",
    "build_gst_compliance_deep_link",
    "parse_gst_compliance_scope",
]
