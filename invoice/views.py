from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from invoice.models import salesOrderdetails,SalesOderHeader,purchaseorder,PurchaseOrderDetails,journal,salereturn,salereturnDetails,PurchaseReturn,Purchasereturndetails,StockTransactions,journalmain,entry,stockdetails,stockmain,goodstransaction,purchasetaxtype,tdsmain,tdstype,productionmain,tdsreturns
from invoice.serializers import SalesOderHeaderSerializer,salesOrderdetailsSerializer,purchaseorderSerializer,PurchaseOrderDetailsSerializer,POSerializer,SOSerializer,journalSerializer,SRSerializer,salesreturnSerializer,salesreturnDetailsSerializer,JournalVSerializer,PurchasereturnSerializer,\
purchasereturndetailsSerializer,PRSerializer,TrialbalanceSerializer,TrialbalanceSerializerbyaccounthead,TrialbalanceSerializerbyaccount,accountheadserializer,accountHead,accountserializer,accounthserializer, stocktranserilaizer,cashserializer,journalmainSerializer,stockdetailsSerializer,stockmainSerializer,\
PRSerializer,SRSerializer,stockVSerializer,stockserializer,Purchasebyaccountserializer,Salebyaccountserializer,entitySerializer1,cbserializer,ledgerserializer,ledgersummaryserializer,stockledgersummaryserializer,stockledgerbookserializer,balancesheetserializer,gstr1b2bserializer,gstr1hsnserializer,\
purchasetaxtypeserializer,tdsmainSerializer,tdsVSerializer,tdstypeSerializer,tdsmaincancelSerializer,salesordercancelSerializer,purchaseordercancelSerializer,purchasereturncancelSerializer,salesreturncancelSerializer,journalcancelSerializer,stockcancelSerializer,SalesOderHeaderpdfSerializer,productionmainSerializer,productionVSerializer,productioncancelSerializer,tdsreturnSerializer
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
        id = tdsmain.objects.filter(entityid= entity).last()
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

        entity = self.request.query_params.get('entity')
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
   # filterset_fields = ['id','ProductName','is_stockable']

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


class purchaseordercancel(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseordercancelSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity = entity)


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
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return SalesOderHeader.objects.filter(entity = entity).prefetch_related('salesorderdetails')


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



class salesorderlatestview(ListCreateAPIView):

    serializer_class = SOSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = SalesOderHeader.objects.filter(entity= entity).last()
        serializer = SOSerializer(id)
        return Response(serializer.data)




class purchasereturnlatestview(ListCreateAPIView):

    serializer_class = PRSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    # def perform_create(self, serializer):
    #     return serializer.save(createdby = self.request.user)

    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = PurchaseReturn.objects.filter(entity= entity).last()
        serializer = PRSerializer(id)
        return Response(serializer.data)


class PurchaseReturnApiView(ListCreateAPIView):

    serializer_class = PurchasereturnSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

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
        id = PurchaseReturn.objects.filter(entity= entity).last()
        serializer = PRSerializer(id)
        return Response(serializer.data)






        ############################################################


class purchaseorderApiView(ListCreateAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    @transaction.atomic
    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity = entity)


class PurchaseOrderDetailsApiView(ListCreateAPIView):

    serializer_class = PurchaseOrderDetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        return PurchaseOrderDetails.objects.filter()


class purchaseorderupdatedelview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter()


class purchaseorderpreviousview(RetrieveUpdateDestroyAPIView):

    serializer_class = purchaseorderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "voucherno"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return purchaseorder.objects.filter(entity =entity)

class purchaseordelatestview(ListCreateAPIView):

    serializer_class = POSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = purchaseorder.objects.filter(entity= entity).last()
        serializer = POSerializer(id)
        return Response(serializer.data)



class purchaseordelatestview(ListCreateAPIView):

    serializer_class = POSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = purchaseorder.objects.filter(entity= entity).last()
        serializer = POSerializer(id)
        return Response(serializer.data)




class gstview(ListCreateAPIView):

   # serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def list(self,request):
        entity = self.request.query_params.get('entity')
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)
        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')
        df = read_frame(stk)
        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)
        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
        dfb2b = df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values()
    #    # df['account__accounthead'] = -1

    #    # return Response(df)
    #     return  Response(df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())
    #     id = list(journalmain.objects.filter(entity= entity,vouchertype = 'J').values())
        #serializer = JournalVSerializer(id)


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

        df = read_frame(stk)

       

        df.rename(columns = {'salesorderheader__billno':'invoiceno','salesorderheader__sorderdate':'invoicedate1','salesorderheader__sorderdate':'invoicedate1','product__totalgst':'rate','linetotal':'invoicevalue','amount':'taxablevalue'}, inplace = True)


        df['placeofsupply'] = '03-Punjab'
        df['applicableoftaxrate'] = ''
        df['ecomgstin'] = ''
     #   df['reversecharge'] = 'N'
       
        df['invoicedate'] = pd.to_datetime(df['invoicedate1']).dt.strftime('%d-%B-%Y')
       # df['account__accounthead'] = -1

       # return Response(df)
        dfb2clarge =  df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values()

        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

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
        dfbebsmall =  df.groupby(['type','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values()

        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('product__hsn','product__productname','product__unitofmeasurement__unitname','orderqty','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

        df = read_frame(stk)

        

        df.rename(columns = {'product__hsn':'hsn', 'product__productname':'description','product__unitofmeasurement__unitname':'uqc','orderqty':'totalquantity','linetotal':'totalvalue','product__totalgst':'rate','amount':'taxablevalue'}, inplace = True)


       
        dfhsn =  df.groupby(['hsn','description','uqc','rate'])[['totalquantity','totalvalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values()

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
        id = journalmain.objects.filter(entity= entity,vouchertype = 'J').last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)


class stockordelatestview(ListCreateAPIView):

    serializer_class = stockVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = stockmain.objects.filter(entity= entity,vouchertype = 'PC').last()
        serializer = stockVSerializer(id)
        return Response(serializer.data)






class productionlatestview(ListCreateAPIView):

    serializer_class = productionVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = productionmain.objects.filter(entity= entity,vouchertype = 'PV').last()
        serializer = productionVSerializer(id)
        return Response(serializer.data)


class bankordelatestview(ListCreateAPIView):

    serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = journalmain.objects.filter(entity= entity,vouchertype = 'B').last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)


class cashordelatestview(ListCreateAPIView):

    serializer_class = JournalVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        id = journalmain.objects.filter(entity= entity,vouchertype = 'C').last()
        serializer = JournalVSerializer(id)
        return Response(serializer.data)



class salesreturnApiView(ListCreateAPIView):

    serializer_class = salesreturnSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

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
    #filterset_fields = ['id','unitType','entityName']

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
    #filterset_fields = ['id','unitType','entityName']

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
    #filterset_fields = ['id','unitType','entityName']

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
        id = salereturn.objects.filter(entity= entity).last()
        serializer = SRSerializer(id)
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
        #stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0) )
       # stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead','account_id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))


        obp =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gte = 0)
        obn =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt= startdate).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lt = 0)
        ob = obp.union(obn)

        #print(ob)

        df = read_frame(ob)

        print(df)

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__id':'account'}, inplace = True)

        dffinal1 = df.groupby(['accounthead','accountheadname'])[['balance1']].sum().reset_index()

        print(dffinal1)

        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)
        stkunion = stk.union(stk2)

        df = read_frame(stkunion)

        print(df)
        
        df['drcr'] = 'CR'

        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'],0)
        #df['credit'] = df['balance'].apply(lambda x: df['balance'] if x < 0 else 0)
        #df['debit'] = df['balance'].apply(lambda x: 0 if x < 0 else df['balance'])

       #print(df)
        

    


        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__id':'account'}, inplace = True)

        dffinal = df.groupby(['accounthead','accountheadname','drcr'])[['debit','credit','balance']].sum().abs().reset_index()

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

        



        

        

        
        df['debit'] = df['debit'].fillna(0)
        df['credit'] = df['credit'].fillna(0)
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'])
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
        # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
        # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
        df['accountheadname'] = np.where(df['_merge'] == 'right_only', df['accountheadname_y'],df['accountheadname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        df = df.drop(['accountheadname_y', 'accountheadname_x','_merge','balance1'],axis = 1)

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

            ob =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gte = 0)
            stk =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
            #return stk
        
        if drcrgroup == 'CR':

            ob =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lte = 0)
            stk =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)



        
        df = read_frame(stk)
        df['drcr'] = 'CR'

        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'],0)

        

        df.rename(columns = {'account__accountname':'accountname','account__id':'account'}, inplace = True)


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

        print(obdf)



        df = df.groupby(['accountname','drcr','account'])[['debit','credit','balance']].sum().abs().reset_index()

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

        df['debit'] = df['debit'].fillna(0)
        df['credit'] = df['credit'].fillna(0)
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0,df['balance1'])
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']
        # df['openingbalance'] = np.where(df['_merge'] == 'both',df['balance1'],df['openingbalance'])
        # df['openingbalance'] = np.where(df['_merge'] == 'right_only', 0,df['balance'])
        df['accountname'] = np.where(df['_merge'] == 'right_only', df['accountname_y'],df['accountname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        df = df.drop(['accountname_y', 'accountname_x','_merge','balance1'],axis = 1)

        print(df)
        
        return Response(df.T.to_dict().values())

class TrialbalancebyaccountApiView(ListAPIView):

    serializer_class = TrialbalanceSerializerbyaccount
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        account1 = self.request.query_params.get('account')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').values('id','account__accountname','transactiontype','transactionid','entrydatetime','desc').annotate(debit = Sum('debitamount'),credit = Sum('creditamount')).order_by('entrydatetime')
        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').values('account__accountname').annotate(debit = Sum('debitamount'),credit = Sum('creditamount')).order_by('entrydatetime')
        df1 = read_frame(ob)
        df1['desc'] = 'Opening Balance'
        df1['entrydatetime'] = startdate
        #print(df1)
        df = read_frame(stk)    

        print(df)

        union_dfs = pd.concat([df1, df], ignore_index=True)
        print(union_dfs)

        #ob = df1.union(df)

        union_dfs['transactiontype'] = union_dfs['transactiontype'].fillna(0)
        union_dfs['id'] = union_dfs['id'].fillna(0)
        union_dfs['transactionid'] = union_dfs['transactionid'].fillna(0)
        union_dfs['desc'] = union_dfs['desc'].fillna(0)
        #union_dfs['entrydatetime'] = union_dfs['desc'].fillna(startdate)
       # print(union_dfs)
        #print(stk)

      #  union_dfs['entrydatetime'] = pd.to_datetime(union_dfs['entrydatetime'])

        

        print(union_dfs)
        return Response(union_dfs.T.to_dict().values())



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



class balancestatement(ListAPIView):

    serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']
    

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

        #ob =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt  = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        #ob2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lt  = enddate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock__id','stock__productname','rate','transactiontype','quantity','entrydatetime')
        sales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1,entrydatetime__lt  = enddate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock__id','stock__productname','rate','transactiontype','quantity','entrydatetime')

        inventory = puchases.union(sales).order_by('entrydatetime')

        #idf1 = read_frame(puchases)

       # print(idf1)

        idf = read_frame(inventory)


        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])


        

        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))

       

        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock__id','transactiontype'])['quantity'].cumsum()

      



        dfR = idf.groupby(['stock__id'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

      

        dfi = dfR

        

       


        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['rate'].astype(float)

        

        dfR = dfR.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)

        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -1

        print(dfR)

        dfi['balance'] = dfi['quantity'].astype(float) * 1 * dfi['rate'].astype(float)

        dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfi.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)

        dfi['account__accounthead__name'] = 'Closing Stock'
        dfi['account__accounthead'] = -1


         ##################################################################


        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lt = startdate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        osales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1,entrydatetime__lt = startdate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(oinventory)
        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])
        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

        odfi = odfR
       #print(dfR)
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['rate'].astype(float)
        odfR = odfR.drop(['stock','transactiontype','entrydatetime','account__id','account__accountname'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = -5


        



        odfi['balance'] = odfi['quantity'].astype(float) * -1 * odfi['rate'].astype(float)

        odfi = odfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfi.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)

        odfi['account__accounthead__name'] = 'Opening Stock'
        odfi['account__accounthead'] = -5


        ##################################################################

      




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)


        #obunion = ob.union(ob2)

        #obdf = read_frame(obunion)
       # obdf = obdf.drop(['debit','credit'],axis=1)

     

        frames = [odfR,df, dfR]

        df = pd.concat(frames)

      

        df['balance'] = df['balance'].astype(float)

        pl1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
        pldf = pldf.drop(['debit','credit'],axis=1)


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        bs1 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gt = 0)
        bs2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)

        bsunion = bs1.union(bs2)

        bsdf = read_frame(bsunion)
        bsdf = bsdf.drop(['debit','credit'],axis=1)


        #print(bsdf)

        pldf['balance'] = pldf['balance'].apply(Decimal)

        #print(pldf['balance'].sum())

        #sum1 = pldf['balance'].sum()

        #print(sum1)

        #bsdf.loc[len(bsdf.index)] = ['Net Loss', -2, -2, 'Net Loss',pldf['balance'].sum()]

        if pldf['balance'].sum() < 0:
            bsdf.loc[len(bsdf.index)] = ['Net Profit', -2, -2, 'Net Profit',pldf['balance'].sum()]
        else:
            bsdf.loc[len(bsdf.index)] = ['Net Loss', -2, -2, 'Net Loss',pldf['balance'].sum()]

        
        frames = [bsdf, dfi,odfi]

        bsdf = pd.concat(frames)


        bsdf['balance'] = bsdf['balance'].astype(float)



        bsdf['drcr'] = bsdf['balance'].apply(lambda x: 0 if x > 0 else 1)
        # #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)

        print(bsdf)

        

       

        

        

        bsdf.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)

        bsdf = bsdf.sort_values(by=['accounthead'],ascending=False)

        print(bsdf)


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


     




      
    
     
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
        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



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

        print(idf)

        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()

        print(idf)



        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

        print(dfR)


        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['rate'].astype(float)

        dfR = dfR.drop(['stock','transactiontype','entrydatetime'],axis=1) 

        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -1

        print(dfR)

        ##################################################################


        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lt = startdate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        osales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1,entrydatetime__lt = startdate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(oinventory)
        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])
        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['rate'].astype(float)
        odfR = odfR.drop(['stock','transactiontype','entrydatetime','account__id','account__accountname'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = -5


        ##################################################################




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)

       # print(df)

        

        
        #print(df)

        #print(df)

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

       # ob =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
       # ob2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__lt = startdate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1),Q(entrydatetime__range=(startdate, enddate))).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lte = enddate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        sales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
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
       #print(dfR)
        dfR['balance'] = dfR['quantity'].astype(float) * -1 * dfR['rate'].astype(float)
        dfR = dfR.drop(['stock','transactiontype','entrydatetime','account__id','account__accountname'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)

        dfR['account__accounthead__name'] = 'Closing Stock'
        dfR['account__accounthead'] = -4



        ##################################################################


        opuchases = StockTransactions.objects.filter(Q(isactive =1),Q(transactiontype__in = ['P','OS']),Q(accounttype = 'DD'),Q(entity = entity1),Q(entrydatetime__lte = startdate)).values('account__accounthead__name','account__accounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        osales = StockTransactions.objects.filter(isactive =1,transactiontype = 'S',accounttype = 'DD',entity = entity1,entrydatetime__lte = startdate).values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname','stock','rate','transactiontype','quantity','entrydatetime','stock__id','stock__productname')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(oinventory)
        idf['transactiontype'] = np.where(idf['transactiontype'] == 'OS','P',idf['transactiontype'])
        idf['quantity'] = np.where(idf['transactiontype'].isin(['P','OS']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','transactiontype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['rate'].astype(float)
        odfR = odfR.drop(['stock','transactiontype','entrydatetime','account__id','account__accountname'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = 21000


        ##################################################################

        #print(dfR)




    #     print(stk2.query.__str__())
    #    # q = stk.filter(balance__gt=0)



        stkunion = stk.union(stk2)

        df = read_frame(stkunion)
        df = df.drop(['debit','credit'],axis=1)


       

       


      

        frames = [odfR,df, dfR]

        df = pd.concat(frames)

       # print(df)

        df['balance'] = df['balance'].astype(float)

        df['balance'] = df['balance'].fillna(0)

      


        if df['balance'].sum() < 0:
            df.loc[len(df.index)] = ['Gross Profit', -1, -1, 'Gross Profit',-df['balance'].sum(),0,-df['balance'].sum()]
        else:
            df.loc[len(df.index)] = ['Gross Loss', -1, -1, 'Gross Loss',-df['balance'].sum(),0,-df['balance'].sum()]


        #print(df)



        df['drcr'] = df['balance'].apply(lambda x: 0 if x > 0 else 1)
        #df = df.loc['Column_Total']= df.sum(numeric_only=True, axis=0)

        

        

       

        

        

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


      


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())


        df = df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead'],ascending=False)

       


     




      
    
     
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
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)



        queryset1=StockTransactions.objects.filter(entity=entity,isactive = 1).only('account__accountname','transactiontype','drcr','transactionid','desc').annotate(debit = Sum('debitamount'),credit =Sum('creditamount')).order_by('account')

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
    def get_queryset(self):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=Product.objects.filter(entity=entity).prefetch_related('goods').order_by('productname')

       

     
        
     
        return queryset


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

        queryset=Product.objects.filter(entity=entity).prefetch_related('goods').order_by('productname')

       

     
        
     
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


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

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
        return  Response(df.groupby(['type','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())

      





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


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

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
        return  Response(df.groupby(['invoiceno','invoicedate','applicableoftaxrate','rate','placeofsupply','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())

      





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


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('product__hsn','product__productname','product__unitofmeasurement__unitname','orderqty','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'product__hsn':'hsn', 'product__productname':'description','product__unitofmeasurement__unitname':'uqc','orderqty':'totalquantity','linetotal':'totalvalue','product__totalgst':'rate','amount':'taxablevalue'}, inplace = True)


       
        return  Response(df.groupby(['hsn','description','uqc','rate'])[['totalquantity','totalvalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())

      




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


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__accountid__gstno','salesorderheader__accountid__accountname','salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

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
        return  Response(df.groupby(['gstin','receivername','invoiceno','invoicedate','rate','placeofsupply','reversecharge','invoicetype','applicableoftaxrate','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())


    

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


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('salesorderheader__accountid__gstno','salesorderheader__accountid__accountname','salesorderheader__billno','salesorderheader__sorderdate','linetotal','amount','cgst','sgst','igst','cgstcess','sgstcess','igstcess','product__totalgst')

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
        return  Response(df.groupby(['gstin','receivername','originalinvoiceno','revisedinvoiceno','originalinvoicedate','revisedinvoicedate','rate','placeofsupply','reversecharge','invoicetype','applicableoftaxrate','ecomgstin'])[['invoicevalue','taxablevalue','cgst','sgst','igst','cgstcess','sgstcess','igstcess']].sum().abs().reset_index().T.to_dict().values())

      




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

    serializer_class = Salebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')


        queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M',transactiontype = transactiontype,isactive = 1).order_by('account')



       # queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M',transactiontype = transactiontype,entrydatetime__range=(startdate, enddate)).order_by('account')

       # queryset=entry.objects.prefetch_related(Prefetch('cashtrans', queryset=queryset1,to_attr='account_transactions')).order_by('-entrydate1')

       

     
        
     
        return queryset1

class purchasebyaccountapi(ListAPIView):

    serializer_class = Purchasebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get_queryset(self):
        #account = self.request.query_params.get('account')
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')




        queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M',transactiontype = transactiontype,entrydatetime__range=(startdate, enddate),isactive = 1).order_by('account').only('account__accountname','account__city', 'transactiontype','drcr','transactionid','desc','creditamount','cgstdr','sgstdr','igstdr','subtotal', )

       # queryset=entry.objects.prefetch_related(Prefetch('cashtrans', queryset=queryset1,to_attr='account_transactions')).order_by('-entrydate1')

       

     
        
     
        return queryset1




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

