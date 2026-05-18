from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from entity.models import (
    ApprovalActionLog,
    ApprovalRequest,
    Entity,
    EntityFinancialYear,
    GstRegistrationType,
    SubEntity,
    UserNotification,
)
from hrms.models import (
    ContractLeaveBalanceSnapshot,
    ContractLeaveLedgerEntry,
    HrEmployee,
    HrEmploymentContract,
    LeaveApplication,
    LeavePolicy,
    LeavePolicyRule,
    LeaveType,
)
from hrms.services import LeaveApplicationService, LeaveApprovalService


class LeaveApprovalWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="leave-approval-user",
            email="leave-approval@example.com",
            password="pass123",
        )
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular GST")
        self.entity = Entity.objects.create(
            entityname="Leave Approval Entity",
            legalname="Leave Approval Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        employee = HrEmployee.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            linked_user=self.user,
            employee_number="LEAVE001",
            legal_first_name="Leave",
            legal_last_name="Approver",
            display_name="Leave Approver",
            work_email="leave.approver@example.com",
        )
        self.contract = HrEmploymentContract.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee=employee,
            contract_code="LEAVE-CON-001",
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            start_date=date(2025, 4, 1),
            payroll_effective_from=date(2025, 4, 1),
            is_payroll_eligible=True,
        )
        self.leave_type = LeaveType.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="EL",
            name="Earned Leave",
            category=LeaveType.Category.EARNED,
            is_paid=True,
            requires_balance=True,
            counts_towards_attendance=True,
            payroll_impact_code="PAID_LEAVE",
            effective_from=date(2025, 4, 1),
        )
        self.leave_policy = LeavePolicy.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="EL-POL",
            name="Earned Leave Policy",
            status=LeavePolicy.Status.ACTIVE,
            is_default=True,
            employee_category=LeavePolicy.EmployeeCategory.SERVICES,
            effective_from=date(2025, 4, 1),
        )
        LeavePolicyRule.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            leave_policy=self.leave_policy,
            leave_type=self.leave_type,
            rule_code="EL-RULE",
            rule_name="Earned Leave Rule",
            rule_json={},
            effective_from=date(2025, 4, 1),
        )
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            contract=self.contract,
            leave_policy=self.leave_policy,
            leave_type=self.leave_type,
            snapshot_date=date(2025, 4, 30),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.ACCRUAL,
            opening_balance=Decimal("5.00"),
            accrued_days=Decimal("0.00"),
            consumed_days=Decimal("0.00"),
            carried_forward_days=Decimal("0.00"),
            lapsed_days=Decimal("0.00"),
            encashed_days=Decimal("0.00"),
            closing_balance=Decimal("5.00"),
            attendance_percentage=Decimal("100.00"),
            trace_json={},
        )

    def test_leave_payroll_impact_is_created_only_after_approval(self):
        application = LeaveApplicationService.create_application(
            attrs={
                "contract": self.contract,
                "leave_type": self.leave_type,
                "leave_policy": self.leave_policy,
                "start_date": date(2025, 5, 1),
                "end_date": date(2025, 5, 2),
                "requested_days": Decimal("2.00"),
                "reason": "Family leave",
            },
            actor=self.user,
        )

        self.assertEqual(application.status, LeaveApplication.Status.SUBMITTED)
        self.assertEqual(application.approval_status, LeaveApplication.ApprovalStatus.PENDING_APPROVAL)
        self.assertFalse(
            ContractLeaveLedgerEntry.objects.filter(reference_id=str(application.id)).exists()
        )

        approved = LeaveApprovalService.approve(
            application=application,
            approver=self.user,
            approved_days=Decimal("2.00"),
            manager_note="approved",
        )

        self.assertEqual(approved.status, LeaveApplication.Status.APPROVED)
        self.assertEqual(approved.approval_status, LeaveApplication.ApprovalStatus.APPROVED)
        self.assertEqual(approved.payroll_impact_json["paid_leave_days"], "2.00")
        ledger = ContractLeaveLedgerEntry.objects.get(reference_id=str(application.id))
        self.assertEqual(ledger.quantity_days, Decimal("-2.00"))

        request = ApprovalRequest.objects.get(workflow_key="leave_application", object_id=str(application.id))
        self.assertEqual(request.status, ApprovalRequest.Status.APPROVED)
        actions = list(
            ApprovalActionLog.objects.filter(approval_request=request).order_by("id").values_list("action", flat=True)
        )
        self.assertEqual(actions, ["SUBMITTED", "ROUTED", "APPROVED"])

    def test_leave_approval_notifies_employee(self):
        application = LeaveApplicationService.create_application(
            attrs={
                "contract": self.contract,
                "leave_type": self.leave_type,
                "leave_policy": self.leave_policy,
                "start_date": date(2025, 5, 5),
                "end_date": date(2025, 5, 5),
                "requested_days": Decimal("1.00"),
                "reason": "Medical appointment",
            },
            actor=self.user,
        )

        LeaveApprovalService.approve(
            application=application,
            approver=self.user,
            approved_days=Decimal("1.00"),
            manager_note="approved with notification",
        )

        self.assertTrue(
            UserNotification.objects.filter(
                user=self.user,
                event__event_code="LEAVE_APPROVED",
            ).exists()
        )
