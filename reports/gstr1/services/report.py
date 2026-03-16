from __future__ import annotations

from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from sales.models import SalesInvoiceHeader

from reports.gstr1.selectors.queries import apply_scope_filters, base_queryset
from reports.gstr1.selectors.scope import parse_scope_params
from reports.gstr1.services.classification import Gstr1ClassificationService
from reports.gstr1.services.summary import Gstr1SummaryService, SECTION_LABELS
from reports.gstr1.services.validation import Gstr1ValidationService


class Gstr1ReportService:
    def build_scope(self, params):
        return parse_scope_params(params)

    def scoped_queryset(self, scope):
        qs = base_queryset()
        return apply_scope_filters(qs, scope)

    def summary(self, scope):
        qs = self.scoped_queryset(scope)
        summary_service = Gstr1SummaryService(base_queryset=qs)
        section_totals = summary_service.build_section_totals()
        return {
            "sections": [
                {
                    "section": code,
                    "label": SECTION_LABELS.get(code, code),
                    **section_totals[code],
                }
                for code in Gstr1ClassificationService.section_codes()
            ],
            "hsn_summary": summary_service.hsn_summary(),
            "document_summary": summary_service.document_summary(),
            "nil_exempt_summary": summary_service.nil_exempt_summary(),
        }

    def section(self, scope, section_code):
        section_code = (section_code or "").upper()
        if section_code not in Gstr1ClassificationService.section_codes():
            raise DRFValidationError({"section": ["Unsupported section code."]})
        qs = self.scoped_queryset(scope).filter(Gstr1ClassificationService.section_filter(section_code))
        return qs

    def validations(self, scope):
        qs = self.scoped_queryset(scope)
        return Gstr1ValidationService(base_queryset=qs).run()

    def invoice_detail(self, scope, invoice_id):
        qs = self.scoped_queryset(scope)
        invoice = qs.filter(id=invoice_id).first()
        if not invoice:
            raise ValidationError({"invoice": ["Invoice not found in selected scope."]})
        return invoice
