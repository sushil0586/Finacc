from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from hrms.models import (
    AttendancePolicy,
    AttendanceApproval,
    AttendanceDeviceLog,
    AttendanceImportBatch,
    AttendanceMonthlyClose,
    ContractLeaveBalanceSnapshot,
    ContractLeaveLedgerEntry,
    DailyAttendance,
    GlobalAttendancePolicyTemplate,
    GlobalHolidayCalendarTemplate,
    GlobalHRPolicyTemplate,
    GlobalLeavePolicyRuleTemplate,
    GlobalLeavePolicyTemplate,
    GlobalLeaveType,
    GlobalShiftTemplate,
    HRPolicy,
    HrEmployee,
    HrEmploymentContract,
    HrHoliday,
    HrHolidayCalendar,
    HrOrganizationUnit,
    HrShift,
    LeavePolicy,
    LeavePolicyRule,
    LeaveApplication,
    LeaveType,
)


class HrOrganizationUnitSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)

    class Meta:
        model = HrOrganizationUnit
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class HrEmployeeSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)

    class Meta:
        model = HrEmployee
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class HrEmploymentContractSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    employee_display_name = serializers.CharField(source="employee.display_name", read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    business_unit_name = serializers.CharField(source="business_unit.name", read_only=True, allow_null=True)
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    designation_name = serializers.CharField(source="designation.name", read_only=True, allow_null=True)
    grade_name = serializers.CharField(source="grade.name", read_only=True, allow_null=True)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, allow_null=True)
    work_location_name = serializers.CharField(source="work_location.name", read_only=True, allow_null=True)
    reports_to_contract_code = serializers.CharField(source="reports_to_contract.contract_code", read_only=True, allow_null=True)
    default_shift_name = serializers.CharField(source="default_shift.name", read_only=True, allow_null=True)
    holiday_calendar_name = serializers.CharField(source="holiday_calendar.name", read_only=True, allow_null=True)

    class Meta:
        model = HrEmploymentContract
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class HrShiftSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)

    class Meta:
        model = HrShift
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class HrHolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = HrHoliday
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class HrHolidayCalendarSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    holidays = HrHolidaySerializer(many=True, read_only=True)

    class Meta:
        model = HrHolidayCalendar
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class LeavePolicyRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePolicyRule
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class LeavePolicySerializer(serializers.ModelSerializer):
    rules = LeavePolicyRuleSerializer(many=True, read_only=True)

    class Meta:
        model = LeavePolicy
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class AttendancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendancePolicy
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class AttendanceImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceImportBatch
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class AttendanceMonthlyCloseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceMonthlyClose
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class AttendanceApprovalSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True)
    employee_display_name = serializers.CharField(source="contract.employee.display_name", read_only=True)
    employee_number = serializers.CharField(source="contract.employee.employee_number", read_only=True)

    class Meta:
        model = AttendanceApproval
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class DailyAttendanceSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True)
    employee_display_name = serializers.CharField(source="contract.employee.display_name", read_only=True)
    employee_number = serializers.CharField(source="contract.employee.employee_number", read_only=True)
    leave_type_name = serializers.CharField(source="leave_application.leave_type.name", read_only=True, allow_null=True)

    class Meta:
        model = DailyAttendance
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class AttendanceDeviceLogSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True, allow_null=True)

    class Meta:
        model = AttendanceDeviceLog
        fields = "__all__"


class HRPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = HRPolicy
        fields = "__all__"
        validators = []

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(getattr(err, "message_dict", {"detail": err.messages}))


class ContractLeaveBalanceSnapshotSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True)
    employee_display_name = serializers.CharField(source="contract.employee.display_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = ContractLeaveBalanceSnapshot
        fields = "__all__"


class ContractLeaveLedgerEntrySerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True)
    employee_display_name = serializers.CharField(source="contract.employee.display_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = ContractLeaveLedgerEntry
        fields = "__all__"


class LeaveApplicationSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract.contract_code", read_only=True)
    employee_display_name = serializers.CharField(source="contract.employee.display_name", read_only=True)
    employee_number = serializers.CharField(source="contract.employee.employee_number", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveApplication
        fields = "__all__"


class GlobalLeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalLeaveType
        fields = "__all__"


class GlobalLeavePolicyRuleTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalLeavePolicyRuleTemplate
        fields = "__all__"


class GlobalLeavePolicyTemplateSerializer(serializers.ModelSerializer):
    rules = GlobalLeavePolicyRuleTemplateSerializer(many=True, read_only=True)

    class Meta:
        model = GlobalLeavePolicyTemplate
        fields = "__all__"


class GlobalShiftTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalShiftTemplate
        fields = "__all__"


class GlobalHolidayCalendarTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalHolidayCalendarTemplate
        fields = "__all__"


class GlobalAttendancePolicyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalAttendancePolicyTemplate
        fields = "__all__"


class GlobalHRPolicyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalHRPolicyTemplate
        fields = "__all__"


class HrmsMetaSerializer(serializers.Serializer):
    organization_unit_types = serializers.ListField(child=serializers.DictField())
    organization_unit_statuses = serializers.ListField(child=serializers.DictField())
    employee_statuses = serializers.ListField(child=serializers.DictField())
    employee_genders = serializers.ListField(child=serializers.DictField())
    employee_marital_statuses = serializers.ListField(child=serializers.DictField())
    contract_statuses = serializers.ListField(child=serializers.DictField())
    contract_types = serializers.ListField(child=serializers.DictField())
    work_models = serializers.ListField(child=serializers.DictField())
    compensation_bases = serializers.ListField(child=serializers.DictField())
    shift_types = serializers.ListField(child=serializers.DictField())
    shift_statuses = serializers.ListField(child=serializers.DictField())
    holiday_calendar_statuses = serializers.ListField(child=serializers.DictField())
    holiday_types = serializers.ListField(child=serializers.DictField())
    onboarding_industry_options = serializers.ListField(child=serializers.DictField(), required=False)
    onboarding_employee_category_options = serializers.ListField(child=serializers.DictField(), required=False)
