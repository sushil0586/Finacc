from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
from payroll.serializers import salarycomponentserializer,employeeserializer,employeesalaryserializer
from payroll.models import salarycomponent,employee,employeesalary
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
from entity.models import entity
from django_pandas.io import read_frame
from django.db.models import Q
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import timedelta,date,datetime
from django_pivot.pivot import pivot



class salarycomponentApiView(ListCreateAPIView):

    serializer_class = salarycomponentserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['tdsreturn']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return salarycomponent.objects.filter()
    

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