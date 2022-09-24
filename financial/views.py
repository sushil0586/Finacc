from django.http import request
from django.shortcuts import render

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from financial.models import account, accountHead
from financial.serializers import accountHeadSerializer,accountSerializer,accountSerializer2,accountHeadSerializer2,accountHeadSerializeraccounts,accountHeadMainSerializer,accountListSerializer
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
import os
import json
from django.db.models import Sum
from django.db.models import Q


class accountHeadApiView(ListCreateAPIView):

    serializer_class = accountHeadSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id','name','code']

    def perform_create(self, serializer):
        


            # id = accountHead.objects.get(id= 1)
            # account.objects.create(**json_data,accounthead = id)
            # print(json_data)
    

        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return accountHead.objects.filter(entity = entity)


class accountHeadupdatedelApiView(RetrieveUpdateDestroyAPIView):

    serializer_class = accountHeadSerializer2
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return accountHead.objects.filter(owner = self.request.user)




class customApiView2(ListAPIView):

    serializer_class = accountHeadSerializeraccounts
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'code':["in", "exact"]
    
    }

    # def perform_create(self, serializer):
    #     return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return accountHead.objects.filter(entity = entity)







class accountApiView2(ListAPIView):

    serializer_class = accountSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['gstno']

    # def perform_create(self, serializer):
    #     return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return account.objects.filter(entity = entity, accountcode = 4000)



class accountApiView3(ListAPIView):

    serializer_class = accountSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['accounthead']

    # def perform_create(self, serializer):
    #     return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return account.objects.filter(entity = entity)



class accountApiView(ListCreateAPIView):

    serializer_class = accountSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['gstno']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return account.objects.filter(entity = entity)



class accountListApiView(ListAPIView):

    serializer_class = accountListSerializer
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        queryset =  account.objects.filter( Q(entity = entity),Q(accounttrans__accounttype__isnull = True) | Q(accounttrans__accounttype__in = ['M','DD'])).values('accountname','city__cityname','id','gstno','pan','accounthead__name','creditaccounthead__name').annotate(debit = Sum('accounttrans__debitamount',default = 0),credit = Sum('accounttrans__creditamount',default = 0))

        #query = queryset.exclude(accounttrans__accounttype  = 'MD')

        #annotate(debit = Sum('accounttrans__debitamount',default = 0),credit = Sum('accounttrans__creditamount',default = 0))

        print(queryset.query.__str__())
        return queryset


class accountupdatedelApiView(RetrieveUpdateDestroyAPIView):

    serializer_class = accountSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return account.objects.filter(owner = self.request.user)



class accountheadApiView3(ListAPIView):

    serializer_class = accountHeadMainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['accounthead','balanceType']

    # def perform_create(self, serializer):
    #     return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return accountHead.objects.filter(entity = entity)