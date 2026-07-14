from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import Entity, SubEntity
from hrms.models import (
    AttendanceApproval,
    AttendanceImportBatch,
    AttendanceMonthlyClose,
    AttendancePolicy,
    ContractLeaveBalanceSnapshot,
    ContractLeaveLedgerEntry,
    DailyAttendance,
    GlobalAttendancePolicyTemplate,
    GlobalHolidayCalendarTemplate,
    GlobalHRPolicyTemplate,
    GlobalLeavePolicyTemplate,
    GlobalLeaveType,
    GlobalShiftTemplate,
    HRPolicy,
    LeavePolicy,
    LeavePolicyRule,
    LeaveApplication,
    LeaveType,
    HrEmployee,
    HrEmploymentContract,
    HrHoliday,
    HrHolidayCalendar,
    HrOrganizationUnit,
    HrShift,
)
from hrms.serializers import (
    AttendanceApprovalSerializer,
    AttendanceImportBatchSerializer,
    AttendanceMonthlyCloseSerializer,
    AttendancePolicySerializer,
    ContractLeaveBalanceSnapshotSerializer,
    ContractLeaveLedgerEntrySerializer,
    DailyAttendanceSerializer,
    GlobalAttendancePolicyTemplateSerializer,
    GlobalHolidayCalendarTemplateSerializer,
    GlobalHRPolicyTemplateSerializer,
    GlobalLeavePolicyTemplateSerializer,
    GlobalLeaveTypeSerializer,
    GlobalShiftTemplateSerializer,
    HRPolicySerializer,
    HrEmployeeSerializer,
    HrEmploymentContractSerializer,
    HrHolidayCalendarSerializer,
    HrHolidaySerializer,
    HrOrganizationUnitSerializer,
    HrShiftSerializer,
    HrmsMetaSerializer,
    LeaveApplicationSerializer,
    LeavePolicyRuleSerializer,
    LeavePolicySerializer,
    LeaveTypeSerializer,
)
from hrms.services import (
    AttendanceCaptureService,
    EmployeeService,
    EmploymentContractService,
    HolidayCalendarService,
    HrmsGlobalAdoptionService,
    LeaveApplicationService,
    LeaveApprovalService,
    LeaveBalanceService,
    LeaveYearService,
    HrmsPermissionService,
    OrganizationUnitService,
    ShiftService,
)
from subscriptions.services import SubscriptionService


class HrmsScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    @staticmethod
    def _parse_int(raw_value, field_name, *, required):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity=True):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if entity_id is not None:
            self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _scope_from_payload(self, request, payload):
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _assert_hrms_permission(self, request, *, entity_id: int, permission_key: str, label: str) -> None:
        try:
            HrmsPermissionService.assert_entity_permission_access(
                user=request.user,
                entity_id=entity_id,
                permission_key=permission_key,
                label=label,
            )
        except PermissionError as err:
            raise PermissionDenied(detail=str(err))
        self.enforce_scope(request, entity_id=entity_id)

    @staticmethod
    def _is_self_service_contract_access(*, user, contract) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        employee = getattr(contract, "employee", None)
        return getattr(employee, "linked_user_id", None) == getattr(user, "id", None)

    @staticmethod
    def _query_value(request, key):
        value = (request.query_params.get(key) or "").strip()
        return value or None

    @staticmethod
    def _query_bool(request, key):
        raw = (request.query_params.get(key) or "").strip().lower()
        if raw in ("true", "1", "yes"):
            return True
        if raw in ("false", "0", "no"):
            return False
        return None

    @staticmethod
    def _parse_date(raw_value, field_name, *, required=False):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            raise ValidationError({field_name: f"{field_name} must be in YYYY-MM-DD format."})


class HrmsMetaAPIView(HrmsScopedAPIView):
    def get(self, request):
        payload = {
            "organization_unit_types": [{"key": key, "label": label} for key, label in HrOrganizationUnit.UnitType.choices],
            "organization_unit_statuses": [{"key": key, "label": label} for key, label in HrOrganizationUnit.Status.choices],
            "employee_statuses": [{"key": key, "label": label} for key, label in HrEmployee.LifecycleStatus.choices],
            "employee_genders": [{"key": key, "label": label} for key, label in HrEmployee.Gender.choices],
            "employee_marital_statuses": [{"key": key, "label": label} for key, label in HrEmployee.MaritalStatus.choices],
            "contract_statuses": [{"key": key, "label": label} for key, label in HrEmploymentContract.ContractStatus.choices],
            "contract_types": [{"key": key, "label": label} for key, label in HrEmploymentContract.ContractType.choices],
            "work_models": [{"key": key, "label": label} for key, label in HrEmploymentContract.WorkModel.choices],
            "compensation_bases": [{"key": key, "label": label} for key, label in HrEmploymentContract.CompensationBasis.choices],
            "shift_types": [{"key": key, "label": label} for key, label in HrShift.ShiftType.choices],
            "shift_statuses": [{"key": key, "label": label} for key, label in HrShift.Status.choices],
            "holiday_calendar_statuses": [{"key": key, "label": label} for key, label in HrHolidayCalendar.Status.choices],
            "holiday_types": [{"key": key, "label": label} for key, label in HrHoliday.HolidayType.choices],
            "onboarding_industry_options": [
                {"key": "sme_office", "label": "SME Office"},
                {"key": "factory", "label": "Factory / Manufacturing"},
                {"key": "retail", "label": "Retail / Shop"},
                {"key": "services", "label": "Services Company"},
                {"key": "contractor", "label": "Contractor Workforce"},
                {"key": "school", "label": "School / Institute"},
                {"key": "custom", "label": "Custom Setup"},
            ],
            "onboarding_employee_category_options": [
                {"key": key, "label": label} for key, label in LeavePolicy.EmployeeCategory.choices
            ],
        }
        return Response(HrmsMetaSerializer(payload).data)


class HrOrganizationUnitListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="organization_unit_view",
            label="view HRMS organization units",
        )
        unit_type = self._query_value(request, "unit_type")
        status_value = self._query_value(request, "status")
        search = self._query_value(request, "search")
        ordering = self._query_value(request, "ordering") or "name"
        serializer = HrOrganizationUnitSerializer(
            OrganizationUnitService.list_units(
                entity_id=entity_id,
                subentity_id=subentity_id,
                unit_type=unit_type,
                status=status_value,
                search=search,
                active_only=(request.query_params.get("active_only") or "true").strip().lower() != "false",
                ordering=ordering,
            ),
            many=True,
        )
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, _ = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="organization_unit_create",
            label="create HRMS organization units",
        )
        serializer = HrOrganizationUnitSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrOrganizationUnitDetailAPIView(HrmsScopedAPIView):
    model = HrOrganizationUnit
    serializer_class = HrOrganizationUnitSerializer

    def _get_object(self, request, pk):
        obj = self.model.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def get(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Organization unit not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="organization_unit_view",
            label="view HRMS organization units",
        )
        return Response(self.serializer_class(obj).data)

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Organization unit not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="organization_unit_update",
            label="update HRMS organization units",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = self.serializer_class(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Organization unit not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="organization_unit_delete",
            label="delete HRMS organization units",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrEmployeeListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="employee_view",
            label="view HRMS employees",
        )
        search = self._query_value(request, "search")
        status_value = self._query_value(request, "status")
        ordering = self._query_value(request, "ordering") or "display_name"
        serializer = HrEmployeeSerializer(
            EmployeeService.list_employees(
                entity_id=entity_id,
                subentity_id=subentity_id,
                search=search,
                status=status_value,
                active_only=(request.query_params.get("active_only") or "true").strip().lower() != "false",
                ordering=ordering,
            ),
            many=True,
        )
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, _ = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="employee_create",
            label="create HRMS employees",
        )
        serializer = HrEmployeeSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrEmployeeDetailAPIView(HrmsScopedAPIView):
    def _get_object(self, request, pk):
        obj = HrEmployee.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def get(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employee_view",
            label="view HRMS employees",
        )
        return Response(HrEmployeeSerializer(obj).data)

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employee_update",
            label="update HRMS employees",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = HrEmployeeSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employee_delete",
            label="delete HRMS employees",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrEmploymentContractListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="employment_contract_view",
            label="view HRMS employment contracts",
        )
        employee_id = self._query_value(request, "employee")
        status_value = self._query_value(request, "status")
        search = self._query_value(request, "search")
        ordering = self._query_value(request, "ordering") or "-payroll_effective_from"
        payroll_eligible = self._query_bool(request, "payroll_eligible")
        serializer = HrEmploymentContractSerializer(
            EmploymentContractService.list_contracts(
                entity_id=entity_id,
                subentity_id=subentity_id,
                employee_id=employee_id,
                payroll_eligible=payroll_eligible,
                status=status_value,
                search=search,
                active_only=(request.query_params.get("active_only") or "true").strip().lower() != "false",
                ordering=ordering,
            ),
            many=True,
        )
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, _ = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="employment_contract_create",
            label="create HRMS employment contracts",
        )
        serializer = HrEmploymentContractSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrEmploymentContractDetailAPIView(HrmsScopedAPIView):
    def _get_object(self, request, pk):
        obj = HrEmploymentContract.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def get(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employment_contract_view",
            label="view HRMS employment contracts",
        )
        return Response(HrEmploymentContractSerializer(obj).data)

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employment_contract_update",
            label="update HRMS employment contracts",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = HrEmploymentContractSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="employment_contract_delete",
            label="delete HRMS employment contracts",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrShiftListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="shift_view",
            label="view HRMS shifts",
        )
        status_value = self._query_value(request, "status")
        search = self._query_value(request, "search")
        ordering = self._query_value(request, "ordering") or "name"
        serializer = HrShiftSerializer(
            ShiftService.list_shifts(
                entity_id=entity_id,
                subentity_id=subentity_id,
                status=status_value,
                search=search,
                active_only=(request.query_params.get("active_only") or "true").strip().lower() != "false",
                ordering=ordering,
            ),
            many=True,
        )
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, _ = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="shift_create",
            label="create HRMS shifts",
        )
        serializer = HrShiftSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrShiftDetailAPIView(HrmsScopedAPIView):
    def _get_object(self, request, pk):
        obj = HrShift.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def get(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Shift not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="shift_view",
            label="view HRMS shifts",
        )
        return Response(HrShiftSerializer(obj).data)

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Shift not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="shift_update",
            label="update HRMS shifts",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = HrShiftSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Shift not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="shift_delete",
            label="delete HRMS shifts",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrHolidayCalendarListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="holiday_calendar_view",
            label="view HRMS holiday calendars",
        )
        year_raw = self._query_value(request, "calendar_year")
        status_value = self._query_value(request, "status")
        search = self._query_value(request, "search")
        ordering = self._query_value(request, "ordering") or "-calendar_year"
        serializer = HrHolidayCalendarSerializer(
            HolidayCalendarService.list_calendars(
                entity_id=entity_id,
                subentity_id=subentity_id,
                calendar_year=int(year_raw) if year_raw else None,
                status=status_value,
                search=search,
                active_only=(request.query_params.get("active_only") or "true").strip().lower() != "false",
                ordering=ordering,
            ),
            many=True,
        )
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, _ = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="holiday_calendar_create",
            label="create HRMS holiday calendars",
        )
        serializer = HrHolidayCalendarSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrHolidayCalendarDetailAPIView(HrmsScopedAPIView):
    def _get_object(self, request, pk):
        obj = HrHolidayCalendar.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def get(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Holiday calendar not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="holiday_calendar_view",
            label="view HRMS holiday calendars",
        )
        return Response(HrHolidayCalendarSerializer(obj).data)

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Holiday calendar not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="holiday_calendar_update",
            label="update HRMS holiday calendars",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = HrHolidayCalendarSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Holiday calendar not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="holiday_calendar_delete",
            label="delete HRMS holiday calendars",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrHolidayListCreateAPIView(HrmsScopedAPIView):
    def get_calendar(self, request, calendar_pk):
        calendar = HrHolidayCalendar.objects.filter(pk=calendar_pk).first()
        if calendar is None:
            return None
        self.enforce_scope(request, entity_id=calendar.entity_id, subentity_id=calendar.subentity_id)
        return calendar

    def get(self, request, calendar_pk):
        calendar = self.get_calendar(request, calendar_pk)
        if calendar is None:
            return Response({"detail": "Holiday calendar not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=calendar.entity_id,
            permission_key="holiday_calendar_view",
            label="view HRMS holiday calendars",
        )
        serializer = HrHolidaySerializer(calendar.holidays.filter(deleted_at__isnull=True).order_by("holiday_date", "name"), many=True)
        return Response(serializer.data)

    def post(self, request, calendar_pk):
        calendar = self.get_calendar(request, calendar_pk)
        if calendar is None:
            return Response({"detail": "Holiday calendar not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=calendar.entity_id,
            permission_key="holiday_calendar_update",
            label="update HRMS holiday calendars",
        )
        payload = request.data.copy()
        payload["entity"] = calendar.entity_id
        payload["subentity"] = calendar.subentity_id
        payload["holiday_calendar"] = str(calendar.id)
        serializer = HrHolidaySerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HrHolidayDetailAPIView(HrmsScopedAPIView):
    def _get_object(self, request, pk):
        obj = HrHoliday.objects.filter(pk=pk).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj

    def patch(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Holiday not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="holiday_calendar_update",
            label="update HRMS holiday calendars",
        )
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        payload["subentity"] = obj.subentity_id
        payload["holiday_calendar"] = str(obj.holiday_calendar_id)
        serializer = HrHolidaySerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get_object(request, pk)
        if obj is None:
            return Response({"detail": "Holiday not found."}, status=status.HTTP_404_NOT_FOUND)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="holiday_calendar_delete",
            label="delete HRMS holiday calendars",
        )
        obj.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrmsGlobalTemplateCatalogAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, _ = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="onboarding_view",
            label="view HRMS onboarding templates",
        )
        payload = {
            "leave_types": GlobalLeaveTypeSerializer(GlobalLeaveType.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
            "leave_policy_templates": GlobalLeavePolicyTemplateSerializer(GlobalLeavePolicyTemplate.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
            "shift_templates": GlobalShiftTemplateSerializer(GlobalShiftTemplate.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
            "holiday_calendar_templates": GlobalHolidayCalendarTemplateSerializer(GlobalHolidayCalendarTemplate.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
            "attendance_policy_templates": GlobalAttendancePolicyTemplateSerializer(GlobalAttendancePolicyTemplate.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
            "hr_policy_templates": GlobalHRPolicyTemplateSerializer(GlobalHRPolicyTemplate.objects.filter(deleted_at__isnull=True).order_by("code"), many=True).data,
        }
        return Response(payload)


class HrmsGlobalAdoptionPreviewAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="onboarding_view",
            label="preview HRMS onboarding adoption",
        )
        industry_type = self._query_value(request, "industry_type") or "custom"
        employee_category = self._query_value(request, "employee_category") or "custom"
        year_raw = self._query_value(request, "year")
        entity = Entity.objects.get(id=entity_id)
        subentity = SubEntity.objects.get(id=subentity_id) if subentity_id else None
        preview = HrmsGlobalAdoptionService.preview_adoption(
            entity=entity,
            subentity=subentity,
            industry_type=industry_type,
            employee_category=employee_category,
            year=int(year_raw) if year_raw else None,
        )
        return Response(preview)


class HrmsGlobalAdoptTemplatesAPIView(HrmsScopedAPIView):
    def post(self, request):
        payload = request.data.copy()
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="onboarding_adopt",
            label="adopt HRMS onboarding templates",
        )
        entity = Entity.objects.get(id=entity_id)
        subentity = SubEntity.objects.get(id=subentity_id) if subentity_id else None
        mode = str(payload.get("mode") or "recommended").strip().lower()
        if mode == "recommended":
            result = HrmsGlobalAdoptionService.adopt_recommended_templates(
                entity=entity,
                subentity=subentity,
                industry_type=str(payload.get("industry_type") or "custom"),
                employee_category=str(payload.get("employee_category") or "custom"),
                year=int(payload.get("year")) if payload.get("year") else None,
            )
        else:
            result = HrmsGlobalAdoptionService.adopt_selected_templates(
                entity=entity,
                subentity=subentity,
                selection={
                    "leave_policy_template_ids": payload.get("leave_policy_template_ids") or [],
                    "shift_template_ids": payload.get("shift_template_ids") or [],
                    "holiday_calendar_template_ids": payload.get("holiday_calendar_template_ids") or [],
                    "attendance_policy_template_ids": payload.get("attendance_policy_template_ids") or [],
                    "hr_policy_template_ids": payload.get("hr_policy_template_ids") or [],
                },
                year=int(payload.get("year")) if payload.get("year") else None,
            )
        return Response(result, status=status.HTTP_201_CREATED)


class HrmsEntitySetupSummaryAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="onboarding_view",
            label="view HRMS onboarding setup",
        )
        entity = Entity.objects.get(id=entity_id)
        subentity = SubEntity.objects.get(id=subentity_id) if subentity_id else None
        return Response(HrmsGlobalAdoptionService.entity_setup_summary(entity=entity, subentity=subentity))


class HrmsEntitySetupPatchAPIView(HrmsScopedAPIView):
    MODEL_MAP = {
        "leave-type": (LeaveType, "leave_type", LeaveTypeSerializer),
        "leave-policy": (LeavePolicy, "leave_policy", LeavePolicySerializer),
        "leave-policy-rule": (LeavePolicyRule, "leave_policy_rule", LeavePolicyRuleSerializer),
        "shift": (HrShift, "shift", HrShiftSerializer),
        "holiday-calendar": (HrHolidayCalendar, "holiday_calendar", HrHolidayCalendarSerializer),
        "attendance-policy": (AttendancePolicy, "attendance_policy", AttendancePolicySerializer),
        "hr-policy": (HRPolicy, "hr_policy", HRPolicySerializer),
    }

    def patch(self, request, setup_type, pk):
        config = self.MODEL_MAP.get(setup_type)
        if config is None:
            return Response({"detail": "Unsupported setup type."}, status=status.HTTP_404_NOT_FOUND)
        model, service_key, serializer_class = config
        obj = model.objects.filter(pk=pk).first()
        if obj is None:
            return Response({"detail": "Setup item not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="onboarding_update",
            label="update HRMS onboarding setup",
        )
        updated = HrmsGlobalAdoptionService.patch_entity_setup(setup_type=service_key, obj=obj, payload=request.data)
        return Response(serializer_class(updated).data)


class DailyAttendanceListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_entry_view",
            label="view attendance entries",
        )
        start_date = self._parse_date(request.query_params.get("start_date"), "start_date", required=False)
        end_date = self._parse_date(request.query_params.get("end_date"), "end_date", required=False)
        queryset = AttendanceCaptureService.list_daily_entries(
            entity_id=entity_id,
            subentity_id=subentity_id,
            contract_id=self._query_value(request, "contract"),
            start_date=start_date,
            end_date=end_date,
        )
        return Response(DailyAttendanceSerializer(queryset, many=True).data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, subentity_id = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_entry_create",
            label="create attendance entries",
        )
        contract = HrEmploymentContract.objects.filter(
            pk=payload.get("contract"),
            entity_id=entity_id,
            subentity_id=subentity_id,
            deleted_at__isnull=True,
        ).first()
        if contract is None:
            raise ValidationError({"contract": "Valid contract is required."})
        leave_application = None
        if payload.get("leave_application"):
            leave_application = LeaveApplication.objects.filter(
                pk=payload.get("leave_application"),
                contract=contract,
                entity_id=entity_id,
                deleted_at__isnull=True,
            ).first()
            if leave_application is None:
                raise ValidationError({"leave_application": "Leave application must belong to the selected contract."})
        entry = AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": contract,
                "attendance_date": self._parse_date(payload.get("attendance_date"), "attendance_date", required=True),
                "status": payload.get("status"),
                "source": payload.get("source"),
                "overtime_hours": payload.get("overtime_hours"),
                "late_mark": payload.get("late_mark", False),
                "attendance_fraction": payload.get("attendance_fraction"),
                "payable_fraction": payload.get("payable_fraction"),
                "lop_fraction": payload.get("lop_fraction"),
                "remarks": payload.get("remarks", ""),
                "leave_application": leave_application,
                "trace_json": payload.get("trace_json") or {},
            },
            actor=request.user,
            instance=DailyAttendance.objects.filter(
                contract=contract,
                attendance_date=self._parse_date(payload.get("attendance_date"), "attendance_date", required=True),
                deleted_at__isnull=True,
            ).first(),
        )
        return Response(DailyAttendanceSerializer(entry).data, status=status.HTTP_201_CREATED)


class DailyAttendanceBulkUpsertAPIView(HrmsScopedAPIView):
    def post(self, request):
        payload = request.data.copy()
        entity_id, subentity_id = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_entry_update",
            label="update attendance entries",
        )
        contract = HrEmploymentContract.objects.filter(
            pk=payload.get("contract"),
            entity_id=entity_id,
            subentity_id=subentity_id,
            deleted_at__isnull=True,
        ).first()
        if contract is None:
            raise ValidationError({"contract": "Valid contract is required."})
        rows = payload.get("rows") or []
        prepared_rows = []
        for row in rows:
            prepared_rows.append(
                {
                    "attendance_date": self._parse_date(row.get("attendance_date"), "attendance_date", required=True),
                    "status": row.get("status"),
                    "source": row.get("source"),
                    "overtime_hours": row.get("overtime_hours"),
                    "late_mark": row.get("late_mark", False),
                    "attendance_fraction": row.get("attendance_fraction"),
                    "payable_fraction": row.get("payable_fraction"),
                    "lop_fraction": row.get("lop_fraction"),
                    "remarks": row.get("remarks", ""),
                    "trace_json": row.get("trace_json") or {},
                }
            )
        items = AttendanceCaptureService.bulk_upsert_entries(
            contract=contract,
            rows=prepared_rows,
            actor=request.user,
            source=payload.get("source", DailyAttendance.EntrySource.MANUAL),
        )
        return Response(DailyAttendanceSerializer(items, many=True).data)


class AttendanceImportBatchListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_import_batch_view",
            label="view attendance import batches",
        )
        queryset = AttendanceImportBatch.objects.filter(entity_id=entity_id, deleted_at__isnull=True)
        if subentity_id is not None:
            queryset = queryset.filter(Q(subentity_id=subentity_id) | Q(subentity_id__isnull=True))
        return Response(AttendanceImportBatchSerializer(queryset.order_by("-uploaded_at"), many=True).data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, subentity_id = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_import_batch_create",
            label="create attendance import batches",
        )
        serializer = AttendanceImportBatchSerializer(
            data={
                "entity": entity_id,
                "subentity": subentity_id,
                "batch_code": payload.get("batch_code"),
                "import_mode": payload.get("import_mode", AttendanceImportBatch.ImportMode.PLACEHOLDER),
                "import_status": payload.get("import_status", AttendanceImportBatch.ImportStatus.UPLOADED),
                "file_name": payload.get("file_name", ""),
                "payload_json": payload.get("payload_json") or {},
                "result_json": payload.get("result_json") or {"message": "Attendance import placeholder accepted."},
                "remarks": payload.get("remarks", ""),
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AttendanceMonthlySummaryAPIView(HrmsScopedAPIView):
    def get(self, request):
        from payroll.models import PayrollPeriod

        entity_id, subentity_id = self._scope_from_query(request)
        mine = self._query_bool(request, "mine")
        if not mine:
            self._assert_hrms_permission(
                request,
                entity_id=entity_id,
                permission_key="attendance_summary_view",
                label="view attendance summaries",
            )
        payroll_period = PayrollPeriod.objects.filter(
            pk=self._query_value(request, "payroll_period"),
            entity_id=entity_id,
            subentity_id=subentity_id,
        ).first()
        if payroll_period is None:
            raise ValidationError({"payroll_period": "Valid payroll_period is required."})
        items = AttendanceCaptureService.list_monthly_summaries(
            entity_id=entity_id,
            subentity_id=subentity_id,
            payroll_period=payroll_period,
            contract_id=self._query_value(request, "contract"),
            employee_user_id=request.user.id if mine else None,
        )
        return Response(
            {
                "payroll_period_id": payroll_period.id,
                "payroll_period_code": payroll_period.code,
                "period_start": payroll_period.period_start,
                "period_end": payroll_period.period_end,
                "items": [
                    {
                        **item,
                        "attendance_days": str(item["attendance_days"]),
                        "payable_days": str(item["payable_days"]),
                        "lop_days": str(item["lop_days"]),
                        "weekly_off_days": str(item["weekly_off_days"]),
                        "holiday_days": str(item["holiday_days"]),
                        "overtime_hours": str(item["overtime_hours"]),
                        "half_days": str(item["half_days"]),
                        "paid_leave_days": str(item["paid_leave_days"]),
                        "unpaid_leave_days": str(item["unpaid_leave_days"]),
                        "covered_days": str(item["covered_days"]),
                    }
                    for item in items
                ],
            }
        )


class AttendancePayrollPeriodListAPIView(HrmsScopedAPIView):
    def get(self, request):
        from payroll.models import PayrollPeriod

        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_payroll_period_view",
            label="view attendance payroll periods",
        )
        queryset = PayrollPeriod.objects.filter(entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        return Response(
            [
                {
                    "id": item.id,
                    "code": item.code,
                    "period_start": item.period_start,
                    "period_end": item.period_end,
                    "status": item.status,
                }
                for item in queryset.order_by("-period_start", "-id")
            ]
        )


class AttendanceApprovalListAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_approval_view",
            label="view attendance approvals",
        )
        queryset = AttendanceApproval.objects.select_related("contract", "contract__employee", "monthly_close").filter(
            entity_id=entity_id,
            deleted_at__isnull=True,
        )
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        payroll_period_code = self._query_value(request, "payroll_period_code")
        if payroll_period_code is None and self._query_value(request, "payroll_period"):
            payroll_period_code = self._query_value(request, "payroll_period")
        if payroll_period_code:
            queryset = queryset.filter(payroll_period_code=payroll_period_code)
        if self._query_value(request, "status"):
            queryset = queryset.filter(status=self._query_value(request, "status"))
        return Response(AttendanceApprovalSerializer(queryset.order_by("contract__contract_code"), many=True).data)


class AttendanceApprovalSubmitAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        from payroll.models import PayrollPeriod

        contract = HrEmploymentContract.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if contract is None:
            return Response({"detail": "Contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=contract.entity_id, subentity_id=contract.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=contract.entity_id,
            permission_key="attendance_approval_submit",
            label="submit attendance approvals",
        )
        payroll_period = PayrollPeriod.objects.filter(
            pk=request.data.get("payroll_period"),
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
        ).first()
        if payroll_period is None:
            raise ValidationError({"payroll_period": "Valid payroll_period is required."})
        approval = AttendanceCaptureService.submit_approval(contract=contract, payroll_period=payroll_period, actor=request.user)
        return Response(AttendanceApprovalSerializer(approval).data)


class AttendanceApprovalApproveAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        approval = AttendanceApproval.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if approval is None:
            return Response({"detail": "Attendance approval not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=approval.entity_id, subentity_id=approval.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=approval.entity_id,
            permission_key="attendance_approval_approve",
            label="approve attendance approvals",
        )
        updated = AttendanceCaptureService.approve_approval(
            approval=approval,
            actor=request.user,
            review_note=str(request.data.get("review_note") or ""),
        )
        return Response(AttendanceApprovalSerializer(updated).data)


class AttendanceApprovalRejectAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        approval = AttendanceApproval.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if approval is None:
            return Response({"detail": "Attendance approval not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=approval.entity_id, subentity_id=approval.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=approval.entity_id,
            permission_key="attendance_approval_reject",
            label="reject attendance approvals",
        )
        updated = AttendanceCaptureService.reject_approval(
            approval=approval,
            actor=request.user,
            review_note=str(request.data.get("review_note") or ""),
        )
        return Response(AttendanceApprovalSerializer(updated).data)


class AttendanceMonthlyCloseListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_monthly_close_view",
            label="view attendance monthly closes",
        )
        queryset = AttendanceMonthlyClose.objects.select_related("payroll_period").filter(
            entity_id=entity_id,
            deleted_at__isnull=True,
        )
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        return Response(AttendanceMonthlyCloseSerializer(queryset.order_by("-payroll_period__period_start"), many=True).data)

    def post(self, request):
        from payroll.models import PayrollPeriod

        payload = request.data.copy()
        entity_id, subentity_id = self._scope_from_payload(request, payload)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="attendance_monthly_close_create",
            label="create attendance monthly closes",
        )
        payroll_period = PayrollPeriod.objects.filter(
            pk=payload.get("payroll_period"),
            entity_id=entity_id,
            subentity_id=subentity_id,
        ).first()
        if payroll_period is None:
            raise ValidationError({"payroll_period": "Valid payroll_period is required."})
        monthly_close = AttendanceCaptureService.get_or_create_monthly_close(
            entity_id=entity_id,
            subentity_id=subentity_id,
            payroll_period=payroll_period,
        )
        return Response(AttendanceMonthlyCloseSerializer(monthly_close).data, status=status.HTTP_201_CREATED)


class AttendanceMonthlyCloseSubmitAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        monthly_close = AttendanceMonthlyClose.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if monthly_close is None:
            return Response({"detail": "Attendance monthly close not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=monthly_close.entity_id, subentity_id=monthly_close.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=monthly_close.entity_id,
            permission_key="attendance_monthly_close_submit",
            label="submit attendance monthly closes",
        )
        updated = AttendanceCaptureService.submit_monthly_close(monthly_close=monthly_close, actor=request.user)
        return Response(AttendanceMonthlyCloseSerializer(updated).data)


class AttendanceMonthlyCloseApproveAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        monthly_close = AttendanceMonthlyClose.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if monthly_close is None:
            return Response({"detail": "Attendance monthly close not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=monthly_close.entity_id, subentity_id=monthly_close.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=monthly_close.entity_id,
            permission_key="attendance_monthly_close_approve",
            label="approve attendance monthly closes",
        )
        updated = AttendanceCaptureService.approve_monthly_close(monthly_close=monthly_close, actor=request.user)
        return Response(AttendanceMonthlyCloseSerializer(updated).data)


class AttendanceMonthlyCloseCloseAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        monthly_close = AttendanceMonthlyClose.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if monthly_close is None:
            return Response({"detail": "Attendance monthly close not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=monthly_close.entity_id, subentity_id=monthly_close.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=monthly_close.entity_id,
            permission_key="attendance_monthly_close_close",
            label="close attendance monthly closes",
        )
        updated = AttendanceCaptureService.close_monthly_close(
            monthly_close=monthly_close,
            actor=request.user,
            close_note=str(request.data.get("close_note") or ""),
        )
        return Response(AttendanceMonthlyCloseSerializer(updated).data)


class LeavePolicyListAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        self._assert_hrms_permission(
            request,
            entity_id=entity_id,
            permission_key="leave_policy_view",
            label="view leave policies",
        )
        queryset = LeavePolicy.objects.filter(entity_id=entity_id, deleted_at__isnull=True)
        if subentity_id is not None:
            queryset = queryset.filter(Q(subentity_id=subentity_id) | Q(subentity_id__isnull=True))
        queryset = queryset.order_by("-is_default", "code")
        return Response(LeavePolicySerializer(queryset, many=True).data)


class LeavePolicyRuleDetailAPIView(HrmsScopedAPIView):
    def patch(self, request, pk):
        obj = LeavePolicyRule.objects.filter(pk=pk).first()
        if obj is None:
            return Response({"detail": "Leave policy rule not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="leave_policy_update",
            label="update leave policies",
        )
        serializer = LeavePolicyRuleSerializer(instance=obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


class LeaveBalanceListAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, _ = self._scope_from_query(request)
        contract_id = self._query_value(request, "contract")
        if not contract_id:
            raise ValidationError({"contract": "contract is required."})
        contract = HrEmploymentContract.objects.filter(pk=contract_id, entity_id=entity_id).first()
        if contract is None:
            return Response({"detail": "Contract not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._is_self_service_contract_access(user=request.user, contract=contract):
            self._assert_hrms_permission(
                request,
                entity_id=entity_id,
                permission_key="leave_balance_view",
                label="view leave balances",
            )
        leave_policy = LeaveBalanceService._active_leave_policy(contract=contract, as_of_date=date.today())
        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=date.today())
        items = [
            {
                "leave_type_id": item.leave_type_id,
                "leave_type_code": item.leave_type_code,
                "leave_type_name": item.leave_type_name,
                "balance_days": str(item.balance_days),
                "encashable_days": str(item.encashable_days),
                "last_snapshot_id": item.last_snapshot_id,
                "trace": item.trace,
            }
            for item in LeaveBalanceService.list_balance_summaries(contract=contract)
        ]
        return Response(
            {
                "contract_id": str(contract.id),
                "leave_year_start": leave_year.start_date,
                "leave_year_end": leave_year.end_date,
                "items": items,
            }
        )


class LeaveLedgerListAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, _ = self._scope_from_query(request)
        contract_id = self._query_value(request, "contract")
        leave_type_id = self._query_value(request, "leave_type")
        queryset = ContractLeaveLedgerEntry.objects.filter(entity_id=entity_id, deleted_at__isnull=True)
        if contract_id:
            contract = HrEmploymentContract.objects.filter(pk=contract_id, entity_id=entity_id).first()
            if contract is None:
                return Response({"detail": "Contract not found."}, status=status.HTTP_404_NOT_FOUND)
            leave_policy = LeaveBalanceService._active_leave_policy(contract=contract, as_of_date=date.today())
            leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=date.today())
            if not self._is_self_service_contract_access(user=request.user, contract=contract):
                self._assert_hrms_permission(
                    request,
                    entity_id=entity_id,
                    permission_key="leave_ledger_view",
                    label="view leave ledgers",
                )
            queryset = queryset.filter(
                contract_id=contract_id,
                effective_date__gte=leave_year.start_date,
                effective_date__lte=leave_year.end_date,
            )
        else:
            self._assert_hrms_permission(
                request,
                entity_id=entity_id,
                permission_key="leave_ledger_view",
                label="view leave ledgers",
            )
        if leave_type_id:
            queryset = queryset.filter(leave_type_id=leave_type_id)
        queryset = queryset.order_by("-effective_date", "-created_at")
        return Response(ContractLeaveLedgerEntrySerializer(queryset, many=True).data)


class LeaveBalanceBootstrapAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        contract = HrEmploymentContract.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if contract is None:
            return Response({"detail": "Contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=contract.entity_id, subentity_id=contract.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=contract.entity_id,
            permission_key="leave_policy_update",
            label="initialize leave balances",
        )
        raw_date = str(request.data.get("as_of_date") or "").strip()
        as_of_date = parse_date(raw_date) if raw_date else date.today()
        if as_of_date is None:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD."})
        result = LeaveBalanceService.bootstrap_from_policy_defaults(contract=contract, as_of_date=as_of_date)
        return Response(result)


class LeaveBalanceAccrualAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        contract = HrEmploymentContract.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if contract is None:
            return Response({"detail": "Contract not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=contract.entity_id, subentity_id=contract.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=contract.entity_id,
            permission_key="leave_policy_update",
            label="run leave accrual",
        )
        raw_date = str(request.data.get("as_of_date") or "").strip()
        as_of_date = parse_date(raw_date) if raw_date else date.today()
        if as_of_date is None:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD."})
        result = LeaveBalanceService.accrue_contract_balances(contract=contract, as_of_date=as_of_date)
        return Response(result)


class LeaveApplicationListCreateAPIView(HrmsScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        mine = self._query_bool(request, "mine")
        if not mine:
            self._assert_hrms_permission(
                request,
                entity_id=entity_id,
                permission_key="leave_application_view",
                label="view leave applications",
            )
        queryset = LeaveApplicationService.list_applications(
            entity_id=entity_id,
            subentity_id=subentity_id,
            contract_id=self._query_value(request, "contract"),
            status_value=self._query_value(request, "status"),
            employee_user_id=request.user.id if mine else None,
        )
        return Response(LeaveApplicationSerializer(queryset, many=True).data)

    def post(self, request):
        payload = request.data.copy()
        entity_id, subentity_id = self._scope_from_payload(request, payload)
        contract = HrEmploymentContract.objects.filter(pk=payload.get("contract"), entity_id=entity_id).first()
        leave_type = LeaveType.objects.filter(pk=payload.get("leave_type"), entity_id=entity_id).first()
        if contract is None:
            raise ValidationError({"contract": "Valid contract is required."})
        if leave_type is None:
            raise ValidationError({"leave_type": "Valid leave type is required."})
        if subentity_id not in (None, contract.subentity_id):
            raise ValidationError({"subentity": "Subentity must match the contract scope."})
        if not self._is_self_service_contract_access(user=request.user, contract=contract):
            self._assert_hrms_permission(
                request,
                entity_id=entity_id,
                permission_key="leave_application_create",
                label="create leave applications",
            )
        application = LeaveApplicationService.create_application(
            attrs={
                "contract": contract,
                "leave_type": leave_type,
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "requested_days": payload.get("requested_days"),
                "reason": payload.get("reason", ""),
                "status": payload.get("status"),
                "created_via": payload.get("created_via", "api"),
            },
            actor=request.user,
        )
        return Response(LeaveApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class LeaveApplicationApprovalAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        application = LeaveApplication.objects.filter(pk=pk).first()
        if application is None:
            return Response({"detail": "Leave application not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=application.entity_id, subentity_id=application.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=application.entity_id,
            permission_key="leave_application_approve",
            label="approve leave applications",
        )
        approved = LeaveApprovalService.approve(
            application=application,
            approver=request.user,
            approved_days=request.data.get("approved_days"),
            manager_note=str(request.data.get("manager_note") or ""),
        )
        return Response(LeaveApplicationSerializer(approved).data)


class LeaveApplicationRejectAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        application = LeaveApplication.objects.filter(pk=pk).first()
        if application is None:
            return Response({"detail": "Leave application not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=application.entity_id, subentity_id=application.subentity_id)
        self._assert_hrms_permission(
            request,
            entity_id=application.entity_id,
            permission_key="leave_application_reject",
            label="reject leave applications",
        )
        rejected = LeaveApprovalService.reject(
            application=application,
            approver=request.user,
            manager_note=str(request.data.get("manager_note") or ""),
        )
        return Response(LeaveApplicationSerializer(rejected).data)


class LeaveApplicationCancelAPIView(HrmsScopedAPIView):
    def post(self, request, pk):
        application = LeaveApplication.objects.filter(pk=pk).first()
        if application is None:
            return Response({"detail": "Leave application not found."}, status=status.HTTP_404_NOT_FOUND)
        self.enforce_scope(request, entity_id=application.entity_id, subentity_id=application.subentity_id)
        if not self._is_self_service_contract_access(user=request.user, contract=application.contract):
            self._assert_hrms_permission(
                request,
                entity_id=application.entity_id,
                permission_key="leave_application_cancel",
                label="cancel leave applications",
            )
        cancelled = LeaveApplicationService.cancel_application(
            application=application,
            actor_id=request.user.id,
            manager_note=str(request.data.get("manager_note") or ""),
        )
        return Response(LeaveApplicationSerializer(cancelled).data)
