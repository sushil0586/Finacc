from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from invoice.models import salesOrderdetails,SalesOderHeader,purchaseorder,PurchaseOrderDetails,journal,salereturn,salereturnDetails,PurchaseReturn,Purchasereturndetails,StockTransactions,journalmain,entry,stockdetails,stockmain,goodstransaction,purchasetaxtype,tdsmain,tdstype,productionmain,tdsreturns,gstorderservices,jobworkchalan,jobworkchalanDetails,debitcreditnote,closingstock,purchaseorderimport
from invoice.serializers import SalesOderHeaderSerializer,salesOrderdetailsSerializer,purchaseorderSerializer,PurchaseOrderDetailsSerializer,POSerializer,SOSerializer,journalSerializer,SRSerializer,salesreturnSerializer,salesreturnDetailsSerializer,JournalVSerializer,PurchasereturnSerializer,\
purchasereturndetailsSerializer,PRSerializer,TrialbalanceSerializer,TrialbalanceSerializerbyaccounthead,TrialbalanceSerializerbyaccount,accountheadserializer,accountHead,accountserializer,accounthserializer, stocktranserilaizer,cashserializer,journalmainSerializer,stockdetailsSerializer,stockmainSerializer,\
PRSerializer,SRSerializer,stockVSerializer,stockserializer,Purchasebyaccountserializer,Salebyaccountserializer,entitySerializer1,cbserializer,ledgerserializer,ledgersummaryserializer,stockledgersummaryserializer,stockledgerbookserializer,balancesheetserializer,gstr1b2bserializer,gstr1hsnserializer,\
purchasetaxtypeserializer,tdsmainSerializer,tdsVSerializer,tdstypeSerializer,tdsmaincancelSerializer,salesordercancelSerializer,purchaseordercancelSerializer,purchasereturncancelSerializer,salesreturncancelSerializer,journalcancelSerializer,stockcancelSerializer,SalesOderHeaderpdfSerializer,productionmainSerializer,productionVSerializer,productioncancelSerializer,tdsreturnSerializer,gstorderservicesSerializer,SSSerializer,gstorderservicecancelSerializer,jobworkchallancancelSerializer,JwvoucherSerializer,jobworkchallanSerializer,debitcreditnoteSerializer,dcnoSerializer,debitcreditcancelSerializer,closingstockSerializer,balancesheetclosingserializer,purchaseorderimportSerializer,PISerializer
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
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


 



class tdsordelatestview(ListCreateAPIView):

    serializer_class = tdsVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = tdsmain.objects.filter(entityid= entity,entityfinid = entityfy).last()
        serializer = tdsVSerializer(id)
        return Response(serializer.data)


class tdstypeApiView(ListCreateAPIView):

    serializer_class = tdstypeSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id','tdsreturn']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        #entity = self.request.query_params.get('entity')
        return tdstype.objects.all()




class tdsreturnApiView(ListCreateAPIView):

    serializer_class = tdsreturnSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['tdsreturn']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return tdsreturns.objects.filter()




class tdsmainApiView(ListCreateAPIView):

    serializer_class = tdsmainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return tdsmain.objects.filter(entityid = entity)


class tdsmainApiView1(XLSXFileMixin, ReadOnlyModelViewSet):

    serializer_class = tdsmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = (XLSXRenderer,)
    filename = 'my_export.xlsx'
    column_header = {
        'titles': [
            "Column_1_name",
            "Column_2_name",
            "Column_3_name",
        ],
        'column_width': [17, 30, 17],
        'height': 25,
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': 'FFCCFFCC',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 14,
                'bold': True,
                'color': 'FF000000',
            },
        },
    }
    body = {
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': 'FFCCFFCC',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 14,
                'bold': False,
                'color': 'FF000000',
            }
        },
        'height': 40,
    }
    column_data_styles = {
        'distance': {
            'alignment': {
                'horizontal': 'right',
                'vertical': 'top',
            },
            'format': '0.00E+00'
        },
        'created_at': {
            'format': 'd.m.y h:mm',
        }
    }
    

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']


    def get_queryset(self):
            entity = self.request.query_params.get('entity')
            id = tdsmain.objects.filter(entityid = entity)
           
            return id

    # def get(self,request):
    #     entity = self.request.query_params.get('entity')
    #     id = tdsmain.objects.filter(entityid = entity)
    #     serializer = tdsmainSerializer(id,many=True)
    #     return Response(serializer.data)    

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)
    
    # def get_queryset(self):

    #     entity = self.request.query_params.get('entity')
    #     return tdsmain.objects.filter(entityid = entity)



class tdsmainupdatedel(RetrieveUpdateDestroyAPIView):

    serializer_class = tdsmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return tdsmain.objects.filter(entityid = entity)


class tdsmaincancel(RetrieveUpdateDestroyAPIView):

    serializer_class = tdsmaincancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return tdsmain.objects.filter(entityid = entity)

class salesordercancel(RetrieveUpdateDestroyAPIView):

    serializer_class = salesordercancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return SalesOderHeader.objects.filter(entity = entity)



class gstservicescancel(RetrieveUpdateDestroyAPIView):

    serializer_class = gstorderservicecancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return gstorderservices.objects.filter(entity = entity)


class purchaseordercancel(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseordercancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity = entity)
    

class jobworkchalancancel(RetrieveUpdateDestroyAPIView):

    serializer_class = jobworkchallancancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return jobworkchalan.objects.filter(entity = entity)


class purchasereturncancel(RetrieveUpdateDestroyAPIView):

    serializer_class = purchasereturncancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return PurchaseReturn.objects.filter(entity = entity)

class journalmaincancel(RetrieveUpdateDestroyAPIView):

    serializer_class = journalcancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return journalmain.objects.filter(entity = entity)



class productionmaincancel(UpdateAPIView):

    serializer_class = productioncancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return journalmain.objects.filter(entity = entity)





class stockmaincancel(RetrieveUpdateDestroyAPIView):

    serializer_class = stockcancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return stockmain.objects.filter(entity = entity)


class salesreturncancel(RetrieveUpdateDestroyAPIView):

    serializer_class = salesreturncancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salereturn.objects.filter(entity = entity)


class tdsmainpreviousapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = tdsmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        #vouchertype = self.request.query_params.get('vouchertype')
        return tdsmain.objects.filter(entityid = entity)



class purchasetaxtypeApiView(ListCreateAPIView):

    serializer_class = purchasetaxtypeserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return purchasetaxtype.objects.filter(entity = entity)


class SalesOderHeaderApiView(ListCreateAPIView):

    serializer_class = SalesOderHeaderSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['billno','sorderdate','entityfinid']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')

     
     


        return SalesOderHeader.objects.filter(entity = entity)
    

class gstorderservicesApiView(ListCreateAPIView):

    serializer_class = gstorderservicesSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['billno','orderdate','entityfinid','orderType']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return gstorderservices.objects.filter(entity = entity)



class gstserviceupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = gstorderservicesSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return gstorderservices.objects.filter(entity = entity)


class gstserviceprevnextview(RetrieveAPIView):

    serializer_class = gstorderservicesSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "billno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        ordertype = self.request.query_params.get('ordertype')
        return gstorderservices.objects.filter(entity = entity,orderType = ordertype)


class salesOrderdetailsApiView(ListCreateAPIView):

    serializer_class = salesOrderdetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        return salesOrderdetails.objects.filter()


        


class salesOrderpdfview(RetrieveAPIView):

    serializer_class = SalesOderHeaderpdfSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return SalesOderHeader.objects.filter(entity = entity).prefetch_related('salesorderdetails')

class salesOrderupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = SalesOderHeaderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return SalesOderHeader.objects.filter(entity = entity).prefetch_related('salesorderdetails')


class salesOrderpreviousview(RetrieveAPIView):

    serializer_class = SalesOderHeaderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "billno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        #billno = self.request.query_params.get('billno')
        return SalesOderHeader.objects.filter(entity = entity)



class salesorderlatestview(ListAPIView):

    serializer_class = SOSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
      #  entityfy = enti
        id = SalesOderHeader.objects.filter(entity= entity,entityfinid = entityfy).last()
        serializer = SOSerializer(id)
        return Response(serializer.data)


class gstorderlatestview(ListAPIView):

    serializer_class = SSSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        ordertype = self.request.query_params.get('ordertype')
        entityfy = self.request.query_params.get('entityfinid')
        id = gstorderservices.objects.filter(entity= entity,orderType = ordertype,entityfinid = entityfy).last()
        serializer = SSSerializer(id)
        return Response(serializer.data)




class purchasereturnlatestview(ListAPIView):

    serializer_class = PRSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = PurchaseReturn.objects.filter(entity= entity,entityfinid = entityfy).last()
        serializer = PRSerializer(id)
        return Response(serializer.data)


class PurchaseReturnApiView(ListCreateAPIView):

    serializer_class = PurchasereturnSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['billno','sorderdate','entityfinid']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return PurchaseReturn.objects.filter(entity = entity)


class PurchaseReturnupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = PurchasereturnSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return PurchaseReturn.objects.filter(entity = entity)


class PurchaseReturnpreviousview(RetrieveAPIView):

    serializer_class = PurchasereturnSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "billno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        #billno = self.request.query_params.get('billno')
        return PurchaseReturn.objects.filter(entity = entity)

class PurchaseReturnlatestview(ListCreateAPIView):

    serializer_class = PRSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = PurchaseReturn.objects.filter(entity= entity,entityfinid=entityfy).last()
        serializer = PRSerializer(id)
        return Response(serializer.data)






        ############################################################


class purchaseorderApiView(ListCreateAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']
    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity = entity)
    

class purchaseorderimportApiView(ListCreateAPIView):

    serializer_class = purchaseorderimportSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']
    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorderimport.objects.filter(entity = entity)


class jobworkchalanApiView(ListCreateAPIView):

    serializer_class = jobworkchallanSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return jobworkchalan.objects.filter(entity = entity)


class PurchaseOrderDetailsApiView(ListCreateAPIView):

    serializer_class = PurchaseOrderDetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return PurchaseOrderDetails.objects.filter()
    

class jobworkchalanupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = jobworkchallanSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return jobworkchalan.objects.filter()


class purchaseorderupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter()


class purchaseorderimportupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderimportSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorderimport.objects.filter()


class purchaseorderpreviousview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity =entity)

class purchaseorderimportpreviousview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderimportSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorderimport.objects.filter(entity =entity)


class jobworkchalanpreviousview(RetrieveAPIView):

    serializer_class = jobworkchallanSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        ordertype = self.request.query_params.get('ordertype')
        return jobworkchalan.objects.filter(entity =entity,ordertype= ordertype)

class purchaseordelatestview(ListAPIView):

    serializer_class = POSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = purchaseorder.objects.filter(entity= entity,entityfinid = entityfy).last()
        serializer = POSerializer(id)
        return Response(serializer.data)
    
class jobworklatestview(ListAPIView):

    serializer_class = JwvoucherSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        ordertype = self.request.query_params.get('ordertype')
        id = jobworkchalan.objects.filter(entity= entity,ordertype = ordertype,entityfinid = entityfy).last()
        serializer = JwvoucherSerializer(id)
        return Response(serializer.data)



# class purchaseordelatestview(ListCreateAPIView):

#     serializer_class = POSerializer
#     permission_classes = (permissions.IsAuthenticated,)

#     filter_backends = [DjangoFilterBackend]
#     def get(self,request):
#         entity = self.request.query_params.get('entity')
#         id = purchaseorder.objects.filter(entity= entity).last()
#         serializer = POSerializer(id)
#         return Response(serializer.data)




class gstview(ListCreateAPIView):

   # serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def list(self,request):
        entity = self.request.query_params.get('entity')
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)
        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')
        df = read_frame(stk)
        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)
        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
        dfb2b = df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values()
    #    # df['account__accounthead'] = -1

    #    # return Response(df)
    #     return  Response(df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())
    #     id = list(journalmain.objects.filter(entity= entity,vouchertype = 'J').values())
        #serializer = JournalVSerializer(id)


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

       

        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)


        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
       # df['account__accounthead'] = -1

       # return Response(df)
        dfb2clarge =  df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values()

        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

       

        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)




        df['type'] = 'OE'
        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
       # df['account__accounthead'] = -1

       # return Response(df)
        dfbebsmall =  df.groupby(['type','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values()

        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('product__hsn','product__productname','product__unitofmeasurement__unitname','orderqty','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        

        df.rename(columns = {'product__hsn':'hsn', 'product__productname':'description','product__unitofmeasurement__unitname':'uqc','orderqty':'totalquantity','linetotal':'totalvalue','product__totalgst':'rate','amount':'taxablevalue'}, inplace = True)


       
        dfhsn =  df.groupby(['hsn','description','uqc','rate'])[['totalquantity','totalvalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values()

        return Response({"gstb2b": dfb2b,
                     "gstb2blarge": dfb2clarge,"gstb2bsmall": dfbebsmall,"gsthsn": dfhsn},
                    status=status.HTTP_200_OK)
        #return Response(serializer.data)



        

class journalordelatestview(ListCreateAPIView):

    serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = journalmain.objects.filter(entity= entity,vouchertype = 'J',entityfinid = entityfy).last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)


class stockordelatestview(ListCreateAPIView):

    serializer_class = stockVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = stockmain.objects.filter(entity= entity,vouchertype = 'PC',entityfinid = entityfy).last()
        serializer = stockVSerializer(id)
        return Response(serializer.data)






class productionlatestview(ListCreateAPIView):

    serializer_class = productionVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = productionmain.objects.filter(entity= entity,vouchertype = 'PV', entityfinid = entityfy).last()
        serializer = productionVSerializer(id)
        return Response(serializer.data)


class bankordelatestview(ListCreateAPIView):

    serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = journalmain.objects.filter(entity= entity,vouchertype = 'B',entityfinid = entityfy).last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)


class cashordelatestview(ListCreateAPIView):

    serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = journalmain.objects.filter(entity= entity,vouchertype = 'C',entityfinid = entityfy).last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)



class salesreturnApiView(ListCreateAPIView):

    serializer_class = salesreturnSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']

    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salereturn.objects.filter(entity = entity)



class journalmainApiView(ListCreateAPIView):

    serializer_class = journalmainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid','vouchertype']

    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return journalmain.objects.filter(entity = entity)



class journalmainupdateapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = journalmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return journalmain.objects.filter(entity = entity)




class productionmainApiView(ListCreateAPIView):

    serializer_class = productionmainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']

    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return productionmain.objects.filter(entity = entity)



class productionmainupdateapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = productionmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return productionmain.objects.filter(entity = entity)




class stockmainApiView(ListCreateAPIView):

    serializer_class = stockmainSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherno','voucherdate','entityfinid']

    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return stockmain.objects.filter(entity = entity)



class stockmainupdateapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = stockmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return stockmain.objects.filter(entity = entity)



class journalmainpreviousapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = journalmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        vouchertype = self.request.query_params.get('vouchertype')
        return journalmain.objects.filter(entity = entity,vouchertype=vouchertype)


class stockmainpreviousapiview(RetrieveUpdateDestroyAPIView):

    serializer_class = stockmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
       # vouchertype = self.request.query_params.get('vouchertype')
        return stockmain.objects.filter(entity = entity)


class productionpreviousapiview(RetrieveAPIView):

    serializer_class = productionmainSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
       # vouchertype = self.request.query_params.get('vouchertype')
        return productionmain.objects.filter(entity = entity)





class salesreturnlatestview(ListCreateAPIView):

    serializer_class = SRSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = salereturn.objects.filter(entity= entity,entityfinid = entityfy ).last()
        serializer = SRSerializer(id)
        return Response(serializer.data)
    

class purchaseimportlatestview(ListCreateAPIView):

    serializer_class = PISerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = purchaseorderimport.objects.filter(entity= entity,entityfinid = entityfy).last()
        serializer = PISerializer(id)
        return Response(serializer.data)


class salesreturnupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = salesreturnSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salereturn.objects.filter()


class salesreturnpreviousview(RetrieveUpdateDestroyAPIView):

    serializer_class = salesreturnSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return salereturn.objects.filter(entity =entity)
    




class JournalApiView(ListCreateAPIView):

    serializer_class = journalSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']


    def create(self, request, *args, **kwargs):  

        serializer = self.get_serializer(data=request.data, many=True)  
        serializer.is_valid(raise_exception=True)  
  
        try:  
            serializer.save(createdby = self.request.user)
           # self.perform_create(serializer)  
            return Response(serializer.data)  
        except:  
            return Response(serializer.errors)  

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return journal.objects.filter(entity = entity)


class tdslist(ListAPIView):

    serializer_class = TrialbalanceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        tdsreturn = self.request.query_params.get('tdsreturn')
        #print(enddate)

       # yesterday = date.today() - timedelta(days = 100)

       # startdate1 = self.request.query_params.get('startdate')
        #stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0) )
       # stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead','account_id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))


        obp =tdsmain.objects.filter(entityid = entity,isactive = 1,voucherdate__range=(startdate, enddate),tdstype__tdsreturn = tdsreturn).values('creditaccountid__accountname','creditaccountid__pan','tdstype__tdssection','voucherdate','debitamount','tdsrate','tdsvalue','surchargerate','surchargevalue','cessrate','cessvalue','hecessrate','hecessvalue','grandtotal','depositdate','tdstype__tdstypename')
        # obn =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lt = 0)
        # ob = obp.union(obn)

        #print(ob)

        df = read_frame(obp)
        df.insert(0, 'S_No', range(1, 1 + len(df)))

    #     print(df)

        df.rename(columns = {'creditaccountid__accountname':'deducteeaccountname', 'creditaccountid__pan':'deducteepan','tdstype__tdssection':'tdssection','tdstype__tdstypename':'deductionremarks'}, inplace = True)

    #     dffinal1 = df.groupby(['accounthead','accountheadname'])[['balance1']].sum().reset_index()

    #     print(dffinal1)

    #     stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
    #     stk2 =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)
    #     stkunion = stk.union(stk2)

    #     df = read_frame(stkunion)

    #     print(df)
        
    #     df['drcr'] = 'CR'

    #     df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
    #     df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
    #     df['debit'] = np.where(df['balance'] > 0, df['balance'],0)
    #     #df['credit'] = df['balance'].apply(lambda x: df['balance'] if x < 0 else 0)
    #     #df['debit'] = df['balance'].apply(lambda x: 0 if x < 0 else df['balance'])

    #    #print(df)
        

    


    #     df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__id':'account'}, inplace = True)

    #     dffinal = df.groupby(['accounthead','accountheadname','drcr'])[['debit','credit','balance']].sum().abs().reset_index()

    #     df = pd.merge(dffinal,dffinal1,on='accounthead',how='outer',indicator=True)


    #     if 'balance1' in df.columns:
    #         df['balance1'] = df['balance1']
    #     else:
    #         df['balance1'] = 0

        
    #     if 'debit' in df.columns:
    #         df['debit'] = df['debit']
    #     else:
    #         df['debit'] = 0

        
    #     if 'credit' in df.columns:
    #         df['credit'] = df['credit']
    #     else:
    #         df['credit'] = 0

        



        

        

        
    #     df['debit'] = df['debit'].fillna(0)
    #     df['credit'] = df['credit'].fillna(0)
    #     df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'])
    #     df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
    #     # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
    #     # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
    #     df['accountheadname'] = np.where(df['_merge'] == 'right_only', df['accountheadname_y'],df['accountheadname_x'])
    #     df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
    #     df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')

    #     df = df.drop(['accountheadname_y', 'accountheadname_x','_merge','balance1'],axis = 1)

    #     print(df)


      
        return Response(df.T.to_dict().values())


class TrialbalanceApiView(ListAPIView):

    serializer_class = TrialbalanceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        #print(enddate)

       # yesterday = date.today() - timedelta(days = 100)

       # startdate1 = self.request.query_params.get('startdate')

       #'account__accounthead__name','account__accounthead'
        #stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0) )
       # stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead','account_id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))


        obp =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gte = 0)
        obn =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt= startdate).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lt = 0)
        ob = obp.union(obn)

        #print(ob)

        df = read_frame(ob)

        print(df)

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead'}, inplace = True)

        dffinal1 = df.groupby(['accounthead','accountheadname'])[['balance1']].sum().reset_index()

        print(dffinal1)

        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__lt = 0)
        stkunion = stk.union(stk2)

        print(stkunion.query.__str__())

        df = read_frame(stkunion)

        print(df)
        
        df['drcr'] = 'CR'

        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'],0)
        #df['credit'] = df['balance'].apply(lambda x: df['balance'] if x < 0 else 0)
        #df['debit'] = df['balance'].apply(lambda x: 0 if x < 0 else df['balance'])

       #print(df)
        

    


        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead'}, inplace = True)

        dffinal = df.groupby(['accounthead','accountheadname','drcr'])[['debit','credit','balance','quantity']].sum().abs().reset_index()

        df = pd.merge(dffinal,dffinal1,on='accounthead',how='outer',indicator=True)


        if 'balance1' in df.columns:
            df['balance1'] = df['balance1']
        else:
            df['balance1'] = 0

        
        if 'debit' in df.columns:
            df['debit'] = df['debit']
        else:
            df['debit'] = 0

        
        if 'credit' in df.columns:
            df['credit'] = df['credit']
        else:
            df['credit'] = 0

        
        if 'quantity' in df.columns:
            df['quantity'] = df['quantity']
        else:
            df['quantity'] = 0

        



        

        

        
        df['debit'] = df['debit'].astype(float).fillna(0)
        df['credit'] = df['credit'].astype(float).fillna(0)
        df['quantity'] = df['quantity'].astype(float).fillna(0)
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'].astype(float).fillna(0))
        df['openingbalance'] =  df['openingbalance'].astype(float).fillna(0)
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
        df['balance'] =  df['balance'].astype(float).fillna(0)
        # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
        # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
        df['accountheadname'] = np.where(df['_merge'] == 'right_only', df['accountheadname_y'],df['accountheadname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        df = df.drop(['accountheadname_y', 'accountheadname_x','_merge','balance1'],axis = 1)

        df = df.sort_values(by=['accountheadname'])


        print(df)


      
        return Response(df.T.to_dict().values())


class TrialbalancebyaccountheadApiView(ListAPIView):

    serializer_class = TrialbalanceSerializerbyaccounthead
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account__accounthead']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        accounthead = self.request.query_params.get('accounthead')
        drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        if drcrgroup == 'DR':

            ob =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gte = 0)
            stk =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gte = 0)
            #return stk
        
        elif drcrgroup == 'CR':

            ob =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lte = 0)
            stk =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__lt = 0)

        else:

            ob =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))
            stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))




        
        df = read_frame(stk)
        df['drcr'] = 'CR'

        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'],0)

        

        df.rename(columns = {'account__accountname':'accountname','account__id':'account','account__accounthead': 'accounthead__id'}, inplace = True)


        obdf = read_frame(ob)


        if 'balance1' in df.columns:
            df['balance1'] = df['balance1']
        else:
            df['balance1'] = 0

        
        if 'debit' in df.columns:
            df['debit'] = df['debit']
        else:
            df['debit'] = 0

        
        if 'credit' in df.columns:
            df['credit'] = df['credit']
        else:
            df['credit'] = 0

        

       # obdf['drcr'] = obdf['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        obdf.rename(columns = {'account__accountname':'accountname','account__id':'account'}, inplace = True)

        #obdf['drcr'] = obdf['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        obdf = obdf.groupby(['accountname','account'])[['balance1']].sum().reset_index()

      #  print(obdf)



        df = df.groupby(['accounthead__id','accountname','drcr','account'])[['debit','credit','balance','quantity']].sum().abs().reset_index()

        df = pd.merge(df,obdf,on='account',how='outer',indicator=True)


        if 'balance1' in df.columns:
            df['balance1'] = df['balance1']
        else:
            df['balance1'] = 0

        
        if 'debit' in df.columns:
            df['debit'] = df['debit']
        else:
            df['debit'] = 0

        
        if 'credit' in df.columns:
            df['credit'] = df['credit']
        else:
            df['credit'] = 0

        if 'quantity' in df.columns:
            df['quantity'] = df['quantity']
        else:
            df['quantity'] = 0

        df['debit'] = df['debit'].fillna(0).astype(float)
        df['credit'] = df['credit'].fillna(0).astype(float)
        df['quantity'] = df['quantity'].astype(float).fillna(0)
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'].astype(float))
        df['openingbalance'] = df['openingbalance'].astype(float)
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
        df['balance'] = df['balance'].astype(float)
        # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
        # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
        df['accountname'] = np.where(df['_merge'] == 'right_only', df['accountname_y'],df['accountname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['accounthead'] = accounthead

        df = df.drop(['accountname_y', 'accountname_x','_merge','balance1','accounthead__id','accounthead'],axis = 1)

        print(df)
        
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())
    
class ledgersummarylatest(ListAPIView):

    serializer_class = TrialbalanceSerializerbyaccounthead
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account__accounthead']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        # accounthead = self.request.query_params.get('accounthead')
        # drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        # if drcrgroup == 'DR':

        #     ob =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gte = 0)
        #     stk =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        #     #return stk
        
        # elif drcrgroup == 'CR':

        #     ob =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lte = 0)
        #     stk =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)

        # else:

        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))




        
        df = read_frame(stk)
        df['drcr'] = 'CR'

        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'],0)

        

        df.rename(columns = {'account__accountname':'accountname','account__id':'account','account__accounthead': 'accounthead__id'}, inplace = True)


        obdf = read_frame(ob)


        if 'balance1' in df.columns:
            df['balance1'] = df['balance1']
        else:
            df['balance1'] = 0

        
        if 'debit' in df.columns:
            df['debit'] = df['debit']
        else:
            df['debit'] = 0

        
        if 'credit' in df.columns:
            df['credit'] = df['credit']
        else:
            df['credit'] = 0

       # obdf['drcr'] = obdf['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        obdf.rename(columns = {'account__accountname':'accountname','account__id':'account'}, inplace = True)

        #obdf['drcr'] = obdf['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        obdf = obdf.groupby(['accountname','account'])[['balance1']].sum().reset_index()

      #  print(obdf)



        df = df.groupby(['accounthead__id','accountname','drcr','account'])[['debit','credit','balance','quantity']].sum().abs().reset_index()

        df = pd.merge(df,obdf,on='account',how='outer',indicator=True)


        if 'balance1' in df.columns:
            df['balance1'] = df['balance1']
        else:
            df['balance1'] = 0

        
        if 'debit' in df.columns:
            df['debit'] = df['debit']
        else:
            df['debit'] = 0

        
        if 'credit' in df.columns:
            df['credit'] = df['credit']
        else:
            df['credit'] = 0

        df['debit'] = df['debit'].fillna(0).astype(float)
        df['credit'] = df['credit'].fillna(0).astype(float)
        df['quantity'] = df['quantity'].fillna(0).astype(float)
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'].astype(float))
        df['openingbalance'] = df['openingbalance'].astype(float)
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
        df['balance'] = df['balance'].astype(float)
        # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
        # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
        df['accountname'] = np.where(df['_merge'] == 'right_only', df['accountname_y'],df['accountname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        #df['accounthead'] = accounthead

        df = df.drop(['accountname_y', 'accountname_x','_merge','balance1','accounthead__id','obdrcr','drcr'],axis = 1)

        print(df)

        df.rename(columns = {'account__accountname':'accountname','account':'id','account__accounthead': 'accounthead__id','balance':'balancetotal'}, inplace = True)
        
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())

class TrialbalancebyaccountApiView(ListAPIView):

    serializer_class = TrialbalanceSerializerbyaccount
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        account1 = self.request.query_params.get('account')
      #  accountheadp = self.request.query_params.get('accounthead')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accountname','transactiontype','transactionid','entrydatetime','desc').annotate(debit = Sum('debitamount'),credit = Sum('creditamount'),quantity = Sum('quantity')).order_by('entrydatetime')
        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accountname').annotate(debit = Sum('debitamount'),credit = Sum('creditamount'),quantity = Sum('quantity')).order_by('entrydatetime')
        df1 = read_frame(ob)
        df1['desc'] = 'Opening Balance'
        df1['entrydatetime'] = startdate
        #print(df1)
        df = read_frame(stk)    

        print(df)

        union_dfs = pd.concat([df1, df], ignore_index=True)
        #print(union_dfs)

        #ob = df1.union(df)

        union_dfs['transactiontype'] = union_dfs['transactiontype'].fillna('')
       # union_dfs['id'] = union_dfs['id'].fillna(0)
        union_dfs['transactionid'] = union_dfs['transactionid'].fillna('')
        union_dfs['desc'] = union_dfs['desc'].fillna('')
        union_dfs['entrydatetime'] = pd.to_datetime(union_dfs['entrydatetime']).dt.strftime('%d-%m-%Y')
        union_dfs['sortdatetime'] = pd.to_datetime(union_dfs['entrydatetime'])
        #union_dfs['entrydatetime'] = union_dfs['desc'].fillna(startdate)
       # print(union_dfs)
        #print(stk)

      #  union_dfs['entrydatetime'] = pd.to_datetime(union_dfs['entrydatetime'])

        

        print(union_dfs.sort_values(by=['entrydatetime']))
        return Response(union_dfs.sort_values(by=['entrydatetime']).T.to_dict().values())



class Trialview(ListAPIView):

    serializer_class = entitySerializer1
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']
    def get_queryset(self):
        #entity = self.request.query_params.get('entity')
        entity1 = self.request.query_params.get('entity')

        # stk = accountHead.objects.prefetch_related(Prefetch('headtrans',queryset = account.objects.prefetch_related(Prefetch('headtrans', queryset=StockTransactions.objects.filter(
        #         entity=entity).order_by('entity'))))to_attr='accounthead_transactions')

        
        # stk = accountHead.objects.prefetch_related(Prefetch('headtrans', queryset=StockTransactions.objects.filter(
        #         entity=entity).order_by('entity'), to_attr='accounthead_transactions')
        # )

        stk = entity.objects.filter(id = entity1).prefetch_related('entity_accountheads','entity_accountheads__headtrans').all()
        
        return stk



class Trialviewaccount(ListAPIView):

    serializer_class = accountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')

        queryset1=StockTransactions.objects.filter(entity=entity).order_by('entity').only('account__accountname','transactiontype','transactionid','entrydatetime','desc','debitamount','creditamount')

        #print(connection.queries[-1])

        #print(queryset1.values())

        queryset=account.objects.prefetch_related(Prefetch('accounttrans', queryset=queryset1,to_attr='account_transactions'))

        print(queryset.query.__str__())
      #  print(connection.queries[])


        

        
        #stk = account.objects.prefetch_related(Prefetch('accounthead_accounts', queryset=queryset1, to_attr='account_transactions')
        
     
        return queryset




class generalfunctions:

    def __init__(self, entityid,startdate,enddate):
        self.entityid = entityid
        self.startdate = startdate
        self.enddate = enddate

    
        

    def getstockdetails(self):
        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = self.entityid),Q(entrydatetime__range=(self.startdate, self.enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = self.entityid),Q(entrydatetime__range=(self.startdate, self.enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)
        stkunion = stk.union(stk2)
        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)
        return df

    def getinventorydetails(self):
        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg

        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = self.entityid),Q(entrydatetime__lt  = self.enddate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock__id','stock__productname','rate','stockttype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lt  = self.enddate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock__id','stock__productname','rate','stockttype','quantity','entrydatetime')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = self.entityid).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
       # idf = read_frame(inventory)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','R','OS']), idf['quantity'],-1 * (idf['quantity']))
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock__id','stockttype'])['quantity'].cumsum()
        dfR = idf.groupby(['stock__id'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        return dfR
       

    def getinventorydetails_1(self,dfR_1):
        dfR_1['balance'] = dfR_1['quantity'].astype(float) * -1 * dfR_1['closingrate'].astype(float)
        dfR_1 = dfR_1.drop(['account__id','stockttype','entrydatetime','account__accountname','closingrate','_merge'],axis=1) 
        dfR_1.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        dfR_1['account__accounthead__name'] = 'Closing Stock'
        dfR_1['account__accounthead'] = -1
        return dfR_1

    def getinventorydetails_2(self,dfi):
        dfi['balance'] = dfi['quantity'].astype(float) * 1 * dfi['closingrate'].astype(float)
        dfi = dfi.drop(['account__id','stockttype','entrydatetime','account__accountname','closingrate','_merge'],axis=1) 
        dfi.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        dfi['account__accounthead__name'] = 'Closing Stock'
        dfi['account__accounthead'] = -1
        return dfi

    def openinginventorydetails(self):
        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg

        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','R']),Q(accounttype = 'DD'),Q(entity = self.entityid),Q(entrydatetime__lt = self.startdate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lt = self.startdate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        idf = read_frame(oinventory)
        closingprice = closingstock.objects.filter(entity = self.entityid).values('stock__id','closingrate')

        cdf = read_frame(closingprice)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','OS','R']), idf['quantity'],-1 * (idf['quantity']))
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        return odfR

    def openinginventorydetails_1(self,odfi):
        odfi['balance'] = odfi['quantity'].astype(float) * -1 * odfi['closingrate'].astype(float)
        odfi = odfi.drop(['account__id','stockttype','entrydatetime','account__accountname','closingrate','_merge'],axis=1) 
        odfi.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfi['account__accounthead__name'] = 'Opening Stock'
        odfi['account__accounthead'] = -5
        return odfi

    def openinginventorydetails_2(self,odfR):
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['closingrate'].astype(float)
        odfR = odfR.drop(['stock','stockttype','entrydatetime','account__id','account__accountname','closingrate','_merge'],axis=1) 
        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = -5
        return odfR


    def getprofitandloss(self):
        pl1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = self.entityid),Q(entrydatetime__range=(self.startdate, self.enddate))).filter(account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = self.entityid),Q(entrydatetime__range=(self.startdate, self.enddate))).filter(account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
        pldf = pldf.drop(['debit','credit'],axis=1)




        return pldf




class balancestatementxl(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']
    

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk = generalfunctions(entityid = entity1,startdate= startdate,enddate=enddate)

        dfR = stk.getinventorydetails()
        dfRFinal = stk.getinventorydetails_1(dfR_1 = dfR)
        dfi = stk.getinventorydetails_2(dfi = dfR)
     


        odfR = stk.openinginventorydetails()
        odfi = stk.openinginventorydetails_1(odfi = odfR)
        odfR = stk.openinginventorydetails_2(odfR= odfR)
                  
        
        df = stk.getstockdetails()
         

        frames = [odfR,df, dfRFinal]

        df = pd.concat(frames)

      

        df['balance'] = df['balance'].astype(float)


        pldf = stk.getprofitandloss()

        


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        bs1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gt = 0)
        bs2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)

        bsunion = bs1.union(bs2)

        bsdf = read_frame(bsunion)
        bsdf = bsdf.drop(['debit','credit'],axis=1)


       

        pldf['balance'] = pldf['balance'].apply(Decimal)

       

        if pldf['balance'].sum() < 0:
            bsdf.loc[len(bsdf.index)] = ['Net Profit', -2, -2, 'Net Profit',pldf['balance'].sum()]
        else:
            bsdf.loc[len(bsdf.index)] = ['Net Loss', -2, -2, 'Net Loss',pldf['balance'].sum()]

        
        frames = [bsdf, dfi,odfi]

        bsdf = pd.concat(frames)


        bsdf['balance'] = bsdf['balance'].astype(float)
        bsdf['drcr'] = bsdf['balance'].apply(lambda x: 0 if x > 0 else 1)
        bsdf.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)
        bsdf = bsdf.sort_values(by=['accounthead'],ascending=False)
        print(bsdf)

        df = bsdf


        df1 = df.groupby(["drcr"]).balance.sum().reset_index()

        print(df1)

        for drcr in df1.itertuples():

            print(drcr)
            for df2,df3 in df.groupby(["drcr"]):
                print(df2)
                print(df3)

            #print(df2)


        #df = bsdf.groupby(['drcr', 'accounthead','accountid'])['balance'].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values()

        #return Response(df)

        #df['sum1'] = df.groupby(by=["accounthead","drcr"]).apply(lambda grp: grp.balance.sum())


        #df1 = df.groupby(["drcr"]).apply(lambda x : x.groupby("accounthead").to_dict('records')).balance.sum()
        # for drcr,dfdrcr in df1:
        #     print(drcr)
        #     print(dfdrcr)


    #     j = (df.groupby(['drcr'])
    #    .apply(lambda x: x.groupby(by="accountheadname",as_index=True)
    #    .agg({'balance':'sum'}).to_dict())
    #    .reset_index()
    #    .rename(columns={0:'Accountheads'})
    #    .to_json(orient='records'))


    #     j = (df.groupby(['drcr'])
    #    .apply(lambda x: x.groupby("accountheadname")[["balance"]].sum().to_dict('records'))
    #    .reset_index()
    #    .rename(columns={0:'Tide-Data'})
    #    .to_json(orient='records'))


    #     print(j)


        #df = df.groupby('split')[['Chain','Food','Healthy']].apply(lambda x: x.set_index('Chain').to_dict(orient='index')).to_dict()



        #print(j)




       # return Response(df)



        # print(df)


        # j = df.groupby(by="drcr").apply(lambda x : x.groupby(by = "accountheadname").apply(lambda grp: grp.groupby(["accountname"]).balance.sum().to_dict()).to_dict()).reset_index().rename(columns={0:'Tide-Data'}).to_json(orient='records')




        # print(j)


        


        #df = df.groupby("drcr").apply(lambda x : x.groupby("accountheadname").apply(lambda y : y.groupby("accountname")[['balance']].sum()))
       # df = bsdf.groupby(["accounthead","accountheadname"]).apply(lambda grp: grp.groupby(by="accountheadname")[["balance"]].sum())

      # import json
       # json_res = list(map(json.dumps, df))

        #print(df)

        #return Response(df)


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


        return Response(df.groupby("drcr").apply(lambda grp1: grp1.groupby(["accounthead","accountheadname"]).apply(lambda grp: grp.groupby(['accountid','accountname']).balance.sum().reset_index().T.to_dict().values()).reset_index().rename(columns={0:'accounts'}).T.to_dict().values()).reset_index().rename(columns={0:'accountheads'}).T.to_dict().values())


     







class balancestatement(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']
    

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk = generalfunctions(entityid = entity1,startdate= startdate,enddate=enddate)

        dfR = stk.getinventorydetails()
        dfRFinal = stk.getinventorydetails_1(dfR_1 = dfR)
        dfi = stk.getinventorydetails_2(dfi = dfR)
     


        odfR = stk.openinginventorydetails()
        odfi = stk.openinginventorydetails_1(odfi = odfR)
        odfR = stk.openinginventorydetails_2(odfR= odfR)
                  
        
        df = stk.getstockdetails()
         

        frames = [odfR,df, dfRFinal]

        df = pd.concat(frames)

      

        df['balance'] = df['balance'].astype(float)


        pldf = stk.getprofitandloss()

        


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        bs1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gt = 0)
        bs2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)

        bsunion = bs1.union(bs2)

        bsdf = read_frame(bsunion)
        bsdf = bsdf.drop(['debit','credit'],axis=1)


       

        pldf['balance'] = pldf['balance'].apply(Decimal)

       

        if pldf['balance'].sum() < 0:
            bsdf.loc[len(bsdf.index)] = ['Net Profit', -2, -2, 'Net Profit',pldf['balance'].sum()]
        else:
            bsdf.loc[len(bsdf.index)] = ['Net Loss', -2, -2, 'Net Loss',pldf['balance'].sum()]

        
        frames = [bsdf, dfi,odfi]

        bsdf = pd.concat(frames)


        bsdf['balance'] = bsdf['balance'].astype(float)
        bsdf['drcr'] = bsdf['balance'].apply(lambda x: 0 if x > 0 else 1)
        bsdf.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)
        bsdf = bsdf.sort_values(by=['accounthead'],ascending=False)
        print(bsdf)

        df = bsdf


        #df = bsdf.groupby(['drcr', 'accounthead','accountid'])['balance'].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values()

        #return Response(df)

        #df['sum1'] = df.groupby(by=["accounthead","drcr"]).apply(lambda grp: grp.balance.sum())


        #df1 = df.groupby(["drcr"]).apply(lambda x : x.groupby("accounthead").to_dict('records')).balance.sum()
        # for drcr,dfdrcr in df1:
        #     print(drcr)
        #     print(dfdrcr)


    #     j = (df.groupby(['drcr'])
    #    .apply(lambda x: x.groupby(by="accountheadname",as_index=True)
    #    .agg({'balance':'sum'}).to_dict())
    #    .reset_index()
    #    .rename(columns={0:'Accountheads'})
    #    .to_json(orient='records'))


    #     j = (df.groupby(['drcr'])
    #    .apply(lambda x: x.groupby("accountheadname")[["balance"]].sum().to_dict('records'))
    #    .reset_index()
    #    .rename(columns={0:'Tide-Data'})
    #    .to_json(orient='records'))


    #     print(j)


        #df = df.groupby('split')[['Chain','Food','Healthy']].apply(lambda x: x.set_index('Chain').to_dict(orient='index')).to_dict()



        #print(j)




       # return Response(df)



        # print(df)


        # j = df.groupby(by="drcr").apply(lambda x : x.groupby(by = "accountheadname").apply(lambda grp: grp.groupby(["accountname"]).balance.sum().to_dict()).to_dict()).reset_index().rename(columns={0:'Tide-Data'}).to_json(orient='records')




        # print(j)


        


        #df = df.groupby("drcr").apply(lambda x : x.groupby("accountheadname").apply(lambda y : y.groupby("accountname")[['balance']].sum()))
       # df = bsdf.groupby(["accounthead","accountheadname"]).apply(lambda grp: grp.groupby(by="accountheadname")[["balance"]].sum())

      # import json
       # json_res = list(map(json.dumps, df))

        #print(df)

        #return Response(df)


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


        #return Response(df.groupby(["drcr"]).apply(lambda grp1: grp1.groupby(["accounthead","accountheadname"]).apply(lambda grp: grp.groupby(['accountid','accountname']).balance.sum().reset_index().T.to_dict().values()).reset_index().rename(columns={0:'Tide-Data'}).T.to_dict().values()).reset_index().rename(columns={0:'Tide-Data'}).T.to_dict().values())


     




      
    
     
        return Response(bsdf.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())



class dashboardkpis(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')

        inventory = puchases.union(sales).order_by('entrydatetime')

        #idf1 = read_frame(puchases)

       # print(idf1)

        idf = read_frame(inventory)


        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])


        

        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))

        #print(idf)

        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()

        #print(idf)



        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

       # print(dfR)


        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['rate'].astype(float)

        dfR = dfR.drop(['stock','transactiontype','entrydatetime'],axis=1) 

        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -1

       # print(dfR)




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)

       # print(df)

        

        
        #print(df)

        #print(df)

        frames = [df, dfR]

        df = pd.concat(frames)

       # print(df)

        df['balance'] = df['balance'].astype(float)

        pl1 =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
        pldf = pldf.drop(['debit','credit'],axis=1)


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        #print(pldf)

        pldf['balance'] = pldf['balance'].astype(float)

        if pldf['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Net Profit', -2, -2, 'Net Profit',-pldf['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Net Loss', -2, -2, 'Net Loss',-pldf['balance'].sum()]



        pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)


        frames = [df, pldf]

        df = pd.concat(frames)

        #print(df)

        

       

        

        

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


       # print(df)

        df2=df[df['accountheadname'].astype(str).str.contains("Purchase|Sale|Gross Profit|Net Profit")]


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())

        #return Response(df2)

        df1 = pd.DataFrame(
       {
        "month": ["May", "June", "July", "August", "Sep", "Oct"],
        "sales": [15000, 7000, 19000,25000,12000,4000],
         "purchases": [18000, 14000, 35000,38000,20000,6000],
         "NetProfit": [3000, 7000, 14000,13000,8000,2000],
            },
            
        )

        return Response(df2.groupby(['accounthead','accountheadname','accountname','accountid'])[['balance']].sum().abs().reset_index().T.to_dict().values())

    #     return Response(df1)

    #   #  return Response(df2.groupby(['accounthead','accountheadname','accountname','accountid'])[['balance']].sum().abs().reset_index())

    #    # return Response(df2.groupby(['accounthead','accountheadname','accountname','accountid'])[['balance']].sum().abs().reset_index().T.reset_index().values.tolist()[4:])


     




      
    
     
    #    # return Response(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().T.to_dict().values())




class dashboardgraphkpis(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')

        inventory = puchases.union(sales).order_by('entrydatetime')

        #idf1 = read_frame(puchases)

       # print(idf1)

        idf = read_frame(inventory)


        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])


        

        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))

        #print(idf)

        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()

        #print(idf)



        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

       # print(dfR)


        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['rate'].astype(float)

        dfR = dfR.drop(['stock','transactiontype','entrydatetime'],axis=1) 

        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -1

       # print(dfR)




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)

       # print(df)

        

        
        #print(df)

        #print(df)

        frames = [df, dfR]

        df = pd.concat(frames)

       # print(df)

        df['balance'] = df['balance'].astype(float)

        pl1 =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
        pldf = pldf.drop(['debit','credit'],axis=1)


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        #print(pldf)

        pldf['balance'] = pldf['balance'].astype(float)

        if pldf['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Net Profit', -2, -2, 'Net Profit',-pldf['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Net Loss', -2, -2, 'Net Loss',-pldf['balance'].sum()]



        pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)


        frames = [df, pldf]

        df = pd.concat(frames)

        #print(df)

        

       

        

        

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


       # print(df)

        df2=df[df['accountheadname'].astype(str).str.contains("Purchase|Sale|Gross Profit|Net Profit")]


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())

        #return Response(df2)

        df1 = pd.DataFrame(
       {
        "month": ["May", "June", "July", "August", "Sep", "Oct"],
        "sales": [15000, 7000, 19000,25000,12000,4000],
         "purchases": [18000, 14000, 35000,38000,20000,6000],
         "netprofit": [3000, 7000, 14000,13000,8000,2000],
            },
            
        )

        return Response(df1)





class incomeandexpensesstatement(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk = generalfunctions(entityid = entity1,startdate= startdate,enddate=enddate)
       



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = entity1)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = entity1).values('stock','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        idf = pd.merge(idf,cdf,on='stock',how='outer',indicator=True)
       # idf = read_frame(inventory)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','OS','R']), idf['quantity'],-1 * (idf['quantity']))
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['closingrate'].astype(float)
        dfR = dfR.drop(['stock','stockttype','entrydatetime','closingrate','_merge'],axis=1) 
        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -1

        ##################################################################


        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lt = startdate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lt = startdate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(oinventory)

        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
       # idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['closingrate'].astype(float)
        odfR = odfR.drop(['stock','stockttype','entrydatetime','account__id','account__accountname','closingrate','_merge'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = -5


        ##################################################################




    
        df = stk.getstockdetails()


        frames = [odfR,df, dfR]

        df = pd.concat(frames)

        print(df)

        df['balance'] = df['balance'].astype(float)

        pl1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 2,entity = entity1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
        pldf = pldf.drop(['debit','credit'],axis=1)


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        print(pldf)

        pldf['balance'] = pldf['balance'].astype(float)

        if pldf['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Net Profit', -2, -2, 'Net Profit',-pldf['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Net Loss', -2, -2, 'Net Loss',-pldf['balance'].sum()]



        pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)


        frames = [df, pldf]

        df = pd.concat(frames)

        print(df)

        

       

        

        

        pldf.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


     




      
    
     
        return Response(pldf.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())






class tradingaccountstatement(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

     

        stk =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__range=(startdate, enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'PC').values('accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__range=(startdate, enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'PC').values('accounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(isactive =1,stockttype__in = ['P','R'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','stockttype','quantity','entrydatetime','stock__id')
        sales =    StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','stockttype','quantity','entrydatetime','stock__id')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
        
        idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        print(idf)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)

        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','R']), idf['quantity'],-1 * (idf['quantity']))
       # print(idf)
        idf['quantity'] = idf['quantity'].astype(float).fillna(0)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['closingrate'].astype(float)
        dfR.head(5)
        dfR = dfR.drop(['stockttype','entrydatetime','_merge'],axis=1) 
        dfR.rename(columns = {'stock__id':'account__id', 'stock':'account__accountname'}, inplace = True)
        dfR['accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -4
        ##################################################################


        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lte = startdate)).values('stock','stockttype','quantity','entrydatetime','stock__id')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = startdate).values('stock','stockttype','quantity','entrydatetime','stock__id')

        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        oinventory = opuchases.union(osales).order_by('entrydatetime')

        cdf = read_frame(closingprice)
        idf = read_frame(oinventory)
        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
       # idf['stockttype'] = np.where(idf['stockttype'] == 'I','S',idf['stockttype'])
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','OS','R']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['closingrate'].astype(float)
        odfR = odfR.drop(['stockttype','entrydatetime','_merge'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock':'account__accountname'}, inplace = True)
        odfR['accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = 21000


        ##################################################################

        #print(dfR)




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
       # df = df.drop(['debit','credit'],axis=1)

        #print(df)



       

       

       


      

        frames = [odfR,df, dfR]

        df = pd.concat(frames)

        #print(df)

        df['balance'] = df['balance'].astype(float).fillna(0)
        df['quantity'] = df['quantity'].astype(float).fillna(0)
        df['closingrate'] = df['closingrate'].astype(float).fillna(0)

      


        if df['balance'].sum() <= 0:
            df.loc[len(df.index)] = ['Gross Profit',0.00, -1,0.00,-df['balance'].sum(),'Gross Profit',-1]
        else:
            df.loc[len(df.index)] =  ['Gross Loss',0.00, -1,0.00,-df['balance'].sum(),'Gross Loss',-1]


        print(df)



        df['drcr'] = df['balance'].apply(lambda x: 0 if x >= 0 else 1)

        df['drcr'] = np.where(df['accounthead__name'] == 'Closing Stock',1,df['drcr'])

       # df['df'] = np.where(idf['accounthead__name'] == 'Opening Stock',0)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)

        

        

       

        

        

        df.rename(columns = {'accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


      


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())

       # print(df)


        df = df.groupby(['accounthead','accountheadname','drcr','accountname','accountid','closingrate'])[['balance','quantity']].sum().abs().reset_index().sort_values(by=['accounthead'],ascending=False)


       # print(df)

       


     




      
    
     
        return Response(df.T.to_dict().values())





class Balancesheetapi(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        stk =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__accounthead__detilsinbs = "Yes").exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1)).filter(account__creditaccounthead__detilsinbs = "Yes").exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(isactive =1,transactiontype = 'P',accounttype = 'DD').values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime')

        inventory = puchases.union(sales).order_by('entrydatetime')

        idf = read_frame(inventory)

        idf['quantity'] = np.where(idf['transactiontype'] == 'P', idf['quantity'],-1 * (idf['quantity']))

        #print(idf)

        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()



        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)


        dfR['balance'] = dfR['quantity'].astype(float) *  dfR['rate'].astype(float)

        dfR = dfR.drop(['stock','transactiontype','entrydatetime'],axis=1) 

        print(dfR)




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)

       # print(df)

        

        df.loc[len(df.index)] = ['Total', -1, -1, 'Total',-df['balance'].sum()]
        #print(df)

        #print(df)

        frames = [df, dfR]

        df = pd.concat(frames)

        #print(df)



        df['drcr'] = df['balance'].apply(lambda x: 0 if x < 0 else 1)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)

       #     print(df)

        df['balance'] = df['balance'].astype(float)

       

        

        

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


        print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


     




      
    
     
        return Response(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().T.to_dict().values())

    


class daybookviewapi(ListAPIView):

    serializer_class = cashserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'cashtrans__transactiontype':["in", "exact"]}
    #filterset_fields = ['cashtrans__accounttype']
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)



        queryset1=StockTransactions.objects.filter(entity=entity,isactive = 1).annotate(debit = Sum('debitamount'),credit =Sum('creditamount')).order_by('account')

      #  print(queryset1)

        queryset=entry.objects.filter(entity=entity,entrydate1__range = (startdate,enddate)).prefetch_related(Prefetch('cashtrans', queryset=queryset1,to_attr='account_transactions')).order_by('entrydate1')
        # for q in queryset.account_transactions:
        #     print(q)

        # print(queryset)
        # print([queryset])
        # for p in queryset:
        #     print(p.account_transactions[0].credit)

       

     
        
     
        return queryset


class cbviewapi(ListAPIView):

    serializer_class = cbserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=entry.objects.filter(entity=entity,entrydate1__range = (startdate,enddate)).prefetch_related('cashtrans').order_by('entrydate1')

       

     
        
     
        return queryset




class ledgerviewapi(ListAPIView):

    serializer_class = ledgerserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"],'creditaccounthead':["in", "exact"],'accounthead':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get_queryset(self):
        acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=account.objects.filter(entity=entity).prefetch_related('accounttrans').order_by('accountname')


        print(queryset.query.__str__())

       

     
        
     
        return queryset



class ledgersummaryapi(ListAPIView):

    serializer_class = ledgersummaryserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get_queryset(self):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=account.objects.filter(entity=entity).prefetch_related('accounttrans').order_by('accountname')

       

     
        
     
        return queryset




class stockledgersummaryapi(ListAPIView):


    serializer_class = stockledgersummaryserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get(self, request, format=None):
        
    
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        # accounthead = self.request.query_params.get('accounthead')
        # drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate),accounttype = 'DD').values('stock__id','stockttype').annotate(quantity = Sum('quantity',default = 0))

        prd = Product.objects.filter(entity = entity,isactive = 1).values('id','productname')




        
        df = read_frame(stk)

        print(df)

        p_table = pd.pivot_table( data=df, 
                        index=['stock__id'], 
                        columns=['stockttype'], 
                        values='quantity')
        
        print(p_table)


        df = p_table.rename_axis(None)

        print(df)

        df['stockttype'] = df.index


        df['I'] = df['I'].fillna(0).astype(float)
        df['P'] = df['P'].fillna(0).astype(float)
        df['S'] = df['S'].fillna(0).astype(float)
        df['R'] = df['R'].fillna(0).astype(float)

        df['balancetotal'] = df['P'] + df['R'] - df['I'] - df['S']

        df.rename(columns = {'I':'issued','P':'purchase','S': 'sale', 'R': 'recieved','stockttype' : 'id'}, inplace = True)



  
       

     
        
     
        return  Response(df.T.to_dict().values())


class stockledgerbookapi(ListAPIView):

    serializer_class = stockledgerbookserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get_queryset(self):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=Product.objects.filter(entity=entity).prefetch_related('stocktrans').order_by('productname')

       

     
        
     
        return queryset



class gstr1b2csmallapi(ListAPIView):

    serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)




        df['type'] = 'OE'
        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
       # df['account__accounthead'] = -1

       # return Response(df)
        return  Response(df.groupby(['type','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())

      





class gstr1b2clargeapi(ListAPIView):

    serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)


        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
       # df['account__accounthead'] = -1

       # return Response(df)
        return  Response(df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())

      





class gstrhsnapi(ListAPIView):

    serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('product__hsn','product__productname','product__unitofmeasurement__unitname','orderqty','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'product__hsn':'hsn', 'product__productname':'description','product__unitofmeasurement__unitname':'uqc','orderqty':'totalquantity','linetotal':'totalvalue','product__totalgst':'rate','amount':'taxablevalue'}, inplace = True)


       
        return  Response(df.groupby(['hsn','description','uqc','rate'])[['totalquantity','totalvalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())

      




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        #stkunion = stk.union(stk2)

     
       #df = df.drop(['debit','credit'],axis=1)

       # queryset=StockTransactions.objects.filter(entity=entity,transactiontype = 'S',accounttype = 'M').values('account__gstno','account__accountname','saleinvoice__billno','saleinvoice__sorderdate')
class gstr1b2bapi(ListAPIView):

    serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        #stardate = self.request.query_params.get('stardate')

        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__accountid__gstno','salesorderheader__accountid__accountname','salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'salesorderheader__accountid__gstno':'gstin', 'salesorderheader__accountid__accountname':'receivername','salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal': 'invoicevalue','amount':'taxablevalue'}, inplace = True)


        df['placeofsupply'] = '03-Punjab'
        df['reversecharge'] = 'N'
        df['invoicetype'] = 'RegularB2B'
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = 'N'
       # df['account__accounthead'] = -1

       # return Response(df)
        return  Response(df.groupby(['gstin','receivername','invoiceno','invoicedate','rate','placeofsupply','reversecharge','invoicetype','applicableoftaxrate','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())


    

class gstr1b2baapi(ListAPIView):

    serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        #stardate = self.request.query_params.get('stardate')

        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__accountid__gstno','salesorderheader__accountid__accountname','salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'salesorderheader__accountid__gstno':'gstin', 'salesorderheader__accountid__accountname':'receivername','salesorderheader__billno':'originalinvoiceno5','salesorderheader__billno':'revisedinvoiceno','salesorderheader__sorderdate':'originalinvoicedate1','salesorderheader__sorderdate':'revisedinvoicedate1','product__totalgst':'rate','linetotal': 'invoicevalue','amount':'taxablevalue'}, inplace = True)


        df['placeofsupply'] = '03-Punjab'
        df['reversecharge'] = 'N'
        df['invoicetype'] = 'RegularB2B'
        df['originalinvoicedate'] = pd.to_datetime(df['revisedinvoicedate1']).dt.strftime('%d-%B-%Y')
        df['revisedinvoicedate'] = pd.to_datetime(df['revisedinvoicedate1']).dt.strftime('%d-%B-%Y')
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = 'N'
        df['originalinvoiceno'] = 1
       # df['account__accounthead'] = -1

        print(df)

       # return Response(df)
        return  Response(df.groupby(['gstin','receivername','originalinvoiceno','revisedinvoiceno','originalinvoicedate','revisedinvoicedate','rate','placeofsupply','reversecharge','invoicetype','applicableoftaxrate','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())

      




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        #stkunion = stk.union(stk2)

     
       #df = df.drop(['debit','credit'],axis=1)

       # queryset=StockTransactions.objects.filter(entity=entity,transactiontype = 'S',accounttype = 'M').values('account__gstno','account__accountname','saleinvoice__billno','saleinvoice__sorderdate')

       

     
        
       
    





class gstr1hsnapi(ListAPIView):

    serializer_class = gstr1hsnserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get_queryset(self):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=StockTransactions.objects.filter(entity=entity,transactiontype = 'S',accounttype = 'DD').values('stock__hsn','stock__productdesc','stock__unitofmeasurement__unitname','stock__totalgst').annotate(quantity = Sum('quantity'),credit =Sum('creditamount'),cgstdr =Sum('cgstdr'),sgstdr =Sum('sgstdr'),igstdr =Sum('igstdr'))

       

     
        
     
        return queryset









class salebyaccountapi(ListAPIView):

    #serializer_class = Salebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']


    def get(self,request):
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        queryset1 = ''

        if transactiontype == 'S':
            queryset1=SalesOderHeader.objects.filter(entity=entity,isactive = 1,sorderdate__range=(startdate, enddate)).values('id','sorderdate','accountid__accountname','accountid__accountcode','totalpieces','totalquanity','subtotal','cgst','sgst','igst','cess','gtotal','accountid__city__cityname').order_by('-sorderdate')

        if transactiontype == 'PR':
            queryset1=PurchaseReturn.objects.filter(entity=entity,isactive = 1,sorderdate__range=(startdate, enddate)).values('id','sorderdate','accountid__accountname','accountid__accountcode','totalpieces','totalquanity','subtotal','cgst','sgst','igst','cess','gtotal','accountid__city__cityname').order_by('-sorderdate') 

        df = read_frame(queryset1)
        df.rename(columns = {'accountid__accountname':'accountname','account__id':'account','totalpieces':'pieces','totalquanity':'weightqty','id':'transactionid','accountid__accountcode':'accountcode','sorderdate':'entrydate','accountid__city__cityname':'city'}, inplace = True)
        df['transactiontype'] = transactiontype
        df['entrydate'] = pd.to_datetime(df['entrydate']).dt.strftime('%d/%m/%y')
        return Response(df.T.to_dict().values())


    

class purchasebyaccountapi(ListAPIView):

    serializer_class = Purchasebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get(self,request):
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        queryset1 = ''

        if transactiontype == 'P':
            queryset1=purchaseorder.objects.filter(entity=entity,isactive = 1,voucherdate__range=(startdate, enddate)).values('id','voucherdate','account__accountname','account__accountcode','totalpieces','totalquanity','subtotal','cgst','sgst','igst','cess','gtotal','account__city__cityname').order_by('-voucherdate')

        if transactiontype == 'SR':
            queryset1=salereturn.objects.filter(entity=entity,isactive = 1,voucherdate__range=(startdate, enddate)).values('id','voucherdate','account__accountname','account__accountcode','totalpieces','totalquanity','subtotal','cgst','sgst','igst','cess','gtotal','account__city__cityname').order_by('-voucherdate') 

        df = read_frame(queryset1)
        df.rename(columns = {'account__accountname':'accountname','account__id':'account','totalpieces':'pieces','totalquanity':'weightqty','id':'transactionid','accountid__accountcode':'accountcode','voucherdate':'entrydate','account__city__cityname':'city'}, inplace = True)
        df['transactiontype'] = transactiontype
        df['entrydate'] = pd.to_datetime(df['entrydate']).dt.strftime('%d/%m/%y')
        return Response(df.T.to_dict().values())




class stockviewapi(ListAPIView):

    serializer_class = stockserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')



        queryset1=StockTransactions.objects.filter(entity=entity).order_by('entity').only('account__accountname','stock__productname','transactiontype','transactionid','entrydatetime')

        queryset=Product.objects.filter(entity=entity).prefetch_related(Prefetch('stocktrans', queryset=queryset1,to_attr='account_transactions'))

       

     
        
     
        return queryset
    

class debitcreditnoteApiView(ListCreateAPIView):

    serializer_class = debitcreditnoteSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['voucherdate','voucherno','entityfinid']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return debitcreditnote.objects.filter(entity = entity)
    

class debitcreditnoteupdatedelApiView(RetrieveUpdateDestroyAPIView):

    serializer_class = debitcreditnoteSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return debitcreditnote.objects.filter(createdby = self.request.user)
    


class debitcreditnotebyvoucherno(RetrieveUpdateDestroyAPIView):

    serializer_class = debitcreditnoteSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        vouchertype = self.request.query_params.get('vouchertype')
        return debitcreditnote.objects.filter(createdby = self.request.user,entity=entity,vouchertype=vouchertype)


class debitcreditlatestvnoview(ListCreateAPIView):

    serializer_class = dcnoSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        vouchertype = self.request.query_params.get('vouchertype')
        entityfy = self.request.query_params.get('entityfinid')
       
        id = debitcreditnote.objects.filter(entity= entity,vouchertype=vouchertype, entityfinid = entityfy).last()
        serializer = dcnoSerializer(id)
        return Response(serializer.data)


class debitcreditcancel(RetrieveUpdateDestroyAPIView):

    serializer_class = debitcreditcancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return debitcreditnote.objects.filter(entity = entity)
    

class closingstockView(ListCreateAPIView):  
         
        serializer_class = closingstockSerializer  


        # def perform_create(self, serializer):
        #     entity = self.request.query_params.get('entity')
        #     closingstock.objects.filter(entity = entity).delete()


        #     return serializer.save(createdby = self.request.user)
      
        def create(self, request, *args, **kwargs):  
            entity = self.request.query_params.get('entity')
            closingstock.objects.filter(entity = entity).delete()

            print(request.data)
          # print(entity)
            serializer = self.get_serializer(data=request.data, many=True)  
            serializer.is_valid(raise_exception=True)  
      
            try:  
                self.perform_create(serializer)  
                return Response(serializer.data, status=status.HTTP_201_CREATED)  
            except:  
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 
            
        def get_queryset(self):
            entity = self.request.query_params.get('entity')
            return   closingstock.objects.filter(entity = entity)
        

class closingstocknew(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

       # ob =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
       # ob2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        # stk =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__range=(startdate, enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gte = 0)
        # stk2 =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__range=(startdate, enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('accounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lte = enddate)).values('accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('accounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','stockttype','quantity','entrydatetime','stock__id','stock__productname')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
        cdf = read_frame(closingprice)
        cdf['closingrate'] = cdf['closingrate'].astype(float).fillna(0)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)

        idf['closingrate'] = idf['closingrate'].astype(float).fillna(0)

        #print



        print(idf)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','OS','R']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        #print(idf)
        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        dfR['balance'] = dfR['quantity'].astype(float)  * dfR['closingrate'].astype(float)
       # print(dfR)
        dfR = dfR.drop(['accounthead__name','account__accounthead','account__id','account__accountname','rate','_merge','stockttype','entrydatetime','stock__productname'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock__id':'stockid', 'stock':'stockname'}, inplace = True)

       


        print(dfR)

        return Response(dfR.T.to_dict().values())


class balancesheetclosingapiView(ListCreateAPIView):

    serializer_class = balancesheetclosingserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return entry.objects.filter(entity = entity)
        



