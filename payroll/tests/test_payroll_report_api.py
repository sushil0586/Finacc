from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import ContractAttendanceSummary, FnFSettlement, PayrollComponent, PayrollRun
from payroll.tests.factories import PayrollFactory

User = get_user_model()


class PayrollReportApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="reports-admin",
            email="reports-admin@example.com",
            password="pass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.scope_patcher = patch("core.entitlements.SubscriptionService.assert_entity_access")
        self.scope_patcher.start()
        self.addCleanup(self.scope_patcher.stop)

        self.setup = PayrollFactory.full_payroll_setup()
        self.entity_id = self.setup["entity"].id
        self.entityfinid_id = self.setup["entityfinid"].id
        self.subentity_id = self.setup["subentity"].id

        self.run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.POSTED,
            payment_status=PayrollRun.PaymentStatus.DISBURSED,
            employee_count=1,
            gross_amount=Decimal("1200.00"),
            deduction_amount=Decimal("160.00"),
            employer_contribution_amount=Decimal("120.00"),
            net_pay_amount=Decimal("1040.00"),
        )
        self.employee_row = PayrollFactory.payroll_run_employee(
            payroll_run=self.run,
            contract_payroll_profile=self.setup["contract_profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            gross_amount=Decimal("1200.00"),
            deduction_amount=Decimal("160.00"),
            employer_contribution_amount=Decimal("120.00"),
            payable_amount=Decimal("1040.00"),
            payment_status=PayrollRun.PaymentStatus.DISBURSED,
        )

        self.basic_component = self.setup["component"]
        self.hra_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="HRA",
            component_type=PayrollComponent.ComponentType.EARNING,
            posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
            semantic_code=PayrollComponent.SemanticCode.HRA,
        )
        self.pf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYEE",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.PF_EMPLOYEE,
        )
        self.pf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYER",
            component_type=PayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.PF_EMPLOYER,
        )
        self.pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.PT,
        )
        self.lwf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="LWF_EMPLOYEE",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.LWF_EMPLOYEE,
        )
        self.lwf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="LWF_EMPLOYER",
            component_type=PayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.LWF_EMPLOYER,
        )

        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.basic_component, amount="1000.00", sequence=10)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.hra_component, amount="200.00", sequence=20)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.pf_employee_component, amount="120.00", sequence=30)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.pf_employer_component, amount="120.00", sequence=40)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.pt_component, amount="40.00", sequence=50)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.lwf_employee_component, amount="10.00", sequence=60)
        PayrollFactory.payroll_run_component(payroll_run_employee=self.employee_row, component=self.lwf_employer_component, amount="10.00", sequence=70)

        attendance_summary = self.setup["attendance_summary"]
        attendance_summary.attendance_days = Decimal("26.00")
        attendance_summary.payable_days = Decimal("24.00")
        attendance_summary.lop_days = Decimal("2.00")
        attendance_summary.overtime_hours = Decimal("3.50")
        attendance_summary.half_days = Decimal("1.00")
        attendance_summary.approval_status = ContractAttendanceSummary.ApprovalStatus.APPROVED
        attendance_summary.save(
            update_fields=[
                "attendance_days",
                "payable_days",
                "lop_days",
                "overtime_hours",
                "half_days",
                "approval_status",
                "updated_at",
            ]
        )
        PayrollFactory.contract_attendance_adjustment(
            entity=self.setup["entity"],
            contract_payroll_profile=self.setup["contract_profile"],
            payroll_period=self.setup["period"],
            adjustment_value="1.00",
            remarks="Manual payable day adjustment",
            is_active=True,
        )
        self.payslip = PayrollFactory.payslip(payroll_run_employee=self.employee_row)
        self.payslip.payload = {
            "payroll_period_code": self.setup["period"].code,
            "run_number": self.run.run_number or "PRUN-1",
            "contract_code": self.setup["hrms_contract"].contract_code,
        }
        self.payslip.save(update_fields=["payload", "updated_at"])

    def _xlsx_first_row(self, content: bytes) -> list[str]:
        with ZipFile(BytesIO(content)) as archive:
            sheet_xml = archive.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(sheet_xml)
        namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row = root.find(".//main:sheetData/main:row", namespace)
        values: list[str] = []
        if row is None:
            return values
        for cell in row.findall("main:c", namespace):
            text = cell.findtext("main:is/main:t", default="", namespaces=namespace)
            values.append(text)
        return values

    def test_payroll_register_payload_uses_snapshots(self):
        response = self.client.get(
            f"/api/payroll/reports/payroll-register/?entity={self.entity_id}&entityfinid={self.entityfinid_id}&subentity={self.subentity_id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["report_type"], "payroll_register")
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["totals"]["gross_amount"], "1200.00")
        self.assertEqual(payload["rows"][0]["proration_factor"], "0.9231")
        self.assertEqual(payload["rows"][0]["adjustment_count"], 1)
        self.assertEqual(payload["traceability"]["source_of_truth"], "Backend payroll snapshots")

    def test_salary_sheet_payload_exposes_dynamic_component_columns(self):
        response = self.client.get(
            f"/api/payroll/reports/salary-sheet/?entity={self.entity_id}&entityfinid={self.entityfinid_id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["report_type"], "salary_sheet")
        labels = [column["label"] for column in payload["columns"]]
        self.assertIn(self.basic_component.name, labels)
        self.assertIn(self.hra_component.name, labels)
        row = payload["rows"][0]
        self.assertEqual(row[self.basic_component.code], "1000.00")
        self.assertEqual(row[self.hra_component.code], "200.00")

    def test_pf_summary_payload_returns_employee_and_employer_shares(self):
        response = self.client.get(
            f"/api/payroll/reports/pf-summary/?entity={self.entity_id}&status=POSTED"
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["report_type"], "pf_summary")
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["rows"][0]["employee_amount"], "120.00")
        self.assertEqual(payload["rows"][0]["employer_amount"], "120.00")
        self.assertEqual(payload["totals"]["total_amount"], "240.00")

    def test_lwf_summary_honors_status_filter(self):
        response = self.client.get(
            f"/api/payroll/reports/lwf-summary/?entity={self.entity_id}&status=REVERSED"
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["row_count"], 0)

    def test_fnf_register_payload_returns_snapshot_amounts(self):
        settlement = FnFSettlement.objects.create(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            hrms_contract=self.setup["hrms_contract"],
            contract_payroll_profile=self.setup["contract_profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            payroll_period=self.setup["period"],
            settlement_number="FNF-001",
            separation_date=date(2025, 4, 29),
            last_working_day=date(2025, 4, 30),
            settlement_date=date(2025, 5, 2),
            status=FnFSettlement.Status.APPROVED,
            earned_amount=Decimal("900.00"),
            deduction_amount=Decimal("100.00"),
            recovery_amount=Decimal("50.00"),
            reimbursement_amount=Decimal("20.00"),
            net_payable_amount=Decimal("770.00"),
            net_recoverable_amount=Decimal("0.00"),
        )

        response = self.client.get(
            f"/api/payroll/reports/fnf-settlement-register/?entity={self.entity_id}&status=APPROVED"
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["report_type"], "fnf_settlement_register")
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["rows"][0]["settlement_number"], settlement.settlement_number)
        self.assertEqual(payload["totals"]["net_payable_amount"], "770.00")

    def test_payroll_register_csv_export_returns_file_with_report_headers(self):
        report_response = self.client.get(
            f"/api/payroll/reports/payroll-register/?entity={self.entity_id}&entityfinid={self.entityfinid_id}"
        )
        expected_headers = [column["label"] for column in report_response.json()["columns"]]
        response = self.client.get(
            f"/api/payroll/reports/payroll-register/export/?entity={self.entity_id}&entityfinid={self.entityfinid_id}&format=csv"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(".csv", response["Content-Disposition"])
        header_row = response.content.decode("utf-8").splitlines()[0]
        self.assertEqual(header_row.split(","), expected_headers)

    def test_salary_sheet_xlsx_export_uses_report_column_headers(self):
        response = self.client.get(
            f"/api/payroll/reports/salary-sheet/export/?entity={self.entity_id}&entityfinid={self.entityfinid_id}&format=xlsx"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        first_row = self._xlsx_first_row(response.content)
        self.assertEqual(first_row[:5], ["Period", "Employee Code", "Employee Name", "Department", "Status"])
        self.assertIn(self.basic_component.name, first_row)
        self.assertIn(self.hra_component.name, first_row)

    def test_admin_payslip_pdf_export_returns_pdf_file(self):
        response = self.client.get(
            f"/api/payroll/runs/{self.run.id}/payslips/{self.employee_row.id}/pdf/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
