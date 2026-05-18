from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from hrms.services import LeavePayrollImpactService
from hrms.services.attendance_capture_service import AttendanceCaptureService
from payroll.models import (
    ContractAttendanceSummary,
    ContractPayrollInputSnapshot,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    ContractTaxDeclaration,
    PayrollPeriod,
    SalaryStructure,
    SalaryStructureVersion,
)
from payroll.services.contract_attendance_adjustment_service import ContractAttendanceAdjustmentService
from payroll.services.contract_attendance_summary_service import ContractAttendanceSummaryService
from payroll.services.contract_payroll_input_snapshot_service import ContractPayrollInputSnapshotService
from payroll.services.contract_tax_declaration_service import ContractTaxDeclarationService
from payroll.services.one_time_pay_item_service import OneTimePayItemService
from payroll.services.payroll_tds_engine import PayrollTDSEngine
from payroll.services.recurring_pay_item_service import RecurringPayItemService


@dataclass(frozen=True)
class PayrollCalculationInput:
    contract_payroll_profile: ContractPayrollProfile | None
    salary_assignment: ContractSalaryStructureAssignment | None
    payroll_period: PayrollPeriod | None
    readiness_snapshot: dict[str, Any]
    employee_code: str
    employee_name: str
    employee_user_id: int | None
    contract_code: str | None
    pay_frequency: str
    payment_mode: str
    payment_account_id: int | None
    payment_account_details: dict[str, Any]
    tax_regime: str
    statutory_flags: dict[str, bool]
    ctc_amount: Decimal
    gross_amount: Decimal
    salary_structure: SalaryStructure | None
    salary_structure_version: SalaryStructureVersion | None
    recurring_items: list[dict[str, Any]]
    one_time_items: list[dict[str, Any]]
    payroll_policy_snapshot: dict[str, Any] | None
    statutory_profile_snapshots: list[dict[str, Any]]
    statutory_registration_snapshots: list[dict[str, Any]]
    tax_declaration_snapshot: dict[str, Any] | None
    tax_projection_snapshot: dict[str, Any]
    attendance_snapshot: dict[str, Any]
    payable_days_snapshot: dict[str, Any]
    attendance_days: Decimal
    payable_days: Decimal
    lop_days: Decimal
    overtime_hours: Decimal
    late_count: int
    half_days: Decimal
    manual_input_snapshot: dict[str, Any]
    source_markers: dict[str, str]

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "employee_code": self.employee_code,
            "employee_name": self.employee_name,
            "employee_user_id": self.employee_user_id,
            "contract_code": self.contract_code,
            "payroll_period_id": self.payroll_period.id if self.payroll_period else None,
            "pay_frequency": self.pay_frequency,
            "payment_mode": self.payment_mode,
            "payment_account_id": self.payment_account_id,
            "payment_account_details": self.payment_account_details,
            "tax_regime": self.tax_regime,
            "statutory_flags": self.statutory_flags,
            "ctc_amount": str(self.ctc_amount),
            "gross_amount": str(self.gross_amount),
            "salary_structure": (
                {
                    "id": self.salary_structure.id,
                    "code": self.salary_structure.code,
                    "name": self.salary_structure.name,
                }
                if self.salary_structure
                else None
            ),
            "salary_structure_version": (
                {
                    "id": self.salary_structure_version.id,
                    "version_no": self.salary_structure_version.version_no,
                    "status": self.salary_structure_version.status,
                }
                if self.salary_structure_version
                else None
            ),
            "payroll_policy": self.payroll_policy_snapshot,
            "recurring_items": self.recurring_items,
            "one_time_items": self.one_time_items,
            "statutory_profiles": self.statutory_profile_snapshots,
            "statutory_registrations": self.statutory_registration_snapshots,
            "tax_declaration": self.tax_declaration_snapshot,
            "tax_projection_snapshot": self.tax_projection_snapshot,
            "attendance_snapshot": self.attendance_snapshot,
            "payable_days_snapshot": self.payable_days_snapshot,
            "attendance_days": str(self.attendance_days),
            "payable_days": str(self.payable_days),
            "lop_days": str(self.lop_days),
            "overtime_hours": str(self.overtime_hours),
            "late_count": self.late_count,
            "half_days": str(self.half_days),
            "manual_input_snapshot": self.manual_input_snapshot,
            "source_markers": self.source_markers,
            "readiness_warning_count": len(self.readiness_snapshot.get("warnings", []) or []),
            "readiness_blocking_count": len(self.readiness_snapshot.get("blocking_issues", []) or []),
        }


class PayrollCalculationInputResolver:
    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _normalize_json(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @classmethod
    def _build_contract_attendance_payload(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod | None,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        int,
        Decimal,
    ]:
        if payroll_period is None:
            return {}, {}, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 0, Decimal("0")
        summary = ContractAttendanceSummaryService.resolve_summary(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
        )
        if summary is None:
            return {}, {}, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 0, Decimal("0")
        if not AttendanceCaptureService.summary_is_payroll_eligible(
            contract=contract_payroll_profile.hrms_contract,
            payroll_period=payroll_period,
            summary=summary,
        ):
            return {}, {}, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 0, Decimal("0")
        attendance_days = cls._decimal(summary.attendance_days)
        payable_days = cls._decimal(summary.payable_days)
        lop_days = cls._decimal(summary.lop_days)
        overtime_hours = cls._decimal(summary.overtime_hours)
        late_count = int(summary.late_count or 0)
        half_days = cls._decimal(summary.half_days)

        aggregate = ContractAttendanceAdjustmentService.aggregate_adjustments(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
        )
        totals_by_type = aggregate.get("totals_by_type", {})
        payable_days += cls._decimal(totals_by_type.get("PAYABLE_DAY"))
        lop_days += cls._decimal(totals_by_type.get("LOP"))
        overtime_hours += cls._decimal(totals_by_type.get("OVERTIME"))
        try:
            late_count += int(cls._decimal(totals_by_type.get("LATE_DEDUCTION")))
        except Exception:
            pass
        half_days += cls._decimal(totals_by_type.get("HALF_DAY"))

        leave_impact_applied = bool((summary.metadata or {}).get("leave_impact_applied"))
        leave_impact = (
            {"paid_leave_days": "0", "unpaid_leave_days": "0", "lop_days": "0", "items": []}
            if leave_impact_applied
            else LeavePayrollImpactService.summarize_period(
                contract=contract_payroll_profile.hrms_contract,
                payroll_period=payroll_period,
            )
        )
        paid_leave_days = cls._decimal(leave_impact.get("paid_leave_days"))
        unpaid_leave_days = cls._decimal(leave_impact.get("unpaid_leave_days"))
        if paid_leave_days:
            payable_days += paid_leave_days
        if unpaid_leave_days:
            lop_days += unpaid_leave_days
            payable_days -= unpaid_leave_days

        attendance_snapshot = {
            "attendance_days": str(attendance_days),
            "payable_days": str(payable_days),
            "lop_days": str(lop_days),
            "weekly_off_days": str(cls._decimal(summary.weekly_off_days)),
            "holiday_days": str(cls._decimal(summary.holiday_days)),
            "overtime_hours": str(overtime_hours),
            "late_count": late_count,
            "half_days": str(half_days),
            "paid_leave_days": str(paid_leave_days),
            "unpaid_leave_days": str(unpaid_leave_days),
            "leave_impact": leave_impact,
            "source": summary.source,
            "approval_status": summary.approval_status,
            "payroll_period_id": summary.payroll_period_id,
            "summary_id": str(summary.id),
            "payroll_eligibility_requirement": AttendanceCaptureService.resolve_payroll_requirement(
                contract=contract_payroll_profile.hrms_contract
            ).level,
        }
        payable_days_snapshot = {
            "payable_days": str(payable_days),
            "lop_days": str(lop_days),
            "half_days": str(half_days),
            "late_count": late_count,
            "paid_leave_days": str(paid_leave_days),
            "unpaid_leave_days": str(unpaid_leave_days),
            "leave_impact": leave_impact,
            "payroll_period_id": summary.payroll_period_id,
            "summary_id": str(summary.id),
        }
        return (
            attendance_snapshot,
            payable_days_snapshot,
            attendance_days,
            payable_days,
            lop_days,
            overtime_hours,
            late_count,
            half_days,
        )

    @classmethod
    def _serialize_tax_declaration(cls, declaration: ContractTaxDeclaration | None) -> dict[str, Any] | None:
        if not declaration:
            return None
        return {
            "id": str(declaration.id),
            "financial_year_id": declaration.financial_year_id,
            "financial_year_name": getattr(declaration.financial_year, "desc", ""),
            "tax_regime": declaration.tax_regime,
            "declaration_status": declaration.declaration_status,
            "declared_annual_income": str(declaration.declared_annual_income or Decimal("0")),
            "previous_employer_income": str(declaration.previous_employer_income or Decimal("0")),
            "previous_employer_tds": str(declaration.previous_employer_tds or Decimal("0")),
            "standard_deduction_amount": str(declaration.standard_deduction_amount or Decimal("0")),
            "professional_tax_declared": str(declaration.professional_tax_declared or Decimal("0")),
            "submitted_at": declaration.submitted_at.isoformat() if declaration.submitted_at else None,
            "approved_at": declaration.approved_at.isoformat() if declaration.approved_at else None,
            "metadata": declaration.metadata or {},
            "lines": [
                {
                    "id": str(line.id),
                    "section_code": line.section_code,
                    "description": line.description,
                    "declared_amount": str(line.declared_amount or Decimal("0")),
                    "approved_amount": str(line.approved_amount or Decimal("0")),
                    "evidence_required": line.evidence_required,
                    "evidence_status": line.evidence_status,
                    "metadata": line.metadata or {},
                    "is_active": line.is_active,
                }
                for line in declaration.lines.filter(is_active=True).order_by("section_code", "id")
            ],
        }

    @classmethod
    def _build_tax_projection_snapshot(cls, declaration: ContractTaxDeclaration | None) -> dict[str, Any]:
        if not declaration:
            return {}
        snapshot: dict[str, Any] = {
            "annual_taxable_income": str(declaration.declared_annual_income or Decimal("0")),
            "projected_taxable_income": str(declaration.declared_annual_income or Decimal("0")),
            "previous_employer_income": str(declaration.previous_employer_income or Decimal("0")),
            "previous_employer_taxable_income": str(declaration.previous_employer_income or Decimal("0")),
            "previous_employer_tds": str(declaration.previous_employer_tds or Decimal("0")),
            "declared_deductions": str(declaration.professional_tax_declared or Decimal("0")),
            "professional_tax_declared": str(declaration.professional_tax_declared or Decimal("0")),
            "standard_deduction_amount": str(declaration.standard_deduction_amount or Decimal("0")),
        }
        review_status = declaration.declaration_status.lower()
        for line in declaration.lines.filter(is_active=True).order_by("section_code", "id"):
            metadata = cls._normalize_json(line.metadata)
            approved_amount = line.approved_amount or Decimal("0")
            declared_amount = line.declared_amount or Decimal("0")
            effective_amount = approved_amount if approved_amount > Decimal("0") else declared_amount
            if line.section_code == line.SectionCode.SECTION_80C:
                snapshot["deduction_80c"] = str(effective_amount)
                snapshot["deduction_80c_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
                snapshot["deduction_80c_review_status"] = metadata.get("review_status") or (
                    "verified" if line.evidence_status == line.EvidenceStatus.VERIFIED else review_status
                )
                if metadata.get("review_note"):
                    snapshot["deduction_80c_review_note"] = metadata.get("review_note")
            elif line.section_code == line.SectionCode.SECTION_80D:
                snapshot["deduction_80d"] = str(effective_amount)
                snapshot["deduction_80d_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
                snapshot["deduction_80d_review_status"] = metadata.get("review_status") or (
                    "verified" if line.evidence_status == line.EvidenceStatus.VERIFIED else review_status
                )
                if metadata.get("review_note"):
                    snapshot["deduction_80d_review_note"] = metadata.get("review_note")
            elif line.section_code == line.SectionCode.HRA:
                snapshot["hra_exemption"] = str(effective_amount)
                if metadata.get("hra_rent_paid_annual") is not None:
                    snapshot["hra_rent_paid_annual"] = metadata.get("hra_rent_paid_annual")
                if metadata.get("hra_rent_months") is not None:
                    snapshot["hra_rent_months"] = metadata.get("hra_rent_months")
                if metadata.get("hra_is_metro_city") is not None:
                    snapshot["hra_is_metro_city"] = metadata.get("hra_is_metro_city")
                if metadata.get("hra_landlord_pan_available") is not None:
                    snapshot["hra_landlord_pan_available"] = metadata.get("hra_landlord_pan_available")
                snapshot["hra_evidence_verified"] = line.evidence_status == line.EvidenceStatus.VERIFIED
                snapshot["hra_review_status"] = metadata.get("review_status") or (
                    "verified" if line.evidence_status == line.EvidenceStatus.VERIFIED else review_status
                )
                if metadata.get("review_note"):
                    snapshot["hra_review_note"] = metadata.get("review_note")
            elif line.section_code == line.SectionCode.OTHER:
                existing_other = cls._decimal(snapshot.get("other_old_regime_deductions"))
                snapshot["other_old_regime_deductions"] = str(existing_other + effective_amount)
        return snapshot

    @classmethod
    def _resolve_contract_native_inputs(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile | None,
        payroll_date: date | None,
        payroll_period: PayrollPeriod | None,
    ) -> tuple[
        dict[str, Any] | None,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        Decimal,
        Decimal,
        Decimal,
        Decimal,
        int,
        Decimal,
        dict[str, Any],
        dict[str, str],
    ]:
        if not contract_payroll_profile or not payroll_date:
            return None, {}, {}, {}, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 0, Decimal("0"), {}, {}
        declaration = ContractTaxDeclarationService.resolve_preferred_declaration(
            contract_payroll_profile=contract_payroll_profile,
            declaration_date=payroll_date,
        )
        declaration_snapshot = cls._serialize_tax_declaration(declaration)
        bundle = ContractPayrollInputSnapshotService.resolve_input_bundle(
            contract_payroll_profile=contract_payroll_profile,
            snapshot_date=payroll_date,
            payroll_period=payroll_period,
        )
        tax_projection_snapshot = cls._build_tax_projection_snapshot(declaration)
        snapshot_sources: dict[str, str] = {}
        tax_projection_item = bundle.get("tax_projection")
        if tax_projection_item:
            tax_projection_snapshot = {
                **tax_projection_snapshot,
                **cls._normalize_json(tax_projection_item.input_json),
            }
            snapshot_sources["tax_projection_snapshot"] = "contract_native"
        elif declaration_snapshot:
            snapshot_sources["tax_projection_snapshot"] = "contract_native"

        manual_input_item = bundle.get("manual_payroll_input")
        manual_input_snapshot = cls._normalize_json(getattr(manual_input_item, "input_json", None))

        if manual_input_snapshot:
            snapshot_sources["manual_payroll_input"] = "contract_native"
        (
            attendance_snapshot,
            payable_days_snapshot,
            attendance_days,
            payable_days,
            lop_days,
            overtime_hours,
            late_count,
            half_days,
        ) = cls._build_contract_attendance_payload(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
        )
        if attendance_snapshot:
            snapshot_sources["attendance_snapshot"] = "contract_native"
            snapshot_sources["payable_days_snapshot"] = "contract_native"
            snapshot_sources["attendance_source"] = "contract_native"
        return (
            declaration_snapshot,
            tax_projection_snapshot,
            attendance_snapshot,
            payable_days_snapshot,
            attendance_days,
            payable_days,
            lop_days,
            overtime_hours,
            late_count,
            half_days,
            manual_input_snapshot,
            snapshot_sources,
        )

    @classmethod
    def _serialize_recurring_items(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile | None,
        payroll_date: date | None,
        readiness_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if readiness_snapshot.get("recurring_items"):
            return list(readiness_snapshot.get("recurring_items", []) or [])
        if not contract_payroll_profile or not payroll_date:
            return []
        return [
            {
                "id": str(item.id),
                "payroll_component_id": item.payroll_component_id,
                "component_code": item.payroll_component.code,
                "component_name": item.payroll_component.name,
                "item_type": item.item_type,
                "amount": str(item.amount),
                "percentage": str(item.percentage),
                "formula_override": item.formula_override,
                "priority": item.priority,
                "remarks": item.remarks,
            }
            for item in RecurringPayItemService.resolve_active_recurring_items(
                contract_payroll_profile=contract_payroll_profile,
                payroll_date=payroll_date,
            )
        ]

    @classmethod
    def _serialize_one_time_items(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile | None,
        payroll_date: date | None,
        payroll_period: PayrollPeriod | None,
        readiness_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if readiness_snapshot.get("one_time_items"):
            return list(readiness_snapshot.get("one_time_items", []) or [])
        if not contract_payroll_profile:
            return []
        return [
            {
                "id": str(item.id),
                "payroll_component_id": item.payroll_component_id,
                "component_code": item.payroll_component.code,
                "component_name": item.payroll_component.name,
                "item_type": item.item_type,
                "amount": str(item.amount),
                "quantity": str(item.quantity),
                "source_type": item.source_type,
                "remarks": item.remarks,
                "effective_date": str(item.effective_date),
                "payroll_period_id": item.payroll_period_id,
            }
            for item in OneTimePayItemService.resolve_payable_items(
                contract_payroll_profile=contract_payroll_profile,
                payroll_date=payroll_date,
                payroll_period=payroll_period,
            )
        ]

    @classmethod
    def resolve(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile | None,
        salary_assignment: ContractSalaryStructureAssignment | None,
        readiness_snapshot: dict[str, Any] | None,
        payroll_date: date | None = None,
        payroll_period: PayrollPeriod | None = None,
    ) -> PayrollCalculationInput:
        readiness_snapshot = readiness_snapshot or {}
        contract = getattr(contract_payroll_profile, "hrms_contract", None)
        employee = getattr(contract, "employee", None)
        (
            declaration_snapshot,
            tax_projection_snapshot,
            attendance_snapshot,
            payable_days_snapshot,
            attendance_days,
            payable_days,
            lop_days,
            overtime_hours,
            late_count,
            half_days,
            manual_input_snapshot,
            source_markers,
        ) = cls._resolve_contract_native_inputs(
            contract_payroll_profile=contract_payroll_profile,
            payroll_date=payroll_date,
            payroll_period=payroll_period,
        )
        salary_structure = getattr(salary_assignment, "salary_structure", None)
        salary_structure_version = getattr(salary_assignment, "salary_structure_version", None)
        tax_projection_snapshot = PayrollTDSEngine.build_projection(
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
            declaration=ContractTaxDeclarationService.resolve_preferred_declaration(
                contract_payroll_profile=contract_payroll_profile,
                declaration_date=payroll_date,
            ) if contract_payroll_profile and payroll_date else None,
            tax_regime=getattr(contract_payroll_profile, "tax_regime", None),
            policy=getattr(salary_structure_version, "calculation_policy_json", None) or {},
            existing_snapshot=tax_projection_snapshot,
            payroll_period=payroll_period,
            monthly_gross_amount=cls._decimal(getattr(salary_assignment, "gross_amount", None)),
            monthly_ctc_amount=cls._decimal(getattr(salary_assignment, "ctc_amount", None)),
        ).snapshot
        if tax_projection_snapshot:
            source_markers["tax_projection_snapshot"] = source_markers.get("tax_projection_snapshot") or "contract_native"
            source_markers["tds_projection_engine"] = "payroll_tds_engine"
        statutory_flags = {
            "pf_applicable": bool(getattr(contract_payroll_profile, "pf_applicable", False)),
            "esi_applicable": bool(getattr(contract_payroll_profile, "esi_applicable", False)),
            "pt_applicable": bool(getattr(contract_payroll_profile, "pt_applicable", False)),
            "tds_applicable": bool(getattr(contract_payroll_profile, "tds_applicable", False)),
            "lwf_applicable": bool(getattr(contract_payroll_profile, "lwf_applicable", False)),
            "overtime_eligible": bool(getattr(contract_payroll_profile, "overtime_eligible", False)),
            "attendance_required": bool(getattr(contract_payroll_profile, "attendance_required", False)),
        }
        recurring_items = cls._serialize_recurring_items(
            contract_payroll_profile=contract_payroll_profile,
            payroll_date=payroll_date,
            readiness_snapshot=readiness_snapshot,
        )
        one_time_items = cls._serialize_one_time_items(
            contract_payroll_profile=contract_payroll_profile,
            payroll_date=payroll_date,
            payroll_period=payroll_period,
            readiness_snapshot=readiness_snapshot,
        )
        return PayrollCalculationInput(
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
            payroll_period=payroll_period,
            readiness_snapshot=readiness_snapshot,
            employee_code=(
                getattr(employee, "employee_number", "")
                or getattr(contract_payroll_profile, "employee_code", "")
            ),
            employee_name=(
                getattr(employee, "display_name", "")
                or getattr(contract_payroll_profile, "employee_name", "")
            ),
            employee_user_id=getattr(employee, "linked_user_id", None),
            contract_code=getattr(contract, "contract_code", None),
            pay_frequency=(
                getattr(contract_payroll_profile, "pay_frequency", "")
                or "MONTHLY"
            ),
            payment_mode=getattr(contract_payroll_profile, "payment_mode", "") or "",
            payment_account_id=getattr(contract_payroll_profile, "bank_account_id", None),
            payment_account_details=getattr(contract_payroll_profile, "bank_account_details", None) or {},
            tax_regime=getattr(contract_payroll_profile, "tax_regime", "") or "",
            statutory_flags=statutory_flags,
            ctc_amount=(
                cls._decimal(getattr(salary_assignment, "ctc_amount", None))
                if salary_assignment and cls._decimal(getattr(salary_assignment, "ctc_amount", None)) > Decimal("0")
                else Decimal("0")
            ),
            gross_amount=(
                cls._decimal(getattr(salary_assignment, "gross_amount", None))
                if salary_assignment and cls._decimal(getattr(salary_assignment, "gross_amount", None)) > Decimal("0")
                else cls._decimal(manual_input_snapshot.get("fixed_salary"))
            ),
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            recurring_items=recurring_items,
            one_time_items=one_time_items,
            payroll_policy_snapshot=readiness_snapshot.get("payroll_policy"),
            statutory_profile_snapshots=list(readiness_snapshot.get("statutory_profiles", []) or []),
            statutory_registration_snapshots=list(readiness_snapshot.get("statutory_registrations", []) or []),
            tax_declaration_snapshot=declaration_snapshot,
            tax_projection_snapshot=tax_projection_snapshot,
            attendance_snapshot=attendance_snapshot,
            payable_days_snapshot=payable_days_snapshot,
            attendance_days=attendance_days,
            payable_days=payable_days,
            lop_days=lop_days,
            overtime_hours=overtime_hours,
            late_count=late_count,
            half_days=half_days,
            manual_input_snapshot=manual_input_snapshot,
            source_markers=source_markers,
        )
