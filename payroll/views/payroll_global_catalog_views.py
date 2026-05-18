from __future__ import annotations

from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from payroll.models import (
    GlobalPayrollComponent,
    GlobalPayrollComponentGroup,
    GlobalSalaryStructureTemplate,
    GlobalSalaryStructureTemplateLine,
)
from payroll.serializers import (
    EntityAdoptionPreviewSerializer,
    EntitySalaryTemplateAdoptionSerializer,
    GlobalPayrollComponentGroupSerializer,
    GlobalPayrollComponentSerializer,
    GlobalSalaryStructureTemplateLineSerializer,
    GlobalSalaryStructureTemplateSerializer,
)
from payroll.services import (
    EntityAdoptionPreviewService,
    EntitySalaryTemplateAdoptionService,
    GlobalPayrollCatalogService,
    GlobalSalaryTemplateService,
    PayrollPermissionService,
)
from payroll.views.scoped import PayrollScopedAPIView


class GlobalCatalogAPIViewMixin:
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _validation_error(err: Exception):
        raise ValidationError({"detail": str(err)})


class GlobalPayrollComponentGroupListCreateAPIView(GlobalCatalogAPIViewMixin, generics.ListCreateAPIView):
    serializer_class = GlobalPayrollComponentGroupSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group_type", "is_active", "is_system"]
    search_fields = ["code", "name", "description"]
    ordering_fields = ["sort_order", "name", "code", "updated_at"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        return GlobalPayrollCatalogService.list_component_groups(
            search=self.request.query_params.get("search"),
            is_active=None,
        )

    def perform_create(self, serializer):
        try:
            serializer.instance = GlobalPayrollCatalogService.create_or_update_component_group(serializer.validated_data)
        except ValueError as err:
            self._validation_error(err)


class GlobalPayrollComponentGroupRetrieveUpdateAPIView(GlobalCatalogAPIViewMixin, generics.RetrieveUpdateAPIView):
    serializer_class = GlobalPayrollComponentGroupSerializer
    queryset = GlobalPayrollComponentGroup.objects.all()

    def perform_update(self, serializer):
        try:
            serializer.instance = GlobalPayrollCatalogService.create_or_update_component_group(
                serializer.validated_data,
                instance=self.get_object(),
            )
        except ValueError as err:
            self._validation_error(err)


class GlobalPayrollComponentListCreateAPIView(GlobalCatalogAPIViewMixin, generics.ListCreateAPIView):
    serializer_class = GlobalPayrollComponentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "component_type", "calculation_type", "statutory_code", "country_code", "state_code", "is_active", "is_system"]
    search_fields = ["code", "name", "description"]
    ordering_fields = ["default_sequence", "name", "code", "updated_at"]
    ordering = ["default_sequence", "code"]

    def get_queryset(self):
        return GlobalPayrollCatalogService.list_components(
            search=self.request.query_params.get("search"),
            component_type=self.request.query_params.get("component_type"),
            is_active=None,
        )

    def perform_create(self, serializer):
        try:
            serializer.instance = GlobalPayrollCatalogService.create_or_update_component(serializer.validated_data)
        except ValueError as err:
            self._validation_error(err)


class GlobalPayrollComponentRetrieveUpdateAPIView(GlobalCatalogAPIViewMixin, generics.RetrieveUpdateAPIView):
    serializer_class = GlobalPayrollComponentSerializer
    queryset = GlobalPayrollComponent.objects.select_related("group").all()

    def perform_update(self, serializer):
        try:
            serializer.instance = GlobalPayrollCatalogService.create_or_update_component(
                serializer.validated_data,
                instance=self.get_object(),
            )
        except ValueError as err:
            self._validation_error(err)


class GlobalSalaryTemplateListCreateAPIView(GlobalCatalogAPIViewMixin, generics.ListCreateAPIView):
    serializer_class = GlobalSalaryStructureTemplateSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["template_type", "country_code", "state_code", "industry_type", "pay_frequency", "is_default", "is_active", "is_system"]
    search_fields = ["code", "name", "description"]
    ordering_fields = ["name", "code", "updated_at", "effective_from"]
    ordering = ["name"]

    def get_queryset(self):
        return (
            GlobalSalaryTemplateService.list_templates(
                search=self.request.query_params.get("search"),
                template_type=self.request.query_params.get("template_type"),
                is_active=None,
            )
            .annotate(active_line_count=Count("lines"))
        )

    def perform_create(self, serializer):
        try:
            serializer.instance = GlobalSalaryTemplateService.create_or_update_template(serializer.validated_data)
        except ValueError as err:
            self._validation_error(err)


class GlobalSalaryTemplateRetrieveUpdateAPIView(GlobalCatalogAPIViewMixin, generics.RetrieveUpdateAPIView):
    serializer_class = GlobalSalaryStructureTemplateSerializer
    queryset = GlobalSalaryStructureTemplate.objects.prefetch_related("lines__component", "lines__component__group").annotate(active_line_count=Count("lines"))

    def perform_update(self, serializer):
        try:
            serializer.instance = GlobalSalaryTemplateService.create_or_update_template(
                serializer.validated_data,
                instance=self.get_object(),
            )
        except ValueError as err:
            self._validation_error(err)


class GlobalSalaryTemplateLineListCreateAPIView(GlobalCatalogAPIViewMixin, generics.ListCreateAPIView):
    serializer_class = GlobalSalaryStructureTemplateLineSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["is_active", "calculation_type", "component"]
    ordering_fields = ["sequence", "updated_at"]
    ordering = ["sequence", "id"]

    def get_template(self):
        return GlobalSalaryStructureTemplate.objects.get(pk=self.kwargs["pk"])

    def get_queryset(self):
        return GlobalSalaryStructureTemplateLine.objects.select_related("component", "component__group", "template").filter(template=self.get_template()).order_by("sequence", "id")

    def perform_create(self, serializer):
        try:
            serializer.instance = GlobalSalaryTemplateService.create_or_update_line(
                self.get_template(),
                serializer.validated_data,
            )
        except ValueError as err:
            self._validation_error(err)


class GlobalSalaryTemplateLineRetrieveUpdateAPIView(GlobalCatalogAPIViewMixin, generics.RetrieveUpdateAPIView):
    serializer_class = GlobalSalaryStructureTemplateLineSerializer
    queryset = GlobalSalaryStructureTemplateLine.objects.select_related("component", "component__group", "template")

    def perform_update(self, serializer):
        line = self.get_object()
        try:
            serializer.instance = GlobalSalaryTemplateService.create_or_update_line(
                line.template,
                serializer.validated_data,
                instance=line,
            )
        except ValueError as err:
            self._validation_error(err)


class GlobalSalaryTemplateAdoptionPreviewAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = "setup"

    def post(self, request, pk: str):
        serializer = EntityAdoptionPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id, _, _ = self._scope_from_payload(request, serializer.validated_data)
        try:
            PayrollPermissionService.assert_entity_permission_access(
                user=request.user,
                entity_id=entity_id,
                permission_key="global_salary_template_view",
                label="preview payroll salary template adoption",
            )
        except PermissionError as err:
            raise PermissionDenied(detail=str(err))
        template = GlobalSalaryTemplateService.get_template_detail(pk)
        preview = EntityAdoptionPreviewService.preview_template(template=template, entity_id=entity_id)
        return Response(preview, status=status.HTTP_200_OK)


class GlobalSalaryTemplateAdoptAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = "setup"

    def post(self, request, pk: str):
        serializer = EntitySalaryTemplateAdoptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id, entityfinid_id, subentity_id = self._scope_from_payload(request, serializer.validated_data)
        try:
            PayrollPermissionService.assert_entity_permission_access(
                user=request.user,
                entity_id=entity_id,
                permission_key="global_salary_template_adopt",
                label="adopt payroll salary templates",
            )
        except PermissionError as err:
            raise PermissionDenied(detail=str(err))
        summary = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=entity_id,
            global_template_id=pk,
            effective_from=serializer.validated_data["effective_from"],
            subentity_id=subentity_id,
            entity_financial_year_id=entityfinid_id,
            structure_name_override=serializer.validated_data.get("structure_name_override"),
            structure_code_override=serializer.validated_data.get("structure_code_override"),
            dry_run=serializer.validated_data.get("dry_run", False),
        )
        if summary["conflicts"] and not summary["adopted"]:
            return Response(summary, status=status.HTTP_409_CONFLICT)
        return Response(summary, status=status.HTTP_200_OK if summary["dry_run"] else status.HTTP_201_CREATED)
