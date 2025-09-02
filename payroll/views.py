from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from asteval import Interpreter
from django.utils.dateparse import parse_date
from django.db import models
from .services import apply_structure_to_entity
#from rest_framework import 

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from rest_framework import permissions,status,generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from payroll.serializers import salarycomponentserializer,employeesalaryserializer,reportingmanagerserializer,EmployeeSerializer,EntityPayrollComponentConfigSerializer,CalculationTypeSerializer,BonusFrequencySerializer,CalculationValueSerializer,ComponentTypeSerializer,PayrollComponentSerializer,EntityPayrollComponentSerializer,PayStructureListReadSerializer,PayStructureReadSerializer,PayStructureComponentReadSerializer,PayStructureSerializer, PayStructureComponentSerializer,PayStructureNestedCreateSerializer
from payroll.models import salarycomponent,employeesalary,EntityPayrollComponentConfig,employeenew,CalculationType, BonusFrequency, CalculationValue, ComponentType,PayrollComponent,EntityPayrollComponent,PayStructure, PayStructureComponent
from django.db import DatabaseError, transaction
from rest_framework.response import Response
from django.db.models import Sum,OuterRef,Subquery,F,Count,IntegerField
from django.db.models import Prefetch
from financial.models import account
from inventory.models import Product
from django.db import connection
from django.core import serializers
from rest_framework.renderers import JSONRenderer
from drf_excel.mixins import XLSXFileMixin
from drf_excel.renderers import XLSXRenderer
from rest_framework.viewsets import ReadOnlyModelViewSet
from entity.models import Entity
from django_pandas.io import read_frame
from django.db.models import Q
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import timedelta,date,datetime
from django_pivot.pivot import pivot
from Authentication.models import User
from payroll.utils.payroll import calculate_salary_components
from payroll.api.filters import EntityPayrollComponentFilter
from rest_framework.permissions import IsAuthenticated
from django.db.models.functions import Coalesce


from payroll.models import (
    OptionSet, Option,
    BusinessUnit, Department, Location, CostCenter,GradeBand, Designation,
)
from .serializers import (
    OptionSetSerializer, OptionSerializer,
    BusinessUnitSerializer, DepartmentSerializer, LocationSerializer, CostCenterSerializer,
     GradeBandSerializer, DesignationSerializer,ManagerListItemSerializer,
)

from payroll.models import (
Employee,
EmploymentAssignment,
EmployeeBankAccount,
EmployeeDocument,
EmployeeStatutoryIN,
EmployeeCompensation
)

from rest_framework import generics as _g, permissions as _p



class GradeBandListCreateAPIView(generics.ListCreateAPIView):
    queryset = GradeBand.objects.select_related("entity").all().order_by("entity_id", "level", "code")
    serializer_class = GradeBandSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "entity": ["exact"],
        "code": ["exact", "icontains"],
        "name": ["icontains"],
        "level": ["exact", "gte", "lte"],
    }
    search_fields = ["code", "name"]
    ordering_fields = ["entity", "level", "code", "name", "id"]
    ordering = ["entity", "level", "code"]

class GradeBandRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = GradeBand.objects.all()
    serializer_class = GradeBandSerializer
    permission_classes = [permissions.IsAuthenticated]

class DesignationListCreateAPIView(generics.ListCreateAPIView):
    queryset = Designation.objects.select_related("entity", "grade_band").all().order_by("entity_id", "name")
    serializer_class = DesignationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "entity": ["exact"],
        "name": ["icontains"],
        "grade_band": ["exact"],
        "grade_band__code": ["exact", "icontains"],
    }
    search_fields = ["name", "grade_band__code"]
    ordering_fields = ["entity", "name", "grade_band", "id"]
    ordering = ["entity", "name"]

class DesignationRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer
    permission_classes = [permissions.IsAuthenticated]





class salarycomponentApiView(ListCreateAPIView):

    serializer_class = salarycomponentserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['tdsreturn']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salarycomponent.objects.filter(entity = entity)
    

class salarycomponentupdatedelApiView(RetrieveUpdateDestroyAPIView):

    serializer_class = salarycomponentserializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salarycomponent.objects.filter(entity = entity)
    
class PayrollComponentByEntityAPIView(APIView):
    def get(self, request, entity_id):
        try:
            entity = Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist:
            return Response({"detail": "Entity not found"}, status=status.HTTP_404_NOT_FOUND)

        components = PayrollComponent.objects.filter(entity=entity)
        serializer = PayrollComponentSerializer(components, many=True)
        return Response(serializer.data)
    

class PayrollComponentDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            component = PayrollComponent.objects.get(pk=pk)
        except PayrollComponent.DoesNotExist:
            return Response({"detail": "PayrollComponent not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PayrollComponentSerializer(component)
        return Response(serializer.data)
    


    





    


class employeesalaryApiView(ListCreateAPIView):

    serializer_class = employeesalaryserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['isactive','entity','employee']

    def create(self, request, *args, **kwargs):  
            
            entity = self.request.query_params.get('entity')
            employee = self.request.query_params.get('employee')

            employeesalary.objects.filter(entity = entity,employee= employee).update(isactive = 0)
                    
            serializer = self.get_serializer(data=request.data, many=True)  
            serializer.is_valid(raise_exception=True)  

           # print(serializer)
      
            try:  
                self.perform_create(serializer)  
                return Response(serializer.data, status=status.HTTP_201_CREATED)  
            except:  
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_queryset(self):

        query = employeesalary.objects.filter()

        pivot_table = pivot(query, 'scomponent', 'employee', 'salaryvalue')

        print(pivot_table)

        return query
    

    



    



    




class EmployeePayrollAPIView(APIView):
    def get(self, request, id):
        emp = get_object_or_404(employeenew, id=id)
        serializer = EmployeeSerializer(emp)
        return Response(serializer.data)

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id):
        emp = get_object_or_404(employeenew, id=id)
        serializer = EmployeeSerializer(emp, data=request.data, partial=False)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class EmployeesByEntityAPIView(APIView):
    def get(self, request, entity_id):
        """
        GET: List all employees by entity_id with nested payroll components
        """
        employees = employeenew.objects.filter(entity_id=entity_id)
        if not employees.exists():
            return Response({"detail": "No employees found for this entity."}, status=status.HTTP_404_NOT_FOUND)

        serializer = EmployeeSerializer(employees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class getsalarystructure(ListAPIView):

   # serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        ctc = self.request.query_params.get('ctc')


        aqs = salarycomponent.objects.filter(entity = entity1).values('id','salarycomponentname','salarycomponentcode', 'componentperiod','defaultpercentage','componenttype')

        df = read_frame(aqs)


        df = read_frame(aqs)
      #  df['yearlycomponent'] = df['yearlycomponent'].astype(float)
       # df['balance'] = df['balance'].astype(float)

        df['yearlycomponent'] = (float(ctc) * df['defaultpercentage'].astype(float))/100.00

        df['monthlycomponent'] = (df['yearlycomponent'].astype(float))/12.00




       # return 1
     
      
        return Response(df.groupby(['id','salarycomponentname','salarycomponentcode','componentperiod','componenttype' ,'defaultpercentage'])[['yearlycomponent','monthlycomponent']].sum().abs().reset_index().sort_values(by=['salarycomponentname']).T.to_dict().values())
    

class CalculateSalaryComponentsView(APIView):
    def post(self, request):
        try:
            basic_salary = float(request.data.get('basic_salary'))
            entity_id = int(request.data.get('entity_id'))

            if not basic_salary or not entity_id:
                return Response({"error": "basic_salary and entity_id are required."}, status=status.HTTP_400_BAD_REQUEST)

            # Call the utility function to calculate salary
            data = calculate_salary_components(basic_salary, entity_id)
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class ActivePayrollComponentsByEntity(APIView):
    def get(self, request, entity_id):
        payroll_configs = EntityPayrollComponentConfig.objects.filter(
            entity_id=entity_id,
            is_active=True
        ).select_related('component')

        serializer = EntityPayrollComponentConfigSerializer(payroll_configs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class CalculationTypeListAPIView(ListAPIView):
    queryset = CalculationType.objects.all()
    serializer_class = CalculationTypeSerializer

class BonusFrequencyListAPIView(ListAPIView):
    queryset = BonusFrequency.objects.all()
    serializer_class = BonusFrequencySerializer


class CalculationValueListAPIView(ListAPIView):
    queryset = CalculationValue.objects.all()
    serializer_class = CalculationValueSerializer

class ComponentTypeListAPIView(ListAPIView):
    queryset = ComponentType.objects.all()
    serializer_class = ComponentTypeSerializer


class PayrollComponentAPIView(APIView):

    def post(self, request):
        serializer = PayrollComponentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        try:
            instance = PayrollComponent.objects.get(pk=pk)
        except PayrollComponent.DoesNotExist:
            return Response({"detail": "PayrollComponent not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PayrollComponentSerializer(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class PayrollComponentDeleteAPIView(APIView):
    def delete(self, request, id):
        payroll_component = get_object_or_404(PayrollComponent, id=id)
        payroll_component.delete()
        return Response({"message": "Payroll Component deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class CalculatePayrollFromCTCAPIView(APIView):
    def post(self, request):
        try:
            entity_id = request.data.get("entity_id")
            ctc_amount = request.data.get("ctc_amount")

            if not entity_id or not ctc_amount:
                return Response({'error': 'entity_id and ctc_amount are required.'}, status=400)

            ctc_amount = float(ctc_amount)
            monthly_ctc = ctc_amount / 12

            configs = EntityPayrollComponentConfig.objects.filter(
                entity_id=entity_id,
                is_active=True
            ).select_related(
                'component__component_type',
                'component__calculation_type',
                'component__bonus_frequency'
            )

            if not configs.exists():
                return Response({'error': 'No active components found for this entity.'}, status=404)

            basic_config = configs.filter(component__is_basic=True).first()
            if not basic_config:
                return Response({'error': 'Basic component not configured for this entity.'}, status=400)

            basic_percent = basic_config.default_value
            monthly_basic = (monthly_ctc * 100) / 100

            variables = {'basic': monthly_basic}
            total_earnings_monthly = 0
            total_earnings_annual = 0
            total_deductions_monthly = 0
            total_deductions_annual = 0
            components_result = []

            aeval = Interpreter()

            # === First pass: Fixed and Percent ===
            for config in configs:
                comp = config.component
                comp_code = comp.code.lower()
                calc_type = comp.calculation_type.name.lower() if comp.calculation_type else 'fixed'
                freq = comp.bonus_frequency.name.lower() if comp.bonus_frequency else 'monthly'

                monthly_value = 0
                if calc_type == 'percent':
                    monthly_value = (monthly_basic * config.default_value) / 100
                elif calc_type == 'fixed':
                    monthly_value = config.default_value

                config._monthly_value = monthly_value
                variables[comp_code] = monthly_value

            # === Second pass: Formula and Annuals ===
            for config in configs:
                comp = config.component
                comp_code = comp.code.lower()
                calc_type = comp.calculation_type.name.lower() if comp.calculation_type else 'fixed'
                freq = comp.bonus_frequency.name.lower() if comp.bonus_frequency else 'monthly'

                if calc_type == 'formula' and comp.formula_expression:
                    try:
                        expression = comp.formula_expression
                        for key, val in variables.items():
                            expression = expression.replace(f'{{{key}}}', str(val))
                        monthly_value = float(aeval(expression))
                    except Exception:
                        monthly_value = 0
                else:
                    monthly_value = config._monthly_value

                # Get correct annual value based on frequency
                if freq == 'yearly':
                    periodic_value = monthly_value
                    annual_value = periodic_value
                    monthly_value = annual_value / 12
                elif freq == 'quarterly':
                    periodic_value = monthly_value
                    annual_value = periodic_value * 4
                    monthly_value = annual_value / 12
                else:  # monthly
                    periodic_value = monthly_value
                    annual_value = periodic_value * 12
                    monthly_value = periodic_value


                variables[comp_code] = monthly_value

                comp_type = comp.component_type.name.lower() if comp.component_type else 'unknown'
                include_in_total = comp_type in ['earning', 'bonus']
                direction = '+' if include_in_total else '-'

                if include_in_total:
                    total_earnings_monthly += monthly_value
                    total_earnings_annual += annual_value
                elif comp_type in ['deduction', 'statutory']:
                    total_deductions_monthly += monthly_value
                    total_deductions_annual += annual_value

                components_result.append({
                    "component_id": comp.id,
                    "component": comp.name,
                    "component_type": comp.component_type.name if comp.component_type else "Unknown",
                    "component_type_id": comp.component_type.id if comp.component_type else None,
                    "direction": direction,
                    "calculation_type": comp.calculation_type.name if comp.calculation_type else "Fixed",
                    "calculation_type_id": comp.calculation_type.id if comp.calculation_type else None,
                    "bonus_frequency": comp.bonus_frequency.name if comp.bonus_frequency else "Monthly",
                    "bonus_frequency_id": comp.bonus_frequency.id if comp.bonus_frequency else None,
                    "default_value": round(config.default_value, 2),
                    "monthly_value": round(monthly_value, 2),
                    "annual_value": round(annual_value, 2),
                    "included_in_total": include_in_total,
                    "min_value": config.min_value,
                    "max_value": config.max_value,
                    "formula_expression": comp.formula_expression,
                })

            net_monthly_salary = total_earnings_monthly - total_deductions_monthly
            net_annual_salary = total_earnings_annual - total_deductions_annual

            return Response({
                "input_ctc": round(ctc_amount, 2),
                "monthly_basic": round(monthly_basic, 2),
                "gross_monthly_total": round(total_earnings_monthly, 2),
                "gross_annual_total": round(total_earnings_annual, 2),
                "difference": round(ctc_amount, 2) - round(total_earnings_annual, 2),
                "difference%": (round(ctc_amount, 2) - round(total_earnings_annual, 2))*100/round(ctc_amount, 2),
                "total_deductions_monthly": round(total_deductions_monthly, 2),
                "total_deductions_annual": round(total_deductions_annual, 2),
                "net_monthly_salary": round(net_monthly_salary, 2),
                "net_annual_salary": round(net_annual_salary, 2),
                "components": components_result
            })

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        

class EntityPayrollComponentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/entity-components/?entity_id=&entity_code=&family_code=&active_on=&as_of=
    POST /api/entity-components/
    """
    queryset = (
        EntityPayrollComponent.objects
        .select_related("entity", "family", "component", "component__slab_group")
        .order_by("entity_id", "family__code", "effective_from")
    )
    serializer_class = EntityPayrollComponentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EntityPayrollComponentFilter
    search_fields = ["family__code", "entity__name", "entity__code"]  # adjust if your Entity has different fields
    ordering_fields = ["entity_id", "entity__code", "family__code", "effective_from", "enabled", "updated_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Helpful when many rows pin to a specific version (avoids N+1 on caps)
        return qs.prefetch_related("component__caps")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        as_of = self.request.query_params.get("as_of")
        dt = parse_date(as_of) if as_of else None
        if dt:
            ctx["as_of_date"] = dt
        return ctx


class EntityPayrollComponentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/PATCH/DELETE /api/entity-components/{id}/?as_of=YYYY-MM-DD
    """
    queryset = (
        EntityPayrollComponent.objects
        .select_related("entity", "family", "component", "component__slab_group")
        .prefetch_related("component__caps")
        .order_by("entity_id", "family__code", "effective_from")
    )
    serializer_class = EntityPayrollComponentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        as_of = self.request.query_params.get("as_of")
        dt = parse_date(as_of) if as_of else None
        if dt:
            ctx["as_of_date"] = dt
        return ctx
    

# ---------------------------
# PayStructure list/create
# ---------------------------
class PayStructureListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PayStructure.objects.all().order_by("code", "entity", "effective_from")
        entity_id = self.request.query_params.get("entity_id")
        code = self.request.query_params.get("code")
        status_q = self.request.query_params.get("status")
        on = self.request.query_params.get("on")  # YYYY-MM-DD filter active on date

        if entity_id == "null":
            qs = qs.filter(entity__isnull=True)
        elif entity_id:
            qs = qs.filter(entity_id=entity_id)

        if code:
            qs = qs.filter(code__iexact=code)

        if status_q:
            qs = qs.filter(status=status_q)

        if on:
            d = parse_date(on)
            if d:
                qs = qs.filter(effective_from__lte=d).filter(
                    models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=d)
                )
        return qs

    # read on GET (list), write on POST (create)
    def get_serializer_class(self):
        return PayStructureListReadSerializer if self.request.method == "GET" else PayStructureSerializer


# ---------------------------
# PayStructure detail
# ---------------------------
class PayStructureDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PayStructure.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # GET detail = rich read with nested items; write = basic writer
        if self.request.method == "GET":
            return PayStructureReadSerializer
        return PayStructureSerializer

    # allow ?as_of=YYYY-MM-DD to control resolved_global in nested items
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method == "GET":
            as_of_param = self.request.query_params.get("as_of")
            if as_of_param:
                d = parse_date(as_of_param)
                if d:
                    ctx = {**ctx, "as_of": d}
        return ctx


# ---------------------------
# PayStructure nested-create (header + items in one POST)
# ---------------------------
class PayStructureNestedCreateView(generics.CreateAPIView):
    serializer_class = PayStructureNestedCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Let serializer.create() do atomic creation + validation
        return super().create(request, *args, **kwargs)


# ---------------------------
# PayStructureComponent list/create
# ---------------------------
class PayStructureComponentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (PayStructureComponent.objects
              .select_related("template", "family", "pinned_global_component")
              .order_by("template", "priority", "id"))
        template_id = self.request.query_params.get("template_id")
        family_code = self.request.query_params.get("family_code")

        if template_id:
            qs = qs.filter(template_id=template_id)
        if family_code:
            qs = qs.filter(family__code__iexact=family_code)
        return qs

    def get_serializer_class(self):
        return PayStructureComponentReadSerializer if self.request.method == "GET" else PayStructureComponentSerializer

    # allow ?as_of=YYYY-MM-DD to resolve globals in list read
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method == "GET":
            as_of_param = self.request.query_params.get("as_of")
            if as_of_param:
                d = parse_date(as_of_param)
                if d:
                    ctx = {**ctx, "as_of": d}
        return ctx


# ---------------------------
# PayStructureComponent detail
# ---------------------------
class PayStructureComponentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = (PayStructureComponent.objects
                .select_related("template", "family", "pinned_global_component")
                .all())
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return PayStructureComponentReadSerializer if self.request.method == "GET" else PayStructureComponentSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method == "GET":
            as_of_param = self.request.query_params.get("as_of")
            if as_of_param:
                d = parse_date(as_of_param)
                if d:
                    ctx = {**ctx, "as_of": d}
        return ctx


# ---------------------------
# Read-only resolve preview (no writes) — generic view
# ---------------------------
class PayStructureResolveView(generics.GenericAPIView):
    """
    GET /api/pay-structures/resolve/?on=YYYY-MM-DD&entity_id=<id>&code=<optional>
    Returns the active structure (preferring entity-scoped, else global) and
    each item augmented with its resolved global (as_of=on).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        on_str = request.query_params.get("on")
        if not on_str:
            return Response({"detail": "Query param 'on' (YYYY-MM-DD) is required."}, status=400)
        on = parse_date(on_str)
        if not on:
            return Response({"detail": "Invalid 'on' date."}, status=400)

        entity_id = request.query_params.get("entity_id")
        code = request.query_params.get("code")

        qs = (PayStructure.objects
              .filter(status=PayStructure.Status.ACTIVE)
              .filter(effective_from__lte=on)
              .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on)))
        if code:
            qs = qs.filter(code__iexact=code)

        if entity_id:
            s = (qs.filter(entity_id=entity_id).order_by("-effective_from").first()
                 or qs.filter(entity__isnull=True).order_by("-effective_from").first())
        else:
            s = qs.filter(entity__isnull=True).order_by("-effective_from").first()

        if not s:
            return Response({"detail": "No active PayStructure found for given filters."}, status=404)

        # Serialize header + items with as_of=on so item.read serializer resolves globals at that date
        ser = PayStructureReadSerializer(s, context={**self.get_serializer_context(), "as_of": on})
        return Response(ser.data, status=200)


# ---------------------------
# Apply structure to an entity (Option A) — generic view
# ---------------------------
class ApplyStructureToEntityView(generics.GenericAPIView):
    """
    POST /api/pay-structures/<pk>/apply/
    Body:
    {
      "entity_id": 101,
      "effective_from": "2025-09-01",   // default = structure.effective_from
      "effective_to": null,             // optional
      "replace": true,                  // default true
      "dry_run": false                  // true = preview only
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        try:
            structure = PayStructure.objects.get(pk=pk)
        except PayStructure.DoesNotExist:
            return Response({"detail": "PayStructure not found."}, status=status.HTTP_404_NOT_FOUND)

        entity_id = request.data.get("entity_id")
        if not entity_id:
            return Response({"detail": "entity_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        eff_from = parse_date(request.data.get("effective_from") or str(structure.effective_from))
        if not eff_from:
            return Response({"detail": "Invalid effective_from date."}, status=status.HTTP_400_BAD_REQUEST)

        eff_to = parse_date(request.data.get("effective_to")) if request.data.get("effective_to") else None
        replace = bool(request.data.get("replace", True))
        dry_run = bool(request.data.get("dry_run", False))

        result = apply_structure_to_entity(
            structure=structure,
            entity_id=int(entity_id),
            eff_from=eff_from,
            eff_to=eff_to,
            replace=replace,
            dry_run=dry_run,
        )
        return Response(result, status=status.HTTP_200_OK)
    


# --- Mixin: filter list by ?entity=<id> and auto-attach entity on POST
class EntityScopedListCreateMixin:
    entity_field = "entity"  # change if your FK is named differently

    def get_queryset(self):
        qs = super().get_queryset()
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            qs = qs.filter(**{f"{self.entity_field}_id": entity_id})
        return qs

    def perform_create(self, serializer):
        entity_id = self.request.query_params.get("entity") or self.request.data.get(self.entity_field)
        if entity_id and not self.request.data.get(self.entity_field):
            serializer.save(**{f"{self.entity_field}_id": entity_id})
        else:
            serializer.save()

# ---------- Options (list/create only)
class OptionSetListCreateAPIView(generics.ListCreateAPIView):
    queryset = OptionSet.objects.all().order_by("id")
    serializer_class = OptionSetSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {"key": ["exact", "icontains"], "entity": ["exact", "isnull"]}
    search_fields = ["key"]
    ordering_fields = ["id", "key"]
    ordering = ["id"]

class OptionListCreateAPIView(generics.ListCreateAPIView):
    queryset = Option.objects.select_related("set").all().order_by("id")
    serializer_class = OptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "set": ["exact"],                 # by set id
        "set__key": ["exact", "icontains"],
        "set__entity": ["exact", "isnull"],
        "code": ["exact", "icontains"],
        "is_active": ["exact"],
        "label": ["icontains"],
    }
    search_fields = ["label", "code", "set__key"]
    ordering_fields = ["sort_order", "label", "code", "id"]
    ordering = ["sort_order", "id"]

# ---------- Business structure (entity-scoped, list/create only)
class BusinessUnitListCreateAPIView(EntityScopedListCreateMixin, generics.ListCreateAPIView):
    queryset = BusinessUnit.objects.select_related("entity").all().order_by("id")
    serializer_class = BusinessUnitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["id", "entity","name"]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]

class DepartmentListCreateAPIView(EntityScopedListCreateMixin, generics.ListCreateAPIView):
    queryset = Department.objects.select_related("entity").all().order_by("id")
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["id", "entity","name"]
    search_fields = [ "name"]
    ordering_fields = ["name", "id"]

class LocationListCreateAPIView(EntityScopedListCreateMixin, generics.ListCreateAPIView):
    queryset = Location.objects.select_related("entity").all().order_by("id")
    serializer_class = LocationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["id", "entity","name"]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]

class CostCenterListCreateAPIView(EntityScopedListCreateMixin, generics.ListCreateAPIView):
    queryset = CostCenter.objects.select_related("entity").all().order_by("id")
    serializer_class = CostCenterSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["id", "entity","name"]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]


# EA_FK, EA_REL = fk_names(EmploymentAssignment, Employee)
# BA_FK, BA_REL = fk_names(EmployeeBankAccount,   Employee)
# DOC_FK, DOC_REL = fk_names(EmployeeDocument,    Employee)
# SI_FK,  SI_REL  = fk_names(EmployeeStatutoryIN, Employee)

class EmployeeListCreateAPIView(_g.ListCreateAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = [_p.IsAuthenticated]
    pagination_class = None  # optional: plain arrays

    def get_queryset(self):
        return (
            Employee.objects
            .select_related("statutory_in")  # OneToOne -> select_related
            .prefetch_related(
                Prefetch("assignments",   queryset=EmploymentAssignment.objects.all()),
                Prefetch("bank_accounts", queryset=EmployeeBankAccount.objects.all()),
                Prefetch("documents",     queryset=EmployeeDocument.objects.all()),
                Prefetch("compensations", queryset=EmployeeCompensation.objects.all()),
            )
            .order_by("id")
        )

class EmployeeDetailAPIView(_g.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = [_p.IsAuthenticated]

    def get_queryset(self):
        # same prefetch as list for consistent nested output
        return EmployeeListCreateAPIView().get_queryset()
    

def _active_on(queryset, on):
    return queryset.filter(
        effective_from__lte=on
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=on)
    )

class ManagersListView(generics.ListAPIView):
    """
    GET /api/payroll/managers/?on=YYYY-MM-DD&entity=<id>
    - on (optional): date to evaluate active assignments (default: today)
    - entity (optional): limit to employees within this entity
    Returns unique employees who are managers on that date, with direct_reports_count.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManagerListItemSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["full_name", "display_name", "code"]
    ordering_fields = ["full_name", "display_name", "id"]
    ordering = ["full_name", "display_name"]

    def get_queryset(self):
        on_str = self.request.query_params.get("on")
        on = parse_date(on_str) if on_str else date.today()

        active = _active_on(EmploymentAssignment.objects.all(), on)

        # Optional: restrict by entity (based on the employee’s entity)
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            active = active.filter(employee__entity_id=entity_id)

        # Distinct manager ids with at least one active report
        manager_ids = active.filter(manager_employee__isnull=False)\
                            .values_list("manager_employee_id", flat=True)\
                            .distinct()

        # Annotate each manager with a count of direct reports on 'on'
        reports_subq = active.filter(manager_employee_id=OuterRef("pk"))\
                             .values("manager_employee_id")\
                             .annotate(c=Count("id"))\
                             .values("c")[:1]

        qs = Employee.objects.filter(id__in=manager_ids)\
                             .annotate(
                                 direct_reports_count=Coalesce(
                                     Subquery(reports_subq, output_field=IntegerField()), 0
                                 )
                             )

        return qs

