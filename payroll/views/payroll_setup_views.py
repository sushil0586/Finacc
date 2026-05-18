from __future__ import annotations

from django.db.models import Max, Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from hrms.models import HrEmploymentContract
from payroll.models import (
    ContractAttendanceSummary,
    ContractPayrollInputSnapshot,
    ContractStatutoryProfile,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    ContractTaxDeclaration,
    ContractTaxDeclarationLine,
    EntityPayrollPolicy,
    EntityStatutoryRegistration,
    OneTimePayItem,
    PayrollComponent,
    PayrollPolicyRule,
    PayrollPeriod,
    RecurringPayItem,
    PayrollRun,
    SalaryStructure,
    StatutoryRule,
    StatutoryScheme,
    StatutorySlab,
)
from payroll.serializers.payroll_setup_serializers import (
    ContractPayrollInputSnapshotSerializer,
    ContractStatutoryProfileSerializer,
    ContractPayrollProfileSerializer,
    ContractSalaryStructureAssignmentSerializer,
    ContractTaxDeclarationLineSerializer,
    ContractTaxDeclarationSerializer,
    EntityPayrollPolicySerializer,
    EntityStatutoryRegistrationSerializer,
    OneTimePayItemSerializer,
    PayrollComponentSerializer,
    PayrollPolicyRuleSerializer,
    PayrollPeriodSerializer,
    PayrollRuntimeReadinessPreviewRequestSerializer,
    RecurringPayItemSerializer,
    SalaryStructureSerializer,
    StatutoryRuleSerializer,
    StatutorySchemeSerializer,
    StatutorySlabSerializer,
)
from payroll.services import (
    ContractPayrollInputSnapshotService,
    ContractStatutoryProfileService,
    ContractPayrollProfileService,
    ContractSalaryAssignmentService,
    ContractTaxDeclarationService,
    EntityPayrollPolicyService,
    EntityStatutoryRegistrationService,
    OneTimePayItemService,
    PayrollPermissionService,
    PayrollPolicyRuleService,
    PayrollRolloutValidationService,
    PayrollSetupService,
    PayrollRunReadinessResolverService,
    RecurringPayItemService,
    StatutoryRuleService,
    StatutorySchemeService,
    StatutorySlabService,
)
from payroll.views.scoped import PayrollScopedAPIView


def _permission_denied(message: str):
    raise PermissionDenied(detail=message)


def _assert_access(request, *, groups: set[str], permissions_required: set[str], label: str) -> None:
    try:
        PayrollPermissionService.assert_named_access(
            user=request.user,
            groups=groups,
            permissions=permissions_required,
            label=label,
        )
    except PermissionError as err:
        _permission_denied(str(err))


class PayrollSetupQuerysetMixin:
    scope_fields = ("entity", "entityfinid", "subentity")

    def filter_scope(self, qs):
        for field in self.scope_fields:
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{f"{field}_id": value})
        return qs


class PayrollSetupScopedAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def _assert_setup_permission(self, request, *, entity_id: int, permission_key: str, label: str, legacy_groups: set[str], legacy_permissions: set[str]):
        if PayrollPermissionService.has_entity_permission_access(user=request.user, entity_id=entity_id, permission_key=permission_key):
            self.enforce_scope(request, entity_id=entity_id)
            return
        _assert_access(request, groups=legacy_groups, permissions_required=legacy_permissions, label=label)
        self.enforce_scope(request, entity_id=entity_id)


class PayrollRuntimeReadinessPreviewAPIView(PayrollSetupScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        serializer = PayrollRuntimeReadinessPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity_id, _, _ = self._scope_from_payload(request, {"entity": payload["entity"]})
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="runtime_readiness_view",
            label="view payroll runtime readiness",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )

        contracts = HrEmploymentContract.objects.select_related("employee").filter(
            entity_id=entity_id,
            is_payroll_eligible=True,
        )
        contract_ids = payload.get("contract_ids") or []
        if contract_ids:
            contracts = contracts.filter(id__in=contract_ids)
        results = [
            PayrollRunReadinessResolverService.resolve_contract_readiness(
                contract=contract,
                payroll_date=payload["payroll_date"],
            )
            for contract in contracts.order_by("contract_code")
        ]
        summaries = [item.to_summary() for item in results]
        counts = {
            "total": len(summaries),
            "ready": sum(1 for item in summaries if item["readiness_status"] == "READY"),
            "warning": sum(1 for item in summaries if item["readiness_status"] == "WARNING"),
            "blocked": sum(1 for item in summaries if item["readiness_status"] == "BLOCKED"),
        }
        return Response(
            {
                "entity": entity_id,
                "payroll_date": payload["payroll_date"].isoformat(),
                "counts": counts,
                "results": summaries,
            }
        )


class PayrollPeriodListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = PayrollPeriodSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "pay_frequency"]
    search_fields = ["code"]

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = PayrollPeriod.objects.select_related("entity", "entityfinid", "subentity", "locked_by", "closed_by").filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return self.filter_scope(qs).order_by("-period_start", "-id")

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="period_view",
            label="view payroll periods",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollperiod"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data, require_entityfinid=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="period_create",
            label="create payroll periods",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.add_payrollperiod"},
        )
        return super().post(request, *args, **kwargs)


class PayrollPeriodRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = PayrollPeriodSerializer

    def get_queryset(self):
        return PayrollPeriod.objects.select_related("entity", "entityfinid", "subentity", "locked_by", "closed_by")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="period_view",
            label="view payroll periods",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollperiod"},
        )
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="period_edit",
            label="edit payroll periods",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollperiod"},
        )
        return super().patch(request, *args, **kwargs)


class PayrollPeriodActionAPIView(PayrollSetupScopedAPIView):

    ACTION_LABELS = {"open": "opened", "close": "closed", "lock": "locked"}

    def post(self, request, pk: int, action: str):
        period = PayrollPeriod.objects.select_related("locked_by", "closed_by").get(pk=pk)
        self._enforce_object_scope(request, period)
        self._assert_setup_permission(
            request,
            entity_id=period.entity_id,
            permission_key="period_edit",
            label=f"{action} payroll periods",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollperiod"},
        )
        note = request.data.get("note", "") if isinstance(request.data, dict) else ""
        try:
            period = PayrollSetupService.transition_period(period=period, action=action, user=request.user, note=note)
        except Exception as err:
            raise ValidationError({"detail": str(err)})
        return Response(
            {
                "message": f"Payroll period {self.ACTION_LABELS.get(action, action)} successfully.",
                "data": PayrollPeriodSerializer(period).data,
            }
        )


class PayrollComponentListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = PayrollComponentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "component_type", "is_active", "is_statutory"]
    search_fields = ["code", "name", "description"]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        return self.filter_scope(PayrollComponent.objects.select_related("entity").filter(entity_id=entity_id)).order_by("default_sequence", "code")

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="component_view",
            label="view payroll components",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollcomponent"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="component_create",
            label="create payroll components",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.add_payrollcomponent"},
        )
        return super().post(request, *args, **kwargs)


class PayrollComponentRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = PayrollComponentSerializer

    def get_queryset(self):
        return PayrollComponent.objects.select_related("entity")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="component_view",
            label="view payroll components",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollcomponent"},
        )
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="component_edit",
            label="edit payroll components",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_payrollcomponent"},
        )
        return super().patch(request, *args, **kwargs)


class SalaryStructureListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = SalaryStructureSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "is_active", "is_template"]
    search_fields = ["code", "name", "notes"]

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        return self.filter_scope(
            SalaryStructure.objects.select_related("entity", "entityfinid", "subentity", "current_version").prefetch_related("current_version__lines", "versions").filter(entity_id=entity_id)
        ).order_by("code")

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="structure_view",
            label="view salary structures",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_salarystructure"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="structure_create",
            label="create salary structures",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.add_salarystructure"},
        )
        return super().post(request, *args, **kwargs)


class SalaryStructureRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = SalaryStructureSerializer

    def get_queryset(self):
        return SalaryStructure.objects.select_related("entity", "entityfinid", "subentity", "current_version").prefetch_related("current_version__lines", "versions")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="structure_view",
            label="view salary structures",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_salarystructure"},
        )
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="structure_edit",
            label="edit salary structures",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_salarystructure"},
        )
        return super().patch(request, *args, **kwargs)


class ContractPayrollProfileListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = ContractPayrollProfileSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "payroll_status", "pay_frequency", "is_active", "hrms_contract"]
    search_fields = ["hrms_contract__contract_code", "hrms_contract__employee__employee_number", "hrms_contract__employee__display_name"]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, subentity_id = self._scope_from_query(self.request, require_entity=True)
        return ContractPayrollProfileService.list_profiles(
            entity_id=entity_id,
            subentity_id=subentity_id,
            search=self.request.query_params.get("search"),
            payroll_status=self.request.query_params.get("payroll_status"),
            pay_frequency=self.request.query_params.get("pay_frequency"),
            is_active=None if self.request.query_params.get("is_active") in (None, "") else self.request.query_params.get("is_active") == "true",
            hrms_contract_id=self.request.query_params.get("hrms_contract"),
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_view",
            label="view contract payroll profiles",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_create",
            label="create contract payroll profiles",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.add_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = ContractPayrollProfileService.create_or_update_profile(serializer.validated_data)
        except ValueError as err:
            raise ValidationError({"detail": str(err)})
        output = self.get_serializer(profile)
        return Response(output.data, status=201)


class ContractPayrollProfileRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractPayrollProfileSerializer

    def get_queryset(self):
        return ContractPayrollProfile.objects.select_related("entity", "hrms_contract", "hrms_contract__employee", "bank_account")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_view",
            label="view contract payroll profiles",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_edit",
            label="edit contract payroll profiles",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = ContractPayrollProfileService.create_or_update_profile(serializer.validated_data, instance=obj)
        except ValueError as err:
            raise ValidationError({"detail": str(err)})
        return Response(self.get_serializer(profile).data)


class ContractSalaryAssignmentListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = ContractSalaryStructureAssignmentSerializer

    def get_contract_profile(self):
        profile = ContractPayrollProfile.objects.select_related("entity").get(pk=self.kwargs["pk"])
        self._enforce_object_scope(self.request, profile)
        return profile

    def get_queryset(self):
        profile = self.get_contract_profile()
        return ContractSalaryAssignmentService.list_assignments(contract_payroll_profile_id=str(profile.id))

    def get(self, request, *args, **kwargs):
        profile = self.get_contract_profile()
        self._assert_setup_permission(
            request,
            entity_id=profile.entity_id,
            permission_key="profile_view",
            label="view contract salary assignments",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        profile = self.get_contract_profile()
        self._assert_setup_permission(
            request,
            entity_id=profile.entity_id,
            permission_key="profile_edit",
            label="assign salary structures to contract payroll profiles",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["contract_payroll_profile"] = profile
        try:
            assignment = ContractSalaryAssignmentService.assign_salary_structure(
                payload,
                close_previous_active=bool(request.data.get("close_previous_active")),
            )
        except ValueError as err:
            raise ValidationError({"detail": str(err)})
        return Response(self.get_serializer(assignment).data, status=201)


class ContractSalaryAssignmentRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractSalaryStructureAssignmentSerializer

    def get_queryset(self):
        return ContractSalaryStructureAssignment.objects.select_related(
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj.contract_payroll_profile)
        return obj

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.contract_payroll_profile.entity_id,
            permission_key="profile_edit",
            label="edit contract salary assignments",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            assignment = ContractSalaryAssignmentService.assign_salary_structure(
                serializer.validated_data,
                instance=obj,
            )
        except ValueError as err:
            raise ValidationError({"detail": str(err)})
        return Response(self.get_serializer(assignment).data)


class ContractTaxDeclarationListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = ContractTaxDeclarationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "contract_payroll_profile", "financial_year", "declaration_status", "tax_regime", "is_active"]
    search_fields = [
        "contract_payroll_profile__hrms_contract__contract_code",
        "contract_payroll_profile__hrms_contract__employee__employee_number",
        "contract_payroll_profile__hrms_contract__employee__display_name",
    ]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        return ContractTaxDeclarationService.list_declarations(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            contract_payroll_profile_id=self.request.query_params.get("contract_payroll_profile"),
            financial_year_id=int(self.request.query_params["financial_year"]) if self.request.query_params.get("financial_year") else None,
            declaration_status=self.request.query_params.get("declaration_status"),
            tax_regime=self.request.query_params.get("tax_regime"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_view",
            label="view contract tax declarations",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_edit",
            label="create contract tax declarations",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            declaration = ContractTaxDeclarationService.create_or_update_declaration(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(declaration).data, status=201)


class ContractTaxDeclarationRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractTaxDeclarationSerializer

    def get_queryset(self):
        return ContractTaxDeclaration.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "financial_year",
        ).prefetch_related("lines")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_view",
            label="view contract tax declarations",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_edit",
            label="edit contract tax declarations",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            declaration = ContractTaxDeclarationService.create_or_update_declaration(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(declaration).data)


class ContractTaxDeclarationApprovalActionAPIView(PayrollSetupScopedAPIView):
    action_name = ""

    def post(self, request, pk):
        declaration = ContractTaxDeclaration.objects.select_related("entity").get(pk=pk)
        self._enforce_object_scope(request, declaration)
        self._assert_setup_permission(
            request,
            entity_id=declaration.entity_id,
            permission_key="profile_edit",
            label=f"{self.action_name} contract tax declarations",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        note = str((request.data or {}).get("note") or "")
        try:
            if self.action_name == "submit":
                declaration = ContractTaxDeclarationService.submit_for_approval(
                    declaration=declaration,
                    actor_id=request.user.id,
                    remarks=note,
                )
            elif self.action_name == "approve":
                declaration = ContractTaxDeclarationService.approve(
                    declaration=declaration,
                    actor_id=request.user.id,
                    remarks=note,
                )
            elif self.action_name == "reject":
                declaration = ContractTaxDeclarationService.reject(
                    declaration=declaration,
                    actor_id=request.user.id,
                    remarks=note,
                )
            elif self.action_name == "cancel":
                declaration = ContractTaxDeclarationService.cancel(
                    declaration=declaration,
                    actor_id=request.user.id,
                    remarks=note,
                )
            else:
                raise ValidationError({"detail": "Unsupported approval action."})
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(ContractTaxDeclarationSerializer(declaration).data)


class ContractTaxDeclarationSubmitAPIView(ContractTaxDeclarationApprovalActionAPIView):
    action_name = "submit"


class ContractTaxDeclarationApproveAPIView(ContractTaxDeclarationApprovalActionAPIView):
    action_name = "approve"


class ContractTaxDeclarationRejectAPIView(ContractTaxDeclarationApprovalActionAPIView):
    action_name = "reject"


class ContractTaxDeclarationCancelAPIView(ContractTaxDeclarationApprovalActionAPIView):
    action_name = "cancel"


class ContractTaxDeclarationLineListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = ContractTaxDeclarationLineSerializer

    def get_declaration(self):
        declaration = ContractTaxDeclaration.objects.select_related("entity").get(pk=self.kwargs["pk"])
        self._enforce_object_scope(self.request, declaration)
        return declaration

    def get_queryset(self):
        declaration = self.get_declaration()
        is_active_param = self.request.query_params.get("is_active")
        queryset = declaration.lines.all()
        if is_active_param not in (None, ""):
            queryset = queryset.filter(is_active=is_active_param == "true")
        return queryset.order_by("section_code", "id")

    def get(self, request, *args, **kwargs):
        declaration = self.get_declaration()
        self._assert_setup_permission(
            request,
            entity_id=declaration.entity_id,
            permission_key="profile_view",
            label="view contract tax declaration lines",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        declaration = self.get_declaration()
        self._assert_setup_permission(
            request,
            entity_id=declaration.entity_id,
            permission_key="profile_edit",
            label="create contract tax declaration lines",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["declaration"] = declaration
        try:
            line = ContractTaxDeclarationService.create_or_update_line(payload)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(line).data, status=201)


class ContractTaxDeclarationLineRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractTaxDeclarationLineSerializer

    def get_queryset(self):
        return ContractTaxDeclarationLine.objects.select_related("declaration", "declaration__entity")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj.declaration)
        return obj

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.declaration.entity_id,
            permission_key="profile_edit",
            label="edit contract tax declaration lines",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            line = ContractTaxDeclarationService.create_or_update_line(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(line).data)


class ContractPayrollInputSnapshotListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = ContractPayrollInputSnapshotSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "contract_payroll_profile", "payroll_period", "input_type", "source", "is_active"]
    search_fields = [
        "contract_payroll_profile__hrms_contract__contract_code",
        "contract_payroll_profile__hrms_contract__employee__employee_number",
        "contract_payroll_profile__hrms_contract__employee__display_name",
    ]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        return ContractPayrollInputSnapshotService.list_snapshots(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            contract_payroll_profile_id=self.request.query_params.get("contract_payroll_profile"),
            payroll_period_id=int(self.request.query_params["payroll_period"]) if self.request.query_params.get("payroll_period") else None,
            input_type=self.request.query_params.get("input_type"),
            source=self.request.query_params.get("source"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_view",
            label="view contract payroll input snapshots",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_edit",
            label="create contract payroll input snapshots",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = ContractPayrollInputSnapshotService.create_or_update_snapshot(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(snapshot).data, status=201)


class ContractPayrollInputSnapshotRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractPayrollInputSnapshotSerializer

    def get_queryset(self):
        return ContractPayrollInputSnapshot.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_period",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_view",
            label="view contract payroll input snapshots",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="profile_edit",
            label="edit contract payroll input snapshots",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollemployeeprofile"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = ContractPayrollInputSnapshotService.create_or_update_snapshot(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(snapshot).data)


class EntityPayrollPolicyListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = EntityPayrollPolicySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "pay_frequency", "is_active", "is_default"]
    search_fields = ["code", "name", "description"]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        is_default_param = self.request.query_params.get("is_default")
        return EntityPayrollPolicyService.list_policies(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            pay_frequency=self.request.query_params.get("pay_frequency"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
            is_default=None if is_default_param in (None, "") else is_default_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="policy_view",
            label="view payroll processing policies",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="policy_create",
            label="create payroll processing policies",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            policy = EntityPayrollPolicyService.create_or_update_policy(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(policy).data, status=201)


class EntityPayrollPolicyRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = EntityPayrollPolicySerializer

    def get_queryset(self):
        return EntityPayrollPolicy.objects.select_related("entity").prefetch_related("rules")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="policy_view",
            label="view payroll processing policies",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="policy_edit",
            label="edit payroll processing policies",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            policy = EntityPayrollPolicyService.create_or_update_policy(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(policy).data)


class EntityPayrollPolicySetDefaultAPIView(PayrollSetupScopedAPIView):
    def post(self, request, pk):
        policy = EntityPayrollPolicy.objects.select_related("entity").get(pk=pk)
        self._enforce_object_scope(request, policy)
        self._assert_setup_permission(
            request,
            entity_id=policy.entity_id,
            permission_key="policy_edit",
            label="set default payroll processing policies",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        policy = EntityPayrollPolicyService.set_default_policy(policy=policy)
        return Response({"message": "Default payroll policy updated successfully.", "data": EntityPayrollPolicySerializer(policy).data})


class PayrollPolicyRuleListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = PayrollPolicyRuleSerializer

    def get_policy(self):
        policy = EntityPayrollPolicy.objects.select_related("entity").get(pk=self.kwargs["pk"])
        self._enforce_object_scope(self.request, policy)
        return policy

    def get_queryset(self):
        policy = self.get_policy()
        is_active_param = self.request.query_params.get("is_active")
        return PayrollPolicyRuleService.list_rules(
            policy=policy,
            rule_type=self.request.query_params.get("rule_type"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        policy = self.get_policy()
        self._assert_setup_permission(
            request,
            entity_id=policy.entity_id,
            permission_key="policy_view",
            label="view payroll policy rules",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        policy = self.get_policy()
        self._assert_setup_permission(
            request,
            entity_id=policy.entity_id,
            permission_key="policy_edit",
            label="create payroll policy rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["policy"] = policy
        try:
            rule = PayrollPolicyRuleService.create_or_update_rule(payload)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(rule).data, status=201)


class PayrollPolicyRuleRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = PayrollPolicyRuleSerializer

    def get_queryset(self):
        return PayrollPolicyRule.objects.select_related("policy", "policy__entity")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj.policy)
        return obj

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.policy.entity_id,
            permission_key="policy_edit",
            label="edit payroll policy rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            rule = PayrollPolicyRuleService.create_or_update_rule(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(rule).data)


class RecurringPayItemListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = RecurringPayItemSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "contract_payroll_profile", "payroll_component", "item_type", "recurrence_frequency", "is_active"]
    search_fields = [
        "contract_payroll_profile__hrms_contract__contract_code",
        "contract_payroll_profile__hrms_contract__employee__employee_number",
        "contract_payroll_profile__hrms_contract__employee__display_name",
        "payroll_component__code",
        "payroll_component__name",
        "remarks",
    ]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        return RecurringPayItemService.list_items(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            item_type=self.request.query_params.get("item_type"),
            payroll_component_id=int(self.request.query_params["payroll_component"]) if self.request.query_params.get("payroll_component") else None,
            contract_payroll_profile_id=self.request.query_params.get("contract_payroll_profile"),
            pay_frequency=self.request.query_params.get("pay_frequency"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="recurring_pay_item_view",
            label="view recurring pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="recurring_pay_item_create",
            label="create recurring pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = RecurringPayItemService.create_or_update_item(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(item).data, status=201)


class RecurringPayItemRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = RecurringPayItemSerializer

    def get_queryset(self):
        return RecurringPayItem.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_component",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="recurring_pay_item_view",
            label="view recurring pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="recurring_pay_item_edit",
            label="edit recurring pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            item = RecurringPayItemService.create_or_update_item(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(item).data)


class OneTimePayItemListCreateAPIView(PayrollSetupScopedAPIView, PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = OneTimePayItemSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "contract_payroll_profile", "payroll_component", "item_type", "approval_status", "source_type", "payroll_period", "is_active"]
    search_fields = [
        "contract_payroll_profile__hrms_contract__contract_code",
        "contract_payroll_profile__hrms_contract__employee__employee_number",
        "contract_payroll_profile__hrms_contract__employee__display_name",
        "payroll_component__code",
        "payroll_component__name",
        "remarks",
    ]
    scope_fields = ("entity",)

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        return OneTimePayItemService.list_items(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            item_type=self.request.query_params.get("item_type"),
            approval_status=self.request.query_params.get("approval_status"),
            source_type=self.request.query_params.get("source_type"),
            payroll_component_id=int(self.request.query_params["payroll_component"]) if self.request.query_params.get("payroll_component") else None,
            contract_payroll_profile_id=self.request.query_params.get("contract_payroll_profile"),
            payroll_period_id=int(self.request.query_params["payroll_period"]) if self.request.query_params.get("payroll_period") else None,
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="one_time_pay_item_view",
            label="view one-time pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="one_time_pay_item_create",
            label="create one-time pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = OneTimePayItemService.create_or_update_item(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(item).data, status=201)


class OneTimePayItemRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = OneTimePayItemSerializer

    def get_queryset(self):
        return OneTimePayItem.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_component",
            "payroll_period",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="one_time_pay_item_view",
            label="view one-time pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="one_time_pay_item_edit",
            label="edit one-time pay items",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            item = OneTimePayItemService.create_or_update_item(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(item).data)


class StatutorySchemeListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = StatutorySchemeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["scheme_type", "country_code", "state_code", "is_active", "is_system"]
    search_fields = ["code", "name", "description"]

    def get_queryset(self):
        is_active_param = self.request.query_params.get("is_active")
        is_system_param = self.request.query_params.get("is_system")
        return StatutorySchemeService.list_schemes(
            search=self.request.query_params.get("search"),
            scheme_type=self.request.query_params.get("scheme_type"),
            country_code=self.request.query_params.get("country_code"),
            state_code=self.request.query_params.get("state_code"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
            is_system=None if is_system_param in (None, "") else is_system_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_scheme_view",
            label="view statutory schemes",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_scheme_create",
            label="create statutory schemes",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            scheme = StatutorySchemeService.create_or_update_scheme(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(scheme).data, status=201)


class StatutorySchemeRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = StatutorySchemeSerializer

    def get_queryset(self):
        return StatutoryScheme.objects.all()

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_scheme_view",
            label="view statutory schemes",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_scheme_edit",
            label="edit statutory schemes",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            scheme = StatutorySchemeService.create_or_update_scheme(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(scheme).data)


class StatutoryRuleListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = StatutoryRuleSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "scheme", "rule_type", "is_active"]
    search_fields = ["rule_code", "rule_name", "scheme__code", "scheme__name"]

    def get_queryset(self):
        entity_param = self.request.query_params.get("entity")
        is_active_param = self.request.query_params.get("is_active")
        return StatutoryRuleService.list_rules(
            entity_id=int(entity_param) if entity_param else None,
            search=self.request.query_params.get("search"),
            scheme_id=self.request.query_params.get("scheme"),
            rule_type=self.request.query_params.get("rule_type"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_view",
            label="view statutory rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        entity_value = request.data.get("entity") or request.query_params.get("entity")
        entity_id = int(entity_value) if entity_value not in (None, "", "null", "None") else None
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_create",
            label="create statutory rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rule = StatutoryRuleService.create_or_update_rule(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(rule).data, status=201)


class StatutoryRuleRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = StatutoryRuleSerializer

    def get_queryset(self):
        return StatutoryRule.objects.select_related("entity", "scheme").prefetch_related("slabs")

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id = obj.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_view",
            label="view statutory rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id = obj.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_edit",
            label="edit statutory rules",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            rule = StatutoryRuleService.create_or_update_rule(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(rule).data)


class StatutorySlabListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = StatutorySlabSerializer

    def get_rule(self):
        return StatutoryRule.objects.select_related("entity", "scheme").get(pk=self.kwargs["pk"])

    def get_queryset(self):
        rule = self.get_rule()
        is_active_param = self.request.query_params.get("is_active")
        return StatutorySlabService.list_slabs(rule=rule, is_active=None if is_active_param in (None, "") else is_active_param == "true")

    def get(self, request, *args, **kwargs):
        rule = self.get_rule()
        entity_id = rule.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_view",
            label="view statutory slabs",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        rule = self.get_rule()
        entity_id = rule.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_edit",
            label="create statutory slabs",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["rule"] = rule
        try:
            slab = StatutorySlabService.create_or_update_slab(payload)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(slab).data, status=201)


class StatutorySlabRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = StatutorySlabSerializer

    def get_queryset(self):
        return StatutorySlab.objects.select_related("rule", "rule__entity", "rule__scheme")

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id = obj.rule.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_view",
            label="view statutory slabs",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return Response(self.get_serializer(obj).data)

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        entity_id = obj.rule.entity_id
        if entity_id is None:
            entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        else:
            self.enforce_scope(request, entity_id=entity_id)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_rule_edit",
            label="edit statutory slabs",
            legacy_groups={"payroll_operator", "payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            slab = StatutorySlabService.create_or_update_slab(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(slab).data)


class EntityStatutoryRegistrationListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = EntityStatutoryRegistrationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "scheme", "registration_state", "is_active"]
    search_fields = ["registration_number", "scheme__code", "scheme__name"]

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        return EntityStatutoryRegistrationService.list_registrations(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            scheme_id=self.request.query_params.get("scheme"),
            registration_state=self.request.query_params.get("registration_state"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_registration_view",
            label="view statutory registrations",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_payload(request, request.data)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="statutory_registration_create",
            label="create statutory registrations",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            registration = EntityStatutoryRegistrationService.create_or_update_registration(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(registration).data, status=201)


class EntityStatutoryRegistrationRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = EntityStatutoryRegistrationSerializer

    def get_queryset(self):
        return EntityStatutoryRegistration.objects.select_related("entity", "scheme")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        return obj

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.entity_id,
            permission_key="statutory_registration_edit",
            label="edit statutory registrations",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            registration = EntityStatutoryRegistrationService.create_or_update_registration(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(registration).data)


class ContractStatutoryProfileListCreateAPIView(PayrollSetupScopedAPIView, generics.ListCreateAPIView):
    serializer_class = ContractStatutoryProfileSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["contract_payroll_profile", "scheme", "is_active", "is_applicable"]
    search_fields = ["contract_payroll_profile__hrms_contract__contract_code", "contract_payroll_profile__hrms_contract__employee__employee_number", "contract_payroll_profile__hrms_contract__employee__display_name", "scheme__code", "scheme__name"]

    def get_queryset(self):
        entity_id, _, _ = self._scope_from_query(self.request, require_entity=True)
        is_active_param = self.request.query_params.get("is_active")
        is_applicable_param = self.request.query_params.get("is_applicable")
        return ContractStatutoryProfileService.list_profiles(
            entity_id=entity_id,
            search=self.request.query_params.get("search"),
            contract_payroll_profile_id=self.request.query_params.get("contract_payroll_profile"),
            scheme_id=self.request.query_params.get("scheme"),
            is_active=None if is_active_param in (None, "") else is_active_param == "true",
            is_applicable=None if is_applicable_param in (None, "") else is_applicable_param == "true",
        )

    def get(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="contract_statutory_profile_view",
            label="view contract statutory profiles",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        contract_profile = ContractPayrollProfile.objects.select_related("entity").get(pk=request.data.get("contract_payroll_profile"))
        self._enforce_object_scope(request, contract_profile)
        self._assert_setup_permission(
            request,
            entity_id=contract_profile.entity_id,
            permission_key="contract_statutory_profile_create",
            label="create contract statutory profiles",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = ContractStatutoryProfileService.create_or_update_profile(serializer.validated_data)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(profile).data, status=201)


class ContractStatutoryProfileRetrieveUpdateAPIView(PayrollSetupScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = ContractStatutoryProfileSerializer

    def get_queryset(self):
        return ContractStatutoryProfile.objects.select_related(
            "contract_payroll_profile",
            "contract_payroll_profile__entity",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "scheme",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj.contract_payroll_profile)
        return obj

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        self._assert_setup_permission(
            request,
            entity_id=obj.contract_payroll_profile.entity_id,
            permission_key="contract_statutory_profile_edit",
            label="edit contract statutory profiles",
            legacy_groups={"payroll_admin"},
            legacy_permissions={"payroll.change_payrollrun"},
        )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = ContractStatutoryProfileService.create_or_update_profile(serializer.validated_data, instance=obj)
        except ValueError as err:
            detail = err.args[0] if err.args else str(err)
            raise ValidationError(detail if isinstance(detail, (dict, list)) else {"detail": str(detail)})
        return Response(self.get_serializer(profile).data)


class PayrollDashboardSummaryAPIView(PayrollSetupScopedAPIView):

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="run_view",
            label="view payroll dashboard",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollrun"},
        )

        periods = PayrollPeriod.objects.all()
        runs = PayrollRun.objects.all()
        profiles = ContractPayrollProfile.objects.all()
        if entity_id:
            periods = periods.filter(entity_id=entity_id)
            runs = runs.filter(entity_id=entity_id)
            profiles = profiles.filter(entity_id=entity_id)
        if entityfinid_id:
            periods = periods.filter(entityfinid_id=entityfinid_id)
            runs = runs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            periods = periods.filter(subentity_id=subentity_id)
            runs = runs.filter(subentity_id=subentity_id)
            profiles = profiles.filter(hrms_contract__subentity_id=subentity_id)

        current_period = periods.order_by("-period_start", "-id").first()
        latest_run = runs.order_by("-posting_date", "-id").first()
        readiness = PayrollSetupService.readiness_summary(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        pending_actions = {
            "draft_runs": runs.filter(status=PayrollRun.Status.DRAFT).count(),
            "calculated_runs": runs.filter(status=PayrollRun.Status.CALCULATED).count(),
            "approved_runs": runs.filter(status=PayrollRun.Status.APPROVED).count(),
            "payment_handoff_pending": runs.filter(
                status=PayrollRun.Status.POSTED, payment_status=PayrollRun.PaymentStatus.NOT_READY
            ).count(),
            "payment_reconcile_pending": runs.filter(
                payment_status__in=[PayrollRun.PaymentStatus.HANDED_OFF, PayrollRun.PaymentStatus.PARTIALLY_DISBURSED]
            ).count(),
        }
        financial_snapshot = runs.aggregate(
            total_gross=Sum("gross_amount"),
            total_deduction=Sum("deduction_amount"),
            total_net=Sum("net_pay_amount"),
        )
        alerts = []
        if readiness["missing_payroll_profile_count"]:
            alerts.append({"code": "MISSING_PROFILE", "severity": "warning", "message": "Some payroll profiles are missing salary structures."})
        if readiness["missing_ledger_mapping_count"]:
            alerts.append({"code": "LEDGER_MAPPING_MISSING", "severity": "blocking", "message": "Ledger mappings are incomplete for the selected scope."})
        if readiness["negative_net_pay_count"]:
            alerts.append({"code": "NEGATIVE_NET_PAY", "severity": "warning", "message": "Negative net pay cases were detected."})
        if readiness["outdated_structure_version_count"]:
            alerts.append(
                {
                    "code": "OUTDATED_STRUCTURE_VERSION",
                    "severity": "warning",
                    "message": "Some payroll profiles are pinned to older salary structure versions.",
                }
            )
        if readiness["missing_calculation_policy_count"] or readiness["incomplete_calculation_policy_count"]:
            alerts.append(
                {
                    "code": "CALCULATION_POLICY_INCOMPLETE",
                    "severity": "warning",
                    "message": "Some employee structure versions are missing calculation policy metadata.",
                }
            )

        payload = {
            "current_period_summary": None if not current_period else PayrollPeriodSerializer(current_period).data,
            "latest_payroll_run_summary": None
            if not latest_run
            else {
                "run_id": latest_run.id,
                "run_number": latest_run.run_number,
                "status": latest_run.status,
                "payment_status": latest_run.payment_status,
                "employee_count": latest_run.employee_count,
                "gross_amount": latest_run.gross_amount,
                "deduction_amount": latest_run.deduction_amount,
                "net_pay_amount": latest_run.net_pay_amount,
            },
            "readiness_counts": readiness,
            "pending_action_counts": pending_actions,
            "financial_snapshot": financial_snapshot,
            "alerts": alerts,
        }
        return Response(payload)


class PayrollReadinessAPIView(PayrollSetupScopedAPIView):

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(request, require_entity=True)
        self._assert_setup_permission(
            request,
            entity_id=entity_id,
            permission_key="profile_view",
            label="view payroll readiness",
            legacy_groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            legacy_permissions={"payroll.view_payrollemployeeprofile"},
        )

        result = PayrollSetupService.readiness_summary(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )

        rollout = None
        if entity_id and entityfinid_id:
            rollout = PayrollRolloutValidationService.validate_setup(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
            )

        profiles = ContractPayrollProfile.objects.select_related(
            "hrms_contract__employee",
            "hrms_contract__subentity",
            "bank_account",
        ).order_by("hrms_contract__employee__employee_number", "id")
        if entity_id:
            profiles = profiles.filter(entity_id=entity_id)
        if subentity_id is not None:
            profiles = profiles.filter(hrms_contract__subentity_id=subentity_id)

        profile_rows = list(profiles[:100])
        profile_ids = [profile.id for profile in profile_rows]
        assignments = {}
        for item in ContractSalaryStructureAssignment.objects.select_related(
            "salary_structure",
            "salary_structure__current_version",
            "salary_structure_version",
        ).filter(
            contract_payroll_profile_id__in=profile_ids,
            is_active=True,
        ).order_by("contract_payroll_profile_id", "-effective_from", "-id"):
            assignments.setdefault(str(item.contract_payroll_profile_id), item)
        summaries = {}
        for item in ContractAttendanceSummary.objects.filter(
            contract_payroll_profile_id__in=profile_ids,
            is_active=True,
        ).order_by("contract_payroll_profile_id", "-payroll_period__period_end", "-id"):
            summaries.setdefault(str(item.contract_payroll_profile_id), item)

        issue_rows = []
        for profile in profile_rows:
            issues = []
            assignment = assignments.get(str(profile.id))
            summary = summaries.get(str(profile.id))
            if assignment is None or not assignment.salary_structure_id:
                issues.append("Salary structure missing")
            if not profile.bank_account_id:
                issues.append("Payment details missing")
            if not profile.tax_regime:
                issues.append("Tax regime missing")
            if summary is None or not summary.attendance_days or not summary.payable_days:
                issues.append("Attendance/payable days missing")
            if (
                assignment is not None
                and assignment.salary_structure_id
                and assignment.salary_structure_version_id
                and getattr(assignment.salary_structure, "current_version_id", None)
                and assignment.salary_structure.current_version_id != assignment.salary_structure_version_id
            ):
                issues.append("Pinned to an older salary structure version")
            version = None if assignment is None else assignment.salary_structure_version or getattr(assignment.salary_structure, "current_version", None)
            if assignment is not None and assignment.salary_structure_id and version is not None:
                policy = version.calculation_policy_json or {}
                if not policy:
                    issues.append("Calculation policy missing on structure version")
                elif any(not policy.get(key) for key in PayrollSetupService.REQUIRED_CALCULATION_POLICY_KEYS):
                    issues.append("Calculation policy incomplete on structure version")
            if issues:
                issue_rows.append(
                    {
                        "payroll_profile_id": str(profile.id),
                        "employee_id": profile.employee_user_id,
                        "employee_code": profile.employee_code,
                        "employee_name": profile.employee_name,
                        "subentity_id": profile.hrms_contract.subentity_id,
                        "issues": issues,
                    }
                )

        payload = {
            **result,
            "employee_issue_rows": issue_rows,
            "rollout_validation": None
            if not rollout
            else {
                "passed": rollout.passed,
                "summary": rollout.summary,
                "issues": [issue.as_dict() for issue in rollout.issues],
            },
        }
        return Response(payload)
