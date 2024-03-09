from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
from payroll.serializers import salarycomponentserializer,employeeserializer,employeesalaryserializer,designationserializer,departmentserializer,reportingmanagerserializer,employeeListSerializer,employeeListfullSerializer
from payroll.models import salarycomponent,employee,employeesalary,designation,department
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
    


    

class employeeApiView(ListCreateAPIView):

    serializer_class = employeeserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['tdsreturn']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return employee.objects.filter(entity = entity)


class employeeupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = employeeserializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "employee"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return employee.objects.filter(entity = entity)
    


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
    


class employeeListApiView(ListAPIView):

    serializer_class = employeeListSerializer
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        queryset =  employee.objects.filter( Q(entity = entity)).values('employee','employee__email')

        #query = queryset.exclude(accounttrans__accounttype  = 'MD')

        #annotate(debit = Sum('accounttrans__debitamount',default = 0),credit = Sum('accounttrans__creditamount',default = 0))

       # print(queryset.query.__str__())
        return queryset
    


class employeeListfullApiView(RetrieveAPIView):

    serializer_class = employeeListfullSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "employee"

    
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
       # employeeid = self.request.query_params.get('employeeid')
        queryset =  employee.objects.filter( Q(entity = entity)).values('employee','employee__email','employee__first_name','employee__last_name','employeeid',)

        #query = queryset.exclude(accounttrans__accounttype  = 'MD')

        #annotate(debit = Sum('accounttrans__debitamount',default = 0),credit = Sum('accounttrans__creditamount',default = 0))

       # print(queryset.query.__str__())
        return queryset
    
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
