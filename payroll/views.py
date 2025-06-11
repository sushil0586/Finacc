from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
from payroll.serializers import salarycomponentserializer,employeesalaryserializer,designationserializer,departmentserializer,reportingmanagerserializer,EmployeeSerializer,EntityPayrollComponentConfigSerializer,CalculationTypeSerializer,BonusFrequencySerializer,CalculationValueSerializer,ComponentTypeSerializer,PayrollComponentSerializer
from payroll.models import salarycomponent,employeesalary,designation,department,EntityPayrollComponentConfig,employeenew,CalculationType, BonusFrequency, CalculationValue, ComponentType,PayrollComponent
from django.db import DatabaseError, transaction
from rest_framework.response import Response
from django.db.models import Sum,OuterRef,Subquery,F
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
    
class designationApiView(ListAPIView):

    serializer_class = designationserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['tdsreturn']

      
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return designation.objects.filter(entity = entity)
    


class departmentApiView(ListAPIView):

    serializer_class = departmentserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['tdsreturn']

      
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return department.objects.filter(entity = entity)
    



    




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
        configs = EntityPayrollComponentConfig.objects.filter(
            entity_id=entity_id,
            is_active=True
        ).select_related('component')

        serializer = EntityPayrollComponentConfigSerializer(configs, many=True)
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
