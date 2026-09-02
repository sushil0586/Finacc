from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from sales.models import SalesInvoiceHeader
from sales.views.sales_meta import SalesInvoiceDetailFormMetaAPIView


class SalesInvoiceDetailFormMetaAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    @patch("sales.views.sales_meta.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "enforce_scope")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_customer_block")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_compliance_action_flags")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_invoice_action_flags")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_sales_settings_payload")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_invoice_form_meta")
    @patch.object(SalesInvoiceDetailFormMetaAPIView, "_invoice_queryset")
    def test_detail_meta_uses_saved_subentity_when_query_branch_is_stale(
        self,
        mocked_queryset,
        mocked_form_meta,
        mocked_settings_payload,
        mocked_action_flags,
        mocked_compliance_flags,
        mocked_customer_block,
        _mocked_enforce_scope,
        mocked_serializer,
    ):
        header = SimpleNamespace(
            subentity_id=30,
            customer_id=None,
            attachments=Mock(order_by=Mock(return_value=[])),
            status=SalesInvoiceHeader.Status.DRAFT,
            get_status_display=lambda: "Draft",
        )
        mocked_queryset.return_value.get.return_value = header
        mocked_form_meta.return_value = {"entity_id": 10, "subentity_id": 30}
        mocked_settings_payload.return_value = {"default_doc_code_invoice": "SINV"}
        mocked_action_flags.return_value = {"can_edit": True}
        mocked_compliance_flags.return_value = {"can_generate_irn": False}
        mocked_customer_block.return_value = None
        mocked_serializer.return_value.data = {"id": 99, "subentity": 30}

        request = self.factory.get(
            "/api/sales/meta/invoice-detail-form/?entity=10&entityfinid=11&subentity=31&invoice=99"
        )
        force_authenticate(request, user=self.user)

        response = SalesInvoiceDetailFormMetaAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        mocked_queryset.assert_called_once_with(10, 11, None, line_mode=None)
        mocked_form_meta.assert_called_once_with(10, 30)
        mocked_settings_payload.assert_called_once_with(10, 11, 30)
        self.assertEqual(response.data["subentity_id"], 30)
