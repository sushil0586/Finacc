from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from Authentication.models import User
from entity.models import EntityEmploymentProfile


class EntityEmploymentProfileSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    business_unit_name = serializers.CharField(source="business_unit.name", read_only=True, allow_null=True)
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)
    work_location_name = serializers.CharField(source="work_location.name", read_only=True, allow_null=True)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, allow_null=True)
    grade_name = serializers.CharField(source="grade.name", read_only=True, allow_null=True)
    designation_name = serializers.CharField(source="designation.name", read_only=True, allow_null=True)
    manager_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    employment_type_label = serializers.CharField(source="get_employment_type_display", read_only=True)
    work_type_label = serializers.CharField(source="get_work_type_display", read_only=True)
    exit_status_label = serializers.CharField(source="get_exit_status_display", read_only=True)

    class Meta:
        model = EntityEmploymentProfile
        fields = [
            "id",
            "entity",
            "entity_name",
            "subentity",
            "subentity_name",
            "employee_user",
            "employee_code",
            "full_name",
            "work_email",
            "business_unit",
            "business_unit_name",
            "department",
            "department_name",
            "work_location",
            "work_location_name",
            "cost_center",
            "cost_center_name",
            "grade",
            "grade_name",
            "designation",
            "designation_name",
            "manager_user",
            "manager_name",
            "employment_type",
            "employment_type_label",
            "work_type",
            "work_type_label",
            "status",
            "status_label",
            "effective_from",
            "effective_to",
            "date_of_joining",
            "probation_end",
            "confirmation_date",
            "last_working_day",
            "separation_reason",
            "exit_status",
            "exit_status_label",
            "metadata",
        ]

    def get_manager_name(self, obj):
        if not obj.manager_user_id:
            return None
        first_name = (obj.manager_user.first_name or "").strip()
        last_name = (obj.manager_user.last_name or "").strip()
        full_name = f"{first_name} {last_name}".strip()
        return full_name or obj.manager_user.email

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        entity = attrs.get("entity") or getattr(instance, "entity", None)
        subentity = attrs.get("subentity", getattr(instance, "subentity", None))
        employee_user = attrs.get("employee_user", getattr(instance, "employee_user", None))
        manager_user = attrs.get("manager_user", getattr(instance, "manager_user", None))

        if employee_user and not isinstance(employee_user, User):
            raise serializers.ValidationError({"employee_user": "Employee user is invalid."})
        if manager_user and not isinstance(manager_user, User):
            raise serializers.ValidationError({"manager_user": "Manager user is invalid."})
        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if manager_user and employee_user and manager_user.id == employee_user.id:
            raise serializers.ValidationError({"manager_user": "Employee cannot be their own manager."})

        return attrs

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.message_dict if hasattr(err, "message_dict") else {"detail": err.messages})

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.message_dict if hasattr(err, "message_dict") else {"detail": err.messages})


class EntityEmploymentManagerSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)
    designation_name = serializers.CharField(source="designation.name", read_only=True, allow_null=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = EntityEmploymentProfile
        fields = [
            "id",
            "employee_user",
            "employee_code",
            "full_name",
            "work_email",
            "department_name",
            "designation_name",
            "subentity_name",
            "manager_user",
            "manager_name",
        ]

    def get_manager_name(self, obj):
        if not obj.manager_user_id:
            return None
        first_name = (obj.manager_user.first_name or "").strip()
        last_name = (obj.manager_user.last_name or "").strip()
        full_name = f"{first_name} {last_name}".strip()
        return full_name or obj.manager_user.email


class EntityEmploymentHierarchyNodeSerializer(EntityEmploymentManagerSerializer):
    status = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta(EntityEmploymentManagerSerializer.Meta):
        fields = EntityEmploymentManagerSerializer.Meta.fields + [
            "status",
            "status_label",
        ]


class EntityEmploymentHierarchySerializer(serializers.Serializer):
    employee_user = serializers.IntegerField()
    employee_code = serializers.CharField()
    full_name = serializers.CharField()
    chain = serializers.ListField(child=serializers.DictField())
    depth = serializers.IntegerField()
