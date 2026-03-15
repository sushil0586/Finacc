from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from vouchers.models import VoucherHeader
from vouchers.views.voucher_meta import VoucherDetailFormMetaAPIView


User = get_user_model()


class VoucherDetailFormMetaAPIViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="voucher_meta_user",
            email="voucher_meta_user@example.com",
            password="pass@12345",
        )

    @patch("vouchers.views.voucher_meta.VoucherDetailSerializer")
    @patch("vouchers.views.voucher_meta.get_object_or_404")
    @patch.object(VoucherDetailFormMetaAPIView, "_voucher_form_meta")
    @patch.object(VoucherDetailFormMetaAPIView, "_voucher_queryset")
    def test_detail_meta_uses_voucher_subentity_when_query_omits_it(
        self,
        mocked_queryset,
        mocked_form_meta,
        mocked_get_object,
        mocked_serializer,
    ):
        header = SimpleNamespace(
            subentity_id=9,
            status=VoucherHeader.Status.DRAFT,
            get_status_display=lambda: "Draft",
            cash_bank_account=None,
        )
        mocked_queryset.return_value = Mock(name="voucher_queryset")
        mocked_get_object.return_value = header
        mocked_form_meta.return_value = {"entity_id": 32, "entityfinid_id": 32, "subentity_id": 9}
        mocked_serializer.return_value.data = {"id": 16}

        request = self.factory.get("/api/vouchers/meta/voucher-detail-form/?entity=32&entityfinid=32&voucher=16")
        force_authenticate(request, user=self.user)

        response = VoucherDetailFormMetaAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        mocked_queryset.assert_called_once_with(32, 32, None, allow_any_subentity=True)
        mocked_form_meta.assert_called_once_with(32, 32, 9)
        self.assertEqual(response.data["voucher_id"], 16)
        self.assertEqual(response.data["subentity_id"], 9)
        self.assertEqual(response.data["voucher"], {"id": 16})
