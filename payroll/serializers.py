from rest_framework import serializers
from payroll.models import salarycomponent,employeesalary,salarytrans,EmployeePayrollComponent,EntityPayrollComponentConfig,employeenew, CalculationType, BonusFrequency, CalculationValue, ComponentType,PayrollComponent
from Authentication.serializers import Registerserializers
from Authentication.models import User
from django.contrib.auth.hashers import make_password
from typing import Any, Dict, Optional
from payroll.models import ComponentFamily, PayrollComponent,EntityPayrollComponent
from entity.models import Entity
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q,OneToOneField, ForeignKey
from .models import PayStructure, PayStructureComponent
from django.db import transaction
from django.apps import apps
from payroll.models import (
    OptionSet, Option,
    BusinessUnit, Department, Location, CostCenter,GradeBand, Designation
)

from rest_framework import serializers as _s
from payroll.models import (
Employee,
EmploymentAssignment,
EmployeeBankAccount,
EmployeeDocument,
EmployeeStatutoryIN,
EmployeeCompensation
)

from django.db.models import Model


class salarycomponentserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = salarycomponent
        fields = ('id','salarycomponentname','salarycomponentcode','componentperiod','componenttype','defaultpercentage','entity','createdby','calculationtype',)

# class employeeserializer(serializers.ModelSerializer):

#     employee = Registerserializers(many=False)

    


#     def create(self, validated_data):
#         #print(validated_data)
#         emp = validated_data.pop('employee')
#         emp.pop('id')

#         try:
            
#             employeeid = User.objects.create(**emp)
#         except Exception as e:
#             error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
#             raise serializers.ValidationError(error)
        
        

#         id = employee.objects.create(employee = employeeid,**validated_data)

#         return id
    
#     def update(self, instance, validated_data):

#         fields = ['entity','createdby','employeeid','dateofjoining','department','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city','isactive',]
#         for field in fields:
#             try:
#                 setattr(instance, field, validated_data[field])
#             except KeyError:  # validated_data may not contain all fields during HTTP PATCH
#                 pass
        
#         instance.save()

#         emp = validated_data.pop('employee')

#         id = emp.pop('id')

#        # print(email)

#         password = emp.pop('password')
#         password = make_password(password)

#         print(emp)

#         try:
#             employeeid = User.objects.filter(id = id).update(**emp,password=password)

#             return instance
        
#         except Exception as e:
#             error = {'message': ",".join(e.args) if len(e.args) > 0 else 'Unknown Error'}
#             raise serializers.ValidationError(error)

        







#     #id = serializers.IntegerField()
#     class Meta:
#         model = employee
#         fields = ('employee','employeeid','dateofjoining','department','entity','createdby','designation','reportingmanager','bankname','bankaccountno','pan','address1','address2','country','state','district','city','isactive',)
#         #depth = 1




class employeesalaryserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = employeesalary
        fields = ('id','employee','scomponent','percentageofctc','salaryvalue','entity','createdby','isactive',)


class salarytransserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = salarytrans
        fields = ('id','salaryamountexpected','salaryamountactual','percentageofctc','salaryvalue','entity','createdby','isactive',)





class reportingmanagerserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = User
        fields = ('id','first_name',)



# class employeeListSerializer(serializers.ModelSerializer):



#     employeeid = serializers.IntegerField(source = 'employee')
#     email =  serializers.CharField(max_length=500,source = 'employee__email')
#     #caccountheadname =  serializers.CharField(max_length=500,source = 'creditaccounthead__name')
  

    

    




    

#     class Meta:
#         model = employee
#         fields =  ('employeeid','email',)


# class employeeListfullSerializer(serializers.ModelSerializer):



#     employeeid = serializers.IntegerField(source = 'employee')
#     email =  serializers.CharField(max_length=500,source = 'employee__email')
#     firstname =  serializers.CharField(max_length=500,source = 'employee__first_name')
#     lastname =  serializers.CharField(max_length=500,source = 'employee__last_name')
#     employee_id =  serializers.CharField(max_length=500,source = 'employeeid')
#     #caccountheadname =  serializers.CharField(max_length=500,source = 'creditaccounthead__name')
  

    

    




    

#     class Meta:
#         model = employee
#         fields =  ('employeeid','email','firstname','lastname','employee_id',)


class EmployeePayrollComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeePayrollComponent
        fields = [
            'id', 'component', 'default_value', 'is_opted_in',
            'overridden_value', 'final_value'
        ]


    

class EntityPayrollComponentConfigSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='component.id')
    name = serializers.CharField(source='component.name')
    componenttype = serializers.CharField(source='component.component_type.name')

    class Meta:
        model = EntityPayrollComponentConfig
        fields = ['id', 'name', 'default_value','componenttype', 'min_value', 'max_value']



class CalculationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationType
        fields = '__all__'

class BonusFrequencySerializer(serializers.ModelSerializer):
    class Meta:
        model = BonusFrequency
        fields = '__all__'

class CalculationValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationValue
        fields = '__all__'

class ComponentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentType
        fields = '__all__'


class EntityPayrollComponentConfigSerializerlist(serializers.ModelSerializer):
    class Meta:
        model = EntityPayrollComponentConfig
        fields = ['id', 'entity', 'default_value', 'selected_amount', 'min_value', 'max_value', 'is_active']


class PayrollComponentSerializer(serializers.ModelSerializer):
    configs = EntityPayrollComponentConfigSerializerlist(many=True, write_only=True)

    class Meta:
        model = PayrollComponent
        fields = [
            'id', 'name', 'code', 'component_type', 'calculation_type',
            'is_taxable', 'is_mandatory', 'is_basic', 'entity',
            'bonus_frequency', 'formula_expression', 'configs'
        ]

    def create(self, validated_data):
        configs_data = validated_data.pop('configs', [])
        component = PayrollComponent.objects.create(**validated_data)
        for config_data in configs_data:
            EntityPayrollComponentConfig.objects.create(component=component, **config_data)
        return component

    def update(self, instance, validated_data):
        configs_data = validated_data.pop('configs', [])

        # Update parent fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        existing_ids = []
        incoming_ids = []

        for config_data in configs_data:
            config_id = config_data.get('id', 0)
            if config_id:
                try:
                    config_instance = EntityPayrollComponentConfig.objects.get(id=config_id, component=instance)
                    for attr, value in config_data.items():
                        if attr != 'id':
                            setattr(config_instance, attr, value)
                    config_instance.save()
                    incoming_ids.append(config_id)
                except EntityPayrollComponentConfig.DoesNotExist:
                    continue  # Skip invalid id
            else:
                new_config = EntityPayrollComponentConfig.objects.create(component=instance, **config_data)
                incoming_ids.append(new_config.id)

        # Delete records not present in incoming data
        existing_ids = list(
            EntityPayrollComponentConfig.objects.filter(component=instance).values_list('id', flat=True)
        )
        to_delete = set(existing_ids) - set(incoming_ids)
        EntityPayrollComponentConfig.objects.filter(id__in=to_delete).delete()

        return instance
    

class EntityPayrollComponentSerializer(serializers.ModelSerializer):
    """
    - family by code (slug)
    - entity by PK (or switch to code via commented line)
    - optional pinned 'component' (global version) by PK
    - global_snapshot read-only for UI guardrails
    """

    # If you prefer entity by code, replace the next line with the commented one.
    entity = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())
    # entity = serializers.SlugRelatedField(slug_field="code", queryset=Entity.objects.all())

    family = serializers.SlugRelatedField(
        slug_field="code",
        queryset=ComponentFamily.objects.all()
    )

    # Optional: pin to a specific global version
    component = serializers.PrimaryKeyRelatedField(
        queryset=PayrollComponent.objects.all(),
        allow_null=True, required=False
    )

    # Extras for convenience in responses
    family_code = serializers.CharField(source="family.code", read_only=True)
    entity_display = serializers.StringRelatedField(source="entity", read_only=True)

    global_snapshot = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = EntityPayrollComponent
        fields = [
            "id",
            # identity / links
            "entity", "entity_display",
            "family", "family_code",
            "component",            # optional pinned version
            "enabled",
            # dates
            "effective_from", "effective_to",
            # method-aware defaults
            "default_percent", "default_amount", "param_overrides", "slab_scope_value",
            # employee override policy
            "allow_emp_override", "emp_min_percent", "emp_max_percent",
            # misc
            "notes",
            # read-only
            "global_snapshot",
            "created_at", "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    # ---- cross-field validation (pinned component sanity) ----
    def validate(self, attrs):
        instance = self.instance
        family = attrs.get("family") or (instance.family if instance else None)
        component = attrs.get("component") if "component" in attrs else (instance.component if instance else None)
        eff_from = attrs.get("effective_from") or (instance.effective_from if instance else None)

        if component is not None:
            # 1) family match
            if family and component.family_id != family.id:
                raise serializers.ValidationError({"component": "Pinned component does not belong to the selected family."})
            # 2) date coverage (use effective_from as anchor)
            if eff_from and not (component.effective_from <= eff_from <= (component.effective_to or eff_from)):
                raise serializers.ValidationError({"component": "Pinned component is not active on the entity's effective_from date."})
        return attrs

    # ---- ensure model.clean() runs (overlaps, method rules, bands, etc.) ----
    def create(self, validated_data):
        obj = EntityPayrollComponent(**validated_data)
        try:
            obj.full_clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        try:
            instance.full_clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        instance.save()
        return instance

    # ---- global snapshot for UI ----
    def get_global_snapshot(self, obj: EntityPayrollComponent) -> Optional[Dict[str, Any]]:
        as_of = (self.context or {}).get("as_of_date")
        g: Optional[PayrollComponent] = obj.resolve_global_version(as_of_date=as_of)
        if not g:
            return None

        caps = []
        for c in g.caps.all().order_by("sort_order", "id"):
            item = {
                "cap_type": c.cap_type,
                "cap_basis": c.cap_basis,
                "cap_value": str(c.cap_value),
                "periodicity": c.periodicity,
            }
            if c.conditions: item["conditions"] = c.conditions
            if c.notes: item["notes"] = c.notes
            caps.append(item)

        slab_group = None
        if g.slab_group_id:
            slab_group = {
                "group_key": g.slab_group.group_key,
                "name": g.slab_group.name,
                "type": g.slab_group.type,
            }

        return {
            "code": g.code,
            "name": g.name,
            "type": g.type,
            "calc_method": g.calc_method,
            "frequency": g.frequency,
            "rounding": g.rounding,
            "priority": g.priority,
            "is_proratable": g.is_proratable,

            "percent_basis": g.percent_basis or None,
            "basis_cap_amount": str(g.basis_cap_amount) if g.basis_cap_amount is not None else None,
            "basis_cap_periodicity": g.basis_cap_periodicity or None,

            "slab_group": slab_group,
            "slab_base": g.slab_base or None,
            "slab_percent_basis": g.slab_percent_basis or None,
            "slab_scope_field": g.slab_scope_field or None,

            "formula_text": g.formula_text or None,
            "default_params": g.default_params or {},

            "policy_band": {
                "min_percent": float(g.policy_band_min_percent) if g.policy_band_min_percent is not None else None,
                "max_percent": float(g.policy_band_max_percent) if g.policy_band_max_percent is not None else None,
            },

            "taxability": g.taxability,
            "pf_include": g.pf_include,
            "esi_include": g.esi_include,
            "pt_include": g.pt_include,
            "lwf_include": g.lwf_include,

            "payslip_group": g.payslip_group,
            "display_order": g.display_order,
            "show_on_payslip": g.show_on_payslip,

            "effective_from": g.effective_from,
            "effective_to": g.effective_to,

            "caps": caps,
        }
    

class PayStructureComponentSerializer(serializers.ModelSerializer):
    family_code = serializers.CharField(source="family.code", read_only=True)
    template_code = serializers.CharField(source="template.code", read_only=True)

    class Meta:
        model = PayStructureComponent
        fields = [
            "id", "template", "template_code",
            "family", "family_code",
            "pinned_global_component",
            "enabled", "required", "priority",
            "default_percent", "default_amount", "param_overrides",
            "slab_scope_value",
            "allow_emp_override", "emp_min_percent", "emp_max_percent",
            "show_on_payslip", "display_order",
            "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayStructureSerializer(serializers.ModelSerializer):
    items = PayStructureComponentSerializer(many=True, read_only=True)

    class Meta:
        model = PayStructure
        fields = [
            "id", "code", "name", "entity",
            "effective_from", "effective_to",
            "status", "rounding", "proration_method",
            "notes", "items",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        code = (attrs.get("code") or getattr(self.instance, "code", "")).upper()
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        a1 = attrs.get("effective_from", getattr(self.instance, "effective_from", None))
        a2 = attrs.get("effective_to", getattr(self.instance, "effective_to", None))
        status = attrs.get("status", getattr(self.instance, "status", None))

        qs = PayStructure.objects.filter(code__iexact=code, entity=entity)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if a1:
            if qs.filter(
                Q(effective_to__isnull=True, effective_from__lte=a2 or a1)
                | Q(effective_to__isnull=False, effective_from__lte=a2 or a1, effective_to__gte=a1)
            ).exists():
                raise serializers.ValidationError("Overlapping effective dates for this code & entity.")

        if status == PayStructure.Status.ACTIVE:
            if qs.filter(status=PayStructure.Status.ACTIVE).filter(
                Q(effective_to__isnull=True, effective_from__lte=a2 or a1)
                | Q(effective_to__isnull=False, effective_from__lte=a2 or a1, effective_to__gte=a1)
            ).exists():
                raise serializers.ValidationError("Another ACTIVE PayStructure overlaps this window.")

        attrs["code"] = code
        return attrs
    


class PayStructureComponentReadSerializer(serializers.ModelSerializer):
    family_code = serializers.CharField(source="family.code", read_only=True)
    template_code = serializers.CharField(source="template.code", read_only=True)

    # Optional: include the resolved global definition as of a date
    resolved_global = serializers.SerializerMethodField()

    class Meta:
        model = PayStructureComponent
        fields = [
            "id",
            "template", "template_code",
            "family", "family_code",
            "pinned_global_component",
            "enabled", "required", "priority",
            "default_percent", "default_amount", "param_overrides",
            "slab_scope_value",
            "allow_emp_override", "emp_min_percent", "emp_max_percent",
            "show_on_payslip", "display_order",
            "notes",
            "resolved_global",            # ← computed
            "created_at", "updated_at",
        ]
        read_only_fields = fields  # this is a read serializer

    def get_resolved_global(self, obj):
        """
        Resolve the PayrollComponentGlobal either by pin or by (family, as_of date).
        The 'as_of' date can be passed via serializer context: {'as_of': date(..)}.
        Fallback: template.effective_from.
        """
        as_of = self.context.get("as_of") or obj.template.effective_from

        # Use pinned if present; else resolve by date
        g = obj.pinned_global_component
        if not g:
            PCG = apps.get_model(obj._meta.app_label, "PayrollComponentGlobal")
            g = (PCG.objects
                 .filter(family=obj.family, effective_from__lte=as_of)
                 .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
                 .order_by("-effective_from")
                 .first())
        if not g:
            return None

        # Core fields (safe across your model)
        data = {
            "id": g.id,
            "family_id": g.family_id,
            "calc_method": g.calc_method,
            "effective_from": g.effective_from,
            "effective_to": g.effective_to,
            "policy_band_min_percent": getattr(g, "policy_band_min_percent", None),
            "policy_band_max_percent": getattr(g, "policy_band_max_percent", None),
        }

        # Helpful optional extras (only if present on your model)
        if hasattr(g, "percent_basis"):
            data["percent_basis"] = g.percent_basis
        if hasattr(g, "slab_group_id"):
            data["slab_group_id"] = g.slab_group_id
        if hasattr(g, "default_params"):
            data["default_params"] = g.default_params

        return data


class PayStructureReadSerializer(serializers.ModelSerializer):
    """
    Detailed read: header + nested items (each item includes resolved_global).
    Pass {'as_of': date} in context to control resolution date; otherwise uses effective_from.
    """
    items = PayStructureComponentReadSerializer(many=True, read_only=True)

    scope_label = serializers.SerializerMethodField()

    class Meta:
        model = PayStructure
        fields = [
            "id", "code", "name", "entity",
            "effective_from", "effective_to",
            "status", "rounding", "proration_method",
            "notes",
            "scope_label",     # GLOBAL or entity id
            "items",           # nested with resolved_global
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_scope_label(self, obj):
        return "GLOBAL" if obj.entity_id is None else str(obj.entity_id)


class PayStructureListReadSerializer(serializers.ModelSerializer):
    """
    Lightweight list view (no nested items), handy for index/list endpoints.
    """
    scope_label = serializers.SerializerMethodField()

    class Meta:
        model = PayStructure
        fields = [
            "id", "code", "name", "entity",
            "effective_from", "effective_to",
            "status",
            "scope_label",
            "updated_at",
        ]
        read_only_fields = fields

    def get_scope_label(self, obj):
        return "GLOBAL" if obj.entity_id is None else str(obj.entity_id)
    


class PayStructureComponentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayStructureComponent
        fields = [
            "family",
            "pinned_global_component",
            "enabled", "required", "priority",
            "default_percent", "default_amount", "param_overrides",
            "slab_scope_value",
            "allow_emp_override", "emp_min_percent", "emp_max_percent",
            "show_on_payslip", "display_order",
            "notes",
        ]

class PayStructureNestedCreateSerializer(serializers.ModelSerializer):
    items = PayStructureComponentCreateSerializer(many=True, write_only=True)

    class Meta:
        model = PayStructure
        fields = [
            "code", "name", "entity",
            "effective_from", "effective_to",
            "status", "rounding", "proration_method",
            "notes",
            "items",
        ]

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items", [])
        header = PayStructure.objects.create(**validated_data)

        # guard: duplicate families in payload
        fam_ids = [i["family"].id for i in items]
        if len(fam_ids) != len(set(fam_ids)):
            raise serializers.ValidationError({"items": "Duplicate family in items."})

        created = []
        for payload in items:
            obj = PayStructureComponent(template=header, **payload)
            obj.full_clean()  # run model validation (method-specific checks)
            obj.save()
            created.append(obj.id)

        return header
    

class OptionSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OptionSet
        fields = ["id", "key", "entity"]  # add created/modified if you want

class OptionSerializer(serializers.ModelSerializer):
    # expose related info read-only
    set_key = serializers.CharField(source="set.key", read_only=True)
    set_entity = serializers.IntegerField(source="set.entity_id", read_only=True)

    class Meta:
        model = Option
        fields = [
            "id",
            # "set",         # PK of OptionSet (writable)
            "set_key",     # read-only
            "set_entity",  # read-only
            "code",
            "label",
            # "sort_order",
            # "is_active",
            # "extra",
        ]
        read_only_fields = ["id"]

class BusinessUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessUnit
        fields = ["id", "name", "entity"]

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "entity"]

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "entity"]

class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = ["id", "name", "entity"]


class GradeBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeBand
        fields = ["id", "entity", "code", "name", "level", "min_ctc", "max_ctc", "created", "modified"]
        read_only_fields = ["id", "created", "modified"]

class DesignationSerializer(serializers.ModelSerializer):
    grade_band_code = serializers.CharField(source="grade_band.code", read_only=True)

    class Meta:
        model = Designation
        fields = ["id", "entity", "name", "grade_band", "grade_band_code", "parent", "created", "modified"]
        read_only_fields = ["id", "created", "modified"]

    def validate(self, attrs):
        entity = attrs.get("entity") or (self.instance.entity if self.instance else None)
        gb = attrs.get("grade_band") or (self.instance.grade_band if self.instance else None)
        if gb and entity and gb.entity_id != entity.id:
            raise serializers.ValidationError("grade_band.entity must match designation.entity")
        return attrs


# ---- child serializers ----
class EmploymentAssignmentSerializer(_s.ModelSerializer):
    id = _s.IntegerField(required=False)
    class Meta:
        model = EmploymentAssignment
        fields = "__all__"
        extra_kwargs = {"employee": {"read_only": True}}

class EmployeeBankAccountSerializer(_s.ModelSerializer):
    id = _s.IntegerField(required=False)
    class Meta:
        model = EmployeeBankAccount
        fields = "__all__"
        extra_kwargs = {"employee": {"read_only": True}}

class EmployeeDocumentSerializer(_s.ModelSerializer):
    id = _s.IntegerField(required=False)
    class Meta:
        model = EmployeeDocument
        fields = "__all__"
        extra_kwargs = {"employee": {"read_only": True}}

class EmployeeCompensationSerializer(_s.ModelSerializer):
    id = _s.IntegerField(required=False)
    class Meta:
        model = EmployeeCompensation
        fields = "__all__"
        extra_kwargs = {"employee": {"read_only": True}}

class EmployeeStatutoryINSerializer(_s.ModelSerializer):
    # One-to-one: no "many=True" here
    class Meta:
        model = EmployeeStatutoryIN
        fields = "__all__"
        extra_kwargs = {"employee": {"read_only": True}}

def _coerce_pks_in_item(item: dict):
    """Convert any model instance or {'id': <pk>} to a plain pk in-place."""
    for k, v in list(item.items()):
        if isinstance(v, Model):
            item[k] = v.pk
        elif isinstance(v, dict) and "id" in v and isinstance(v["id"], (int, str)):
            item[k] = v["id"]

# ---- employee (nested) ----
class EmployeeSerializer(_s.ModelSerializer):
    # names match your related_name's → DO NOT pass source=
    assignments   = EmploymentAssignmentSerializer(many=True, required=False)
    bank_accounts = EmployeeBankAccountSerializer(many=True, required=False)
    documents     = EmployeeDocumentSerializer(many=True, required=False)
    compensations = EmployeeCompensationSerializer(many=True, required=False)
    statutory_in  = EmployeeStatutoryINSerializer(required=False, allow_null=True)

    class Meta:
        model = Employee
        fields = "__all__"

    # helpers
    def _upsert_many(self, *, parent, items, qs, serializer_class, fk_name="employee", partial=False):
        existing = {obj.id: obj for obj in qs}
        seen = set()
        for item in (items or []):
            _coerce_pks_in_item(item)              # normalize other FKs
            item.pop(fk_name, None)                # <-- don't let incoming data carry 'employee'
            item_id = item.get("id")

            if item_id and item_id in existing:
                inst = existing[item_id]
                ser = serializer_class(inst, data=item, partial=partial)
                ser.is_valid(raise_exception=True)
                ser.save(**{fk_name: parent})      # <-- attach FK here
                seen.add(item_id)
            else:
                item.pop("id", None)
                ser = serializer_class(data=item)
                ser.is_valid(raise_exception=True)
                ser.save(**{fk_name: parent})      # <-- attach FK here

        if not partial:
            for cid, inst in existing.items():
                if cid not in seen:
                    inst.delete()

    def _upsert_one(self, *, parent, item, attr_name, serializer_class, fk_name="employee", partial=False):
        """For OneToOne (statutory_in)."""
        if item is None:
            return
        _coerce_pks_in_item(item)
        item.pop(fk_name, None)                     # incoming data must not carry 'employee'

        # read existing O2O instance if present
        try:
            inst = getattr(parent, attr_name)
        except serializer_class.Meta.model.DoesNotExist:
            inst = None

        if inst:
            ser = serializer_class(inst, data=item, partial=partial)
        else:
            ser = serializer_class(data=item)
        ser.is_valid(raise_exception=True)
        ser.save(**{fk_name: parent})               # <-- attach FK here

    # create / update
    def create(self, validated_data):
        assignments   = validated_data.pop("assignments",   [])
        bank_accounts = validated_data.pop("bank_accounts", [])
        documents     = validated_data.pop("documents",     [])
        compensations = validated_data.pop("compensations", [])
        statutory_in  = validated_data.pop("statutory_in",  None)

        emp = Employee.objects.create(**validated_data)

        self._upsert_many(parent=emp, items=assignments,   qs=emp.assignments.all(),
                        serializer_class=EmploymentAssignmentSerializer, fk_name="employee")
        self._upsert_many(parent=emp, items=bank_accounts, qs=emp.bank_accounts.all(),
                        serializer_class=EmployeeBankAccountSerializer, fk_name="employee")
        self._upsert_many(parent=emp, items=documents,     qs=emp.documents.all(),
                        serializer_class=EmployeeDocumentSerializer, fk_name="employee")
        self._upsert_many(parent=emp, items=compensations, qs=emp.compensations.all(),
                        serializer_class=EmployeeCompensationSerializer, fk_name="employee")
        self._upsert_one (parent=emp, item=statutory_in,   attr_name="statutory_in",
                        serializer_class=EmployeeStatutoryINSerializer, fk_name="employee")
        return emp

    def update(self, instance, validated_data):
        partial = getattr(self, "partial", False)
        assignments   = validated_data.pop("assignments",   None)
        bank_accounts = validated_data.pop("bank_accounts", None)
        documents     = validated_data.pop("documents",     None)
        compensations = validated_data.pop("compensations", None)
        statutory_in  = validated_data.pop("statutory_in",  None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if assignments is not None:
            self._upsert_many(parent=instance, items=assignments, qs=instance.assignments.all(),
                            serializer_class=EmploymentAssignmentSerializer, fk_name="employee", partial=partial)
        if bank_accounts is not None:
            self._upsert_many(parent=instance, items=bank_accounts, qs=instance.bank_accounts.all(),
                            serializer_class=EmployeeBankAccountSerializer, fk_name="employee", partial=partial)
        if documents is not None:
            self._upsert_many(parent=instance, items=documents, qs=instance.documents.all(),
                            serializer_class=EmployeeDocumentSerializer, fk_name="employee", partial=partial)
        if compensations is not None:
            self._upsert_many(parent=instance, items=compensations, qs=instance.compensations.all(),
                            serializer_class=EmployeeCompensationSerializer, fk_name="employee", partial=partial)
        if statutory_in is not None:
            self._upsert_one(parent=instance, item=statutory_in, attr_name="statutory_in",
                            serializer_class=EmployeeStatutoryINSerializer, fk_name="employee", partial=partial)
        return instance
    

class ManagerListItemSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = Employee
        fields = ["id", "full_name", "display_name", "code"]
        read_only_fields = fields


