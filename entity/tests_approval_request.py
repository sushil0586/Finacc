from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from entity.approval_request_serializers import ApprovalRequestActionSerializer
from entity.models import ApprovalRequest, Entity
from subscriptions.services import SubscriptionService


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class ApprovalRequestActionApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="approval-owner@example.com",
            username="approval-owner@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Approval Entity", createdby=self.owner)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.approval_request = ApprovalRequest.objects.create(
            entity=self.entity,
            content_type=ContentType.objects.get_for_model(Entity),
            object_id=str(self.entity.id),
            workflow_key="employment_change",
            title="Employment Change",
            status=ApprovalRequest.Status.SUBMITTED,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_action_serializer_rejects_oversized_remarks(self):
        serializer = ApprovalRequestActionSerializer(data={"remarks": "R" * 256})

        self.assertFalse(serializer.is_valid())
        self.assertIn("remarks", serializer.errors)

    def test_approve_endpoint_rejects_oversized_remarks_before_service(self):
        response = self.client.post(
            f"/api/entity/approval-requests/{self.approval_request.id}/approve/",
            {"remarks": "R" * 256},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("remarks", response.data)
