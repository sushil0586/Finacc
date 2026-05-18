from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import Prefetch, Q
from django.utils import timezone

from payroll.models import (
    ContractAttendanceAdjustment,
    ContractAttendanceSummary,
    FnFSettlement,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    StatutoryScheme,
)

ZERO = Decimal("0.00")


def _decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_str(value: Decimal | int | float | str | None) -> str:
    return format(_decimal(value).quantize(Decimal("0.01")), "f")


def _safe_divide(numerator: Decimal, denominator: Decimal) -> str | None:
    if denominator <= ZERO:
        return None
    return format((numerator / denominator).quantize(Decimal("0.0001")), "f")


def _component_amount_map(row: PayrollRunEmployee) -> dict[str, Decimal]:
    values: dict[str, Decimal] = {}
    for component in row.components.all():
        values[component.component_code] = values.get(component.component_code, ZERO) + _decimal(component.amount)
    return values


@dataclass(frozen=True)
class PayrollReportFilters:
    entity_id: int
    entityfinid_id: int | None = None
    subentity_id: int | None = None
    payroll_period_id: int | None = None
    department_id: int | None = None
    org_unit_id: int | None = None
    employee_id: int | None = None
    contract_id: int | None = None
    status: str | None = None
    statutory_scheme_id: str | None = None
    from_date: object | None = None
    to_date: object | None = None


class PayrollComplianceReportService:
    REPORT_PAYROLL_REGISTER = "payroll_register"
    REPORT_SALARY_SHEET = "salary_sheet"
    REPORT_PF_SUMMARY = "pf_summary"
    REPORT_ESI_SUMMARY = "esi_summary"
    REPORT_PT_SUMMARY = "pt_summary"
    REPORT_LWF_SUMMARY = "lwf_summary"
    REPORT_FNF_REGISTER = "fnf_settlement_register"

    STATUTORY_COMPONENT_MAP = {
        REPORT_PF_SUMMARY: {
            "employee_codes": {"PF_EMPLOYEE"},
            "employer_codes": {"PF_EMPLOYER"},
            "label": "PF Summary",
        },
        REPORT_ESI_SUMMARY: {
            "employee_codes": {"ESI_EMPLOYEE"},
            "employer_codes": {"ESI_EMPLOYER"},
            "label": "ESI Summary",
        },
        REPORT_PT_SUMMARY: {
            "employee_codes": {"PT"},
            "employer_codes": set(),
            "label": "PT Summary",
        },
        REPORT_LWF_SUMMARY: {
            "employee_codes": {"LWF_EMPLOYEE"},
            "employer_codes": {"LWF_EMPLOYER"},
            "label": "LWF Summary",
        },
    }

    @classmethod
    def build_report(cls, *, report_type: str, filters: PayrollReportFilters) -> dict:
        if report_type == cls.REPORT_PAYROLL_REGISTER:
            return cls._build_payroll_register(filters=filters)
        if report_type == cls.REPORT_SALARY_SHEET:
            return cls._build_salary_sheet(filters=filters)
        if report_type in cls.STATUTORY_COMPONENT_MAP:
            return cls._build_statutory_summary(report_type=report_type, filters=filters)
        if report_type == cls.REPORT_FNF_REGISTER:
            return cls._build_fnf_register(filters=filters)
        raise ValueError(f"Unsupported report type '{report_type}'.")

    @classmethod
    def _base_employee_rows(cls, *, filters: PayrollReportFilters):
        queryset = PayrollRunEmployee.objects.select_related(
            "payroll_run__entity",
            "payroll_run__entityfinid",
            "payroll_run__subentity",
            "payroll_run__payroll_period",
            "contract_payroll_profile__hrms_contract__employee",
            "contract_payroll_profile__hrms_contract__business_unit",
            "contract_payroll_profile__hrms_contract__department",
            "contract_payroll_profile__hrms_contract__team",
            "contract_payroll_profile__hrms_contract__designation",
            "contract_payroll_profile__hrms_contract__grade",
            "contract_payroll_profile__hrms_contract__cost_center",
            "contract_payroll_profile__hrms_contract__work_location",
            "salary_structure",
            "salary_structure_version",
        ).prefetch_related(
            Prefetch(
                "components",
                queryset=PayrollRunEmployeeComponent.objects.select_related("component").order_by("sequence", "id"),
            )
        ).filter(payroll_run__entity_id=filters.entity_id)

        if filters.entityfinid_id is not None:
            queryset = queryset.filter(payroll_run__entityfinid_id=filters.entityfinid_id)
        if filters.subentity_id is not None:
            queryset = queryset.filter(payroll_run__subentity_id=filters.subentity_id)
        if filters.payroll_period_id is not None:
            queryset = queryset.filter(payroll_run__payroll_period_id=filters.payroll_period_id)
        if filters.department_id is not None:
            queryset = queryset.filter(contract_payroll_profile__hrms_contract__department_id=filters.department_id)
        if filters.org_unit_id is not None:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__business_unit_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__department_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__team_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__designation_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__grade_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__cost_center_id=filters.org_unit_id)
                | Q(contract_payroll_profile__hrms_contract__work_location_id=filters.org_unit_id)
            )
        if filters.employee_id is not None:
            queryset = queryset.filter(contract_payroll_profile__hrms_contract__employee_id=filters.employee_id)
        if filters.contract_id is not None:
            queryset = queryset.filter(contract_payroll_profile__hrms_contract_id=filters.contract_id)
        if filters.status:
            queryset = queryset.filter(payroll_run__status__iexact=filters.status)
        if filters.from_date is not None:
            queryset = queryset.filter(payroll_run__posting_date__gte=filters.from_date)
        if filters.to_date is not None:
            queryset = queryset.filter(payroll_run__posting_date__lte=filters.to_date)
        return queryset.order_by(
            "payroll_run__payroll_period__period_start",
            "contract_payroll_profile__hrms_contract__employee__employee_number",
            "id",
        )

    @classmethod
    def _attendance_maps(cls, *, rows: Iterable[PayrollRunEmployee]) -> tuple[dict[tuple[str, int], ContractAttendanceSummary], dict[tuple[str, int], list[ContractAttendanceAdjustment]]]:
        row_list = list(rows)
        if not row_list:
            return {}, {}
        contract_ids = {row.contract_payroll_profile_id for row in row_list if row.contract_payroll_profile_id}
        period_ids = {row.payroll_run.payroll_period_id for row in row_list if row.payroll_run.payroll_period_id}
        summaries = ContractAttendanceSummary.objects.filter(
            contract_payroll_profile_id__in=contract_ids,
            payroll_period_id__in=period_ids,
            is_active=True,
        )
        summary_map = {
            (str(item.contract_payroll_profile_id), item.payroll_period_id): item
            for item in summaries
        }
        adjustments = ContractAttendanceAdjustment.objects.filter(
            contract_payroll_profile_id__in=contract_ids,
            payroll_period_id__in=period_ids,
            is_active=True,
        ).order_by("id")
        adjustment_map: dict[tuple[str, int], list[ContractAttendanceAdjustment]] = {}
        for item in adjustments:
            key = (str(item.contract_payroll_profile_id), item.payroll_period_id)
            adjustment_map.setdefault(key, []).append(item)
        return summary_map, adjustment_map

    @classmethod
    def _base_payload(cls, *, report_type: str, title: str, filters: PayrollReportFilters, columns: list[dict], rows: list[dict], summary_cards: list[dict], grouped_summary: list[dict], totals: dict) -> dict:
        return {
            "report_type": report_type,
            "title": title,
            "generated_at": timezone.now().isoformat(),
            "filters": {
                "entity": filters.entity_id,
                "entityfinid": filters.entityfinid_id,
                "subentity": filters.subentity_id,
                "payroll_period": filters.payroll_period_id,
                "department": filters.department_id,
                "org_unit": filters.org_unit_id,
                "employee": filters.employee_id,
                "contract": filters.contract_id,
                "status": filters.status,
                "statutory_scheme": filters.statutory_scheme_id,
                "from_date": filters.from_date.isoformat() if filters.from_date else None,
                "to_date": filters.to_date.isoformat() if filters.to_date else None,
            },
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "summary_cards": summary_cards,
            "grouped_summary": grouped_summary,
            "totals": totals,
            "export": {
                "ready": True,
                "formats": ["xlsx", "csv"],
                "structure": {
                    "columns": [column["key"] for column in columns],
                    "row_count": len(rows),
                    "metadata_fields": [
                        "entity",
                        "payroll_period_or_range",
                        "generated_by",
                        "generated_at",
                        "filters_applied",
                        "source_snapshot_note",
                    ],
                },
                "message": "Exports are generated from this same snapshot payload without recalculating payroll.",
            },
            "traceability": {
                "source_of_truth": "Backend payroll snapshots",
                "notes": [
                    "This report reads payroll run, component, attendance, statutory, and FnF snapshots only.",
                    "No payroll recalculation is performed inside reporting APIs.",
                ],
            },
        }

    @classmethod
    def _build_payroll_register(cls, *, filters: PayrollReportFilters) -> dict:
        rows = list(cls._base_employee_rows(filters=filters))
        attendance_map, adjustment_map = cls._attendance_maps(rows=rows)
        results: list[dict] = []
        gross_total = ZERO
        deduction_total = ZERO
        employer_total = ZERO
        net_total = ZERO
        by_period: dict[str, dict] = {}

        for row in rows:
            run = row.payroll_run
            contract = row.contract_payroll_profile.hrms_contract
            employee = contract.employee
            attendance = attendance_map.get((str(row.contract_payroll_profile_id), run.payroll_period_id))
            adjustments = adjustment_map.get((str(row.contract_payroll_profile_id), run.payroll_period_id), [])
            gross_total += _decimal(row.gross_amount)
            deduction_total += _decimal(row.deduction_amount)
            employer_total += _decimal(row.employer_contribution_amount)
            net_total += _decimal(row.payable_amount)
            period_key = getattr(run.payroll_period, "code", "Unknown")
            period_bucket = by_period.setdefault(period_key, {"group": period_key, "employee_count": 0, "net_payable": ZERO})
            period_bucket["employee_count"] += 1
            period_bucket["net_payable"] += _decimal(row.payable_amount)
            results.append(
                {
                    "id": row.id,
                    "run_id": run.id,
                    "employee_run_id": row.id,
                    "run_number": run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    "period_code": getattr(run.payroll_period, "code", ""),
                    "posting_date": run.posting_date.isoformat() if run.posting_date else None,
                    "employee_code": employee.employee_number,
                    "employee_name": employee.display_name,
                    "contract_code": contract.contract_code,
                    "department_name": getattr(contract.department, "name", "") or "",
                    "gross_amount": _decimal_str(row.gross_amount),
                    "deduction_amount": _decimal_str(row.deduction_amount),
                    "employer_contribution_amount": _decimal_str(row.employer_contribution_amount),
                    "net_payable": _decimal_str(row.payable_amount),
                    "payroll_status": run.status,
                    "payment_status": row.payment_status,
                    "attendance_days": _decimal_str(getattr(attendance, "attendance_days", ZERO)),
                    "payable_days": _decimal_str(getattr(attendance, "payable_days", ZERO)),
                    "lop_days": _decimal_str(getattr(attendance, "lop_days", ZERO)),
                    "overtime_hours": _decimal_str(getattr(attendance, "overtime_hours", ZERO)),
                    "half_days": _decimal_str(getattr(attendance, "half_days", ZERO)),
                    "proration_factor": _safe_divide(
                        _decimal(getattr(attendance, "payable_days", ZERO)),
                        _decimal(getattr(attendance, "attendance_days", ZERO)),
                    ),
                    "adjustment_count": len(adjustments),
                    "trace_actions": [
                        {"kind": "attendance", "label": "Attendance Trace", "run_id": run.id, "employee_run_id": row.id},
                        {"kind": "statutory", "label": "Statutory Trace", "run_id": run.id, "employee_run_id": row.id},
                    ],
                    "trace_summary": {
                        "component_count": len(row.components.all()),
                        "snapshot_source": "payroll_run_employee",
                    },
                }
            )

        columns = [
            {"key": "run_number", "label": "Run No", "type": "string"},
            {"key": "period_code", "label": "Period", "type": "string"},
            {"key": "employee_code", "label": "Employee Code", "type": "string"},
            {"key": "employee_name", "label": "Employee", "type": "string"},
            {"key": "contract_code", "label": "Contract", "type": "string"},
            {"key": "department_name", "label": "Department", "type": "string"},
            {"key": "gross_amount", "label": "Gross", "type": "amount"},
            {"key": "deduction_amount", "label": "Deductions", "type": "amount"},
            {"key": "employer_contribution_amount", "label": "Employer Cost", "type": "amount"},
            {"key": "net_payable", "label": "Net Pay", "type": "amount"},
            {"key": "payroll_status", "label": "Payroll Status", "type": "status"},
            {"key": "payment_status", "label": "Payment Status", "type": "status"},
            {"key": "proration_factor", "label": "Proration", "type": "decimal"},
        ]
        grouped = [
            {
                "group": key,
                "employee_count": value["employee_count"],
                "net_payable": _decimal_str(value["net_payable"]),
            }
            for key, value in by_period.items()
        ]
        return cls._base_payload(
            report_type=cls.REPORT_PAYROLL_REGISTER,
            title="Payroll Register",
            filters=filters,
            columns=columns,
            rows=results,
            summary_cards=[
                {"label": "Employees", "value": len(results)},
                {"label": "Gross", "value": _decimal_str(gross_total)},
                {"label": "Net Pay", "value": _decimal_str(net_total)},
            ],
            grouped_summary=grouped,
            totals={
                "gross_amount": _decimal_str(gross_total),
                "deduction_amount": _decimal_str(deduction_total),
                "employer_contribution_amount": _decimal_str(employer_total),
                "net_payable": _decimal_str(net_total),
            },
        )

    @classmethod
    def _build_salary_sheet(cls, *, filters: PayrollReportFilters) -> dict:
        rows = list(cls._base_employee_rows(filters=filters))
        component_order: list[tuple[str, str]] = []
        component_seen: set[str] = set()
        component_totals: dict[str, Decimal] = {}
        results: list[dict] = []
        net_total = ZERO

        for row in rows:
            amount_map = _component_amount_map(row)
            for component in row.components.all():
                if component.component_code not in component_seen:
                    component_order.append((component.component_code, component.component_name))
                    component_seen.add(component.component_code)
                component_totals[component.component_code] = component_totals.get(component.component_code, ZERO) + _decimal(component.amount)

        for row in rows:
            run = row.payroll_run
            contract = row.contract_payroll_profile.hrms_contract
            employee = contract.employee
            amount_map = _component_amount_map(row)
            row_payload = {
                "id": row.id,
                "run_id": run.id,
                "employee_run_id": row.id,
                "period_code": getattr(run.payroll_period, "code", ""),
                "employee_code": employee.employee_number,
                "employee_name": employee.display_name,
                "contract_code": contract.contract_code,
                "department_name": getattr(contract.department, "name", "") or "",
                "gross_amount": _decimal_str(row.gross_amount),
                "deduction_amount": _decimal_str(row.deduction_amount),
                "net_payable": _decimal_str(row.payable_amount),
                "trace_actions": [
                    {"kind": "attendance", "label": "Attendance Trace", "run_id": run.id, "employee_run_id": row.id},
                    {"kind": "statutory", "label": "Statutory Trace", "run_id": run.id, "employee_run_id": row.id},
                ],
                "trace_summary": {
                    "component_amounts": {key: _decimal_str(value) for key, value in amount_map.items()},
                    "snapshot_source": "payroll_run_employee_component",
                },
            }
            for component_code, _component_name in component_order:
                row_payload[component_code] = _decimal_str(amount_map.get(component_code, ZERO))
            results.append(row_payload)
            net_total += _decimal(row.payable_amount)

        columns = [
            {"key": "period_code", "label": "Period", "type": "string"},
            {"key": "employee_code", "label": "Employee Code", "type": "string"},
            {"key": "employee_name", "label": "Employee", "type": "string"},
            {"key": "contract_code", "label": "Contract", "type": "string"},
            {"key": "department_name", "label": "Department", "type": "string"},
        ]
        for component_code, component_name in component_order:
            columns.append({"key": component_code, "label": component_name, "type": "amount"})
        columns.extend(
            [
                {"key": "gross_amount", "label": "Gross", "type": "amount"},
                {"key": "deduction_amount", "label": "Deductions", "type": "amount"},
                {"key": "net_payable", "label": "Net Pay", "type": "amount"},
            ]
        )
        grouped = [
            {"group": component_name, "component_code": component_code, "amount": _decimal_str(component_totals.get(component_code, ZERO))}
            for component_code, component_name in component_order
        ]
        return cls._base_payload(
            report_type=cls.REPORT_SALARY_SHEET,
            title="Salary Sheet",
            filters=filters,
            columns=columns,
            rows=results,
            summary_cards=[
                {"label": "Employees", "value": len(results)},
                {"label": "Components", "value": len(component_order)},
                {"label": "Net Pay", "value": _decimal_str(net_total)},
            ],
            grouped_summary=grouped,
            totals={
                "employees": len(results),
                "net_payable": _decimal_str(net_total),
                "components": {component_code: _decimal_str(total) for component_code, total in component_totals.items()},
            },
        )

    @classmethod
    def _build_statutory_summary(cls, *, report_type: str, filters: PayrollReportFilters) -> dict:
        config = cls.STATUTORY_COMPONENT_MAP[report_type]
        scheme = None
        if filters.statutory_scheme_id:
            scheme = StatutoryScheme.objects.filter(pk=filters.statutory_scheme_id).first()
        if scheme is not None:
            expected_type = report_type.replace("_summary", "").replace("pt", "PT").replace("pf", "PF").replace("esi", "ESI").replace("lwf", "LWF").upper()
            if scheme.scheme_type != expected_type:
                return cls._base_payload(
                    report_type=report_type,
                    title=config["label"],
                    filters=filters,
                    columns=[],
                    rows=[],
                    summary_cards=[],
                    grouped_summary=[],
                    totals={},
                )

        rows = list(cls._base_employee_rows(filters=filters))
        results: list[dict] = []
        employee_total = ZERO
        employer_total = ZERO
        by_period: dict[str, Decimal] = {}

        for row in rows:
            run = row.payroll_run
            contract = row.contract_payroll_profile.hrms_contract
            employee = contract.employee
            employee_amount = ZERO
            employer_amount = ZERO
            related_components: list[dict] = []
            for component in row.components.all():
                semantic_code = getattr(component.component, "semantic_code", "") or component.component_code
                if semantic_code in config["employee_codes"]:
                    employee_amount += _decimal(component.amount)
                    related_components.append({"component_id": component.component_id, "component_code": component.component_code, "amount": _decimal_str(component.amount)})
                elif semantic_code in config["employer_codes"]:
                    employer_amount += _decimal(component.amount)
                    related_components.append({"component_id": component.component_id, "component_code": component.component_code, "amount": _decimal_str(component.amount)})
            if employee_amount == ZERO and employer_amount == ZERO:
                continue
            total_amount = employee_amount + employer_amount
            employee_total += employee_amount
            employer_total += employer_amount
            period_key = getattr(run.payroll_period, "code", "Unknown")
            by_period[period_key] = by_period.get(period_key, ZERO) + total_amount
            results.append(
                {
                    "id": row.id,
                    "run_id": run.id,
                    "employee_run_id": row.id,
                    "period_code": period_key,
                    "employee_code": employee.employee_number,
                    "employee_name": employee.display_name,
                    "contract_code": contract.contract_code,
                    "department_name": getattr(contract.department, "name", "") or "",
                    "employee_amount": _decimal_str(employee_amount),
                    "employer_amount": _decimal_str(employer_amount),
                    "total_amount": _decimal_str(total_amount),
                    "payroll_status": run.status,
                    "payment_status": row.payment_status,
                    "trace_actions": [
                        {"kind": "statutory", "label": "Statutory Trace", "run_id": run.id, "employee_run_id": row.id},
                    ],
                    "trace_summary": {
                        "components": related_components,
                        "snapshot_source": "payroll_run_employee_component",
                    },
                }
            )

        columns = [
            {"key": "period_code", "label": "Period", "type": "string"},
            {"key": "employee_code", "label": "Employee Code", "type": "string"},
            {"key": "employee_name", "label": "Employee", "type": "string"},
            {"key": "contract_code", "label": "Contract", "type": "string"},
            {"key": "department_name", "label": "Department", "type": "string"},
            {"key": "employee_amount", "label": "Employee Share", "type": "amount"},
            {"key": "employer_amount", "label": "Employer Share", "type": "amount"},
            {"key": "total_amount", "label": "Total", "type": "amount"},
            {"key": "payroll_status", "label": "Payroll Status", "type": "status"},
        ]
        return cls._base_payload(
            report_type=report_type,
            title=config["label"],
            filters=filters,
            columns=columns,
            rows=results,
            summary_cards=[
                {"label": "Rows", "value": len(results)},
                {"label": "Employee Share", "value": _decimal_str(employee_total)},
                {"label": "Employer Share", "value": _decimal_str(employer_total)},
            ],
            grouped_summary=[
                {"group": key, "total_amount": _decimal_str(value)}
                for key, value in by_period.items()
            ],
            totals={
                "employee_amount": _decimal_str(employee_total),
                "employer_amount": _decimal_str(employer_total),
                "total_amount": _decimal_str(employee_total + employer_total),
            },
        )

    @classmethod
    def _build_fnf_register(cls, *, filters: PayrollReportFilters) -> dict:
        queryset = FnFSettlement.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "hrms_contract__employee",
            "hrms_contract__department",
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
            "payroll_period",
        ).prefetch_related("components").filter(entity_id=filters.entity_id)
        if filters.entityfinid_id is not None:
            queryset = queryset.filter(entityfinid_id=filters.entityfinid_id)
        if filters.subentity_id is not None:
            queryset = queryset.filter(subentity_id=filters.subentity_id)
        if filters.department_id is not None:
            queryset = queryset.filter(hrms_contract__department_id=filters.department_id)
        if filters.org_unit_id is not None:
            queryset = queryset.filter(
                Q(hrms_contract__business_unit_id=filters.org_unit_id)
                | Q(hrms_contract__department_id=filters.org_unit_id)
                | Q(hrms_contract__team_id=filters.org_unit_id)
                | Q(hrms_contract__designation_id=filters.org_unit_id)
                | Q(hrms_contract__grade_id=filters.org_unit_id)
                | Q(hrms_contract__cost_center_id=filters.org_unit_id)
                | Q(hrms_contract__work_location_id=filters.org_unit_id)
            )
        if filters.employee_id is not None:
            queryset = queryset.filter(hrms_contract__employee_id=filters.employee_id)
        if filters.contract_id is not None:
            queryset = queryset.filter(hrms_contract_id=filters.contract_id)
        if filters.status:
            queryset = queryset.filter(status__iexact=filters.status)
        if filters.from_date is not None:
            queryset = queryset.filter(settlement_date__gte=filters.from_date)
        if filters.to_date is not None:
            queryset = queryset.filter(settlement_date__lte=filters.to_date)

        settlements = list(queryset.order_by("-settlement_date", "-id"))
        net_payable_total = ZERO
        net_recoverable_total = ZERO
        by_status: dict[str, dict] = {}
        results: list[dict] = []

        for settlement in settlements:
            employee = settlement.hrms_contract.employee
            component_count = settlement.components.count()
            net_payable_total += _decimal(settlement.net_payable_amount)
            net_recoverable_total += _decimal(settlement.net_recoverable_amount)
            status_bucket = by_status.setdefault(
                settlement.status,
                {"group": settlement.status, "count": 0, "net_payable": ZERO, "net_recoverable": ZERO},
            )
            status_bucket["count"] += 1
            status_bucket["net_payable"] += _decimal(settlement.net_payable_amount)
            status_bucket["net_recoverable"] += _decimal(settlement.net_recoverable_amount)
            results.append(
                {
                    "id": str(settlement.id),
                    "settlement_number": settlement.settlement_number or f"FNF-{settlement.id}",
                    "employee_code": employee.employee_number,
                    "employee_name": employee.display_name,
                    "contract_code": settlement.hrms_contract.contract_code,
                    "department_name": getattr(settlement.hrms_contract.department, "name", "") or "",
                    "settlement_date": settlement.settlement_date.isoformat(),
                    "separation_date": settlement.separation_date.isoformat(),
                    "last_working_day": settlement.last_working_day.isoformat(),
                    "status": settlement.status,
                    "earned_amount": _decimal_str(settlement.earned_amount),
                    "deduction_amount": _decimal_str(settlement.deduction_amount),
                    "recovery_amount": _decimal_str(settlement.recovery_amount),
                    "reimbursement_amount": _decimal_str(settlement.reimbursement_amount),
                    "net_payable_amount": _decimal_str(settlement.net_payable_amount),
                    "net_recoverable_amount": _decimal_str(settlement.net_recoverable_amount),
                    "component_count": component_count,
                    "trace_summary": {
                        "snapshot_source": "fnf_settlement",
                        "component_count": component_count,
                    },
                }
            )

        columns = [
            {"key": "settlement_number", "label": "Settlement No", "type": "string"},
            {"key": "employee_code", "label": "Employee Code", "type": "string"},
            {"key": "employee_name", "label": "Employee", "type": "string"},
            {"key": "contract_code", "label": "Contract", "type": "string"},
            {"key": "department_name", "label": "Department", "type": "string"},
            {"key": "settlement_date", "label": "Settlement Date", "type": "date"},
            {"key": "status", "label": "Status", "type": "status"},
            {"key": "earned_amount", "label": "Earned", "type": "amount"},
            {"key": "deduction_amount", "label": "Deduction", "type": "amount"},
            {"key": "recovery_amount", "label": "Recovery", "type": "amount"},
            {"key": "reimbursement_amount", "label": "Reimbursement", "type": "amount"},
            {"key": "net_payable_amount", "label": "Net Payable", "type": "amount"},
            {"key": "net_recoverable_amount", "label": "Net Recoverable", "type": "amount"},
        ]
        return cls._base_payload(
            report_type=cls.REPORT_FNF_REGISTER,
            title="FnF Settlement Register",
            filters=filters,
            columns=columns,
            rows=results,
            summary_cards=[
                {"label": "Settlements", "value": len(results)},
                {"label": "Net Payable", "value": _decimal_str(net_payable_total)},
                {"label": "Net Recoverable", "value": _decimal_str(net_recoverable_total)},
            ],
            grouped_summary=[
                {
                    "group": key,
                    "count": value["count"],
                    "net_payable": _decimal_str(value["net_payable"]),
                    "net_recoverable": _decimal_str(value["net_recoverable"]),
                }
                for key, value in by_status.items()
            ],
            totals={
                "net_payable_amount": _decimal_str(net_payable_total),
                "net_recoverable_amount": _decimal_str(net_recoverable_total),
            },
        )
