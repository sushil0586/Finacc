from django.shortcuts import render

# Create your views here.
from collections import defaultdict
import re
from django.db.models import Min, Max
from invoice.models import JournalLine  # <-- your GL table
from typing import Tuple, List,Optional
from invoice.serializers import stocktransconstant
from .pagination import SmallPageNumberPagination,SimpleNumberPagination

from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json
from pandas.tseries.offsets import MonthEnd,QuarterEnd
from decimal import Decimal,InvalidOperation
from django.db.models import Sum, Q, Value as V,DecimalField,ExpressionWrapper,Count
from django.utils.timezone import make_aware, is_aware
from .serializers import CashbookUnifiedSerializer,TrialBalanceAccountRowSerializer,TrialBalanceAccountLedgerRowSerializer
from django.utils.dateparse import parse_date
from collections import deque
from django.utils import timezone  
from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from invoice.models import StockTransactions,closingstock,salesOrderdetails,entry,SalesOderHeader,PurchaseReturn,purchaseorder,salereturn,journalmain,salereturnDetails,Purchasereturndetails
# from invoice.serializers import SalesOderHeaderSerializer,salesOrderdetailsSerializer,purchaseorderSerializer,PurchaseOrderDetailsSerializer,POSerializer,SOSerializer,journalSerializer,SRSerializer,salesreturnSerializer,salesreturnDetailsSerializer,JournalVSerializer,PurchasereturnSerializer,\
# purchasereturndetailsSerializer,PRSerializer,TrialbalanceSerializer,TrialbalanceSerializerbyaccounthead,TrialbalanceSerializerbyaccount,accountheadserializer,accountHead,accountserializer,accounthserializer, stocktranserilaizer,cashserializer,journalmainSerializer,stockdetailsSerializer,stockmainSerializer,\
# PRSerializer,SRSerializer,stockVSerializer,stockserializer,Purchasebyaccountserializer,Salebyaccountserializer,entitySerializer1,cbserializer,ledgerserializer,ledgersummaryserializer,stockledgersummaryserializer,stockledgerbookserializer,balancesheetserializer,gstr1b2bserializer,gstr1hsnserializer,\
# purchasetaxtypeserializer,tdsmainSerializer,tdsVSerializer,tdstypeSerializer,tdsmaincancelSerializer,salesordercancelSerializer,purchaseordercancelSerializer,purchasereturncancelSerializer,salesreturncancelSerializer,journalcancelSerializer,stockcancelSerializer,SalesOderHeaderpdfSerializer,productionmainSerializer,productionVSerializer,productioncancelSerializer,tdsreturnSerializer,gstorderservicesSerializer,SSSerializer,gstorderservicecancelSerializer,jobworkchallancancelSerializer,JwvoucherSerializer,jobworkchallanSerializer,debitcreditnoteSerializer,dcnoSerializer,debitcreditcancelSerializer,closingstockSerializer

from reports.serializers import closingstockSerializer,stockledgerbookserializer,stockledgersummaryserializer,ledgerserializer,cbserializer,stockserializer,cashserializer,accountListSerializer2,ledgerdetailsSerializer,ledgersummarySerializer,stockledgerdetailSerializer,stockledgersummarySerializer,TrialBalanceSerializer,StockDayBookSerializer,StockSummarySerializerList,SalesGSTSummarySerializer,LedgerSummaryRequestSerializer,LedgerSummaryRowSerializer
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
from django.db import DatabaseError, transaction
from rest_framework.response import Response
from django.db.models import Sum,OuterRef,Subquery,F,Sum, F, Value, DecimalField,CharField
from django.db.models import Prefetch
from financial.models import account,accountHead
from inventory.models import Product
from django.db import connection
from django.core import serializers
from rest_framework.renderers import JSONRenderer
from drf_excel.mixins import XLSXFileMixin
from drf_excel.renderers import XLSXRenderer
from rest_framework.viewsets import ReadOnlyModelViewSet
from entity.models import Entity,entityconstitution,entityfinancialyear,entityfinancialyear as FinancialYear
from django_pandas.io import read_frame
from django.db.models import Q
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import timedelta,date,datetime
import pytz
import json
from django.db.models import Case, When
from django.db.models import Q, Sum, F
from django.db.models.functions import Coalesce
from django_pandas.io import read_frame
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from entity.models import Entity, entityfinancialyear
from financial.models import account
from inventory.models import Product
import pandas as pd
from datetime import datetime
from reports.models import TransactionType
from .serializers import TransactionTypeSerializer
from .serializers import EMICalculatorSerializer
from helpers.utils.emi import calculate_emi
from reports.serializers import TrialBalanceHeadRowSerializer
ZERO = Decimal("0.00")



class closingstockBalance(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1,stockttype__in = ['P','O','R'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate)).values('stock','stockttype','quantity','entrydatetime','stock__id','id')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','stockttype','quantity','entrydatetime','stock__id','id')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
        #print(idf)
        cdf = read_frame(closingprice)
        cdf['closingrate'] = cdf['closingrate'].astype(float).fillna(0)
      #  print(cdf)
        

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
       # print(idf)

        idf['closingrate'] = idf['closingrate'].astype(float).fillna(0)

        #print



       # print(idf)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R','O']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','O','R']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()

      #  dfR['closingrate'] = dfR['closingrate'].astype(float).fillna(0)
       # dfR['rate'] = dfR['rate'].astype(float).fillna(0)
       # print(idf)
        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        #print(dfR)

       # dfR['rate'] = dfR['rate'].fillna(0)

        #dfR['closingrate'] = np.where(dfR['closingrate'] >0,dfR['closingrate'],dfR['rate'])
        dfR['balance'] = dfR['quantity'].astype(float)  * dfR['closingrate'].astype(float)
       # print(dfR)
        dfR = dfR.drop(['_merge','stockttype','entrydatetime','id'],axis=1) 

        #print(dfR)

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock':'stockname'}, inplace = True)

        dfR.rename(columns = {'stock__id':'stock', 'closingrate':'rate'}, inplace = True)



       


        print(dfR)

        dfR = dfR.groupby(['stockname','stock','rate'])[['quantity','balance']].sum().abs().reset_index()

        return Response(dfR.T.to_dict().values())



class closingstocknew(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =   self.request.query_params.get('enddate')

        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1,stockttype__in = ['P','O','R'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate)).values('stock','rate','stockttype','quantity','entrydatetime','stock__id','id')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id','id')
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = entity1).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
      #  print(idf)
        cdf = read_frame(closingprice)
        cdf['closingrate'] = cdf['closingrate'].astype(float).fillna(0)
        print(cdf)
        

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        print(idf)

        idf['closingrate'] = idf['closingrate'].astype(float).fillna(0)

        #print



       # print(idf)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R','O']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','O','R']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()

      #  dfR['closingrate'] = dfR['closingrate'].astype(float).fillna(0)
       # dfR['rate'] = dfR['rate'].astype(float).fillna(0)
       # print(idf)
        dfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       # print(dfR)

        dfR['rate'] = dfR['rate'].fillna(0)

        #dfR['closingrate'] = np.where(dfR['closingrate'] >0,dfR['closingrate'],dfR['rate'])
        dfR['balance'] = dfR['quantity'].astype(float)  * dfR['closingrate'].astype(float)
       # print(dfR)
        dfR = dfR.drop(['rate','_merge','stockttype','entrydatetime','id'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock__id':'stockid', 'stock':'stockname'}, inplace = True)


        dfR = dfR.groupby(['stockname','stockid','closingrate'])[['quantity','balance']].sum().abs().reset_index()

       


        print(dfR)

        return Response(dfR.T.to_dict().values())
    


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
        
class dashboardkpis(ListAPIView):

   # serializer_class = balancesheetserializer
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
    

class dashboardgraphkpis(ListAPIView):

    #serializer_class = balancesheetserializer
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


class gstr3b1(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        stk =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(Q(isactive = 1),Q(entity = entity1)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)



        


        #print(df.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs())

        #return Response(df2)

        df1 = pd.DataFrame(
       {
        "NatureofSupplies": ["(a) outward taxable supplies(Other then Zero rated ,Nil rated and Execpted)", "(b) Outward taxable supplies (Zero rated)", "(C) Other outward supplies", "(d) Inward supplies", "(e) Non-GST outward supplies"],
        "Totaltaxablesupplies": [15000, 7000, 19000,25000,12000],
         "IntegartedTax": [18000, 14000, 35000,38000,20000],
         "CentralTax": [3000, 7000, 14000,13000,8000],
         "StateUTTax": [3000, 7000, 14000,13000,8000],
         "Cess": [3000, 7000, 14000,13000,8000],
            },
            
        )


        df2 = pd.DataFrame(
       {
        "NatureofSupplies": [" Supplies made to unregistered persons", "Supplies made to composition taxable persons", "Supplies made to UIN holders"],
        "placeofsupplies": ["Punjab", "Haryana", "chandigarh"],
         "Totaltaxablevalue": [18000, 14000, 35000],
         "integratedtax": [3000, 7000, 14000],
        
            },
            
        )


        df3 = pd.DataFrame(
       {
        "Details": ["(A) ITC Available(whether in full or part)", "(1) Import of goods", "(2) Import of services","(3) Import supplies liable to reverse chnarge(Other than 1 & 2 above)", "(4) Inwrad supplies from ISD","(5) All other ITC","(B) ITC Reversed","(1) As per rules 42 & 43 of CGST rules","(2) Others","(C) Net ITC available(A) - (B)","(D) Ineligible ITC","(1) AS Per section 17(5)","(2) Others"],
         "integratedtax": [18000, 14000, 35000,18000, 14000, 35000,18000, 14000, 35000,35000,1200,1200,1200],
         "CentralTax": [18000, 14000, 35000,18000, 14000, 35000,18000, 14000, 35000,3500,1200,1200,1200],
         "StateUTTax": [18000, 14000, 35000,18000, 14000, 35000,18000, 14000, 35000,3500,1200,1200,1200],
         "Cess": [18000, 14000, 35000,18000, 14000, 35000,18000, 14000, 35000,3500,1200,1200,1200],
         "Isbold": [True, False, False,False, False, False,True,False, False,True,True,False,False],
        
            },
            
        )


        df4 = pd.DataFrame(
       {
        "natureofsupplies": ["From a supplier under composition scheme, Exempt and Nil rated supplies", "Non GST Supply"],
         "interstatesupplies": [18000, 14000],
         "intrastatesupplies": [18000, 14000],
        },
            
        )

        df5 = pd.DataFrame(
       {
        "description": ["Integrated Tax", "Central Tax","State/UT Tax","Cess"],
        "Taxpayable": [18000, 14000,18000, 14000],
        "integratedtax": [18000, 14000,18000, 14000],
        "centraltax": [18000, 14000,18000, 14000],
        "stateuttax": [18000, 14000,18000, 14000],
        "cess": [18000, 14000,18000, 14000],
        "integratedtax": [18000, 14000,18000, 14000],
        "taxpaidtdstcs" : [18000, 14000,18000, 14000],
        "taxcesspaidincash": [18000, 14000,18000, 14000],
        "interest": [18000, 14000,18000, 14000],
        "latefee": [18000, 14000,18000, 14000],
        },
            
        )

        df6 = pd.DataFrame(
       {
        "details": ["TDS", "TCS"],
        "integratedtax": [18000, 14000],
        "centraltax": [18000, 14000],
        "statetax": [18000, 14000],
        },
            
        )

        #print(json.loads(df1.T.to_json()))


        headers = json.dumps({ 

                              'Year'  : 2023,
                              'Month' : 12,
                              'entity' : 'Reliance industries',
                              'GSTIN' : '03APXPB5894F',
                              
                              'table1':json.loads(df1.to_json(orient='records')),
                              'table2':json.loads(df2.to_json(orient='records')),
                              'table3':json.loads(df3.to_json(orient='records')),
                              'table4':json.loads(df4.to_json(orient='records')),
                              'table5':json.loads(df5.to_json(orient='records')),
                              'table6':json.loads(df6.to_json(orient='records')),
                               })

        # allDays=[]
        # allDays.append(df1.T.to_dict().values())
        # allDays.append(df2.T.to_dict().values())

        return JsonResponse(json.loads(headers), safe = False)

        #return JsonResponse(json.loads(df1.T.to_json()), safe = False)

       # return Response(df1.T.to_dict().values())
    

    

class generalfunctions:

    def __init__(self, entityid,startdate,enddate):
        self.entityid = entityid
        self.startdate = startdate
        self.enddate = enddate

    
        

    def getstockdetails(self):
        stk =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate)).filter(account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)
        stkunion = stk.union(stk2)
        df = read_frame(stkunion)
      #  df = df.drop(['debit','credit'],axis=1)
        return df

    def getinventorydetails(self):
        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if len(dfg) > 0:
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg

        utc = pytz.UTC

        currentdates = entityfinancialyear.objects.get(
            entity=self.entityid,
            finendyear__gte=self.startdate,
            finstartyear__lte=self.startdate
        )

        # Optimize filtering logic
        is_active = currentdates.isactive == 1
        enddate_filtered = utc.localize(datetime.strptime(self.enddate, '%Y-%m-%d')) >= currentdates.finendyear

        purchase_filters = {
            'isactive': 1,
            'stockttype__in': ['P', 'R', 'O'],
            'accounttype': 'DD',
            'entity': self.entityid,
            'entrydatetime__lte': self.enddate
        }

        sales_filters = {
            'isactive': 1,
            'stockttype__in': ['S', 'I'],
            'accounttype': 'DD',
            'entity': self.entityid,
            'entrydatetime__lte': self.enddate
        }

        # Apply filters
        purchases = StockTransactions.objects.filter(**purchase_filters)
        sales = StockTransactions.objects.filter(**sales_filters)

        if is_active:
            purchases = purchases.values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')
            sales = sales.values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')
        elif enddate_filtered:
            purchases = purchases.exclude(account__accountcode=9000).values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')
            sales = sales.exclude(isbalancesheet=0).values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')
        else:
            purchases = purchases.values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')
            sales = sales.exclude(isbalancesheet=0).values('stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate', 'id')

        inventory = purchases.union(sales).order_by('entrydatetime')

        closingprice = closingstock.objects.filter(entity=self.entityid).values('stock__id', 'closingrate')

        idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        idf = pd.merge(idf, cdf, on='stock__id', how='outer', indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P', 'R', 'O']), 'P', 'S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P', 'R', 'O']), idf['quantity'], -1 * idf['quantity'])
        idf['quantity'] = idf['quantity'].astype(float).fillna(0)
        idf['CS'] = idf.groupby(['stock__id', 'stockttype'])['quantity'].cumsum()

        dfR = idf.groupby(['stock__id'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

        return dfR


    
    



    def getinventorydetails_1(self, dfR_1):
        # Convert necessary columns to float once
        dfR_1['closingrate'] = np.where(dfR_1['closingrate'] > 0, dfR_1['closingrate'], dfR_1['rate'])
        
        # Calculate 'balance' efficiently
        dfR_1['quantity'] = dfR_1['quantity'].astype(float)  # Convert once to float for reuse
        dfR_1['closingrate'] = dfR_1['closingrate'].astype(float)  # Ensure it's float
        dfR_1['balance'] = dfR_1['quantity'] * -1 * dfR_1['closingrate']
        
        # Drop unnecessary columns
        dfR_1.drop(['stockttype', 'entrydatetime', '_merge', 'rate', 'id'], axis=1, inplace=True)
        
        # Rename columns
        dfR_1.rename(columns={'stock__id': 'account__id', 'stock': 'account__accountname'}, inplace=True)
        
        # Add static columns
        dfR_1['accounthead__name'] = 'Closing Stock'
        
        # Fetch the account ID only once
        account_id = accountHead.objects.get(code=200, entity=self.entityid).id
        dfR_1['account__accounthead'] = account_id
        
        return dfR_1

    def getinventorydetails_2(self,dfi):
        dfi['balance'] = dfi['quantity'].astype(float) * 1 * dfi['closingrate'].astype(float)
        dfi = dfi.drop(['stockttype','entrydatetime','_merge'],axis=1) 
        dfi.rename(columns = {'stock__id':'account__id', 'stock':'account__accountname'}, inplace = True)
        dfi['account__accounthead__name'] = 'Closing Stock'

        account_id = accountHead.objects.get(code = 200).id
        dfi['account__accounthead'] = account_id
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
        

        opuchases = StockTransactions.objects.filter(isactive =1,stockttype__in = ['P','R','O'],accounttype = 'DD',entity = self.entityid,entrydatetime__lt = self.startdate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lt = self.startdate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
        oinventory = opuchases.union(osales).order_by('entrydatetime')
        idf = read_frame(oinventory)


       
        closingprice = closingstock.objects.filter(entity = self.entityid).values('stock__id','closingrate')

        cdf = read_frame(closingprice)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R','O']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','O','R']), idf['quantity'],-1 * (idf['quantity']))
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
        return odfR

    def openinginventorydetails_1(self,odfi):
        odfi['balance'] = odfi['quantity'].astype(float) * -1 * odfi['rate'].astype(float)
        odfi = odfi.drop(['stockttype','entrydatetime','closingrate','_merge'],axis=1) 
        odfi.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfi['account__accounthead__name'] = 'Opening Stock'
        account_id = accountHead.objects.get(code = 9000,entity = self.entityid).id
        odfi['account__accounthead'] = account_id
        return odfi

    def openinginventorydetails_2(self,odfR):
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['rate'].astype(float)
        odfR = odfR.drop(['stock','stockttype','entrydatetime','closingrate','_merge'],axis=1) 
        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        account_id = accountHead.objects.get(code = 9000,entity = self.entityid).id
        #dfR_1['account__accounthead'] = account_id


        odfR['account__accounthead'] = account_id
        return odfR


    def getprofitandloss(self):

        utc=pytz.UTC
        
        currentdates = entityfinancialyear.objects.get(entity = self.entityid,finendyear__gte = self.startdate  ,finstartyear__lte =  self.startdate)

        if currentdates.isactive == 1 or utc.localize(datetime.strptime(self.enddate, '%Y-%m-%d')):
            pl1 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('creditamount',default = 0) - Sum('debitamount',default = 0)).filter(balance__gte = 0)
            pl2 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('creditamount',default = 0) - Sum('debitamount',default = 0)).filter(balance__lte = 0)
        else:
            pl1 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2,isbalancesheet = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('creditamount',default = 0) - Sum('debitamount',default = 0)).filter(balance__gte = 0)
            pl2 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2,isbalancesheet = 1).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('creditamount',default = 0) - Sum('debitamount',default = 0)).filter(balance__lte = 0)


        plunion = pl1.union(pl2)

        pldf = read_frame(plunion)
       # pldf = pldf.drop(['debit','credit'],axis=1)




        return pldf
    

    def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg
    

    def getopeningstockdetails(self):
        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if len(dfg) > 0:
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg

        # Combined filter for transactions
        filters = {
            'isactive': 1,
            'accounttype': 'DD',
            'entity': self.entityid,
            'entrydatetime__lt': self.startdate
        }

        # Single query for both purchases and sales
        transactions = StockTransactions.objects.filter(**filters).values(
            'stock', 'stockttype', 'quantity', 'entrydatetime', 'stock__id', 'rate'
        )

        # Fetch closing prices in one go
        closingprice = closingstock.objects.filter(entity=self.entityid).values('stock__id', 'closingrate')

        # Union and order the inventory (no need to filter separately for purchases and sales)
        oinventory = transactions.order_by('entrydatetime')

        # Read frames
        cdf = read_frame(closingprice)
        idf = read_frame(oinventory)

        # Merge dataframes
        idf = pd.merge(idf, cdf, on='stock__id', how='outer', indicator=True)

        # Vectorized operations for stock type and quantity adjustments
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P', 'R', 'O']), 'P', 'S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P', 'O', 'R']), idf['quantity'], -1 * idf['quantity'])
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock', 'stockttype'])['quantity'].cumsum()

        # Apply FiFo function and reset index
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

        # Update closing rate and calculate balance
        odfR['closingrate'] = np.where(odfR['rate'] > 0, odfR['rate'], odfR['closingrate'])
        odfR['balance'] = odfR['quantity'] * odfR['closingrate']

        # Drop unnecessary columns
        odfR.drop(['stockttype', 'entrydatetime', '_merge', 'rate'], axis=1, inplace=True)

        # Rename columns for clarity
        odfR.rename(columns={'stock__id': 'account__id', 'stock': 'account__accountname'}, inplace=True)
        odfR['accounthead__name'] = 'Opening Stock'

        # Fetch account ID once and use it directly
        account_id = accountHead.objects.get(code=9000, entity=self.entityid).id
        odfR['account__accounthead'] = account_id

        return odfR



      #  return odfR
    

    def gettradingdetails(self):

       # currentdates = entityfinancialyear.objects.get(entity = self.entityid,finendyear__gte = self.startdate  ,finstartyear__lte =  self.startdate)

       # currentdates.finstartyear

        # Common filters
        common_filters = {
            'isactive': 1,
            'entity': self.entityid,
            'account__accounthead__detailsingroup': 1,
        }

        exclude_filters = {
            'accounttype': 'MD',
            'transactiontype': 'PC',
        }

        annotate_fields = {
            'balance': Sum('debitamount', default=0) - Sum('creditamount', default=0),
            'quantity': Sum('quantity', default=0),
        }

        values_fields = ['accounthead__name', 'account__accounthead', 'account__id', 'account__accountname']

        # stk0 Query
        stk0 = StockTransactions.objects.filter(
            **common_filters,
            entrydatetime=self.startdate,
            account__accountcode=9000
        ).exclude(**exclude_filters).values(*values_fields).annotate(**annotate_fields).filter(balance__gt=0)

        # stk Query
        stk = StockTransactions.objects.filter(
            **common_filters,
            entrydatetime__range=(self.startdate, self.enddate)
        ).exclude(
            **exclude_filters
        ).exclude(
            account__accountcode__in=[200, 9000]
        ).values(*values_fields).annotate(**annotate_fields).filter(balance__gt=0)

        # stk2 Query (similar to stk with balance__lt=0 and a different value field)
        stk2 = StockTransactions.objects.filter(
            **common_filters,
            entrydatetime__range=(self.startdate, self.enddate)
        ).exclude(
            **exclude_filters
        ).exclude(
            account__accountcode__in=[200, 9000]
        ).values('accounthead__name', 'account__creditaccounthead', 'account__id', 'account__accountname').annotate(**annotate_fields).filter(balance__lt=0)

        # Union of queries
        plunion = stk.union(stk2, stk0)

        # Convert to DataFrame
        pldf = read_frame(plunion)

       # print(pldf)

        return pldf
    

    def getgrossprofit(self,odfR,df, dfR):

        df = pd.concat([odfR, df, dfR], ignore_index=True)

        # Convert and fill missing values in one step
        df[['balance', 'quantity', 'closingrate']] = df[['balance', 'quantity', 'closingrate']].fillna(0).astype(float)

        # Determine the gross result type and value
        balance_sum = df['balance'].sum()
        if balance_sum < 0:
            result_row = ['Gross Profit', 0.00, -1, 0.00, -balance_sum, 'Gross Profit', -1]
        else:
            result_row = ['Gross Loss', 0.00, -1, 0.00, -balance_sum, 'Gross Loss', -1]

        # Append the result row
        df.loc[len(df.index)] = result_row

        return df

    def get_gpp_and_l(self, odfR, df, dfR, pldf):
        # Combine all frames into one DataFrame
        combined_df = pd.concat([odfR, df, dfR])

        # Ensure 'balance' column is of float type
        combined_df['balance'] = combined_df['balance'].astype(float)

        # Calculate the gross profit/loss
        total_balance = combined_df['balance'].sum()

        if total_balance <= 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit', -total_balance]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss', -total_balance]

        # Ensure 'balance' column in pldf is of float type
        pldf['balance'] = pldf['balance'].astype(float)

        # Calculate net profit/loss based on updated pldf balance
        net_balance = pldf['balance'].sum()

        if net_balance > 0:
            pldf.loc[len(pldf.index)] = ['Net Profit', -2, -2, 'Net Profit', -net_balance]
        else:
            pldf.loc[len(pldf.index)] = ['Net Loss', -2, -2, 'Net Loss', -net_balance]

        # Optional: Uncomment the following line if you need a 'drcr' column
        # pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)

        return pldf
    
    def getgppandl(self,odfR,df, dfR,pldf):
        frames = [odfR,df, dfR]

        df = pd.concat(frames)

       # print(df)

        df['balance'] = df['balance'].astype(float)
       # print(df)

        if df['balance'].sum() <= 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',-df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',-df['balance'].sum()]

        #print(pldf)

        pldf['balance'] = pldf['balance'].astype(float)
        if df['balance'].sum() > 0:
            pldf.loc[len(pldf.index)] = ['Net Profit', -2, -2, 'Net Profit',-pldf['balance'].sum()]
            
        else:
            pldf.loc[len(pldf.index)] = ['Net Loss ', -2, -2, 'Net Loss',-pldf['balance'].sum()]
           

        #pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)

        return pldf

    


class BalanceStatement(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']
    

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        # Initialize the stk object with necessary parameters
        stk = generalfunctions(entityid=entity1, startdate=startdate, enddate=enddate)

        # Retrieve required data frames in one go
        dfR_initial = stk.getinventorydetails()
        dfR = stk.getinventorydetails_1(dfR_1=dfR_initial)

        # Opening stock details
        odfR = stk.getopeningstockdetails()

        # Other details
        df = stk.gettradingdetails()
        pldf = stk.getprofitandloss()

        # Final data frame
        dfi = dfR  # or you can keep it as dfR if needed in later code

        # Step 1: Optimize `pldf` initialization
        pldf = stk.get_gpp_and_l(odfR=odfR, df=df, dfR=dfR, pldf=pldf)
        pldf = pldf.loc[pldf.account__id == -2]  # Filter directly after initialization

        # Step 2: Pre-fetch related data for `account` and `entityfinancialyear` queries
        acc = account.objects.select_related().get(accountcode=9000, entity=entity1)
        currentdates = entityfinancialyear.objects.get(
            entity=entity1, finendyear__gte=startdate, finstartyear__lte=startdate
        )

        utc = pytz.UTC
        is_financial_year_active = (
            currentdates.isactive == 1
            or utc.localize(datetime.strptime(enddate, '%Y-%m-%d')) > currentdates.finendyear
        )

        # Step 3: Consolidate common query parameters for StockTransactions
        common_filters = {
            "isactive": 1,
            "entity": entity1,
            "entrydatetime__range": (currentdates.finstartyear, enddate),
            "account__accounthead__detailsingroup": 3,
        }
        exclude_md = {"accounttype": "MD"}

        # Step 4: Use condition to construct queries
        if is_financial_year_active:
            bs1 = (
                StockTransactions.objects.filter(**common_filters)
                .exclude(**exclude_md)
                .values(
                    "accounthead__name",
                    "account__accounthead",
                    "account__id",
                    "account__accountname",
                )
                .annotate(balance=Sum("debitamount", default=0) - Sum("creditamount", default=0))
                .filter(balance__gt=0)
            )
            bs2 = (
                StockTransactions.objects.filter(**common_filters)
                .exclude(**exclude_md)
                .values(
                    "account__creditaccounthead__name",
                    "account__creditaccounthead",
                    "account__id",
                    "account__accountname",
                )
                .annotate(balance=Sum("debitamount", default=0) - Sum("creditamount", default=0))
                .filter(balance__lt=0)
            )
        else:
            bs1 = (
                StockTransactions.objects.filter(**common_filters, isbalancesheet=1)
                .exclude(**exclude_md)
                .values(
                    "accounthead__name",
                    "account__accounthead",
                    "account__id",
                    "account__accountname",
                )
                .annotate(balance=Sum("debitamount", default=0) - Sum("creditamount", default=0))
                .filter(balance__gt=0)
            )
            bs2 = (
                StockTransactions.objects.filter(**common_filters, isbalancesheet=1)
                .exclude(**exclude_md)
                .values(
                    "account__creditaccounthead__name",
                    "account__creditaccounthead",
                    "account__id",
                    "account__accountname",
                )
                .annotate(balance=Sum("debitamount", default=0) - Sum("creditamount", default=0))
                .filter(balance__lt=0)
            )

        # Step 5: Union queries and convert to DataFrame
        bsunion = bs1.union(bs2)
        bsdf = read_frame(bsunion)

        # Step 6: Rename columns in `pldf`
        pldf.rename(columns={"account__accounthead__name": "accounthead__name"}, inplace=True)


       # print(pldf)

        
        bsdf = pd.concat([bsdf, dfi, pldf], ignore_index=True)

        # Convert 'balance' column to float in one step
        bsdf['balance'] = bsdf['balance'].astype(float)

        # Determine 'drcr' column using vectorized operations
        bsdf['drcr'] = np.where(
            bsdf['accounthead__name'] == 'Closing Stock', 0,
            np.where(
                bsdf['accounthead__name'] == 'Opening Stock', 1,
                np.where(bsdf['balance'] > 0, 0, 1)
            )
        )

        # Rename columns in one operation
        bsdf.rename(
            columns={
                'accounthead__name': 'accountheadname',
                'account__accounthead': 'accounthead',
                'account__accountname': 'accountname',
                'account__id': 'accountid'
            },
            inplace=True
        )

        # Sort the dataframe by 'accounthead'
        bsdf.sort_values(by=['accounthead'], ascending=False, inplace=True)

        # Update 'balance' column based on 'drcr'
        bsdf['balance'] = np.where(bsdf['drcr'] == 1, bsdf['balance'].abs(), -bsdf['balance'].abs())

        # Group and aggregate the data
        grouped_df = (
            bsdf.groupby(['accounthead', 'accountheadname', 'drcr', 'accountname', 'accountid'])
            [['balance', 'quantity']]
            .sum()
            .abs()
            .reset_index()
            .sort_values(by=['accounthead'])
        )
        

        # Return the transformed data as a dictionary of values
        return Response(grouped_df.T.to_dict().values())
    


class tradingaccountstatement(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        # Fetch query parameters
        entity_id = self.request.query_params.get('entity')
        start_date = self.request.query_params.get('startdate')
        end_date = self.request.query_params.get('enddate')

        # Initialize general functions with parameters
        gf = generalfunctions(entityid=entity_id, startdate=start_date, enddate=end_date)

        # Get inventory details
        dfR_initial = gf.getinventorydetails()

        # Process inventory details with custom function
        dfR = gf.getinventorydetails_1(dfR_1=dfR_initial)

        # Get opening stock details
        odfR = gf.getopeningstockdetails()

        # Get trading details
        trading_df = gf.gettradingdetails()

        # Calculate gross profit
        df = gf.getgrossprofit(odfR=odfR, df=trading_df, dfR=dfR)

        # Apply 'drcr' logic in a vectorized manner for performance
        df['drcr'] = np.where(df['accounthead__name'] == 'Closing Stock', 1, np.where(df['balance'] >= 0, 0, 1))

        # Rename columns for better readability
        df.rename(columns={
            'accounthead__name': 'accountheadname',
            'account__accounthead': 'accounthead',
            'account__accountname': 'accountname',
            'account__id': 'accountid'
        }, inplace=True)

        # Group by relevant fields, aggregate, and sort the data
        grouped_df = (df.groupby(
                        ['accounthead', 'accountheadname', 'drcr', 'accountname', 'accountid', 'closingrate']
                    )[['balance', 'quantity']].sum()
                    .abs().reset_index()
                    .sort_values(by='accounthead', ascending=False))

        # Convert the DataFrame to a list of dictionaries and return the response
        return Response(grouped_df.T.to_dict().values())
    

class incomeandexpensesstatement(ListAPIView):

   # serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        # Initialize stk object
        stk = generalfunctions(entityid=entity1, startdate=startdate, enddate=enddate)

        # Fetch initial inventory details
        dfR_initial = stk.getinventorydetails()
        
        # Process inventory details (avoid unnecessary copying)
        dfR = stk.getinventorydetails_1(dfR_1=dfR_initial)
        
        # Get opening stock details
        odfR = stk.getopeningstockdetails()

        # Fetch trading details and profit & loss details
        df = stk.gettradingdetails()
        pldf = stk.getprofitandloss()

        # Combine dataframes using optimized processing
        pldf = stk.get_gpp_and_l(odfR=odfR, df=df, dfR=dfR, pldf=pldf)

        # Replace lambda with vectorized operations
        pldf['drcr'] = (pldf['balance'] > 0).astype(int)

        # Rename columns (inplace is already optimized)
        pldf.rename(columns={
            'account__accounthead__name': 'accountheadname', 
            'account__accounthead': 'accounthead',
            'account__accountname': 'accountname',
            'account__id': 'accountid'
        }, inplace=True)

        # Final aggregation (ensure efficient groupby)
        result = pldf.groupby(
            ['accounthead', 'accountheadname', 'drcr', 'accountname', 'accountid']
        )[['balance']].sum().abs().reset_index().sort_values(by=['accounthead'])

        # Return the result as a dictionary of values
        return Response(result.T.to_dict().values())

    

class netprofitbalance(ListAPIView):

   # serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
        stk = generalfunctions(entityid = entity1,startdate= startdate,enddate=enddate)
       
        dfR_initial = stk.getinventorydetails()
        dfR = stk.getinventorydetails_1(dfR_1 = dfR_initial)

        ##################################################################
        odfR = stk.getopeningstockdetails()
        ##################################################################
        df = stk.getstockdetails()
        pldf = stk.getprofitandloss()

        pldf = stk.getgppandl(odfR = odfR,df = df, dfR = dfR,pldf=pldf)

        pldf['drcr'] = pldf['balance'].apply(lambda x: 0 if x > 0 else 1)
        
          

        

        pldf.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)


       # print(pldf)


        pldf = pldf[((pldf.accountid == -2))]

        constitution = Entity.objects.get(id = entity1)

        print(constitution.const.constcode)

        if constitution.const.constcode == 1001:
            aqs = account.objects.filter(entity = entity1,accounthead__code = 6200).values('id','accountname','accounthead__id', 'accounthead__name','sharepercentage')
            
            


        if constitution.const.constcode == 1000:
            aqs = account.objects.filter(entity = entity1,accounthead__code = 6300).values('id','accountname','accounthead__id','sharepercentage')

        adf = read_frame(aqs)
        print(adf)

        adf['key'] = 1
        pldf['key'] = 1

        print(adf)
        print(pldf)


        result = pd.merge(adf, pldf, on ='key').drop(['key','accounthead','accountid','accountname_y'],axis = 1)


        result['sharepercentage'] = result['sharepercentage'].astype(float)
        result['balance'] = result['balance'].astype(float)

        

        result['balance'] = (result['sharepercentage'] * result['balance'])/100

        

        result.rename(columns = {'accounthead__id':'accounthead','accountname_x':'accountname','id':'account'}, inplace = True)

        print(result)








        


        


        



        


     


     




      
    
     
        return Response(result.groupby(['accounthead','accountheadname','drcr','accountname','account'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())
    
    

class gstrhsnapi(ListAPIView):

    #serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')


        stk =salesOrderdetails.objects.filter(Q(isactive = 1),Q(entity = entity),Q(salesorderheader__sorderdate__range = (stardate,enddate))).values('product__hsn','product__productname','product__unitofmeasurement__unitname','orderqty','linetotal','amount','cgst','sgst','igst','cess','product__totalgst')

        df = read_frame(stk)

        print(df)

        df.rename(columns = {'product__hsn':'hsn', 'product__productname':'description','product__unitofmeasurement__unitname':'uqc','orderqty':'totalquantity','linetotal':'totalvalue','product__totalgst':'rate','amount':'taxablevalue'}, inplace = True)


       
        return  Response(df.groupby(['hsn','description','uqc','rate'])[['totalquantity','totalvalue','taxablevalue','cgst','sgst','igst','cess']].sum().abs().reset_index().T.to_dict().values())
    

class gstr1b2csmallapi(ListAPIView):

    #serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        



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

   # serializer_class = gstr1b2bserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'id':["in", "exact"]
    
    # }
    #filterset_fields = ['id']
    def get(self, request, format=None):
       # acc = self.request.query_params.get('acc')
        entity = self.request.query_params.get('entity')
        stardate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        



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
    

class gstr1b2baapi(ListAPIView):

    #serializer_class = gstr1b2bserializer
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

        stardate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        



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
    

class gstr1b2bapi(ListAPIView):

    #serializer_class = gstr1b2bserializer
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

        stardate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        



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
        enddate = self.request.query_params.get('enddate')

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


class ledgersummarylatestget(ListAPIView):

   # serializer_class = TrialbalanceSerializerbyaccounthead
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account__accounthead']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        # accounthead = self.request.query_params.get('accounthead')
        # drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
       
        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))




        
        df = read_frame(stk)

        if len(df.index) > 0:

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

            finaldf = df.sort_values(by=['accountname']).T.to_dict().values()

            return Response(finaldf)
         
        return Response(df)


class ledgersummarylatest(ListAPIView):

    serializer_class = ledgersummarySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account__accounthead']


    
    def post(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = request.data.get('entity',None)
        # accounthead = self.request.query_params.get('accounthead')
        # drcrgroup = self.request.query_params.get('drcr')
        startdate = request.data.get('startdate',None)
        enddate = request.data.get('enddate',None)
       
        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))

        if request.data.get('accounthead'):
            accountheads =  [int(x) for x in request.data.get('accounthead', '').split(',')]
            ob = ob.filter(accounthead__in=accountheads)
            stk = stk.filter(accounthead__in=accountheads)

        if request.data.get('account'):
            accounts =  [int(x) for x in request.data.get('account', '').split(',')]
            ob = ob.filter(account__in=accounts)
            stk = stk.filter(account__in=accounts)

        if request.data.get('drcr') == '1':

            stk = stk.filter(balance__gt=0)
          #  print(stk.query.__str__())
        
        if request.data.get('drcr') == '0':

            stk = stk.filter(balance__lt=0)

        if request.data.get('drcr') == 'O':

            stk = stk.filter(transactiontype = 'O')
           # print(stk.query.__str__())

        if request.data.get('amountstart') and request.data.get('amountend'):
            stk = stk.filter((Q(balance__gte=Decimal(request.data.get('amountstart'))) & Q(balance__lte=Decimal(request.data.get('amountend')))))




        
        df = read_frame(stk)

        print(df)

        if len(df.index) > 0:

            df['drcr'] = 'CR'

            df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
            df['credit'] = np.where(df['balance'] < 0, df['balance'],0)
            df['debit'] = np.where(df['balance'] >= 0, df['balance'],0)

            

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

            finaldf = df.sort_values(by=['accountname']).T.to_dict().values()

            return Response(finaldf)
         
        return Response(df)
    


class accountbalance(ListAPIView):

   # serializer_class = TrialbalanceSerializerbyaccounthead
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = ['account__accounthead']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        # accounthead = self.request.query_params.get('accounthead')
        # drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        df = read_frame(stk)

        df['balance'] = df['debit'] - df['credit']

        df['debit'] = np.where(df['balance'] >= 0,df['balance'],0)
        df['credit'] = np.where(df['balance'] <= 0,-df['balance'],0)



        df['drcr'] = np.where(df['credit'] > df['debit'],0,1)

        df = df[~((df.credit == 0.0) & (df.debit == 0.0))]

        #df = df.groupby(['accounthead__id','accountname','drcr','account'])[['debit','credit','quantity']].sum().abs().reset_index()
        df.rename(columns = {'account__accountname':'accountname','account__id':'account','account__accounthead': 'accounthead','account__accounthead__name':'accountheadname','account__accounthead__detailsingroup':'accounttype','credit':'creditamount','debit':'debitamount'}, inplace = True)
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())



class ledgerapiApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []

    #serializer_class = LoginSerializer


    def post(self,request):
        email = request.data.get('email',None)
        password = request.data.get('password',None)

        print(email)
        print(password)


        return Response(email)

       # user = authenticate(username = email,password = password)

        # if user:
        #     serializer = self.serializer_class(user)
        #     return response.Response(serializer.data,status = status.HTTP_200_OK)
        # return response.Response({'message': "Invalid credentials"},status = status.HTTP_401_UNAUTHORIZED)
    


class ledgerdetails(ListAPIView):

    serializer_class = ledgerdetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'account':["in", "exact"],'accounthead':["in", "exact"]}


    
    def post(self, request, format=None):
        entity = request.data.get('entity', None)
        startdate = request.data.get('startdate', None)
        enddate = request.data.get('enddate')
        print(account)
        currentdates = entityfinancialyear.objects.filter(
                entity=entity,
                finstartyear__lte=enddate,  
                finendyear__gte=startdate   
            ).first()
        utc = pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        stk = StockTransactions.objects.filter(
            entry__entrydate1__range=(currentdates.finstartyear, enddate),
            isactive=1,
            entity=entity
        ).exclude(accounttype='MD').exclude(transactiontype__in=['PC']).values(
            'account__accountname',
            'entry__entrydate1',
            'transactiontype',
            'transactionid',
            'drcr',
            'desc',
            'account__id'
        ).annotate(
            debitamount=Sum('debitamount'),
            creditamount=Sum('creditamount'),
            quantity=Sum('quantity')
        ).order_by('entry__entrydate1')

        # Define transformations for filters
        filters = {
            'accounthead': lambda x: list(map(int, x.split(','))),
            'account': lambda x: list(map(int, x.split(','))),
            'transactiontype': lambda x: x.split(','),  # No need for explicit `str` casting
        }

        # Apply filters based on request data
        for key, transform in filters.items():
            value = request.data.get(key)
            if value:
                stk = stk.filter(**{f'{key}__in': transform(value)})

        # Handle 'drcr' filters
        drcr = request.data.get('drcr')
        if drcr == '1':
            stk = stk.filter(debitamount__gt=0)
        elif drcr == '0':
            stk = stk.filter(creditamount__gt=0)

        # Apply description filter
        desc = request.data.get('desc')
        if desc:
            stk = stk.filter(desc__icontains=desc)

        # Apply amount range filter
        amountstart = request.data.get('amountstart')
        amountend = request.data.get('amountend')
        if amountstart and amountend:
            amountstart = Decimal(amountstart)
            amountend = Decimal(amountend)
            stk = stk.filter(
                Q(debitamount__range=(amountstart, amountend)) |
                Q(creditamount__range=(amountstart, amountend))
            )

        df = read_frame(stk)

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        openingbalance = df[(df['entry__entrydate1'] >= datetime.date(currentdates.finstartyear)) & (df['entry__entrydate1'] < startdate.date())]

        details = df[(df['entry__entrydate1'] >= startdate.date()) & (df['entry__entrydate1'] < enddate.date())]

        details['debitamount'] = details['debitamount'].astype(float).fillna(0)
        details['creditamount'] = details['creditamount'].astype(float).fillna(0)
        details['quantity'] = details['quantity'].astype(float).fillna(0)

        if request.data.get('aggby'):
            details['entry__entrydate1'] = pd.to_datetime(details['entry__entrydate1'], errors='coerce')
            details['entry__entrydate1'] = details['entry__entrydate1'].dt.to_period(request.data.get('aggby')).dt.end_time
            if request.data.get('aggby') != 'D':
                details['transactiontype'] = request.data.get('aggby')
                details['transactionid'] = -1
                details['drcr'] = True
                details['desc'] = pd.to_datetime(details['entry__entrydate1'], format='%m').dt.strftime('%b')
                details = details.groupby(['account__accountname', 'account__id', 'entry__entrydate1', 'transactiontype', 'transactionid', 'drcr', 'desc'])[['debitamount', 'creditamount', 'quantity']].sum().abs().reset_index()

        openingbalance = openingbalance[['account__accountname', 'debitamount', 'creditamount', 'quantity', 'account__id']].copy()

        openingbalance['debitamount'] = openingbalance['debitamount'].astype(float).fillna(0)
        openingbalance['creditamount'] = openingbalance['creditamount'].astype(float).fillna(0)
        openingbalance['quantity'] = openingbalance['quantity'].astype(float).fillna(0)

        openingbalance = openingbalance.groupby(['account__accountname', 'account__id'])[['debitamount', 'creditamount', 'quantity']].sum().abs().reset_index()

        openingbalance['balance'] = openingbalance['debitamount'] - openingbalance['creditamount']

        openingbalance['debitamount'] = np.where(openingbalance['balance'] >= 0, openingbalance['balance'], 0)
        openingbalance['creditamount'] = np.where(openingbalance['balance'] <= 0, -openingbalance['balance'], 0)

        openingbalance['drcr'] = np.where(openingbalance['balance'] > 0, True, False)

        openingbalance['entry__entrydate1'] = startdate
        openingbalance['transactiontype'] = 'O'
        openingbalance['transactionid'] = -1
        openingbalance['desc'] = 'Opening'

        openingbalance.drop(['balance'], axis=1)

        df = pd.concat([openingbalance, details]).reset_index()

        df['debitamount'] = df['debitamount'].astype(float).fillna(0)
        df['creditamount'] = df['creditamount'].astype(float).fillna(0)
        df['quantity'] = df['quantity'].astype(float).fillna(0)

        df = df.groupby(['account__accountname', 'account__id'])[['debitamount', 'creditamount', 'quantity']].sum().abs().reset_index()

        df['balance'] = df['debitamount'] - df['creditamount']

        df['drcr'] = np.where(df['balance'] > 0, True, False)

        df['entry__entrydate1'] = enddate
        df['transactiontype'] = 'T'
        df['transactionid'] = -1
        df['desc'] = 'Total'

        df.drop(['balance'], axis=1)

        print(df)

        df2 = pd.concat([openingbalance, details])

        bsdf = pd.concat([df2, df]).reset_index()

        bsdf = bsdf[['account__accountname', 'account__id', 'creditamount', 'debitamount', 'desc', 'entry__entrydate1', 'transactiontype', 'transactionid', 'drcr', 'quantity']]

        bsdf.rename(columns={'account__accountname': 'accountname', 'account__id': 'accountid', 'entry__entrydate1': 'entrydate'}, inplace=True)

        bsdf['displaydate'] = pd.to_datetime(bsdf['entrydate']).dt.strftime('%d-%m-%Y')

        pd.set_option('display.max_columns', None)
        bsdf.head()

        print(bsdf)

        account_summaries = pd.DataFrame()

        if len(bsdf.index) > 0:
            account_summaries = (bsdf.groupby(['accountname', 'accountid'])
                         .apply(lambda x: x[['creditamount', 'debitamount', 'desc', 'entrydate', 'transactiontype', 'transactionid', 'displaydate', 'drcr', 'quantity']].to_dict('records'))
                         .reset_index()
                         .rename(columns={0: 'accounts'})).T.to_dict().values()

        print(account_summaries)




        
        
        
        return Response(account_summaries)




class interestdetails(ListAPIView):

    serializer_class = ledgerdetailsSerializer
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = {'account':["in", "exact"],'accounthead':["in", "exact"]}


    
    def post(self, request, format=None):
        #entity = request.data.get('entity')
        entity = request.data.get('entity',None)
        startdate = request.data.get('startdate',None)
        enddate = request.data.get('enddate')
        # param_list = request.GET.getlist('account')
        # print(param_list)
        # if request.data.get('account'):
        #     accounts =  [int(x) for x in request.GET.get('account', '').split(',')]
        print(account)
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accountname','entry__entrydate1','account__id').annotate(debitamount = Sum('debitamount',default=0),creditamount = Sum('creditamount',default=0)).order_by('account__id','entry__entrydate1')

        # if request.data.get('accounthead'):
        #     accountheads =  [int(x) for x in request.data.get('accounthead', '').split(',')]
        #     stk = stk.filter(accounthead__in=accountheads)
        
        if request.data.get('account'):
            accounts =  [int(x) for x in request.data.get('account', '').split(',')]
            stk = stk.filter(account__in=accounts)
        
        # if request.data.get('transactiontype'):
        #     transactiontype =  [str(x) for x in request.data.get('transactiontype', '').split(',')]
        #     stk = stk.filter(transactiontype__in=transactiontype)
        #    # print(stk.query.__str__())
        #    # details = details[(details['transactiontype'].isin(transactiontype))]

        # if request.data.get('drcr') == '1':

        #     stk = stk.filter(debitamount__gt=0)
        #   #  print(stk.query.__str__())
        
        # if request.data.get('drcr') == '0':

        #     stk = stk.filter(creditamount__gt=0)
        #    # print(stk.query.__str__())

        # if request.data.get('desc'):
        #     stk = stk.filter(desc__icontains=request.data.get('desc'))

        # if request.data.get('amountstart') and request.data.get('amountend'):
        #     stk = stk.filter((Q(debitamount__gte=Decimal(request.data.get('amountstart'))) & Q(debitamount__lte=Decimal(request.data.get('amountend')))) | (Q(creditamount__gte=Decimal(request.data.get('amountstart'))) & Q(creditamount__lte=Decimal(request.data.get('amountend')))))
           


            

         
            
        df = read_frame(stk)
        df['balance'] = df['debitamount'] - df['creditamount']


        df['balance'] = df['balance'].astype(float)



        #df['Closingbalance'] = df.groupby(['account__id','account__accountname','entry__entrydate1'])['balance'].cumsum()

        
        df['Closingbalance'] = df.groupby(['account__id','account__accountname','entry__entrydate1'])['balance'].cumsum()
       # df['entry__entrydate1'] = df.groupby(['account__id','account__accountname'])['entry__entrydate1'].apply(lambda x: x.sort_values())
        df['diff'] = df.groupby(['account__id','account__accountname'])['entry__entrydate1'].diff().astype('timedelta64[D]')

       # print(np.timedelta64(1,'D'))

       # print(df)
        df['diff'] = df['diff'].shift(-1)
        df['diff'] = df['diff'].fillna(0)   
        df['Closingbalance'] = df['Closingbalance'].astype(float).abs()

      #  print(df.dtypes)


        df['int'] = ((df['Closingbalance']  * df['diff'] * 6.00/365.00)/100.00).abs().round(2)


        df['Total'] = df['balance'].astype(float).abs() +  df['int'].abs()

        df['Total'] = df['Total'].round(2)

        df.rename(columns = {'account__accountname':'accountname','account__id':'accountid','entry__entrydate1':'entrydate'}, inplace = True)


        print(df)

        


    #     df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

    #     openingbalance = df[(df['entry__entrydate1'] >= datetime.date(currentdates.finstartyear)) & (df['entry__entrydate1'] < startdate.date())]

    #     details = df[(df['entry__entrydate1'] >= startdate.date()) & (df['entry__entrydate1'] < enddate.date())]

    #     details['debitamount'] = details['debitamount'].astype(float).fillna(0)
    #     details['creditamount'] = details['creditamount'].astype(float).fillna(0)
    #     details['quantity'] = details['quantity'].astype(float).fillna(0)



    #     ################################### TransactionType ###################################


    #     # if request.data.get('transactiontype'):
    #     #     transactiontype =  [str(x) for x in request.data.get('transactiontype', '').split(',')]
    #     #     details = details[(details['transactiontype'].isin(transactiontype))]

       
    #    ################################### Debit/Credit ###################################
        
    #     # if request.data.get('drcr') == '1':

            

    #     #     details = details[(details['debitamount'] > 0)]

        

    #     # if request.data.get('drcr') == '0':

    #     #     details = details[(details['creditamount'] > 0)]

        
    #     ################################### desc ###################################

        
    #     # if request.data.get('desc'):
    #     #     details = details[details['desc'].str.contains(request.data.get('desc'), regex=True, na=True)]


    #     ################################### Range between 2 values ###################################

        
    #     # if request.data.get('amountstart') and request.data.get('amountend') :
    #     #     details = details[((details['debitamount'] >= int(request.data.get('amountstart'))) & (details['debitamount'] <= int(request.data.get('amountend')))) | ((details['creditamount'] >= int(request.data.get('amountstart'))) & (details['creditamount'] <= int(request.data.get('amountend'))))]

        
    #   #  print(details)

    #     # if request.data.get('aggby') == 'M':
    #     #     details['entry__entrydate1'] = pd.to_datetime(details['entry__entrydate1'], format="%Y-%m") + MonthEnd(0)
    #     #     details['transactiontype'] = 'A'
    #     #     details['transactionid'] = -1
    #     #     details['drcr'] = True
    #     #    # details['desc'] = 'Agg'
    #     #     details['desc'] = pd.to_datetime(details['entry__entrydate1'], format='%q').dt.strftime('%b')
    #     #     details = details.groupby(['account__accountname','account__id','entry__entrydate1','transactiontype','transactionid','drcr','desc'])[['debitamount','creditamount','quantity']].sum().abs().reset_index()

    #     if request.data.get('aggby'):
    #         details['entry__entrydate1'] = pd.to_datetime(details['entry__entrydate1'], errors='coerce')
    #         details['entry__entrydate1'] = details['entry__entrydate1'].dt.to_period(request.data.get('aggby')).dt.end_time
    #         if request.data.get('aggby') != 'D':
    #             details['transactiontype'] = request.data.get('aggby')
    #             details['transactionid'] = -1
            
    #         details['drcr'] = True
    #        # details['desc'] = 'Agg'
    #         details['desc'] = pd.to_datetime(details['entry__entrydate1'], format='%m').dt.strftime('%b')
    #         details = details.groupby(['account__accountname','account__id','entry__entrydate1','transactiontype','transactionid','drcr','desc'])[['debitamount','creditamount','quantity']].sum().abs().reset_index()
        
    #     # if request.data.get('aggby') == 'W':
    #     #     details['entry__entrydate1'] = pd.to_datetime(details['entry__entrydate1'], errors='coerce')
    #     #     details['entry__entrydate1'] = details['entry__entrydate1'].dt.to_period("W").dt.end_time
    #     #     details['transactiontype'] = 'A'
    #     #     details['transactionid'] = -1
    #     #     details['drcr'] = True
    #     #    # details['desc'] = 'Agg'
    #     #     details['desc'] = pd.to_datetime(details['entry__entrydate1'], format='%m').dt.strftime('%b')
    #     #     details = details.groupby(['account__accountname','account__id','entry__entrydate1','transactiontype','transactionid','drcr','desc'])[['debitamount','creditamount','quantity']].sum().abs().reset_index()
            


        

    #     openingbalance = openingbalance[['account__accountname','debitamount','creditamount','quantity','account__id']].copy()

    #     openingbalance['debitamount'] = openingbalance['debitamount'].astype(float).fillna(0)
    #     openingbalance['creditamount'] = openingbalance['creditamount'].astype(float).fillna(0)
    #     openingbalance['quantity'] = openingbalance['quantity'].astype(float).fillna(0)
    #    # openingbalance['balance'] = openingbalance['balance'].astype(float).fillna(0)

    #     openingbalance = openingbalance.groupby(['account__accountname','account__id'])[['debitamount','creditamount','quantity']].sum().abs().reset_index()
    #    # print(openingbalance)

        
    #     openingbalance['balance'] = openingbalance['debitamount'] - openingbalance['creditamount']
        
    #     openingbalance['debitamount'] = np.where(openingbalance['balance'] >= 0,openingbalance['balance'],0)
    #     openingbalance['creditamount'] = np.where(openingbalance['balance'] <= 0,-openingbalance['balance'],0)

    #     openingbalance['drcr'] = np.where(openingbalance['balance'] > 0,True,False)

    #     openingbalance['entry__entrydate1'] = startdate
    #     openingbalance['transactiontype'] = 'O'
    #     openingbalance['transactionid'] = -1
    #     openingbalance['desc'] = 'Opening'

    #     openingbalance.drop(['balance'],axis = 1)


    #     df = pd.concat([openingbalance,details]).reset_index()

    #     ##############################################################

    #     df['debitamount'] = df['debitamount'].astype(float).fillna(0)
    #     df['creditamount'] = df['creditamount'].astype(float).fillna(0)
    #     df['quantity'] = df['quantity'].astype(float).fillna(0)

    #     df = df.groupby(['account__accountname','account__id'])[['debitamount','creditamount','quantity']].sum().abs().reset_index()
    #    # print(openingbalance)

        

        
      #  df['balance'] = df['debitamount'] - df['creditamount']
        
        # df['debitamount'] = np.where(df['balance'] >= 0,df['balance'],0)
        # df['creditamount'] = np.where(df['balance'] <= 0,-df['balance'],0)

      #  df['drcr'] = np.where(df['balance'] > 0,True,False)

    #     df['entry__entrydate1'] = enddate
    #     df['transactiontype'] = 'T'
    #     df['transactionid'] = -1
    #     df['desc'] = 'Total'

    #     df.drop(['balance'],axis = 1)

    #     print(df)


    #     #frames = [openingbalance,details]

    #     df2 = pd.concat([openingbalance,details])

    #     bsdf = pd.concat([df2,df]).reset_index()


    #     bsdf =bsdf[['account__accountname','account__id','creditamount','debitamount','desc','entry__entrydate1','transactiontype','transactionid','drcr','quantity']]

    #   #  bsdf['entrydatetime'] = pd.to_datetime(bsdf['entrydatetime']).dt.strftime('%d-%m-%Y')

    #     bsdf.rename(columns = {'account__accountname':'accountname','account__id':'accountid','entry__entrydate1':'entrydate'}, inplace = True)

    #     bsdf['displaydate'] = pd.to_datetime(bsdf['entrydate']).dt.strftime('%d-%m-%Y')

    #     pd.set_option('display.max_columns', None)
    #     bsdf.head()

    #     print(bsdf)

       # bsdf['entrydate'] = pd.to_datetime(bsdf['entrydate'], format="%Y-%m") + MonthEnd(0)

        # bsdf['entrydate'] = pd.to_datetime(bsdf['entrydate'],format="%Y-%m-%d %H:%M:%S")



        # newdf = bsdf.groupby(['accountname','accountid',bsdf['entrydate'].dt.month])['creditamount','debitamount'].sum().reset_index()

        # newdf['entrydate'] = pd.to_datetime(newdf['entrydate'], format='%m').dt.strftime('%b')

        # print(newdf)

        



        

        j = pd.DataFrame()

        if len(df.index) > 0:
            j = (df.groupby(['accountname','accountid'])
            .apply(lambda x: x[['entrydate','balance','Closingbalance','diff','int','Total']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'accounts'})).T.to_dict().values()




        
        
        
        return Response(j)

class stockledgersummary(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        # stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        # if self.request.query_params.get('stock'):
        #         stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
        #         stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,stock__in=stocks,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        # else:
        stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')

        if self.request.query_params.get('stockcategory'):
                stockcategories =  [int(x) for x in request.GET.get('stockcategory', '').split(',')]
                stk = stk.filter(stock__productcategory__in = stockcategories)

        if self.request.query_params.get('stock'):
                stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
                stk = stk.filter(stock__in = stocks)
        
        if self.request.query_params.get('stocktype'):
                stocktypes =  [int(x) for x in request.GET.get('stocktype', '').split(',')]
                stk = stk.filter(stocktype__in = stocktypes)
        
            
        df = read_frame(stk)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'stock__productname':'productname','stock__id':'productid','entry__entrydate1':'entrydate'}, inplace = True)

        

        df['salequantity'] = np.where(df['stockttype'] == "S",df['quantity'],0)
        df['purchasequantity'] = np.where(df['stockttype'] == "P",df['quantity'],0)
        df['iquantity'] = np.where(df['stockttype'] == "I",df['quantity'],0)
        df['rquantity'] = np.where(df['stockttype'] == "R",df['quantity'],0)

        dfd =df[(df['entrydate'] >= startdate.date()) & (df['entrydate'] < enddate.date())]
      
        openingbalance = df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] < startdate.date())]
        openingbalance['salequantity'] = openingbalance['salequantity'].astype(float).fillna(0)
        openingbalance['purchasequantity'] = openingbalance['purchasequantity'].astype(float).fillna(0)
        openingbalance['rquantity'] = openingbalance['rquantity'].astype(float).fillna(0)
        openingbalance['iquantity'] = openingbalance['iquantity'].astype(float).fillna(0)
        df = dfd.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()
        openingbalance = openingbalance.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()   
        openingbalance['openingbalance'] = openingbalance['purchasequantity'] + openingbalance['rquantity'] - openingbalance['iquantity'] - openingbalance['salequantity']

        

        openingbalance = openingbalance.drop(['salequantity','purchasequantity','rquantity','iquantity','productname'],axis = 1)
        df1 = pd.merge(df,openingbalance,on='productid',how='outer',indicator=True).reset_index()
        df1['openingbalance'] = df1['openingbalance'].astype(float).fillna(0)
        print(df1)
      #  bsdf = pd.concat([df]).reset_index()




       




        
        
        
        return Response(df1.T.to_dict().values())
    

class stockledgersummarypost(ListAPIView):

    serializer_class = stockledgersummarySerializer

    

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def post(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = request.data.get('entity',None)
        startdate = request.data.get('startdate')
        enddate = request.data.get('enddate')
            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        # stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        # if self.request.query_params.get('stock'):
        #         stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
        #         stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,stock__in=stocks,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        # else:
        stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')

        if request.data.get('stockcategory'):
                stockcategories =  [int(x) for x in request.data.get('stockcategory', '').split(',')]
                stk = stk.filter(stock__productcategory__in = stockcategories)

        if request.data.get('stock'):
                stocks =  [int(x) for x in request.data.get('stock', '').split(',')]
                stk = stk.filter(stock__in = stocks)
        
        if request.data.get('stocktype'):
                stocktypes =  [str(x) for x in request.data.get('stocktype', '').split(',')]
                stk = stk.filter(stocktype__in = stocktypes)
        
            
        df = read_frame(stk)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'stock__productname':'productname','stock__id':'productid','entry__entrydate1':'entrydate'}, inplace = True)

        

        df['salequantity'] = np.where(df['stockttype'] == "S",df['quantity'],0)
        df['purchasequantity'] = np.where(df['stockttype'] == "P",df['quantity'],0)
        df['iquantity'] = np.where(df['stockttype'] == "I",df['quantity'],0)
        df['rquantity'] = np.where(df['stockttype'] == "R",df['quantity'],0)

        dfd =df[(df['entrydate'] >= startdate.date()) & (df['entrydate'] < enddate.date())]
      
        openingbalance = df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] < startdate.date())]
        openingbalance['salequantity'] = openingbalance['salequantity'].astype(float).fillna(0)
        openingbalance['purchasequantity'] = openingbalance['purchasequantity'].astype(float).fillna(0)
        openingbalance['rquantity'] = openingbalance['rquantity'].astype(float).fillna(0)
        openingbalance['iquantity'] = openingbalance['iquantity'].astype(float).fillna(0)
        df = dfd.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()
        openingbalance = openingbalance.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()   
        openingbalance['openingbalance'] = openingbalance['purchasequantity'] + openingbalance['rquantity'] - openingbalance['iquantity'] - openingbalance['salequantity']

        

        openingbalance = openingbalance.drop(['salequantity','purchasequantity','rquantity','iquantity','productname'],axis = 1)
        df1 = pd.merge(df,openingbalance,on='productid',how='outer',indicator=True).reset_index()
        df1['openingbalance'] = df1['openingbalance'].astype(float).fillna(0)
        print(df1)
      #  bsdf = pd.concat([df]).reset_index()




       




        
        
        
        return Response(df1.T.to_dict().values())


class daybookdetails(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')

        
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        # stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        # if self.request.query_params.get('stock'):
        #         stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
        #         stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,stock__in=stocks,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        # else:
        stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity).exclude(accounttype__in = ['MD']).values('account__id','account__accountname','transactiontype','transactionid','desc','entry__entrydate1','debitamount','creditamount','drcr','accounttype','iscashtransaction').order_by('entry__entrydate1')
            
        df = read_frame(stk)

        datestk = entry.objects.filter(entrydate1__range = (startdate,enddate),isactive = 1,entity = entity).values('entrydate1').order_by('entrydate1')

        dfdate = read_frame(datestk)

        dfdate.rename(columns = {'entrydate1':'entrydate'}, inplace = True)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'account__accountname':'accountname','account__id':'accountid','entry__entrydate1':'entrydate'}, inplace = True)

        dfd =df[(df['entrydate'] >= startdate.date()) & (df['entrydate'] < enddate.date()) & (df['accounttype'] == 'CIH')]

        accdetails =df[(df['entrydate'] >= startdate.date()) & (df['entrydate'] <= enddate.date()) & (df['accounttype'] != 'CIH')]
      
        openingbalance = df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] < startdate.date()) & (df['accounttype'] == 'CIH') & (df['iscashtransaction'] == True) ] 

        openingbalance['entrydate'] = startdate

        openingbalance['entrydate'] = pd.to_datetime(openingbalance['entrydate'], format='%Y-%m-%d').dt.date

        openingbalance = openingbalance.groupby(['entrydate'])[['debitamount','creditamount']].sum().abs().reset_index()
        


        dfd = dfd.groupby(['entrydate'])[['debitamount','creditamount']].sum().abs().reset_index()
        dfd['debitamount'] = dfd['debitamount'].astype(float).fillna(0)
        dfd['creditamount'] = dfd['creditamount'].astype(float).fillna(0)


        print(dfd)

        dfdnew = pd.merge(dfdate,dfd,on='entrydate',how='outer',indicator=True).reset_index()


        print(dfdnew)

       

        dfdnew['debitamount'] = dfdnew['debitamount'].astype(float).fillna(0)
        dfdnew['creditamount'] = dfdnew['creditamount'].astype(float).fillna(0)

        

        dfdnew = dfdnew.drop(['_merge','index'],axis = 1)

       # dfd = dfdnew


        # dfd['debitamount'] = dfd['debitamount'].astype(float).fillna(0)
        # dfd['creditamount'] = dfd['creditamount'].astype(float).fillna(0)

        print(openingbalance)

        bsdf = pd.concat([openingbalance,dfdnew]).reset_index()

        print(bsdf)

        bsdf['balance'] = bsdf['debitamount'] - bsdf['creditamount']

        print(bsdf.dtypes)

        bsdf['balance'] = bsdf['balance'].astype(float).fillna(0)

        bsdf['Closingbalance'] = bsdf['balance'].cumsum()

        #

        


        bsdf['Openingbalance'] = bsdf['Closingbalance'] - bsdf['balance']

        bsdf['Openingbalance'] = bsdf['Openingbalance'].astype(float).fillna(0)
        bsdf['debitamount'] = bsdf['debitamount'].astype(float).fillna(0)

        bsdf['Closingbalance'] = bsdf['Closingbalance'].astype(float).fillna(0)
        bsdf['creditamount'] = bsdf['creditamount'].astype(float).fillna(0)

        bsdf['receipttotal'] = bsdf['Openingbalance'] +  bsdf['debitamount']

        bsdf['paymenttotal'] = bsdf['Closingbalance'] +  bsdf['creditamount']

        bsdf.rename(columns = {'debitamount':'receipt','creditamount':'payment'}, inplace = True)

        print(bsdf)


        print('--------------------------------------------------')


        #pr


        accdetails = accdetails.groupby(['accountid','accountname','transactiontype','transactionid','desc','entrydate','drcr'])[['debitamount','creditamount']].sum().abs().reset_index()


        bsdf = pd.merge(bsdf,accdetails,on='entrydate',how='outer',indicator=True).reset_index()

      #  print(bsdf['balance'].cumsum(axis = 0, skipna = True))

        #bsdf = bsdf.groupby(['entrydate'])[['debitamount','creditamount']].sum().abs().reset_index()


        print('abdnsbdnsdbndbn')


        pd.set_option('display.max_columns', None)
        bsdf.head()

        bsdf = bsdf.fillna(0)


     #   print(bsdf)


        j = pd.DataFrame()
        if len(bsdf.index) > 0:
            j = (bsdf.groupby(['entrydate','receipt','payment','Closingbalance','Openingbalance','receipttotal','paymenttotal'])
            .apply(lambda x: x[['accountid','accountname','desc','debitamount','creditamount','drcr','transactiontype','transactionid']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'accounts'})).T.to_dict().values()

        
          
        
        
        return Response(j)


class DayDetails(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, format=None):
        entity = request.data.get('entity', None)
        startdate = request.data.get('startdate')
        enddate = request.data.get('enddate')

        if not (entity and startdate and enddate):
            return Response({"error": "Missing required parameters."}, status=400)

        # Convert startdate and enddate to datetime
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')

        # Get financial year for the entity
        try:
            currentdates = entityfinancialyear.objects.get(
                entity=entity,
                finendyear__gte=startdate,
                finstartyear__lte=startdate
            )
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Financial year not found."}, status=404)

        # Combine filters to reduce redundant queries
        filter_conditions = Q(entry__entrydate1__range=(currentdates.finstartyear, enddate)) & Q(isactive=1) & Q(entity=entity)

        # First Query: Stock transactions (filtered)
        stk = StockTransactions.objects.filter(
            filter_conditions & Q(accounttype__in=['M', 'CIH']) & Q(iscashtransaction=1)
        ).values(
            'account__id', 'account__accountname', 'transactiontype', 'transactionid', 'desc', 
            'entry__entrydate1', 'drcr', 'accounttype', 'entry'
        ).annotate(
            debitamount=Sum('debitamount'),
            creditamount=Sum('creditamount')
        ).order_by('entry__entrydate1')

        # Load transactions to dataframe
        df = read_frame(stk)

        # Second Query: Stock transactions details (more detailed filtering)
        stkdetails = StockTransactions.objects.filter(
            filter_conditions
        ).exclude(
            accounttype__in=['MD']
        ).values(
            'account__id', 'account__accountname', 'transactiontype', 'transactionid', 'desc', 
            'entry__entrydate1', 'drcr', 'accounttype', 'entry'
        ).annotate(
            debitamount=Sum('debitamount'),
            creditamount=Sum('creditamount')
        ).order_by('entry__entrydate1')

                # Apply transaction type filter if provided
        transactiontype = request.data.get('transactiontype')
        if transactiontype:
            transactiontype_list = [str(x) for x in transactiontype.split(',')]
            stkdetails = stkdetails.filter(transactiontype__in=transactiontype_list)

        # Load detailed transactions to dataframe
        dfdetails = read_frame(stkdetails)

        # Process df and dfdetails
        def process_dataframe(df):
            df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date
            df.rename(columns={
                'account__accountname': 'accountname',
                'account__id': 'accountid',
                'entry__entrydate1': 'entrydate'
            }, inplace=True)
            return df

        df = process_dataframe(df)
        dfdetails = process_dataframe(dfdetails)

        # Filter CIH and non-CIH account types
        dfd = df[(df['entrydate'] >= currentdates.finstartyear.date()) &
                 (df['entrydate'] <= enddate.date()) &
                 (df['accounttype'] == 'CIH')]

        accdetails = dfdetails[(dfdetails['entrydate'] >= startdate.date()) &
                               (dfdetails['entrydate'] <= enddate.date()) &
                               (dfdetails['accounttype'] != 'CIH')]

        # Sum debit and credit amounts
        accdetails['debitamount'] = accdetails['debitamount'].astype(float).fillna(0)
        accdetails['creditamount'] = accdetails['creditamount'].astype(float).fillna(0)
        dfddetails = accdetails.groupby(['entrydate', 'entry'])[['debitamount', 'creditamount']].sum().abs().reset_index()

        # Rename columns
        dfddetails.rename(columns={'debitamount': 'payment', 'creditamount': 'receipt'}, inplace=True)

        dfd['debitamount'] = dfd['debitamount'].astype(float).fillna(0)
        dfd['creditamount'] = dfd['creditamount'].astype(float).fillna(0)
        dfd = dfd.groupby(['entrydate', 'entry'])[['debitamount', 'creditamount']].sum().abs().reset_index()

        # Merge dataframes
        bsdf = pd.merge(dfddetails, dfd, on='entrydate', how='outer').reset_index(drop=True)
        bsdf.fillna(0, inplace=True)

        # Calculate balances
        bsdf['balance'] = bsdf['debitamount'] - bsdf['creditamount']
        bsdf['Closingbalance'] = bsdf['balance'].cumsum()
        bsdf['Openingbalance'] = bsdf['Closingbalance'] - bsdf['balance']
        bsdf['receipttotal'] = bsdf['Openingbalance'] + bsdf['receipt']
        bsdf['paymenttotal'] = bsdf['Closingbalance'] + bsdf['payment']

        # Drop unnecessary columns
        bsdf = bsdf.drop(['debitamount', 'creditamount'], axis=1)

        # Merge with account details
        bsdfnew = accdetails.merge(bsdf, on='entrydate')
        bsdfnew = bsdfnew[(bsdfnew['entrydate'] >= startdate.date()) &
                          (bsdfnew['entrydate'] <= enddate.date())]
        

        print(bsdfnew.columns.tolist())

        # Prepare final JSON response
        if not bsdfnew.empty:
            grouped = bsdfnew.groupby(['entrydate', 'receipt', 'payment',
                                       'Closingbalance', 'Openingbalance',
                                       'receipttotal', 'paymenttotal'])
            j = (grouped.apply(lambda x: x[['accountid', 'accountname', 'desc',
                                            'debitamount', 'creditamount',
                                            'drcr']].to_dict('records'))
                 .reset_index().rename(columns={0: 'accounts'}).to_dict('records'))
            
            #    j = (grouped.apply(
            #         lambda x: x.groupby(['accountid', 'accountname'])
            #                 .apply(lambda y: y[['desc', 'debitamount', 'creditamount', 'drcr']].to_dict('records'))
            #                 .reset_index(name='transactions')
            #                 .to_dict('records')
            #     )
            #     .reset_index(name='accounts')
            #     .to_dict('records'))
        else:
            j = []

        return Response(j)



class cashbooksummary(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')


            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')

        
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,accounttype__in = ['M','CIH'],iscashtransaction= 1).values('account__id','account__accountname','transactiontype','transactionid','desc','entry__entrydate1','debitamount','creditamount','drcr','accounttype','entry').order_by('entry__entrydate1')
            
        df = read_frame(stk)

      #  print(df)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'account__accountname':'accountname','account__id':'accountid','entry__entrydate1':'entrydate'}, inplace = True)

        dfd =df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] <= enddate.date()) & (df['accounttype'] == 'CIH')]

        accdetails =df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] <=   enddate.date()) & (df['accounttype'] == 'M')]

        

      
        

        dfd['debitamount'] = dfd['debitamount'].astype(float).fillna(0)
        dfd['creditamount'] = dfd['creditamount'].astype(float).fillna(0)

        if self.request.query_params.get('aggby'):
            dfd['entrydate'] = pd.to_datetime(dfd['entrydate'], errors='coerce')
            dfd['entrydate'] = dfd['entrydate'].dt.to_period(self.request.query_params.get('aggby')).dt.end_time
            dfd['startdate'] = dfd['entrydate'].dt.to_period(self.request.query_params.get('aggby')).dt.start_time
            # details['transactiontype'] = request.data.get('aggby')
            # details['transactionid'] = -1
            # details['drcr'] = True
           # details['desc'] = 'Agg'
            dfd['entrydate'] = pd.to_datetime(dfd['entrydate']).dt.date
            dfd['startdate'] = pd.to_datetime(dfd['startdate']).dt.date
            #dfd['entrydate'] = pd.to_datetime(dfd['entrydate'], format='%m').dt.strftime('%b')
            dfd = dfd.groupby(['startdate','entrydate'])[['debitamount','creditamount']].sum().abs().reset_index()

        else:
            dfd = dfd.groupby(['entrydate'])[['debitamount','creditamount']].sum().abs().reset_index()
        bsdf = dfd
        print(bsdf)

        bsdf['balance'] = bsdf['debitamount'] - bsdf['creditamount']

        bsdf['Closingbalance'] = bsdf['balance'].cumsum()

        bsdf['Openingbalance'] = bsdf['Closingbalance'] - bsdf['balance']

       # bsdf['receipttotal'] = bsdf['Openingbalance'] +  bsdf['debitamount']

       # bsdf['paymenttotal'] = bsdf['Closingbalance'] +  bsdf['creditamount']

        bsdf.rename(columns = {'debitamount':'receipt','creditamount':'payment'}, inplace = True)

        bsdfnew = bsdf
       # bsdfnew = accdetails.merge(bsdf,on='entrydate')

        bsdfnew =bsdfnew[(bsdfnew['entrydate'] >= startdate.date()) & (bsdfnew['entrydate'] <=   enddate.date())]
        # j = pd.DataFrame()
        # if len(bsdfnew.index) > 0:
        #     j = (bsdfnew.groupby(['entrydate','receipt','payment','Closingbalance','Openingbalance','receipttotal','paymenttotal'])
        #     .apply(lambda x: x[['accountid','accountname','desc','debitamount','creditamount','drcr']].to_dict('records'))
        #     .reset_index()
        #     .rename(columns={0:'accounts'})).T.to_dict().values()

        

       

        
        
        
        return Response(bsdfnew.T.to_dict().values())


class cashbookdetails(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):

        
        entity = request.query_params.get('entity')
        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')

        if not all([entity, start_date, end_date]):
            return Response({"error": "Missing required query parameters"}, status=400)

        # Convert start and end dates to datetime
        utc = pytz.UTC
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

        print(start_date)

        # Fetch the current financial year for the entity
        # current_fin_year = entityfinancialyear.objects.filter(
        #     entity=entity,
        #     finendyear__gte=start_date,
        #     finstartyear__lte=start_date,
        # ).first()

        current_fin_year = entityfinancialyear.objects.filter(
            entity=entity,
            finstartyear__lte=start_date,  
            finendyear__gte=end_date   
        ).first()

        # If no exact match is found, extend to the earliest and latest available financial years
        if not current_fin_year:
            min_finstartyear = entityfinancialyear.objects.filter(entity=entity).aggregate(Min('finstartyear'))['finstartyear__min']
            max_finendyear = entityfinancialyear.objects.filter(entity=entity).aggregate(Max('finendyear'))['finendyear__max']

            if min_finstartyear and max_finendyear:
                current_fin_year = entityfinancialyear.objects.filter(
                    entity=entity,
                    finstartyear=min_finstartyear,
                    finendyear=max_finendyear
                )
        
        #print(min_finstartyear)

        print(current_fin_year.finstartyear)

        # Fetch stock transactions
        transactions = StockTransactions.objects.filter(
            entry__entrydate1__range=(current_fin_year.finstartyear, end_date),
            isactive=1,
            entity=entity,
            accounttype__in=['M', 'CIH'],
            iscashtransaction=1,
        ).values(
            'account__id', 'account__accountname', 'transactiontype', 'transactionid',
            'desc', 'entry__entrydate1', 'debitamount', 'creditamount', 'drcr',
            'accounttype', 'entry'
        ).order_by('entry__entrydate1')

        if not transactions.exists():
            return Response([])

        # Convert transactions to a DataFrame
        df = read_frame(transactions)
        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1']).dt.date
        df.rename(columns={
            'account__accountname': 'accountname',
            'account__id': 'accountid',
            'entry__entrydate1': 'entrydate',
        }, inplace=True)

        # Filter data for cash-in-hand (CIH) and accounts (M)
        cash_in_hand = df[(df['entrydate'] >= current_fin_year.finstartyear.date()) &
                          (df['entrydate'] <= end_date.date()) &
                          (df['accounttype'] == 'CIH')]

        accounts = df[(df['entrydate'] >= current_fin_year.finstartyear.date()) &
                      (df['entrydate'] <= end_date.date()) &
                      (df['accounttype'] == 'M')]

        # Process cash-in-hand data
        cash_in_hand[['debitamount', 'creditamount']] = cash_in_hand[['debitamount', 'creditamount']].astype(float).fillna(0)
        grouped = cash_in_hand.groupby(['entrydate', 'entry'])[['debitamount', 'creditamount']].sum().abs().reset_index()

        grouped['balance'] = grouped['debitamount'] - grouped['creditamount']
        grouped['Closingbalance'] = grouped['balance'].cumsum()
        grouped['Openingbalance'] = grouped['Closingbalance'] - grouped['balance']
        grouped['receipttotal'] = grouped['Openingbalance'] + grouped['debitamount']
        grouped['paymenttotal'] = grouped['Closingbalance'] + grouped['creditamount']
        grouped.rename(columns={'debitamount': 'receipt', 'creditamount': 'payment'}, inplace=True)

        # Merge account details with grouped data
        merged_data = accounts.merge(grouped, on='entrydate', how='inner')
        merged_data = merged_data[(merged_data['entrydate'] >= start_date.date()) &
                                  (merged_data['entrydate'] <= end_date.date())]

        # Generate response
        if merged_data.empty:
            return Response([])
            

        grouped_data = (
            merged_data
            .groupby(['entrydate', 'receipt', 'payment', 'Closingbalance', 'Openingbalance', 'receipttotal', 'paymenttotal'])
            .apply(lambda x: x[['accountid', 'accountname', 'desc', 'debitamount', 'creditamount', 'drcr']].to_dict('records'))
        )


        # grouped_data = (
        #     merged_data
        #     .groupby(['entrydate', 'receipt', 'payment', 'Closingbalance', 'Openingbalance', 'receipttotal', 'paymenttotal'])
        #     .apply(lambda group: group.groupby('drcr').apply(
        #         lambda drcr_group: drcr_group.groupby('desc').apply(
        #             lambda desc_group: desc_group[['accountid', 'accountname', 'debitamount', 'creditamount']].to_dict('records')
        #         ).to_dict()
        #     ).to_dict())
        # )

        # Reset the index and format the output
        grouped_data = grouped_data.reset_index(name='accounts')

        # Convert to dictionary values
        result = grouped_data.to_dict(orient='records')

        return Response(result)


class stockledgerdetails(ListAPIView):

    serializer_class = stockledgerdetailSerializer
    permission_classes = (permissions.IsAuthenticated,)

      
    def post(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        #entity = request.data.get('entity',None)
        entity = request.data.get('entity',None)
        startdate = request.data.get('startdate',None)
        enddate = request.data.get('enddate',None)
            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d') if startdate else None
        enddate = datetime.strptime(enddate, '%Y-%m-%d') if enddate else None
        # stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        # if self.request.query_params.get('stock'):
        #         stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
        #         stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,stock__in=stocks,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        # else:

        stk = StockTransactions.objects.filter(
        entry__entrydate1__range=(currentdates.finstartyear, enddate),
        isactive=1,
        entity=entity,
        accounttype='DD'
        ).values(
            'stock__id', 'stock__productname', 'entry', 'transactiontype', 
            'transactionid', 'stockttype', 'desc', 'quantity', 'entry__entrydate1'
        ).order_by('entry__entrydate1')
        #stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        filters = {
        'stockcategory': ('stock__productcategory__id__in', int),
        'stock': ('stock__in', int),
        'stocktype': ('stockttype__in', str),
        'transactiontype': ('transactiontype__in', str)
        }

        for key, (filter_field, cast_type) in filters.items():
            if request.data.get(key):
                values = [cast_type(x) for x in request.data.get(key, '').split(',')]
                stk = stk.filter(**{filter_field: values})
        
            
        df = read_frame(stk)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'stock__productname':'productname','stock__id':'productid','entry__entrydate1':'entrydate'}, inplace = True)

        for col, stock_type in [('salequantity', 'S'), ('purchasequantity', 'P'),
                            ('iquantity', 'I'), ('rquantity', 'R')]:
            df[col] = np.where(df['stockttype'] == stock_type, df['quantity'], 0)

        
        openingbalance = df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & 
                         (df['entrydate'] < startdate.date())]
        details = df[(df['entrydate'] >= startdate.date()) & 
                    (df['entrydate'] < enddate.date())]
      
        


        details = details[['productname','productid','transactiontype','transactionid','desc','entrydate','salequantity','purchasequantity','rquantity','iquantity']]

       #details = details.groupby(['productname','productid','transactiontype','transactionid','desc','entrydate'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()

       # print(details[['productname','productid','transactiontype','transactionid','desc','entrydate']])

        aggby = request.data.get('aggby')
        if aggby:
            details['entrydate'] = pd.to_datetime(details['entrydate']).dt.to_period(aggby).dt.end_time
            if aggby != 'D':
                details['transactiontype'] = aggby
                details['transactionid'] = -1
            details['desc'] = pd.to_datetime(details['entrydate']).dt.strftime('%b')
            details = details.groupby(
                ['productname', 'productid', 'transactiontype', 'transactionid', 'desc', 'entrydate']
            ).agg(
                {'salequantity': 'sum', 'purchasequantity': 'sum', 
                'rquantity': 'sum', 'iquantity': 'sum'}
            ).reset_index()

       # print

        


        def process_group(df, transactiontype, desc, entrydate):
            return df.groupby(['productname', 'productid']).agg(
            {'salequantity': 'sum', 'purchasequantity': 'sum', 
             'rquantity': 'sum', 'iquantity': 'sum'}
            ).reset_index().assign(
                transactiontype=transactiontype, transactionid='-1', 
                desc=desc, entrydate=entrydate
            )

        openingbalance = process_group(openingbalance, 'O', 'Opening Balance', startdate)
        total = process_group(df, 'ST', 'Total', enddate)

        # Combine results
        bsdf = pd.concat([openingbalance, details, total]).reset_index(drop=True)
        bsdf['entrydate'] = bsdf['entrydate'].dt.strftime('%d-%m-%Y')

       
        grouped_data = (
            bsdf.groupby(['productname', 'productid'])
            .apply(lambda x: x[['salequantity', 'purchasequantity', 
                                'rquantity', 'iquantity', 'desc', 
                                'entrydate', 'transactiontype', 'transactionid']].to_dict('records'))
            .reset_index().rename(columns={0: 'accounts'})
        )
        
        return Response(grouped_data.to_dict('records'))


class stockledgerdetailsget(ListAPIView):

   
    permission_classes = (permissions.IsAuthenticated,)

      
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        #entity = request.data.get('entity',None)
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
            
        currentdates = entityfinancialyear.objects.get(entity = entity,finendyear__gte = startdate  ,finstartyear__lte =  startdate)
        utc=pytz.UTC
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        # stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).exclude(account__accountcode__in = ['200','9000']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        if self.request.query_params.get('stock'):
                stocks =  [int(x) for x in request.GET.get('stock', '').split(',')]
                stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,stock__in=stocks,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
        else:
            stk = StockTransactions.objects.filter(entry__entrydate1__range = (currentdates.finstartyear,enddate),isactive = 1,entity = entity,accounttype = 'DD').values('stock__id','stock__productname','entry','transactiontype','transactionid','stockttype','desc','quantity','entry__entrydate1').order_by('entry__entrydate1')
            
        df = read_frame(stk)

       

        

        df['entry__entrydate1'] = pd.to_datetime(df['entry__entrydate1'], format='%Y-%m-%d').dt.date

        df.rename(columns = {'stock__productname':'productname','stock__id':'productid','entry__entrydate1':'entrydate'}, inplace = True)

        df['salequantity'] = np.where(df['stockttype'] == "S",df['quantity'],0)
        df['purchasequantity'] = np.where(df['stockttype'] == "P",df['quantity'],0)
        df['iquantity'] = np.where(df['stockttype'] == "I",df['quantity'],0)
        df['rquantity'] = np.where(df['stockttype'] == "R",df['quantity'],0)
      
        openingbalance = df[(df['entrydate'] >= datetime.date(currentdates.finstartyear)) & (df['entrydate'] < startdate.date())]

        details = df[(df['entrydate'] >= startdate.date()) & (df['entrydate'] < enddate.date())]

        details['salequantity'] = details['salequantity'].astype(float).fillna(0)
        details['purchasequantity'] = details['purchasequantity'].astype(float).fillna(0)
        details['rquantity'] = details['rquantity'].astype(float).fillna(0)
        details['iquantity'] = details['iquantity'].astype(float).fillna(0)


        openingbalance['salequantity'] = openingbalance['salequantity'].astype(float).fillna(0)
        openingbalance['purchasequantity'] = openingbalance['purchasequantity'].astype(float).fillna(0)
        openingbalance['rquantity'] = openingbalance['rquantity'].astype(float).fillna(0)
        openingbalance['iquantity'] = openingbalance['iquantity'].astype(float).fillna(0)



        df = df.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()

        openingbalance = openingbalance.groupby(['productname','productid'])[['salequantity','purchasequantity','rquantity','iquantity']].sum().abs().reset_index()


        details = details.drop(['entry','stockttype','quantity'],axis = 1)

        df['transactiontype'] = 'ST'
        df['transactionid'] = '-1'
        df['desc'] = 'Total'
        df['entrydate'] = enddate


        openingbalance['transactiontype'] = 'O'
        openingbalance['transactionid'] = '-1'
        openingbalance['desc'] = 'Opening Balance'
        openingbalance['entrydate'] = startdate

        

        


        bsdf = pd.concat([openingbalance,details,df]).reset_index()

       # bsdf = bsdf.drop(['index'],axis = 1) 

       
        j = pd.DataFrame()
        if len(bsdf.index) > 0:
            j = (bsdf.groupby(['productname','productid'])
            .apply(lambda x: x[['salequantity','purchasequantity','rquantity','iquantity','desc','entrydate','transactiontype','transactionid']].to_dict('records'))
            .reset_index()
            .rename(columns={0:'accounts'})).T.to_dict().values()




        
        
        
        return Response(j)
    

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


# class ledgerviewapi(ListAPIView):

#     serializer_class = ledgerserializer
#   #  filter_class = accountheadFilter
#     permission_classes = (permissions.IsAuthenticated,)

#     filter_backends = [DjangoFilterBackend]
#     filterset_fields = {'id':["in", "exact"],'creditaccounthead':["in", "exact"],'accounthead':["in", "exact"]
    
#     }
#     #filterset_fields = ['id']
#     def get_queryset(self):
#         acc = self.request.query_params.get('acc')
#         entity = self.request.query_params.get('entity')

        



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=account.objects.filter(entity=entity).prefetch_related('accounttrans').order_by('accountname')


        print(queryset.query.__str__())


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
        enddate =  self.request.query_params.get('enddate')



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=entry.objects.filter(entity=entity,entrydate1__range = (startdate,enddate)).prefetch_related('cashtrans').order_by('entrydate1')

       

     
        
     
        return queryset
    
class salebyaccountapi(ListAPIView):

    #serializer_class = Salebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']


    def get(self, request):
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        # Validate required parameters
        if not all([entity, transactiontype, startdate, enddate]):
            return Response({"error": "Missing required parameters"}, status=400)

        # Determine the appropriate queryset based on transaction type
        queryset = None
        filter_criteria = {
            "entity": entity,
            "isactive": 1,
            "sorderdate__range": (startdate, enddate),
        }
        selected_fields = [
            "id", "sorderdate", "accountid__accountname", "accountid__accountcode",
            "totalpieces", "totalquanity", "subtotal", "cgst", "sgst", "igst",
            "cess", "gtotal", "accountid__city__cityname",
        ]

        if transactiontype == "S":
            queryset = SalesOderHeader.objects.filter(**filter_criteria).values(*selected_fields).order_by("sorderdate")
        elif transactiontype == "PR":
            queryset = PurchaseReturn.objects.filter(**filter_criteria).values(*selected_fields).order_by("sorderdate")
        else:
            return Response({"error": "Invalid transaction type"}, status=400)

        # Convert queryset to DataFrame and process it
        df = read_frame(queryset)
        column_mapping = {
            "accountid__accountname": "accountname",
            "accountid__accountcode": "accountcode",
            "totalpieces": "pieces",
            "totalquanity": "weightqty",
            "id": "transactionid",
            "sorderdate": "entrydate",
            "accountid__city__cityname": "city",
        }
        df.rename(columns=column_mapping, inplace=True)

        # Add additional columns
        df["transactiontype"] = transactiontype
        df["entrydate"] = pd.to_datetime(df["entrydate"]).dt.strftime("%d-%m-%y")

        # Return the response
        return Response(df.to_dict(orient="records"))


class printvoucherapi(ListAPIView):

    #serializer_class = Salebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']


    def get(self, request):
        entity = self.request.query_params.get('entity')
        transactiontype = self.request.query_params.get('transactiontype')
        transactionid = self.request.query_params.get('transactionid')

        # Fetch the stock transactions
        queryset = StockTransactions.objects.filter(
            isactive=1,
            entity=entity,
            transactiontype=transactiontype,
            transactionid=transactionid
        ).exclude(accounttype__in=['MD']).values(
            'account__id', 'account__accountname', 'transactiontype', 'transactionid', 'desc',
            'entry__entrydate1', 'debitamount', 'creditamount', 'drcr', 'id', 'voucherno'
        ).order_by('id')

        # Convert queryset to DataFrame
        df = read_frame(queryset)
        df.rename(columns={
            'account__accountname': 'accountname',
            'account__id': 'account',
            'entry__entrydate1': 'entrydate'
        }, inplace=True)

        # Add columns and format
        df['transactiontype'] = transactiontype
        df['entrydate'] = pd.to_datetime(df['entrydate']).dt.strftime('%d-%m-%y')

        # Group data
        df = df.groupby(
            ['entrydate', 'voucherno', 'account', 'accountname', 'desc', 'drcr']
        )[['debitamount', 'creditamount']].sum().abs().reset_index()

        # Summarize totals
        df_sum = df.groupby(
            ['entrydate', 'voucherno']
        )[['debitamount', 'creditamount']].sum().abs().reset_index()

        df_sum['account'] = -1
        df_sum['desc'] = ''
        df_sum['drcr'] = True
        df_sum['accountname'] = 'Grand Total'

        # Concatenate summarized totals with the grouped data
        df = pd.concat([df, df_sum]).reset_index(drop=True)

        # Add voucher type based on transaction type
        voucher_map = {
            'C': 'Cash Voucher',
            'B': 'Bank Voucher',
            'J': 'Journal Voucher',
            'S': 'Sale Bill Voucher',
            'P': 'Purchase Voucher',
            'T': 'TDS Voucher',
            'PR': 'Purchase Return Voucher',
            'SR': 'Sale Return Voucher',
            'PI': 'Purchase Import Voucher',
            'RV': 'Receipt Voucher'
        }

        df['voucher'] = voucher_map.get(transactiontype, 'Unknown Voucher')

        # Format final result
        result = []
        if len(df) > 0:
            result = (df.groupby(['entrydate', 'voucherno', 'voucher'])
                    .apply(lambda x: x[['account', 'accountname', 'desc', 'debitamount', 'creditamount', 'drcr']].to_dict('records'))
                    .reset_index()
                    .rename(columns={0: 'accounts'})
                    .T.to_dict()
                    .values())

        return Response(result)
    
class purchasebyaccountapi(ListAPIView):

   #serializer_class = Purchasebyaccountserializer
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id']
    def get(self, request):
    # Extract query parameters
        params = self.request.query_params
        entity = params.get('entity')
        transactiontype = params.get('transactiontype')
        startdate = params.get('startdate')
        enddate = params.get('enddate')

        # Define a mapping of transaction types to models
        model_mapping = {
            'P': purchaseorder,
            'SR': salereturn
        }

        # Fetch the appropriate model based on transactiontype
        model = model_mapping.get(transactiontype)

        if model:
            queryset = model.objects.filter(
                entity=entity,
                isactive=1,
                voucherdate__range=(startdate, enddate)
            ).values(
                'id', 'voucherdate', 'account__accountname', 'account__accountcode',
                'totalpieces', 'totalquanity', 'subtotal', 'cgst', 'sgst',
                'igst', 'cess', 'gtotal', 'account__city__cityname'
            ).order_by('-voucherdate')

            # Convert queryset to DataFrame and process
            df = read_frame(queryset)
            df.rename(
                columns={
                    'account__accountname': 'accountname',
                    'account__id': 'account',
                    'totalpieces': 'pieces',
                    'totalquanity': 'weightqty',
                    'id': 'transactionid',
                    'accountid__accountcode': 'accountcode',
                    'voucherdate': 'entrydate',
                    'account__city__cityname': 'city'
                },
                inplace=True
            )
            df['transactiontype'] = transactiontype
            df['entrydate'] = pd.to_datetime(df['entrydate']).dt.strftime('%d-%m-%y')

            return Response(df.T.to_dict().values())

        # Handle invalid transaction type
        return Response({"error": "Invalid transaction type"}, status=400)
    

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
        enddate =  self.request.query_params.get('enddate')



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
    


class TrialbalanceApiView(ListAPIView):

    #serializer_class = TrialbalanceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
        utc = pytz.UTC

        print("startdate (before conversion):", type(startdate), startdate)
        print("enddate (before conversion):", type(enddate), enddate)

        if isinstance(startdate, str):
            startdate = datetime.strptime(startdate, "%Y-%m-%d")

        if isinstance(enddate, str):
            enddate = datetime.strptime(enddate, "%Y-%m-%d")

        if not is_aware(startdate):
            startdate = make_aware(startdate)

        if not is_aware(enddate):
            enddate = make_aware(enddate)

        print(startdate)
        print(enddate)
        

        # Fetch the financial year details for the given entity and startdate
        try:
            currentdates = entityfinancialyear.objects.filter(
                entity=entity,
                finstartyear__lte=enddate,  
                finendyear__gte=startdate   
            ).first()

            if currentdates:
                finstartyear = currentdates.finstartyear
                finendyear = currentdates.finendyear

                # Ensure finstartyear and finendyear are timezone-aware
                if not is_aware(finstartyear):
                    finstartyear = make_aware(finstartyear)

                if not is_aware(finendyear):
                    finendyear = make_aware(finendyear)

                # Now, max() and min() will work without errors
                startdate = max(startdate, finstartyear)
                enddate = min(enddate, finendyear)
        except entityfinancialyear.DoesNotExist:
            currentdates = None  # Or handle the exception as needed

                # Common filters and configurations
        base_filters = {
            'entity': entity,
            'isactive': 1,
            'entrydatetime__lte': startdate
        }
        exclude_filters = {
            'accounttype__in': ['MD'],
            'transactiontype__in': ['PC']
        }
        annotations = {
            'debit': Sum('debitamount', default=0),
            'credit': Sum('creditamount', default=0),
            'balance1': Sum('debitamount', default=0) - Sum('creditamount', default=0)
        }

        # Determine the entrydatetime filter based on conditions
        if currentdates.finstartyear == startdate:
            obp_filters = {**base_filters, 'entrydatetime__gt': currentdates.finstartyear}
        elif currentdates.isactive == 1:
            obp_filters = {**base_filters, 'entrydatetime__gte': currentdates.finstartyear}
        else:
            obp_filters = {**base_filters, 'entrydatetime__gte': currentdates.finstartyear}

        # Query for obp (positive balance)
        obp = StockTransactions.objects.filter(**obp_filters).exclude(**exclude_filters).values(
            'account__accounthead__name', 'account__accounthead', 'account__id'
        ).annotate(**annotations).filter(balance1__gt=0)

        # Query for obn (negative balance)
        obn = StockTransactions.objects.filter(**obp_filters).exclude(**exclude_filters).values(
            'account__creditaccounthead__name', 'account__creditaccounthead', 'account__id'
        ).annotate(**annotations).filter(balance1__lt=0)



        

            # Union operation
        ob = obp.union(obn)

        # Convert queryset to DataFrame once
        df = read_frame(ob)

        # Rename columns more efficiently
        df.rename(columns={
            'account__accounthead__name': 'accountheadname',
            'account__accounthead': 'accounthead'
        }, inplace=True)

        # Perform the groupby operation in a single step, summing 'balance1'
        dffinal1 = df.groupby(['accounthead', 'accountheadname'], as_index=False)['balance1'].sum()


        print(dffinal1)

        
        if currentdates.finstartyear < startdate:
            base_queryset = StockTransactions.objects.filter(
            entity=entity,
            isactive=1,
            entrydatetime__range=(startdate, enddate),
            istrial=1
            ).exclude(
                accounttype__in=['MD']
            ).exclude(
                transactiontype__in=['PC']
            ).exclude(
                account__accountcode__in=[200, 9000]
            )

            # Query for positive balance (balance__gt=0) 
            stk = base_queryset.values(
                'account__accounthead__name', 
                'account__accounthead', 
                'account__id'
            ).annotate(
                debit=Sum('debitamount', default=0),
                credit=Sum('creditamount', default=0),
                balance=Sum('debitamount', default=0) - Sum('creditamount', default=0),
                quantity=Sum('quantity', default=0)
            ).filter(balance__gt=0)

            # Query for negative balance (balance__lt=0)
            stk2 = base_queryset.values(
                'account__creditaccounthead__name',
                'account__creditaccounthead',
                'account__id'
            ).annotate(
                debit=Sum('debitamount', default=0),
                credit=Sum('creditamount', default=0),
                balance=Sum('debitamount', default=0) - Sum('creditamount', default=0),
                quantity=Sum('quantity', default=0)
            ).filter(balance__lt=0)
            stkunion = stk.union(stk2)
        else:
            # Common filters and annotations
            common_filters = {
                'entity': entity,
                'isactive': 1,
                'istrial': 1
            }

            common_annotations = {
                'debit': Sum('debitamount', default=0),
                'credit': Sum('creditamount', default=0),
                'balance': Sum('debitamount', default=0) - Sum('creditamount', default=0),
                'quantity': Sum('quantity', default=0)
            }

            # Query for stk0
            stk0 = StockTransactions.objects.filter(
                **common_filters,
                entrydatetime=currentdates.finstartyear,
                account__accountcode=9000
            ).exclude(accounttype__in=['MD']).exclude(transactiontype__in=['PC'])\
            .values('account__accounthead__name', 'account__accounthead', 'account__id')\
            .annotate(**common_annotations).filter(balance__gt=0)

            # Query for stk
            stk = StockTransactions.objects.filter(
                **common_filters,
                entrydatetime__range=(startdate, enddate)
            ).exclude(accounttype__in=['MD']).exclude(transactiontype__in=['PC'])\
            .exclude(account__accountcode__in=[200, 9000])\
            .values('account__accounthead__name', 'account__accounthead', 'account__id')\
            .annotate(**common_annotations).filter(balance__gt=0)

            # Query for stk2
            stk2 = StockTransactions.objects.filter(
                **common_filters,
                entrydatetime__range=(startdate, enddate)
            ).exclude(accounttype__in=['MD']).exclude(transactiontype__in=['PC'])\
            .exclude(account__accountcode__in=[200, 9000])\
            .values('account__creditaccounthead__name', 'account__creditaccounthead', 'account__id')\
            .annotate(**common_annotations).filter(balance__lt=0)

            stkunion = stk.union(stk2,stk0)

        

    #  print(stkunion.query.__str__())

        df = read_frame(stkunion)

        print(df)
        
        df['drcr'] = np.where(df['balance'] < 0, 'CR', 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'], 0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'], 0)

        # Rename columns
        df.rename(columns={
            'account__accounthead__name': 'accountheadname',
            'account__accounthead': 'accounthead'
        }, inplace=True)

        # Group by and aggregate
        dffinal = df.groupby(['accounthead', 'accountheadname', 'drcr'])[['debit', 'credit', 'balance', 'quantity']].sum().abs().reset_index()

        # Merge with dffinal1 and handle missing columns
        df = pd.merge(dffinal, dffinal1, on='accounthead', how='outer', indicator=True)

        # Set default values for missing columns
        for col in ['balance1', 'debit', 'credit', 'quantity']:
            if col in df.columns:
                df[col] = df[col].astype(float).fillna(0)
            else:
                df[col] = 0.0  # Create the column with 0.0 as default value

        # Calculate opening balance and final balance
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0, df['balance1'])
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']

        # Update accountheadname and DR/CR flags
        df['accountheadname'] = np.where(df['_merge'] == 'right_only', df['accountheadname_y'], df['accountheadname_x'])
        df['drcr'] = np.where(df['balance'] < 0, 'CR', 'DR')
        df['obdrcr'] = np.where(df['openingbalance'] < 0, 'CR', 'DR')

        # Drop unnecessary columns and sort
        df = df.drop(['accountheadname_y', 'accountheadname_x', '_merge', 'balance1'], axis=1)
        df = df.sort_values(by='accountheadname')
        return Response(df.T.to_dict().values())
    

class TrialbalancebyaccountheadApiView(ListAPIView):

    #serializer_class = TrialbalanceSerializerbyaccounthead
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account__accounthead']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        accounthead = self.request.query_params.get('accounthead')
        drcrgroup = self.request.query_params.get('drcr')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        # Constants
        utc = pytz.UTC
        exclude_account_types = ['MD']
        exclude_transaction_types = ['PC']

        # Get financial year details
        currentdates = entityfinancialyear.objects.filter(
                entity=entity,
                finstartyear__lte=enddate,  
                finendyear__gte=startdate   
            ).first()

        # Helper: Base Query Filters
        base_filters = {
            'entity': entity,
            'isactive': 1,
            'entrydatetime__lte': startdate,
            'entrydatetime__gte': currentdates.finstartyear,
        }

        # Adjust filters based on DR/CR group
        balance_filter = Q()
        if drcrgroup == 'DR':
            balance_filter = Q(balance1__gt=0)
        elif drcrgroup == 'CR':
            balance_filter = Q(balance1__lt=0)

        # Handle initial balance case
        if currentdates.finstartyear == utc.localize(datetime.strptime(startdate, '%Y-%m-%d')):
            base_filters['entrydatetime__gt'] = currentdates.finstartyear

        ob = StockTransactions.objects.filter(**base_filters) \
            .exclude(accounttype__in=exclude_account_types) \
            .exclude(transactiontype__in=exclude_transaction_types) \
            .values('accounthead__id', 'account__accountname', 'account__id') \
            .annotate(
                debit=Sum('debitamount', default=0),
                credit=Sum('creditamount', default=0),
                balance1=Sum('debitamount', default=0) - Sum('creditamount', default=0)
            ) \
            .filter(balance_filter)

        # Query for stock transactions within date range
        stk_filters = {
            'entity': entity,
            'isactive': 1,
            'entrydatetime__range': (startdate, enddate),
        }
        if drcrgroup == 'DR':
            stk_filters['account__accounthead'] = accounthead
            balance_condition = Q(balance__gt=0)
        elif drcrgroup == 'CR':
            stk_filters['account__creditaccounthead'] = accounthead
            balance_condition = Q(balance__lt=0)
        else:
            balance_condition = Q()

        stk = StockTransactions.objects.filter(**stk_filters) \
            .exclude(accounttype='MD') \
            .exclude(transactiontype__in=exclude_transaction_types) \
            .values('accounthead__id', 'account__accountname', 'account__id') \
            .annotate(
                debit=Sum('debitamount', default=0),
                credit=Sum('creditamount', default=0),
                balance=Sum('debitamount', default=0) - Sum('creditamount', default=0),
                quantity=Sum('quantity', default=0)
            ) \
            .filter(balance_condition)




        
        df = read_frame(stk)
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['credit'] = np.where(df['balance'] < 0, df['balance'], 0)
        df['debit'] = np.where(df['balance'] > 0, df['balance'], 0)

        # Rename columns for consistency
        df.rename(columns={
            'account__accountname': 'accountname',
            'account__id': 'account',
            'account__accounthead': 'accounthead__id'
        }, inplace=True)

        # Convert `ob` queryset to DataFrame
        obdf = read_frame(ob)
        obdf.rename(columns={
            'account__accountname': 'accountname',
            'account__id': 'account'
        }, inplace=True)

        # Group `obdf` by account and sum `balance1`
        obdf = obdf.groupby(['accountname', 'account'])[['balance1']].sum().reset_index()

        # Group `df` by required fields
        df = df.groupby(['accounthead__id', 'accountname', 'drcr', 'account'])[['debit', 'credit', 'balance', 'quantity']] \
            .sum().abs().reset_index()

        # Merge `df` and `obdf` on account, preserving all entries
        df = pd.merge(df, obdf, on='account', how='outer', indicator=True)

        # Fill missing columns with default values
        for col in ['balance1', 'debit', 'credit', 'quantity']:
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(float)
            else:
                df[col] = 0.0  # Create the column with default value

        # Calculate opening balance and updated balance
        df['openingbalance'] = np.where(df['_merge'] == 'left_only', 0, df['balance1'])
        df['balance'] = df['debit'] - df['credit'] + df['openingbalance']

        # Update account names based on merge results
        df['accountname'] = np.where(df['_merge'] == 'right_only', df['accountname_y'], df['accountname_x'])
        df['drcr'] = df['balance'].apply(lambda x: 'CR' if x < 0 else 'DR')
        df['obdrcr'] = df['openingbalance'].apply(lambda x: 'CR' if x < 0 else 'DR')

        # Add `accounthead` column
        df['accounthead'] = accounthead

        # Drop unnecessary columns
        df.drop(['accountname_y', 'accountname_x', '_merge', 'balance1', 'accounthead__id'], axis=1, inplace=True)

        # Remove rows where both balance and opening balance are zero
        df = df[~((df['balance'] == 0.0) & (df['openingbalance'] == 0.0))]

        # Return sorted response
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())

class TrialbalancebyaccountApiView(ListAPIView):

    #serializer_class = TrialbalanceSerializerbyaccount
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account']


    
    def get(self, request, format=None):
        # Extract query parameters
        entity = self.request.query_params.get('entity')
        account1 = self.request.query_params.get('account')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')

        # Common filtering condition for both queries
        common_filters = {
            'entity': entity,
            'isactive': 1,
            'account': account1
        }
        
        # Query for transactions within the date range
        stk = StockTransactions.objects.filter(
            **common_filters, 
            entrydatetime__range=(startdate, enddate)
        ).exclude(accounttype='MD').exclude(transactiontype__in=['PC']).values(
            'account__accountname', 'transactiontype', 'transactionid', 
            'entrydatetime', 'desc'
        ).annotate(
            debit=Sum('debitamount'),
            credit=Sum('creditamount'),
            quantity=Sum('quantity')
        ).order_by('entrydatetime')
        
        # Query for opening balance (before the start date)
        ob = StockTransactions.objects.filter(
            **common_filters,
            entrydatetime__lt=startdate
        ).exclude(accounttype='MD').exclude(transactiontype__in=['PC']).values(
            'account__accountname'
        ).annotate(
            debit=Sum('debitamount'),
            credit=Sum('creditamount'),
            quantity=Sum('quantity')
        ).order_by('entrydatetime')

        # Convert querysets to DataFrames
        df1 = read_frame(ob)
        df1['desc'] = 'Opening Balance'
        df1['entrydatetime'] = startdate
        
        # Ensure numeric columns are properly formatted
        df1[['quantity', 'debit', 'credit']] = df1[['quantity', 'debit', 'credit']].fillna(0).astype(float)

        # Group and aggregate data for opening balance
        df1 = df1.groupby(['account__accountname', 'entrydatetime', 'desc'])[['debit', 'credit', 'quantity']].sum().abs().reset_index()

        # If df1 has data, calculate the balance and adjust debit/credit
        if not df1.empty:
            df1['transactionid'] = -1
            df1['balance'] = df1['debit'] - df1['credit']
            df1['balance'] = df1['balance'].fillna(0).astype(float)
            
            # Adjust debit and credit based on balance
            df1['debit'] = df1['balance'].apply(lambda x: max(x, 0))
            df1['credit'] = df1['balance'].apply(lambda x: min(x, 0))
            
            # Drop the balance column
            df1.drop('balance', axis=1, inplace=True)

        # Convert main transaction DataFrame to DataFrame
        df = read_frame(stk)
        
        # Ensure numeric columns are properly formatted
        df[['quantity', 'debit', 'credit']] = df[['quantity', 'debit', 'credit']].fillna(0).astype(float)

        # Concatenate opening balance and main transactions DataFrames
        union_dfs = pd.concat([df1, df], ignore_index=True)

        # Fill missing values and preprocess columns
        union_dfs['transactiontype'] = union_dfs['transactiontype'].fillna('')
        union_dfs['transactionid'] = union_dfs['transactionid'].fillna('')
        union_dfs['desc'] = union_dfs['desc'].fillna('')
        union_dfs['sortdatetime'] = pd.to_datetime(union_dfs['entrydatetime'])
        union_dfs['entrydatetime'] = union_dfs['entrydatetime'].apply(lambda x: pd.to_datetime(x).strftime('%d-%m-%Y'))
        
        # Sorting by datetime for final presentation
        union_dfs.sort_values(by='sortdatetime', inplace=True)

        # Grouping final data and summing over specified columns
        union_dfs = union_dfs.groupby(
            ['account__accountname', 'sortdatetime', 'desc', 'transactionid', 'transactiontype', 'entrydatetime']
        )[['debit', 'credit', 'quantity']].sum().reset_index().sort_values(by='sortdatetime', ascending=True)

        # Return the response
        return Response(union_dfs.T.to_dict().values())

    

class accountListapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')

        if self.request.query_params.get('accounthead'):
            accountheads =  [int(x) for x in request.GET.get('accounthead', '').split(',')]
            queryset =  StockTransactions.objects.filter(entity = entity,accounthead__in = accountheads).values('account__id','account__accountname').distinct().order_by('account')
        else:
            queryset =  StockTransactions.objects.filter(entity = entity).values('account__id','account__accountname').distinct().order_by('account')

        df = read_frame(queryset) 
        df.rename(columns = {'account__accountname':'accountname','account__id':'id'}, inplace = True)

        return Response(df.T.to_dict().values())
    

class accountheadListapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        queryset =  StockTransactions.objects.filter(entity = entity).values('accounthead__id','accounthead__name').distinct().order_by('accounthead__id')

        df = read_frame(queryset) 

        df=df.dropna(subset=['accounthead__id','accounthead__name'])

        

        print(df)
        df.rename(columns = {'accounthead__name':'name','accounthead__id':'id'}, inplace = True)

        return Response(df.T.to_dict().values())
    


class productListapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        queryset =  StockTransactions.objects.filter(entity = entity,accounttype = 'DD',isactive =1).values('stock__id','stock__productname').distinct().order_by('stock')

        df = read_frame(queryset) 
        df.rename(columns = {'stock__id':'id','stock__productname':'productname'}, inplace = True)

        return Response(df.T.to_dict().values())
    
class productcategoryListapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        queryset =  StockTransactions.objects.filter(entity = entity,accounttype = 'DD',isactive =1).values('stock__productcategory__id','stock__productcategory__pcategoryname').distinct().order_by('stock__productcategory__id')

        df = read_frame(queryset) 
        df.rename(columns = {'stock__productcategory__id':'id','stock__productcategory__pcategoryname':'productcategoryname'}, inplace = True)

        return Response(df.T.to_dict().values())




class stocktypeListapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        queryset =  StockTransactions.objects.filter(entity = entity,accounttype = 'DD',isactive =1).values('stockttype').distinct().order_by('stockttype')

        df = read_frame(queryset) 

        df['stocktypename'] = np.where(df['stockttype'] == 'S', 'Sale',
              np.where(df['stockttype'] == 'P', 'Purchase',
              np.where(df['stockttype'] == 'I', 'Issued', 'recieved')))


       # df.rename(columns = {'stock__productcategory__id':'id','stock__productcategory__pcategoryname':'productcategoryname'}, inplace = True)

        return Response(df.T.to_dict().values())




class accountbindapiview(ListAPIView):
    serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')

        if self.request.query_params.get('accounthead'):
            accountheads =  [int(x) for x in request.GET.get('accounthead', '').split(',')]
            queryset =  StockTransactions.objects.filter(entity = entity,accounthead__in = accountheads).values('account__id','account__accountname').distinct().order_by('account')
        else:
            queryset =  StockTransactions.objects.filter(entity = entity).values('account__id','account__accountname','account__accountcode','account__gstno','account__pan','account__city','account__saccode').annotate(balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))

           # 'accountname','accountcode','city','gstno','pan','saccode'

        df = read_frame(queryset) 
        df.rename(columns = {'account__accountname':'accountname','account__id':'id','account__accountcode':'accountcode','account__gstno':'gstno','account__pan':'pan','account__city':'city','account__saccode':'saccode'}, inplace = True)

        return Response(df.T.to_dict().values())
    

class TrialBalanceViewFinal(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_opening_balance(self, entity_id, start_date):
        """Fetches opening balances before the start date."""
        opening_transactions = StockTransactions.objects.filter(
            entity_id=entity_id,
            entrydatetime__date__lt=start_date
        ).exclude(accounttype='MD').exclude(transactiontype='PC')

        opening_balance_data = opening_transactions.values('account__accounthead__id', 'account__creditaccounthead__id', 'account__accountname').annotate(
            opening_debit=Coalesce(Sum('debitamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4)),
            opening_credit=Coalesce(Sum('creditamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4))
        ).annotate(
            opening_balance=F('opening_debit') - F('opening_credit'),
            accounthead_id=Case(
                When(opening_balance__lt=0, then=F('account__creditaccounthead__id')),
                default=F('account__accounthead__id'),
                output_field=CharField()
            ),
            accounthead=Case(
                When(opening_balance__lt=0, then=F('account__creditaccounthead__name')),
                default=F('account__accounthead__name'),
                output_field=CharField()
            )
        ).values(
            accounthead_id=F('accounthead_id'),
            accounthead=F('accounthead'),
            opening_balance=F('opening_balance')
        )

        return {entry["accounthead"]: {"id": entry["accounthead_id"], "opening_balance": entry["opening_balance"]} for entry in opening_balance_data}

    def get_transactions(self, entity_id, start_date, end_date):
        """Fetches transactions within the given date range."""
        transactions = StockTransactions.objects.filter(
            entity_id=entity_id,
            entrydatetime__date__range=(start_date, end_date)
        ).exclude(accounttype='MD').exclude(transactiontype='PC')

        transaction_data = transactions.values(
            'account__accounthead__id', 
            'account__creditaccounthead__id', 
            'account__accountname'
        ).annotate(
            total_debit=Coalesce(Sum('debitamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4)),
            total_credit=Coalesce(Sum('creditamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4))
        ).annotate(
            balance=F('total_debit') - F('total_credit'),
            accounthead_id=Case(
                When(balance__lt=0, then=F('account__creditaccounthead__id')),
                default=F('account__accounthead__id'),
                output_field=CharField()
            ),
            accounthead=Case(
                When(balance__lt=0, then=F('account__creditaccounthead__name')),
                default=F('account__accounthead__name'),
                output_field=CharField()
            )
        ).values(
            accounthead_id=F('accounthead_id'),
            accounthead=F('accounthead'),
            balance=F('balance'),
            total_debit=F('total_debit'),
            total_credit=F('total_credit')
        )

        return {
            entry["accounthead"]: {
                "id": entry["accounthead_id"],
                "balance": entry["balance"],
                "debit": entry["balance"] if entry["balance"] > 0 else 0,
                "credit": -entry["balance"] if entry["balance"] < 0 else 0
            } for entry in transaction_data
        }

    def aggregate_data(self, opening_balance_dict, transaction_dict):
        """Aggregates opening balances and transactions into a final result."""
        final_aggregation = {}

        # Add Opening Balances First
        for accounthead, data in opening_balance_dict.items():
            final_aggregation[accounthead] = {
                'accounthead_id': data["id"],  # ✅ Correcting to accounthead_id
                'accounthead': accounthead,
                'debit': 0,
                'credit': 0,
                'balance': data["opening_balance"],
                'opening_balance': data["opening_balance"]
            }

        # Add Transactions to the Final Data
        for accounthead, trans_data in transaction_dict.items():
            if accounthead in final_aggregation:
                final_aggregation[accounthead]['debit'] += trans_data["debit"]
                final_aggregation[accounthead]['credit'] += trans_data["credit"]
                final_aggregation[accounthead]['balance'] += trans_data["balance"]
            else:
                final_aggregation[accounthead] = {
                    'accounthead_id': trans_data["id"],  # ✅ Correcting to accounthead_id
                    'accounthead': accounthead,
                    'debit': trans_data["debit"],
                    'credit': trans_data["credit"],
                    'opening_balance': 0,
                    'balance': trans_data["balance"]
                }

        # Add DR/CR Indicators
        final_result = []
        for accounthead, data in final_aggregation.items():
            data["drcr"] = "DR" if data["balance"] > 0 else "CR"
            data["obdrcr"] = "DR" if data["opening_balance"] > 0 else "CR"

            final_result.append(data)

        return final_result

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get('entity')
        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')

        if not entity_id or not start_date or not end_date:
            return Response({'error': 'Missing required parameters'}, status=400)

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        # Get Data
        opening_balance_dict = self.get_opening_balance(entity_id, start_date)
        transaction_dict = self.get_transactions(entity_id, start_date, end_date)

        # Aggregate & Return
        final_result = self.aggregate_data(opening_balance_dict, transaction_dict)
        return Response(final_result)


class TrialBalanceViewaccountFinal(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_opening_balance(self, entity_id, start_date, accounthead=None, drcr=None):
        """Fetches opening balances before the start date with filters."""
        opening_transactions = StockTransactions.objects.filter(
            entity_id=entity_id,
            entrydatetime__date__lt=start_date
        ).exclude(accounttype='MD').exclude(transactiontype='PC')

        if accounthead:
            if drcr == 'dr':
                opening_transactions = opening_transactions.filter(account__accounthead=accounthead)
            else:
                opening_transactions = opening_transactions.filter(account__creditaccounthead=accounthead)

        opening_balance_data = opening_transactions.values('account__id', 'account__accountname', 'account__accounthead').annotate(
            opening_debit=Coalesce(Sum('debitamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4)),
            opening_credit=Coalesce(Sum('creditamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4))
        ).annotate(
            opening_balance=F('opening_debit') - F('opening_credit')
        ).values(
            account_id=F('account__id'),
            accountname=F('account__accountname'),
            accounthead=F('account__accounthead'),
            opening_balance=F('opening_balance')
        )

        return {
            entry["account_id"]: {
                "accountname": entry["accountname"],
                "accounthead": entry["accounthead"],
                "opening_balance": entry["opening_balance"]
            } for entry in opening_balance_data
        }

    def get_transactions(self, entity_id, start_date, end_date, accounthead=None, drcr=None):
        """Fetches transactions within the given date range with filters."""
        transactions = StockTransactions.objects.filter(
            entity_id=entity_id,
            entrydatetime__date__range=(start_date, end_date)
        ).exclude(accounttype='MD').exclude(transactiontype='PC')

        if accounthead:
            if drcr == 'dr':
                transactions = transactions.filter(account__accounthead=accounthead)
            else:
                transactions = transactions.filter(account__creditaccounthead=accounthead)

        transaction_data = transactions.values(
            'account__id', 'account__accountname', 'account__accounthead'
        ).annotate(
            total_debit=Coalesce(Sum('debitamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4)),
            total_credit=Coalesce(Sum('creditamount'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4)),
            total_quantity=Coalesce(Sum('quantity'), Value(0), output_field=DecimalField(max_digits=14, decimal_places=4))
        ).annotate(
            balance=F('total_debit') - F('total_credit')
        ).values(
            account_id=F('account__id'),
            accountname=F('account__accountname'),
            accounthead=F('account__accounthead'),
            balance=F('balance'),
            total_debit=F('total_debit'),
            total_credit=F('total_credit'),
            total_quantity=F('total_quantity')
        )

        # Apply final filtering based on drcr parameter
        if drcr == 'dr':
            transaction_data = [entry for entry in transaction_data if entry["balance"] > 0]
        elif drcr == 'cr':
            transaction_data = [entry for entry in transaction_data if entry["balance"] < 0]

        return {
            entry["account_id"]: {
                "accountname": entry["accountname"],
                "accounthead": entry["accounthead"],
                "balance": entry["balance"],
                "debit": entry["balance"] if entry["balance"] > 0 else 0,
                "credit": -entry["balance"] if entry["balance"] < 0 else 0,
                "total_quantity": entry["total_quantity"]
            } for entry in transaction_data
        }

    def aggregate_data(self, opening_balance_dict, transaction_dict):
        """Aggregates opening balances and transactions into a final result."""
        final_aggregation = {}

        for account_id, data in opening_balance_dict.items():
            final_aggregation[account_id] = {
                'account_id': account_id,
                'accountname': data["accountname"],
                'accounthead': data["accounthead"],
                'debit': 0,
                'credit': 0,
                'balance': data["opening_balance"],
                'opening_balance': data["opening_balance"],
                'total_quantity': 0
            }

        for account_id, trans_data in transaction_dict.items():
            if account_id in final_aggregation:
                final_aggregation[account_id]['debit'] += trans_data["debit"]
                final_aggregation[account_id]['credit'] += trans_data["credit"]
                final_aggregation[account_id]['balance'] += trans_data["balance"]
                final_aggregation[account_id]['total_quantity'] += trans_data["total_quantity"]
            else:
                final_aggregation[account_id] = {
                    'account_id': account_id,
                    'accountname': trans_data["accountname"],
                    'accounthead': trans_data["accounthead"],
                    'debit': trans_data["debit"],
                    'credit': trans_data["credit"],
                    'opening_balance': 0,
                    'balance': trans_data["balance"],
                    'total_quantity': trans_data["total_quantity"]
                }

        final_result = []
        for account_id, data in final_aggregation.items():
            data["drcr"] = "DR" if data["balance"] > 0 else "CR"
            data["obdrcr"] = "DR" if data["opening_balance"] > 0 else "CR"
            final_result.append(data)

        return final_result

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get('entity')
        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')
        accounthead = request.query_params.get('accounthead')
        drcr = request.query_params.get('drcr')

        if not entity_id or not start_date or not end_date:
            return Response({'error': 'Missing required parameters'}, status=400)

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        opening_balance_dict = self.get_opening_balance(entity_id, start_date, accounthead, drcr)
        transaction_dict = self.get_transactions(entity_id, start_date, end_date, accounthead, drcr)

        final_result = self.aggregate_data(opening_balance_dict, transaction_dict)
        return Response(final_result)


class StockSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get('entity_id')
        if not entity_id:
            return Response({"error": "entity_id is required"}, status=400)

        transactions = StockTransactions.objects.filter(entity_id=entity_id).order_by('entrydate', 'id')
        products = Product.objects.select_related('productcategory').filter(stocktrans__entity_id=entity_id).distinct()

        summary = []

        for product in products:
            fifo_stack = deque()
            sale_rate = 0
            total_inward_qty = 0
            total_outward_qty = 0
            total_inward_value = 0
            last_movement = None

            product_trans = transactions.filter(stock=product)

            for tx in product_trans:
                qty = tx.quantity or 0
                last_movement = tx.entrydate if tx.entrydate else last_movement

                if tx.stockttype in ['P', 'R']:
                    rate = tx.rate or sale_rate
                    fifo_stack.append((qty, rate))
                    total_inward_qty += qty
                    total_inward_value += qty * rate

                    if tx.stockttype == 'S':
                        sale_rate = tx.rate or sale_rate

                elif tx.stockttype in ['S', 'I']:
                    qty_out = qty
                    cost_out = 0

                    while qty_out > 0 and fifo_stack:
                        available_qty, rate = fifo_stack[0]
                        if available_qty <= qty_out:
                            cost_out += available_qty * rate
                            qty_out -= available_qty
                            fifo_stack.popleft()
                        else:
                            cost_out += qty_out * rate
                            fifo_stack[0] = (available_qty - qty_out, rate)
                            qty_out = 0

                    total_outward_qty += qty

            qty_available = total_inward_qty - total_outward_qty
            unit_rate = (total_inward_value / total_inward_qty) if total_inward_qty else 0
            total_value = qty_available * unit_rate

            summary.append({
                'Category': product.productcategory.pcategoryname if product.productcategory else '',
                'Code': product.productcode,
                'Description': product.productname,
              #  'UOM': product.uom,
                'Quantity_Available': round(qty_available, 4),
                'Unit_Rate_FIFO': round(unit_rate, 4),
                'Total_Value': round(total_value, 2),
                'Last_Movement_Date': last_movement,
            })

        return Response(summary)

class StockDayBookReportView(ListAPIView):
    serializer_class = StockDayBookSerializer

    def get_queryset(self):
        queryset = StockTransactions.objects.select_related(
            'stock', 'stock__unitofmeasurement', 'account'
        ).order_by('entrydatetime')

        entity_id = self.request.query_params.get('entity')
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id,accounttype='DD',isactive =1)

        return queryset
        
def calculate_fifo_rate(product, entity_id, end_date, total_qty):
    try:
        if total_qty <= 0:
            return Decimal('0.00'), Decimal('0.00')

        qty_remaining = total_qty
        total_value = Decimal('0.00')

        inflow_txns = StockTransactions.objects.filter(
            stock=product,
            entity_id=entity_id,
            accounttype='DD',
            isactive=1,
            stockttype__in=['P'],
            entrydatetime__lte=end_date
        ).order_by('entrydatetime')

        for txn in inflow_txns:
            txn_qty = txn.quantity or 0
            txn_rate = txn.rate or 0

            if txn_qty <= 0:
                continue

            if qty_remaining >= txn_qty:
                total_value += txn_qty * txn_rate
                qty_remaining -= txn_qty
            else:
                total_value += qty_remaining * txn_rate
                break

        fifo_rate = total_value / total_qty if total_qty > 0 else Decimal('0.00')
        return round(fifo_rate, 2), round(total_value, 2)

    except Exception:
        return Decimal('0.00'), Decimal('0.00')

def calculate_lifo_rate(product, entity_id, end_date, total_qty):
    try:
        if total_qty <= 0:
            return Decimal('0.00'), Decimal('0.00')

        qty_remaining = total_qty
        total_value = Decimal('0.00')

        inflow_txns = StockTransactions.objects.filter(
            stock=product,
            entity_id=entity_id,
            accounttype='DD',
            isactive=1,
            stockttype__in=['P'],
            entrydatetime__lte=end_date
        ).order_by('-entrydatetime')

        for txn in inflow_txns:
            txn_qty = txn.quantity or 0
            txn_rate = txn.rate or 0

            if txn_qty <= 0:
                continue

            if qty_remaining >= txn_qty:
                total_value += txn_qty * txn_rate
                qty_remaining -= txn_qty
            else:
                total_value += qty_remaining * txn_rate
                break

        lifo_rate = total_value / total_qty if total_qty > 0 else Decimal('0.00')
        return round(lifo_rate, 2), round(total_value, 2)

    except Exception:
        return Decimal('0.00'), Decimal('0.00')

def calculate_average_rate(product, entity_id, end_date):
    try:
        inflow_txns = StockTransactions.objects.filter(
            stock=product,
            entity_id=entity_id,
            accounttype='DD',
            isactive=1,
            stockttype__in=['P'],
            entrydatetime__lte=end_date
        )

        total_qty = inflow_txns.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        total_value = sum((txn.quantity or 0) * (txn.rate or 0) for txn in inflow_txns)

        avg_rate = total_value / total_qty if total_qty > 0 else Decimal('0.00')
        return round(avg_rate, 2), round(total_value, 2)

    except Exception:
        return Decimal('0.00'), Decimal('0.00')

def get_last_sale_rate(product, entity_id, end_date):
    last_sale_txn = StockTransactions.objects.filter(
        stock=product,
        entity_id=entity_id,
        accounttype='DD',
        isactive=1,
        stockttype='S',
        entrydatetime__lte=end_date
    ).order_by('-entrydatetime').first()

    return round(last_sale_txn.rate or Decimal('0.00'), 2) if last_sale_txn else Decimal('0.00')

# Stock summary view
class StockSummaryView(APIView):
    def get(self, request, *args, **kwargs):
        try:
            entity_id = request.query_params.get('entity_id')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            ratemethod = request.query_params.get('method', 'fifo')

            if not (entity_id and start_date and end_date):
                return Response({'error': 'Missing parameters'}, status=status.HTTP_400_BAD_REQUEST)

            start_date = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
            end_date = timezone.make_aware(datetime.strptime(end_date, "%Y-%m-%d"))

            summary = []
            products = Product.objects.filter(entity_id=entity_id)

            for product in products:
                opening_in = StockTransactions.objects.filter(
                    stock=product,
                    entity_id=entity_id,
                    accounttype='DD',
                    isactive=1,
                    stockttype__in=['R', 'P'],
                    entry__entrydate1__lt=start_date
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

                opening_out = StockTransactions.objects.filter(
                    stock=product,
                    entity_id=entity_id,
                    accounttype='DD',
                    isactive=1,
                    stockttype__in=['I', 'S'],
                    entry__entrydate1__lt=start_date
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

                opening_qty = opening_in - opening_out

                inward_qty = StockTransactions.objects.filter(
                    stock=product,
                    entity_id=entity_id,
                    accounttype='DD',
                    isactive=1,
                    stockttype__in=['R', 'P'],
                    entry__entrydate1__range=[start_date, end_date]
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

                outward_qty = StockTransactions.objects.filter(
                    stock=product,
                    entity_id=entity_id,
                    accounttype='DD',
                    isactive=1,
                    stockttype__in=['I', 'S'],
                    entry__entrydate1__range=[start_date, end_date]
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

                if opening_qty == 0 and inward_qty == 0 and outward_qty == 0:
                    continue

                closing_qty = opening_qty + inward_qty - outward_qty

                if ratemethod == 'fifo':
                    rate, value = calculate_lifo_rate(product, entity_id, end_date, closing_qty)
                elif ratemethod == 'lifo':
                    rate, value = calculate_fifo_rate(product, entity_id, end_date, closing_qty)
                elif ratemethod == 'avg':
                    rate, value = calculate_average_rate(product, entity_id, end_date)
                    value = closing_qty * rate
                elif ratemethod == 'lastsale':
                    rate = get_last_sale_rate(product, entity_id, end_date)
                    value = closing_qty * rate
                else:
                    rate, value = Decimal('0.00'), Decimal('0.00')

                last_movement = StockTransactions.objects.filter(
                    stock=product,
                    entity_id=entity_id,
                    accounttype='DD',
                    isactive=1
                ).aggregate(last=Max('entrydatetime'))['last']

                summary.append({
                    'productdesc': product.productdesc or '',
                    'productname': product.productname,
                    'category': product.productcategory.pcategoryname if hasattr(product, 'productcategory') and product.productcategory else '',
                    'uom': product.unitofmeasurement.unitcode if product.unitofmeasurement else '',
                    'opening_qty': float(opening_qty),
                    'inward_qty': float(inward_qty),
                    'outward_qty': float(outward_qty),
                    'closing_qty': float(closing_qty),
                    'rate': float(rate),
                    'value': float(value),
                    'last_movement_date': last_movement.strftime('%d-%m-%Y') if last_movement else None
                })

            serializer = StockSummarySerializerList(summary, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StockLedgerBookView(APIView):
    def get(self, request):
        entity_id = request.GET.get("entity_id")
        product_id = request.GET.get("product")
        method = request.GET.get("method", "fifo").lower()
        date_from = request.GET.get("start_date")
        date_to = request.GET.get("end_date")

        if not (entity_id and product_id):
            return Response({"error": "Entity and Product are required."}, status=400)

        all_transactions = StockTransactions.objects.filter(entity_id=entity_id, stock_id=product_id,accounttype='DD',isactive=1).order_by("entrydatetime")

        # Opening Balance Calculation (before date_from)
        opening_qty = Decimal(0)
        opening_value = Decimal(0)
        rate_stack = deque()
        total_qty = Decimal(0)
        total_value = Decimal(0)

        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
                opening_txns = all_transactions.filter(entrydatetime__date__lt=date_from_obj)

                for tx in opening_txns:
                    qty = tx.quantity or Decimal(0)
                    rate = tx.rate or Decimal(0)

                    if tx.stockttype in ['P', 'R']:  # Inward
                        if method in ['fifo', 'lifo']:
                            rate_stack.append({'qty': qty, 'rate': rate})
                        elif method == 'avg':
                            total_qty += qty
                            total_value += qty * rate
                        opening_qty += qty
                        opening_value += qty * rate

                    elif tx.stockttype in ['S', 'I']:  # Outward
                        if method == 'fifo':
                            rate_used = self.calculate_fifo_rate(rate_stack, qty)
                        elif method == 'lifo':
                            rate_used = self.calculate_lifo_rate(rate_stack, qty)
                        elif method == 'avg':
                            rate_used = (total_value / total_qty) if total_qty else Decimal(0)
                            total_qty -= qty
                            total_value -= qty * rate_used
                            rate_used = rate_used
                        opening_qty -= qty
                        opening_value -= qty * rate_used

            except ValueError:
                return Response({"error": "Invalid date_from format. Use YYYY-MM-DD"}, status=400)

        # Filter main transactions
        txns = all_transactions
        if date_from:
            txns = txns.filter(entrydatetime__date__gte=date_from_obj)
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
                txns = txns.filter(entrydatetime__date__lte=date_to_obj)
            except ValueError:
                return Response({"error": "Invalid date_to format. Use YYYY-MM-DD"}, status=400)

        ledger = []
        balance_qty = opening_qty
        last_known_rate = (opening_value / opening_qty) if opening_qty > 0 else Decimal(0)
        value_balance = balance_qty * last_known_rate

        # Add Opening Row
        ledger.append({
            "Date": date_from_obj if date_from else None,
            "Trans_No": "OPENING",
            "Type": "Opening Balance",
            "In_Qty": None,
            "Out_Qty": None,
            "Rate": float(last_known_rate),
            "Value": float(opening_value),
            "Balance_Qty": float(balance_qty),
            "Value_Balance": float(value_balance),
            "From": "",
            "To": "",
            "Remarks": ""
        })

        # Process Each Transaction
        for tx in txns:
            row = {}
            row['Date'] = tx.entrydatetime.date() if tx.entrydatetime else None
            row['Trans No'] = tx.voucherno or ''
            row['Type'] = self.get_transaction_type(tx)

            in_qty = out_qty = None
            if tx.stockttype in ['P', 'R']:
                in_qty = tx.quantity or Decimal(0)
                rate = tx.rate or Decimal(0)
                last_known_rate = rate

                if method in ['fifo', 'lifo']:
                    rate_stack.append({'qty': in_qty, 'rate': rate})
                elif method == 'avg':
                    total_qty += in_qty
                    total_value += in_qty * rate
                    last_known_rate = (total_value / total_qty) if total_qty else Decimal(0)

            elif tx.stockttype in ['S', 'I']:
                out_qty = tx.quantity or Decimal(0)
                if method == 'fifo':
                    last_known_rate = self.calculate_fifo_rate(rate_stack, out_qty)
                elif method == 'lifo':
                    last_known_rate = self.calculate_lifo_rate(rate_stack, out_qty)
                elif method == 'avg':
                    last_known_rate = (total_value / total_qty) if total_qty else Decimal(0)
                    total_qty -= out_qty
                    total_value -= out_qty * last_known_rate

            row['In Qty'] = float(in_qty) if in_qty else None
            row['Out Qty'] = float(out_qty) if out_qty else None
            row['Rate'] = float(last_known_rate)
            row['Value'] = float((in_qty or out_qty or Decimal(0)) * last_known_rate)

            # Update balance
            balance_qty += (in_qty or Decimal(0)) - (out_qty or Decimal(0))
            value_balance = balance_qty * last_known_rate
            row['Balance Qty'] = float(balance_qty)
            row['Value Balance'] = float(value_balance)

            row['From'] = tx.account.accountname if tx.drcr else ''
            row['To'] = tx.account.accountname if not tx.drcr else ''
            row['Remarks'] = tx.desc

            ledger.append(row)

        return Response(ledger)

    def calculate_fifo_rate(self, rate_stack, out_qty):
        value = Decimal(0)
        remaining = out_qty
        while remaining > 0 and rate_stack:
            layer = rate_stack[0]
            used = min(remaining, layer['qty'])
            value += used * layer['rate']
            layer['qty'] -= used
            remaining -= used
            if layer['qty'] == 0:
                rate_stack.popleft()
        return (value / out_qty) if out_qty else Decimal(0)

    def calculate_lifo_rate(self, rate_stack, out_qty):
        value = Decimal(0)
        remaining = out_qty
        while remaining > 0 and rate_stack:
            layer = rate_stack[-1]
            used = min(remaining, layer['qty'])
            value += used * layer['rate']
            layer['qty'] -= used
            remaining -= used
            if layer['qty'] == 0:
                rate_stack.pop()
        return (value / out_qty) if out_qty else Decimal(0)

    def get_transaction_type(self, tx):
        if tx.transactiontype == 'PRO':
            return 'Issued to Production' if tx.stockttype == 'I' else 'Received from Production'
        elif tx.stockttype == 'P':
            return 'Purchase'
        elif tx.stockttype == 'S':
            return 'Sale'
        return tx.transactiontype or ''


class TransactionTypeListView(APIView):
    def get(self, request):
        transaction_types = TransactionType.objects.all()
        serializer = TransactionTypeSerializer(transaction_types, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

def get_aging_bucket(days_overdue):
    if days_overdue <= 0:
        return 'current'
    elif days_overdue <= 30:
        return 'bucket_1_30'
    elif days_overdue <= 60:
        return 'bucket_31_60'
    elif days_overdue <= 90:
        return 'bucket_61_90'
    else:
        return 'bucket_90_plus'


class AccountsReceivableAgingReport(APIView):
    def post(self, request):
        try:
            entity = request.data.get("entity")
            startdate_str = request.data.get("startdate")
            enddate_str = request.data.get("enddate")

            if not all([entity,startdate_str, enddate_str]):
                return Response({"error": "Missing required parameters"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                startdate = datetime.strptime(startdate_str, "%Y-%m-%d").date()
                enddate = datetime.strptime(enddate_str, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

            today = date.today()

            transactions = StockTransactions.objects.select_related('account', 'entry').filter(
                entity=entity,
                accounttype='M',
                isactive=True,
                account__isnull=False,
                entry__isnull=False,
                entry__entrydate1__range=(startdate, enddate)
            ).order_by('entry__entrydate1')

            customer_data = defaultdict(lambda: {
                "customer_name": "",
                "total_amount": 0.0,
                "amount_received": 0.0,
                "total_balance": 0.0,
                "current": 0.0,
                "bucket_1_30": 0.0,
                "bucket_31_60": 0.0,
                "bucket_61_90": 0.0,
                "bucket_90_plus": 0.0,
                "last_invoice_date": None,
                "last_due_date": None,
                "last_payment_received_date": None
            })

            account_transactions = defaultdict(list)
            customer_payments = defaultdict(list)

            for txn in transactions:
                account_name = txn.account.accountname if txn.account else "Unknown"
                entry_date = txn.entry.entrydate1
                due_date = entry_date + timedelta(days=15) if entry_date else None

                if not account_name or not entry_date:
                    continue

                customer_data[account_name]["customer_name"] = account_name

                if txn.debitamount and txn.debitamount > 0:
                    account_transactions[account_name].append({
                        "amount": float(txn.debitamount),
                        "entry_date": entry_date,
                        "due_date": due_date,
                    })
                    customer_data[account_name]["total_amount"] += float(txn.debitamount)

                    if not customer_data[account_name]["last_invoice_date"] or entry_date > customer_data[account_name]["last_invoice_date"]:
                        customer_data[account_name]["last_invoice_date"] = entry_date
                        customer_data[account_name]["last_due_date"] = due_date

                elif txn.creditamount and txn.creditamount > 0:
                    customer_data[account_name]["amount_received"] += float(txn.creditamount)
                    customer_payments[account_name].append({
                        "amount": float(txn.creditamount),
                        "payment_date": entry_date
                    })

                    if (not customer_data[account_name]["last_payment_received_date"]
                            or entry_date > customer_data[account_name]["last_payment_received_date"]):
                        customer_data[account_name]["last_payment_received_date"] = entry_date

            final_output = []
            for account_name, invoices in account_transactions.items():
                payments = customer_payments.get(account_name, [])
                invoice_queue = list(invoices)
                payment_queue = list(payments)

                for payment in payment_queue:
                    amount = payment["amount"]
                    while amount > 0 and invoice_queue:
                        invoice = invoice_queue[0]
                        if invoice["amount"] <= amount:
                            amount -= invoice["amount"]
                            invoice_queue.pop(0)
                        else:
                            invoice["amount"] -= amount
                            amount = 0

                total_balance = 0.0
                for invoice in invoice_queue:
                    balance = invoice["amount"]
                    days_due = (today - invoice["due_date"]).days
                    total_balance += balance
                    if days_due <= 0:
                        customer_data[account_name]["current"] += balance
                    elif days_due <= 30:
                        customer_data[account_name]["bucket_1_30"] += balance
                    elif days_due <= 60:
                        customer_data[account_name]["bucket_31_60"] += balance
                    elif days_due <= 90:
                        customer_data[account_name]["bucket_61_90"] += balance
                    else:
                        customer_data[account_name]["bucket_90_plus"] += balance

                customer_data[account_name]["total_balance"] = total_balance

            for data in customer_data.values():
                final_output.append({
                    "customer_name": data["customer_name"],
                    "total_amount": round(data["total_amount"], 2),
                    "amount_received": round(data["amount_received"], 2),
                    "total_balance": round(data["total_balance"], 2),
                    "current": round(data["current"], 2),
                    "bucket_1_30": round(data["bucket_1_30"], 2),
                    "bucket_31_60": round(data["bucket_31_60"], 2),
                    "bucket_61_90": round(data["bucket_61_90"], 2),
                    "bucket_90_plus": round(data["bucket_90_plus"], 2),
                    "last_invoice_date": data["last_invoice_date"],
                    "last_due_date": data["last_due_date"],
                    "last_payment_received_date": data["last_payment_received_date"]
                })

            return Response(final_output)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class AccountsPayableAgingReportView(APIView):
    def post(self, request):
        try:
            entity = request.data.get('entity')
            startdate = request.data.get('startdate')
            enddate = request.data.get('enddate')

            if not (entity and  startdate and enddate):
                return Response({"error": "Missing required parameters"}, status=status.HTTP_400_BAD_REQUEST)

            start_date = datetime.strptime(startdate, "%Y-%m-%d").date()
            end_date = datetime.strptime(enddate, "%Y-%m-%d").date()
            today = date.today()

            transactions = StockTransactions.objects.select_related('account', 'entry').filter(
                accounttype='M',
                isactive=True,
                account__isnull=False,
                entry__entrydate1__range=(start_date, end_date),
                entity=entity
            )

            vendor_data = defaultdict(lambda: {
                "vendor_name": "",
                "total_amount": 0.0,
                "amount_paid": 0.0,
                "total_balance": 0.0,
                "current": 0.0,
                "bucket_1_30": 0.0,
                "bucket_31_60": 0.0,
                "bucket_61_90": 0.0,
                "bucket_90_plus": 0.0,
                "last_invoice_date": None,
                "last_due_date": None,
                "last_payment_date": None
            })

            transactions_by_vendor = defaultdict(list)
            for txn in transactions:
                if txn.account and txn.entry:
                    transactions_by_vendor[txn.account.accountname].append(txn)

            for vendor_name, txns in transactions_by_vendor.items():
                bills = []
                payments = []

                for txn in sorted(txns, key=lambda x: x.entry.entrydate1):
                    if txn.debitamount and txn.debitamount > 0:
                        bills.append({
                            "amount": float(txn.debitamount),
                            "entry_date": txn.entry.entrydate1,
                            "due_date": txn.entry.entrydate1 + timedelta(days=15),
                        })
                        if (not vendor_data[vendor_name]["last_invoice_date"]) or txn.entry.entrydate1 > vendor_data[vendor_name]["last_invoice_date"]:
                            vendor_data[vendor_name]["last_invoice_date"] = txn.entry.entrydate1
                            vendor_data[vendor_name]["last_due_date"] = txn.entry.entrydate1 + timedelta(days=15)

                        vendor_data[vendor_name]["total_amount"] += float(txn.debitamount)

                    elif txn.creditamount and txn.creditamount > 0:
                        payments.append({
                            "amount": float(txn.creditamount),
                            "entry_date": txn.entry.entrydate1
                        })
                        vendor_data[vendor_name]["amount_paid"] += float(txn.creditamount)

                        if (not vendor_data[vendor_name]["last_payment_date"]) or txn.entry.entrydate1 > vendor_data[vendor_name]["last_payment_date"]:
                            vendor_data[vendor_name]["last_payment_date"] = txn.entry.entrydate1

                for payment in payments:
                    amt = payment["amount"]
                    for bill in bills:
                        if bill["amount"] == 0:
                            continue
                        if amt <= 0:
                            break
                        applied = min(amt, bill["amount"])
                        bill["amount"] -= applied
                        amt -= applied

                for bill in bills:
                    if bill["amount"] > 0:
                        days_due = (today - bill["due_date"]).days
                        vendor_data[vendor_name]["total_balance"] += bill["amount"]

                        if days_due <= 0:
                            vendor_data[vendor_name]["current"] += bill["amount"]
                        elif days_due <= 30:
                            vendor_data[vendor_name]["bucket_1_30"] += bill["amount"]
                        elif days_due <= 60:
                            vendor_data[vendor_name]["bucket_31_60"] += bill["amount"]
                        elif days_due <= 90:
                            vendor_data[vendor_name]["bucket_61_90"] += bill["amount"]
                        else:
                            vendor_data[vendor_name]["bucket_90_plus"] += bill["amount"]

                vendor_data[vendor_name]["vendor_name"] = vendor_name

            return Response(list(vendor_data.values()))

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EMICalculatorAPIView(APIView):
    def post(self, request):
        serializer = EMICalculatorSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            emi, schedule = calculate_emi(
                data['principal'],
                data['annual_rate'],
                data['tenure_months'],
                data['start_date'],
                data['interest_type']
            )
            return Response({
                'monthly_emi': emi,
                'amortization_schedule': schedule
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class GSTSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        def aggregate_queryset(qs):
            return qs.aggregate(
                amount=Coalesce(Sum('amount'), Value(0, output_field=DecimalField())),
                cgst=Coalesce(Sum('cgst'), Value(0, output_field=DecimalField())),
                sgst=Coalesce(Sum('sgst'), Value(0, output_field=DecimalField())),
                igst=Coalesce(Sum('igst'), Value(0, output_field=DecimalField()))
            )

        def fetch_and_aggregate(gst_filter):
            sales_qs = salesOrderdetails.objects.filter(gst_filter)
            return_qs = Purchasereturndetails.objects.filter(gst_filter)
            salereturn_qs = salereturnDetails.objects.filter(gst_filter)
    
            sales_agg = aggregate_queryset(sales_qs)
            return_agg = aggregate_queryset(return_qs)
            salereturn_agg = aggregate_queryset(salereturn_qs)

            return {
                "total_amount": (sales_agg["amount"] + return_agg["amount"]) - salereturn_agg["amount"],
                "cgst": (sales_agg["cgst"] + return_agg["cgst"]) - salereturn_agg["cgst"],
                "sgst": (sales_agg["sgst"] + return_agg["sgst"]) - salereturn_agg["sgst"],
                "igst": (sales_agg["igst"] + return_agg["igst"]) - salereturn_agg["igst"]
            }

        # Outward taxable supplies (> 0%)
        taxable_filter = (
            Q(cgstpercent__gt=0) |
            Q(sgstpercent__gt=0) |
            Q(igstpercent__gt=0)
        )

        # 0% GST supplies (exactly 0)
        zero_filter = (
            Q(cgstpercent=0) &
            Q(sgstpercent=0) &
            Q(igstpercent=0)
        )

        # Nil-rated supplies (null or not provided)
        nil_filter = (
            Q(cgstpercent__isnull=True) &
            Q(sgstpercent__isnull=True) &
            Q(igstpercent__isnull=True)
        )

        data = {
            "Outward taxable supplies": fetch_and_aggregate(taxable_filter),
            "Outward supplies at 0% GST": fetch_and_aggregate(zero_filter),
            "Nil rated outward supplies": fetch_and_aggregate(nil_filter),
        }

        return Response(data)



class TrialBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    # ----- helpers ---------------------------------------------------------
    def _sum_debit(self, qs):
        return Coalesce(Sum(Case(When(drcr=True, then=F('amount')),
                                 default=Value(0),
                                 output_field=DecimalField(max_digits=14, decimal_places=2))),
                        Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)))

    def _sum_credit(self, qs):
        return Coalesce(Sum(Case(When(drcr=False, then=F('amount')),
                                 default=Value(0),
                                 output_field=DecimalField(max_digits=14, decimal_places=2))),
                        Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)))

    def _opening_by_account(self, entity_id, start_date, accounthead_id=None, drcr_filter=None):
        """
        Opening = sum of all postings strictly before start_date
        """
        qs = (JournalLine.objects
              .filter(entity_id=entity_id, entrydate__lt=start_date)
              .select_related('account', 'accounthead'))

        if accounthead_id:
            qs = qs.filter(accounthead_id=accounthead_id)

        # (optional) filter by side for opening
        if drcr_filter == 'dr':
            qs = qs.filter(drcr=True)
        elif drcr_filter == 'cr':
            qs = qs.filter(drcr=False)

        # aggregate per account
        agg = (qs.values('account_id', 'account__accountname', 'accounthead_id', 'accounthead__accounthead')
                 .annotate(
                     opening_debit=self._sum_debit(qs),
                     opening_credit=self._sum_credit(qs),
                 )
                 .annotate(
                     opening_balance=F('opening_debit') - F('opening_credit')
                 ))

        # return as dict keyed by account_id
        return {
            row['account_id']: {
                'account_id': row['account_id'],
                'accountname': row['account__accountname'],
                'accounthead_id': row['accounthead_id'],
                'accounthead': row['accounthead__accounthead'],
                'opening_debit': row['opening_debit'],
                'opening_credit': row['opening_credit'],
                'opening_balance': row['opening_balance'],
            }
            for row in agg
        }

    def _period_by_account(self, entity_id, start_date, end_date, accounthead_id=None, drcr_filter=None):
        """
        Movements in the date window (inclusive)
        """
        qs = (JournalLine.objects
              .filter(entity_id=entity_id, entrydate__range=(start_date, end_date))
              .select_related('account', 'accounthead'))

        if accounthead_id:
            qs = qs.filter(accounthead_id=accounthead_id)

        # (optional) filter by side for period totals
        if drcr_filter == 'dr':
            qs = qs.filter(drcr=True)
        elif drcr_filter == 'cr':
            qs = qs.filter(drcr=False)

        agg = (qs.values('account_id', 'account__accountname', 'accounthead_id', 'accounthead__accounthead')
                .annotate(
                    period_debit=self._sum_debit(qs),
                    period_credit=self._sum_credit(qs),
                )
                .annotate(
                    period_balance=F('period_debit') - F('period_credit')
                ))

        return {
            row['account_id']: {
                'account_id': row['account_id'],
                'accountname': row['account__accountname'],
                'accounthead_id': row['accounthead_id'],
                'accounthead': row['accounthead__accounthead'],
                'period_debit': row['period_debit'],
                'period_credit': row['period_credit'],
                'period_balance': row['period_balance'],
            }
            for row in agg
        }

    # ----- GET -------------------------------------------------------------
    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get('entity')
        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')
        accounthead_id = request.query_params.get('accounthead')  # accountHead PK (optional)
        drcr = request.query_params.get('drcr')  # 'dr' | 'cr' | None

        if not entity_id or not start_date or not end_date:
            return Response({'error': 'Missing required parameters: entity, startdate, enddate'}, status=400)

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        # Opening and period dictionaries keyed by account_id
        opening = self._opening_by_account(entity_id, start_date, accounthead_id, drcr)
        period = self._period_by_account(entity_id, start_date, end_date, accounthead_id, drcr)

        # Merge
        account_ids = set(opening.keys()) | set(period.keys())
        result = []
        for acc_id in account_ids:
            o = opening.get(acc_id)
            p = period.get(acc_id)

            accountname = (o or p)['accountname']
            accounthead = (o or p)['accounthead']
            accounthead_id = (o or p)['accounthead_id']

            opening_debit = (o or {}).get('opening_debit', Decimal('0'))
            opening_credit = (o or {}).get('opening_credit', Decimal('0'))
            opening_balance = (o or {}).get('opening_balance', Decimal('0'))

            period_debit = (p or {}).get('period_debit', Decimal('0'))
            period_credit = (p or {}).get('period_credit', Decimal('0'))
            period_balance = (p or {}).get('period_balance', Decimal('0'))

            closing_balance = opening_balance + period_balance

            result.append({
                'account_id': acc_id,
                'accountname': accountname,
                'accounthead_id': accounthead_id,
                'accounthead': accounthead,

                'opening_debit': opening_debit,
                'opening_credit': opening_credit,
                'opening_balance': opening_balance,
                'obdrcr': 'DR' if opening_balance > 0 else 'CR' if opening_balance < 0 else '',

                'period_debit': period_debit,
                'period_credit': period_credit,
                'period_balance': period_balance,

                'closing_balance': closing_balance,
                'drcr': 'DR' if closing_balance > 0 else 'CR' if closing_balance < 0 else '',
            })

        # Optional post-filter by DR/CR on closing (kept for parity with your old view)
        if drcr == 'dr':
            result = [r for r in result if r['closing_balance'] > 0]
        elif drcr == 'cr':
            result = [r for r in result if r['closing_balance'] < 0]

        # Sort nicely by account head then account name
        result.sort(key=lambda r: (str(r['accounthead'] or ''), str(r['accountname'] or '')))

        return Response(result)



class TrialbalanceApiViewJournal(ListAPIView):
    """
    GET /api/reports/trial-balance/?entity=1&startdate=2025-04-01&enddate=2025-04-30

    Trial Balance aggregated at AccountHead level with sign-based head selection:
      - DR (>=0): group under account.accounthead
      - CR (<0):  group under account.creditaccounthead
      - Fallback to JournalLine.accounthead where account is missing.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = TrialBalanceHeadRowSerializer

    # ---- safer ISO date parsing (trims & normalizes smart dashes) ----
    def _parse_ymd(self, s: str) -> date:
        if s is None:
            raise ValueError("empty")
        s = str(s).strip().replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        return date.fromisoformat(s)  # strict YYYY-MM-DD

    def get(self, request, *args, **kwargs):
        # ---- params ----
        entity_id = request.query_params.get("entity")
        start_s = request.query_params.get("startdate")
        end_s = request.query_params.get("enddate")

        if entity_id is None or start_s is None or end_s is None:
            return Response(
                {"detail": "Query params required: entity, startdate, enddate (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entity_id = str(entity_id).strip()
        start_s = str(start_s).strip()
        end_s = str(end_s).strip()

        # ---- date parsing ----
        try:
            startdate = self._parse_ymd(start_s)
            enddate = self._parse_ymd(end_s)
        except Exception:
            # echo back what we received to help spot hidden chars
            return Response(
                {"detail": "Dates must be YYYY-MM-DD.", "received": {"startdate": start_s, "enddate": end_s}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if startdate > enddate:
            # empty range → empty TB is valid
            return Response([], status=status.HTTP_200_OK)

        # ---- optional clamp to financial year (JournalLine.entrydate is a DateField) ----
        fy = (
            entityfinancialyear.objects
            .filter(
                entity_id=entity_id,
                finstartyear__date__lte=enddate,
                finendyear__date__gte=startdate,
            )
            .order_by("-finstartyear")
            .first()
        )
        if fy:
            startdate = max(startdate, fy.finstartyear.date())
            enddate = min(enddate, fy.finendyear.date())
            if startdate > enddate:
                return Response([], status=status.HTTP_200_OK)

        # =========================
        # 1) OPENING (< startdate) PER ACCOUNT
        # =========================
        opening_acct = (
            JournalLine.objects
            .filter(entity_id=entity_id, entrydate__lt=startdate)
            .values(
                "account_id",
                # account-based heads
                "account__accounthead_id",
                "account__accounthead__name",
                "account__creditaccounthead_id",
                "account__creditaccounthead__name",
                # fallback explicit head on the line (when account is null)
                "accounthead_id",
                "accounthead__name",
            )
            .annotate(
                opening=Sum(
                    Case(
                        When(drcr=True, then=F("amount")),      # Debit +
                        When(drcr=False, then=-F("amount")),     # Credit −
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                    default=V(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
        )

        # =========================
        # 2) PERIOD ([start,end]) PER ACCOUNT
        # =========================
        period_acct = (
            JournalLine.objects
            .filter(entity_id=entity_id, entrydate__gte=startdate, entrydate__lte=enddate)
            .values(
                "account_id",
                "account__accounthead_id",
                "account__accounthead__name",
                "account__creditaccounthead_id",
                "account__creditaccounthead__name",
                "accounthead_id",
                "accounthead__name",
            )
            .annotate(
                debit=Sum(
                    Case(
                        When(drcr=True, then=F("amount")),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                    default=V(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                credit=Sum(
                    Case(
                        When(drcr=False, then=F("amount")),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                    default=V(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
            )
        )

        # =========================
        # 3) MERGE PER-ACCOUNT
        # =========================
        per_acct = {}

        def _extract_heads(row):
            # Prefer account.* heads; fall back to explicit JournalLine.accounthead
            ah_id = row.get("account__accounthead_id") or row.get("accounthead_id")
            ah_nm = row.get("account__accounthead__name") or row.get("accounthead__name")
            ch_id = row.get("account__creditaccounthead_id") or ah_id
            ch_nm = row.get("account__creditaccounthead__name") or ah_nm
            return ah_id, ah_nm, ch_id, ch_nm

        for r in opening_acct:
            aid = r["account_id"]  # may be None if line had no account
            ah_id, ah_nm, ch_id, ch_nm = _extract_heads(r)
            if ah_id is None and ch_id is None:
                continue
            per_acct[aid] = dict(
                opening=r["opening"] or ZERO,
                debit=ZERO, credit=ZERO,
                ah_id=ah_id, ah_name=ah_nm or "",
                ch_id=ch_id, ch_name=ch_nm or "",
            )

        for r in period_acct:
            aid = r["account_id"]
            ah_id, ah_nm, ch_id, ch_nm = _extract_heads(r)
            if ah_id is None and ch_id is None:
                continue
            item = per_acct.setdefault(aid, dict(
                opening=ZERO, debit=ZERO, credit=ZERO,
                ah_id=ah_id, ah_name=ah_nm or "",
                ch_id=ch_id, ch_name=ch_nm or "",
            ))
            item["debit"] = (item["debit"] or ZERO) + (r["debit"] or ZERO)
            item["credit"] = (item["credit"] or ZERO) + (r["credit"] or ZERO)
            if not item["ah_name"] and ah_nm:
                item["ah_name"] = ah_nm
            if not item["ch_name"] and ch_nm:
                item["ch_name"] = ch_nm

        # If no data, short-circuit
        if not per_acct:
            return Response([], status=status.HTTP_200_OK)

        # =========================
        # 4) CHOOSE DISPLAY HEAD BY CLOSING SIGN & RE-AGGREGATE
        # =========================
        by_head = {}  # key = head_id
        for _, v in per_acct.items():
            closing = (v["opening"] or ZERO) + (v["debit"] or ZERO) - (v["credit"] or ZERO)
            if closing >= 0:
                hid, hname = v["ah_id"], v["ah_name"]
            else:
                hid, hname = v["ch_id"], v["ch_name"]

            if hid is None:
                continue

            agg = by_head.setdefault(hid, dict(
                accounthead=hid,
                accountheadname=hname or "",
                openingbalance=ZERO,
                debit=ZERO,
                credit=ZERO,
            ))
            agg["openingbalance"] += v["opening"] or ZERO
            agg["debit"] += v["debit"] or ZERO
            agg["credit"] += v["credit"] or ZERO

        # =========================
        # 5) FINALIZE & RETURN
        # =========================
        out = []
        for hid, v in by_head.items():
            closing = (v["openingbalance"] or ZERO) + (v["debit"] or ZERO) - (v["credit"] or ZERO)
            v["closingbalance"] = closing
            v["drcr"] = "CR" if closing < 0 else "DR"
            v["obdrcr"] = "CR" if (v["openingbalance"] or ZERO) < 0 else "DR"
            out.append(v)

        out.sort(key=lambda x: (x["accountheadname"] or "").lower())
        return Response(self.serializer_class(out, many=True).data, status=status.HTTP_200_OK)


# ---- numeric constants (avoid Decimal/Integer mixed types in aggregates) ----
ZERO = Decimal("0.00")
DEC0 = V(Decimal("0.00"), output_field=DecimalField(max_digits=18, decimal_places=2))


# ----------------------
# Helper functions
# ----------------------
def _parse_iso_date(s: str) -> date:
    """Strict YYYY-MM-DD with dash normalization and trimming."""
    if s is None:
        raise ValueError("empty")
    s = str(s).strip().replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    return date.fromisoformat(s)

def _bool(s: Optional[str], default: bool = False) -> bool:
    if s is None:
        return default
    return str(s).strip().lower() in {"1", "true", "yes", "y", "t"}

def _fy_covering_date(entity_id: int, d: date):
    """Return FY row covering date d (entityfinancialyear has finstartyear/finendyear, often DateTimeFields)."""
    return (
        entityfinancialyear.objects
        .filter(entity_id=entity_id, finstartyear__date__lte=d, finendyear__date__gte=d)
        .order_by("finstartyear")
        .first()
    )

def _fys_overlapping_range(entity_id: int, d1: date, d2: date) -> List[entityfinancialyear]:
    return list(
        entityfinancialyear.objects
        .filter(entity_id=entity_id)
        .filter(finstartyear__date__lte=d2, finendyear__date__gte=d1)
        .order_by("finstartyear")
    )

def _clip_to_fy(d1: date, d2: date, fy: entityfinancialyear) -> Tuple[date, date]:
    fy_start = fy.finstartyear.date()
    fy_end   = fy.finendyear.date()
    return max(d1, fy_start), min(d2, fy_end)

def _fy_name(fy: entityfinancialyear) -> str:
    s = fy.finstartyear.date()
    e = fy.finendyear.date()
    return f"FY {s.year}-{str(e.year)[-2:]}"

def _aggregate_opening(base_qs, before_date: date) -> Decimal:
    """Opening = Σ(Dr − Cr) strictly before 'before_date'."""
    agg = base_qs.filter(entrydate__lt=before_date).aggregate(
        dr=Coalesce(Sum("amount", filter=Q(drcr=True)), DEC0),
        cr=Coalesce(Sum("amount", filter=Q(drcr=False)), DEC0),
    )
    return Decimal(agg["dr"]) - Decimal(agg["cr"])

def _fetch_period_rows(base_qs, d1: date, d2: date):
    return list(
        base_qs.filter(entrydate__gte=d1, entrydate__lte=d2)
               .order_by("entrydate", "voucherno", "id")
               .values("entrydate", "voucherno", "desc", "drcr", "amount")
    )

def _build_lines_and_totals(rows, opening: Decimal):
    running = opening
    out = []
    tot_dr = ZERO
    tot_cr = ZERO

    for r in rows:
        amt = Decimal(r["amount"])
        if r["drcr"]:
            debit, credit = amt, ZERO
            running += amt
            tot_dr += amt
        else:
            debit, credit = ZERO, amt
            running -= amt
            tot_cr += amt

        out.append({
            "date": r["entrydate"],
            "voucherno": r["voucherno"] or "",
            "desc": r["desc"] or "",
            "debit": debit,
            "credit": credit,
            "balance": running,
        })

    closing = opening + tot_dr - tot_cr
    return out, tot_dr, tot_cr, closing

def _build_day_sections(lines, opening: Decimal, include_empty_days: bool, d1: date, d2: date):
    from collections import defaultdict as _dd
    buckets = _dd(list)
    for row in lines:
        buckets[row["date"]].append(row)

    if include_empty_days:
        days = []
        cur = d1
        while cur <= d2:
            days.append(cur)
            cur += timedelta(days=1)
    else:
        days = sorted(buckets.keys())

    sections = []
    carry = opening
    for d in days:
        items = buckets.get(d, [])
        day_dr = sum((i["debit"] for i in items), ZERO)
        day_cr = sum((i["credit"] for i in items), ZERO)
        day_open = carry
        day_close = day_open + day_dr - day_cr
        sections.append({
            "date": d,
            "day_opening": day_open,
            "items": items,
            "day_receipts": day_dr,
            "day_payments": day_cr,
            "day_closing_balance": day_close,
        })
        carry = day_close

    return sections


# ----------------------
# API View
# ----------------------
class CashBookAPIView(APIView):
    """
    Unified Cash Book API (single or multi-FY via `sections[]`)

    GET /api/reports/cashbook?entity=1&from=YYYY-MM-DD&to=YYYY-MM-DD
      Optional:
        - account_id=INT                (default: const.getcashid(entity))
        - voucherno=JV123               (exact)
        - txn=Sale,Receipt              (IN-list)
        - desc_contains=rent            (icontains)
        - min_amount=100.00
        - max_amount=5000
        - include_empty_days=true|false (default false)
        - posted_only=true|false        (default true; filters entry__is_posted=True)
        - strict_fy=true|false          (default false; if true and FY missing → 400)
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        # ---- required params ----
        entity_raw = request.query_params.get("entity")
        from_raw   = request.query_params.get("from")
        to_raw     = request.query_params.get("to")
        if entity_raw is None or from_raw is None or to_raw is None:
            return Response(
                {"detail": "Query params required: entity, from, to (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            entity_id = int(str(entity_raw).strip())
            from_dt   = _parse_iso_date(from_raw)
            to_dt     = _parse_iso_date(to_raw)
        except Exception:
            return Response(
                {"detail": "Dates must be YYYY-MM-DD.",
                 "received": {"from": from_raw, "to": to_raw}},
                status=status.HTTP_400_BAD_REQUEST
            )
        if to_dt < from_dt:
            return Response({"detail": "'to' must be >= 'from'."}, status=400)

        # ---- resolve account (default: cash for entity) ----
        account_pk: Optional[int] = None
        account_q = request.query_params.get("account_id")
        if account_q:
            try:
                account_pk = int(account_q)
            except ValueError:
                return Response({"detail": "Invalid account_id."}, status=400)
        else:
            try:
                const = stocktransconstant()
                acct = const.getcashid(entity_id)  # may return model or int
                account_pk = int(acct.pk) if hasattr(acct, "pk") else int(acct)
            except Exception as ex:
                return Response({"detail": f"Unable to resolve cash account for entity={entity_id}: {ex}"}, status=400)

        include_empty_days = _bool(request.query_params.get("include_empty_days"), default=False)
        posted_only        = _bool(request.query_params.get("posted_only"), default=True)
        strict_fy          = _bool(request.query_params.get("strict_fy"), default=False)

        # ---- base queryset ----
        base = JournalLine.objects.filter(entity_id=entity_id, account_id=account_pk)
        # if posted_only:
        #     base = base.filter(entry__is_posted=True)  # remove if your header lacks this flag

        # ---- optional filters ----
        voucherno = request.query_params.get("voucherno")
        if voucherno:
            base = base.filter(voucherno=voucherno)

        txn_raw = request.query_params.get("txn")
        if txn_raw:
            txns = [t.strip() for t in txn_raw.split(",") if t.strip()]
            if txns:
                base = base.filter(transactiontype__in=txns)

        desc_contains = request.query_params.get("desc_contains")
        if desc_contains:
            base = base.filter(desc__icontains=desc_contains)

        min_amount = request.query_params.get("min_amount")
        if min_amount:
            try:
                base = base.filter(amount__gte=Decimal(min_amount))
            except (InvalidOperation, ValueError):
                return Response({"detail": "Invalid min_amount."}, status=400)

        max_amount = request.query_params.get("max_amount")
        if max_amount:
            try:
                base = base.filter(amount__lte=Decimal(max_amount))
            except (InvalidOperation, ValueError):
                return Response({"detail": "Invalid max_amount."}, status=400)

        # ---- financial year handling (soft fallback) ----
        fy_from = _fy_covering_date(entity_id, from_dt)
        fy_to   = _fy_covering_date(entity_id, to_dt)

        # If FY rows missing → fallback to a single non-FY section unless strict_fy=true
        if not fy_from or not fy_to:
            if strict_fy:
                return Response(
                    {"detail": "Requested dates are not fully covered by financial year setup.",
                     "hint": "Add FY rows for these dates or call without strict_fy."},
                    status=400
                )

            grand_opening = _aggregate_opening(base, from_dt)
            rows = _fetch_period_rows(base, from_dt, to_dt)
            lines, tot_dr, tot_cr, closing = _build_lines_and_totals(rows, grand_opening)
            day_sections = _build_day_sections(lines, grand_opening, include_empty_days, from_dt, to_dt)

            payload = {
                "entity": entity_id,
                "account_id": account_pk,
                "from_date": from_dt,
                "to_date": to_dt,
                "spans_multiple_fy": False,
                "grand_opening": grand_opening,
                "grand_total_receipts": tot_dr,
                "grand_total_payments": tot_cr,
                "grand_closing": closing,
                "sections": [
                    {
                        # FY metadata omitted when FY rows are absent
                        "from_date": from_dt,
                        "to_date": to_dt,
                        "opening_balance": grand_opening,
                        "total_receipts": tot_dr,
                        "total_payments": tot_cr,
                        "closing_balance": closing,
                        "lines": lines,
                        "day_sections": day_sections,
                    }
                ],
            }
            return Response(CashbookUnifiedSerializer(payload).data, status=200)

        # ---- same-FY fast path ----
        grand_opening = _aggregate_opening(base, from_dt)

        if fy_from.id == fy_to.id:
            rows = _fetch_period_rows(base, from_dt, to_dt)
            lines, tot_dr, tot_cr, closing = _build_lines_and_totals(rows, grand_opening)
            day_sections = _build_day_sections(lines, grand_opening, include_empty_days, from_dt, to_dt)

            payload = {
                "entity": entity_id,
                "account_id": account_pk,
                "from_date": from_dt,
                "to_date": to_dt,
                "spans_multiple_fy": False,
                "grand_opening": grand_opening,
                "grand_total_receipts": tot_dr,
                "grand_total_payments": tot_cr,
                "grand_closing": closing,
                "sections": [
                    {
                        "fy_name": _fy_name(fy_from),
                        "fy_start": fy_from.finstartyear.date(),
                        "fy_end": fy_from.finendyear.date(),
                        "from_date": from_dt,
                        "to_date": to_dt,
                        "opening_balance": grand_opening,
                        "total_receipts": tot_dr,
                        "total_payments": tot_cr,
                        "closing_balance": closing,
                        "lines": lines,
                        "day_sections": day_sections,
                    }
                ],
            }
            return Response(CashbookUnifiedSerializer(payload).data, status=200)

        # ---- multi-FY path ----
        fys = _fys_overlapping_range(entity_id, from_dt, to_dt)
        if not fys:
            return Response({"detail": "No financial year overlaps the requested range."}, status=400)

        sections = []
        rolling_opening = grand_opening
        grand_dr = ZERO
        grand_cr = ZERO
        last_closing = rolling_opening

        for fy in fys:
            sub_from, sub_to = _clip_to_fy(from_dt, to_dt, fy)
            rows = _fetch_period_rows(base, sub_from, sub_to)
            lines, tot_dr, tot_cr, closing = _build_lines_and_totals(rows, rolling_opening)
            day_sections = _build_day_sections(lines, rolling_opening, include_empty_days, sub_from, sub_to)

            sections.append({
                "fy_name": _fy_name(fy),
                "fy_start": fy.finstartyear.date(),
                "fy_end": fy.finendyear.date(),
                "from_date": sub_from,
                "to_date": sub_to,
                "opening_balance": rolling_opening,
                "total_receipts": tot_dr,
                "total_payments": tot_cr,
                "closing_balance": closing,
                "lines": lines,
                "day_sections": day_sections,
            })

            grand_dr += tot_dr
            grand_cr += tot_cr
            rolling_opening = closing
            last_closing = closing

        multi_payload = {
            "entity": entity_id,
            "account_id": account_pk,
            "from_date": from_dt,
            "to_date": to_dt,
            "spans_multiple_fy": True,
            "grand_opening": grand_opening,
            "grand_total_receipts": grand_dr,
            "grand_total_payments": grand_cr,
            "grand_closing": last_closing,
            "sections": sections,
        }
        return Response(CashbookUnifiedSerializer(multi_payload).data, status=200)



class TrialbalanceApiViewJournalByAccount(ListAPIView):
    """
    GET /api/reports/trial-balance/accounts/?entity=1&accounthead=10&startdate=2025-04-01&enddate=2025-04-30

    Emits Trial Balance rows *per account* whose chosen display head equals ?accounthead.
    Head rule (per account): closing >= 0 → account.accounthead, else → account.creditaccounthead.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = TrialBalanceAccountRowSerializer

    def _parse_ymd(self, s: str) -> date:
        s = str(s or "").strip().replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        return date.fromisoformat(s)  # strict YYYY-MM-DD

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get("entity")
        head_id_s = request.query_params.get("accounthead")
        start_s   = request.query_params.get("startdate")
        end_s     = request.query_params.get("enddate")

        if not (entity_id and head_id_s and start_s and end_s):
            return Response({"detail": "Required: entity, accounthead, startdate, enddate (YYYY-MM-DD)"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            startdate = self._parse_ymd(start_s)
            enddate   = self._parse_ymd(end_s)
            head_id   = int(head_id_s)
        except Exception:
            return Response(
                {"detail": "Invalid inputs.", "received": {"accounthead": head_id_s, "startdate": start_s, "enddate": end_s}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if startdate > enddate:
            return Response([], status=status.HTTP_200_OK)

        # Clamp to FY if present
        fy = (
            entityfinancialyear.objects
            .filter(entity_id=entity_id,
                    finstartyear__date__lte=enddate,
                    finendyear__date__gte=startdate)
            .order_by("-finstartyear")
            .first()
        )
        if fy:
            startdate = max(startdate, fy.finstartyear.date())
            enddate   = min(enddate, fy.finendyear.date())
            if startdate > enddate:
                return Response([], status=status.HTTP_200_OK)

        # ---- Opening (< startdate) per account ----
        opening_qs = (
            JournalLine.objects
            .filter(entity_id=entity_id, entrydate__lt=startdate)
            .exclude(account_id__isnull=True)
            .values(
                "account_id", "account__accountname",
                "account__accounthead_id", "account__accounthead__name",
                "account__creditaccounthead_id", "account__creditaccounthead__name",
            )
            .annotate(
                opening=Sum(
                    Case(
                        When(drcr=True, then=F("amount")),
                        When(drcr=False, then=-F("amount")),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                    default=V(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
        )

        # ---- Period ([start,end]) per account ----
        period_qs = (
            JournalLine.objects
            .filter(entity_id=entity_id, entrydate__gte=startdate, entrydate__lte=enddate)
            .exclude(account_id__isnull=True)
            .values(
                "account_id", "account__accountname",
                "account__accounthead_id", "account__accounthead__name",
                "account__creditaccounthead_id", "account__creditaccounthead__name",
            )
            .annotate(
                debit=Sum(
                    Case(When(drcr=True, then=F("amount")), default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2)),
                    default=V(0), output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                credit=Sum(
                    Case(When(drcr=False, then=F("amount")), default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2)),
                    default=V(0), output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
            )
        )

        # ---- Merge per account ----
        per_account = {}
        for r in opening_qs:
            aid = r["account_id"]
            per_account[aid] = dict(
                account=aid,
                accountname=r["account__accountname"] or "",
                opening=r["opening"] or ZERO,
                debit=ZERO, credit=ZERO,
                ah_id=r["account__accounthead_id"],
                ah_name=r["account__accounthead__name"] or "",
                ch_id=r["account__creditaccounthead_id"],
                ch_name=r["account__creditaccounthead__name"] or "",
            )

        for r in period_qs:
            aid = r["account_id"]
            item = per_account.setdefault(aid, dict(
                account=aid,
                accountname=r["account__accountname"] or "",
                opening=ZERO, debit=ZERO, credit=ZERO,
                ah_id=r["account__accounthead_id"],
                ah_name=r["account__accounthead__name"] or "",
                ch_id=r["account__creditaccounthead_id"],
                ch_name=r["account__creditaccounthead__name"] or "",
            ))
            item["debit"]  = (item["debit"]  or ZERO) + (r["debit"]  or ZERO)
            item["credit"] = (item["credit"] or ZERO) + (r["credit"] or ZERO)

        if not per_account:
            return Response([], status=status.HTTP_200_OK)

        # ---- Choose head by sign; keep only requested head ----
        rows = []
        for v in per_account.values():
            closing = (v["opening"] or ZERO) + (v["debit"] or ZERO) - (v["credit"] or ZERO)
            disp_head_id, disp_head_name = (
                (v["ah_id"], v["ah_name"]) if closing >= 0 else (v["ch_id"], v["ch_name"])
            )
            if disp_head_id is None or disp_head_id != head_id:
                continue

            rows.append(dict(
                account=v["account"],
                accountname=v["accountname"],
                accounthead=head_id,
                accountheadname=disp_head_name or "",
                openingbalance=v["opening"] or ZERO,
                debit=v["debit"] or ZERO,
                credit=v["credit"] or ZERO,
                closingbalance=closing,
                drcr=("CR" if closing < 0 else "DR"),
                obdrcr=("CR" if (v["opening"] or ZERO) < 0 else "DR"),
            ))

        rows.sort(key=lambda x: (x["accountname"] or "").lower())

        # Serialize (fast — pure dicts, no DB hits)
        data = self.serializer_class(rows, many=True).data
        return Response(data, status=status.HTTP_200_OK)

DEC = DecimalField(max_digits=18, decimal_places=2)               # reuse this
VZ  = lambda: V(ZERO, output_field=DEC)                           # Decimal zero Value()
class TrialbalanceApiViewJournalByAccountLedger(ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = TrialBalanceAccountLedgerRowSerializer

    def _parse_ymd(self, s: str) -> date:
        s = str(s or "").strip().replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        return date.fromisoformat(s)

    def get(self, request, *args, **kwargs):
        entity_id  = request.query_params.get("entity")
        account_id = request.query_params.get("account")
        start_s    = request.query_params.get("startdate")
        end_s      = request.query_params.get("enddate")

        if not (entity_id and account_id and start_s and end_s):
            return Response({"detail": "Required: entity, account, startdate, enddate (YYYY-MM-DD)"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            startdate = self._parse_ymd(start_s)
            enddate   = self._parse_ymd(end_s)
            account_id = int(account_id)
        except Exception:
            return Response({"detail": "Invalid inputs.", "received": {
                "entity": entity_id, "account": request.query_params.get("account"),
                "startdate": start_s, "enddate": end_s}},
                status=status.HTTP_400_BAD_REQUEST)

        if startdate > enddate:
            return Response([], status=status.HTTP_200_OK)

        # ---- Clamp to FY if present ----
        fy = (
            entityfinancialyear.objects
            .filter(entity_id=entity_id,
                    finstartyear__date__lte=enddate,
                    finendyear__date__gte=startdate)
            .order_by("-finstartyear")
            .first()
        )
        if fy:
            startdate = max(startdate, fy.finstartyear.date())
            enddate   = min(enddate, fy.finendyear.date())
            if startdate > enddate:
                return Response([], status=status.HTTP_200_OK)

        # ---- 1) Opening balance (< startdate) ----
        opening_sum = (
            JournalLine.objects
            .filter(entity_id=entity_id, account_id=account_id, entrydate__lt=startdate)
            .aggregate(opening=Coalesce(
                Sum(
                    Case(
                        When(drcr=True,  then=F("amount")),
                        When(drcr=False, then=-F("amount")),
                        default=VZ(),
                        output_field=DEC,
                    ),
                    output_field=DEC,
                ),
                VZ(),
                output_field=DEC,
            ))
        )["opening"] or ZERO

        # account name
        name_row = (
            JournalLine.objects
            .filter(entity_id=entity_id, account_id=account_id)
            .values("account__accountname")
            .order_by("entrydate", "id")
            .first()
        )
        accountname = (name_row or {}).get("account__accountname", "") or ""

        opening_row = None
        if opening_sum is not None:
            obal = opening_sum
            opening_row = dict(
                account=account_id,
                accountname=accountname,
                sortdate=startdate,                             # Date object → ISO in JSON
                entrydate=startdate.strftime("%d-%m-%Y"),       # Display string
                narration="Opening Balance",
                transactiontype="OPENING",
                transactionid=0,                                # opening sentinel
                debit=(obal if obal > 0 else ZERO),
                credit=(obal if obal < 0 else ZERO),
                runningbalance=obal,
            )

        # ---- 2) Period lines (detail-level) ----
        # Project fields directly present on JournalLine:
        values_list = [
            "id", "account_id", "account__accountname", "entrydate",
            "drcr", "amount",
            "transactiontype", "transactionid", "voucherno",   # <-- direct fields
        ]
        # Optional narration-ish fields
        for opt in ("desc", "narration", "notes"):
            try:
                JournalLine._meta.get_field(opt)
                values_list.append(opt)
            except Exception:
                pass

        lines_qs = (
            JournalLine.objects
            .filter(entity_id=entity_id, account_id=account_id,
                    entrydate__gte=startdate, entrydate__lte=enddate)
            .values(*values_list)
            .order_by("entrydate", "id")
        )

        def pick_first(row, candidates):
            for c in candidates:
                if c in row and row[c] not in (None, "", " "):
                    return str(row[c])
            return ""

        rows = []
        running = opening_sum if opening_sum is not None else ZERO
        if opening_row:
            rows.append(opening_row)

        for r in lines_qs:
            amt = r["amount"] or ZERO
            is_dr = bool(r["drcr"])
            debit  = amt if is_dr else ZERO
            credit = amt if not is_dr else ZERO
            running = running + debit - credit

            # narration (desc/narration/notes if present; model at least has desc)
            narration = pick_first(r, ["desc", "narration", "notes"])

            # transactiontype from model (fallback to UNKNOWN if somehow empty)
            txn_type = (r.get("transactiontype") or "").strip() or "UNKNOWN"

            # transactionid from model (header id); if null/blank, fallback to line id
            jl_txn_id = r.get("transactionid")
            try:
                txn_id = int(jl_txn_id) if jl_txn_id is not None and str(jl_txn_id).strip() != "" else int(r["id"])
            except Exception:
                txn_id = int(r["id"])

            rows.append(dict(
                account=r["account_id"],
                accountname=r.get("account__accountname") or accountname,
                sortdate=r["entrydate"],                        # date object
                entrydate=r["entrydate"].strftime("%d-%m-%Y"),  # display string
                narration=narration or "",
                transactiontype=txn_type,
                transactionid=txn_id,                           # <-- JournalLine.transactionid (header id)
                debit=debit,
                credit=credit,
                runningbalance=running,
            ))

        return Response(self.serializer_class(rows, many=True).data, status=status.HTTP_200_OK)

DEC18_2 = DecimalField(max_digits=18, decimal_places=2)
ZERO_D = Decimal("0.00")
ZERO = V(ZERO_D, output_field=DEC18_2)

class LedgerSummaryJournalline(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    ORDER_MAP = {
        "accountname": "account__accountname",
        "-accountname": "-account__accountname",
        "head_name": "account__accounthead__name",
        "-head_name": "-account__accounthead__name",
        "opening": "openingbalance",
        "-opening": "-openingbalance",
        "debit": "debit",
        "-debit": "-debit",
        "credit": "credit",
        "-credit": "-credit",
        "period_net": "period_net",
        "-period_net": "-period_net",
        "abs_movement": "abs_movement",
        "-abs_movement": "-abs_movement",
        "balancetotal": "balancetotal",
        "-balancetotal": "-balancetotal",
    }

    def post(self, request, *_args, **_kwargs):
        # 1) Validate input
        in_ser = LedgerSummaryRequestSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        p = in_ser.validated_data

        entity_id = p["entity"]
        startdate = p["startdate"]
        enddate = p["enddate"]
        group_by = p["group_by"]

        # 2) Base queryset (up to enddate)
        qs = JournalLine.objects.filter(
            entity_id=entity_id,
            account__isnull=False,
            entrydate__lte=enddate,
        )

        # 3) Optional filters (apply to qs)
        if p.get("txn_in"):
            include_txn = [x.strip() for x in str(p["txn_in"]).split(",") if x.strip()]
            qs = qs.filter(transactiontype__in=include_txn)

        if p.get("voucherno"):
            qs = qs.filter(voucherno=str(p["voucherno"]))
        if p.get("vno_contains"):
            qs = qs.filter(voucherno__icontains=str(p["vno_contains"]))
        if p.get("desc_contains"):
            qs = qs.filter(desc__icontains=str(p["desc_contains"]))

        if p.get("accounthead"):
            ah_ids = [int(x) for x in str(p["accounthead"]).split(",") if x.strip()]
            qs = qs.filter(account__accounthead_id__in=ah_ids)
        else:
            ah_ids = None  # for totals reuse below

        if p.get("account"):
            acc_ids = [int(x) for x in str(p["account"]).split(",") if x.strip()]
            qs = qs.filter(account_id__in=acc_ids)
        else:
            acc_ids = None  # for totals reuse below

        # 4) Aggregations (one grouped query)
        period_f = Q(entrydate__gte=startdate, entrydate__lte=enddate)

        opening_expr = Coalesce(
            Sum(
                Case(
                    When(drcr=True, then=F("amount")),
                    When(drcr=False, then=-F("amount")),
                    default=V(0),
                    output_field=DEC18_2,
                ),
                filter=Q(entrydate__lt=startdate),
                output_field=DEC18_2,
            ),
            ZERO,
        )
        debit_expr = Coalesce(
            Sum(F("amount"), filter=period_f & Q(drcr=True), output_field=DEC18_2),
            ZERO,
        )
        credit_expr = Coalesce(
            Sum(F("amount"), filter=period_f & Q(drcr=False), output_field=DEC18_2),
            ZERO,
        )
        period_net_expr = ExpressionWrapper(F("debit") - F("credit"), output_field=DEC18_2)
        abs_mov_expr = ExpressionWrapper(F("debit") + F("credit"), output_field=DEC18_2)
        closing_expr = ExpressionWrapper(F("openingbalance") + F("debit") - F("credit"), output_field=DEC18_2)

        # Group fields
        if group_by == "head":
            group_vals = ["account__accounthead_id", "account__accounthead__name"]
        else:
            group_vals = [
                "account_id",
                "account__accountname",
                "account__accounthead_id",
                "account__accounthead__name",
            ]

        qs = (
            qs.values(*group_vals)
              .annotate(
                  openingbalance=opening_expr,
                  debit=debit_expr,
                  credit=credit_expr,
              )
              .annotate(
                  period_net=period_net_expr,
                  abs_movement=abs_mov_expr,
                  balancetotal=closing_expr,
                  txn_count=Count("id", filter=period_f),
                  last_txn_date=Max("entrydate", filter=period_f),
              )
              .annotate(
                  drcr=Case(When(balancetotal__lt=0, then=V("CR")), default=V("DR")),
                  obdrcr=Case(When(openingbalance__lt=0, then=V("CR")), default=V("DR")),
              )
        )

        # 5) Summary-focused filters
        sign = p.get("sign", "ALL")
        if sign == "DR":
            qs = qs.filter(balancetotal__gt=0)
        elif sign == "CR":
            qs = qs.filter(balancetotal__lt=0)

        if not p.get("include_zero", False):
            qs = qs.exclude(balancetotal=ZERO_D)

        if p.get("min_activity") is not None:
            qs = qs.filter(abs_movement__gte=p["min_activity"])

        if p.get("amount_min") is not None:
            qs = qs.filter(balancetotal__gte=p["amount_min"])
        if p.get("amount_max") is not None:
            qs = qs.filter(balancetotal__lte=p["amount_max"])

        # 6) Ordering (safe per grouping)
        order_key = (p.get("order_by") or "").strip() or ("head_name" if group_by == "head" else "accountname")
        order_field = self.ORDER_MAP.get(order_key)
        if group_by == "head" and order_field in ("account__accountname", "-account__accountname"):
            order_field = "account__accounthead__name"
        if not order_field:
            order_field = "account__accounthead__name" if group_by == "head" else "account__accountname"
        qs = qs.order_by(order_field)

        # 7) GRAND TOTALS — recompute from JournalLine with same filters (no alias aggregation)
        totals_qs = JournalLine.objects.filter(
            entity_id=entity_id,
            account__isnull=False,
            entrydate__lte=enddate,
        )
        if p.get("txn_in"):
            totals_qs = totals_qs.filter(transactiontype__in=include_txn)
        if p.get("voucherno"):
            totals_qs = totals_qs.filter(voucherno=str(p["voucherno"]))
        if p.get("vno_contains"):
            totals_qs = totals_qs.filter(voucherno__icontains=str(p["vno_contains"]))
        if p.get("desc_contains"):
            totals_qs = totals_qs.filter(desc__icontains=str(p["desc_contains"]))
        if ah_ids:
            totals_qs = totals_qs.filter(account__accounthead_id__in=ah_ids)
        if acc_ids:
            totals_qs = totals_qs.filter(account_id__in=acc_ids)

        opening_total_expr = Coalesce(
            Sum(
                Case(
                    When(drcr=True, then=F("amount")),
                    When(drcr=False, then=-F("amount")),
                    default=V(0),
                    output_field=DEC18_2,
                ),
                filter=Q(entrydate__lt=startdate),
                output_field=DEC18_2,
            ),
            ZERO,
        )
        debit_total_expr = Coalesce(
            Sum(F("amount"), filter=period_f & Q(drcr=True), output_field=DEC18_2),
            ZERO,
        )
        credit_total_expr = Coalesce(
            Sum(F("amount"), filter=period_f & Q(drcr=False), output_field=DEC18_2),
            ZERO,
        )

        totals_raw = totals_qs.aggregate(
            opening=opening_total_expr,
            debit=debit_total_expr,
            credit=credit_total_expr,
        )
        opening_t = totals_raw["opening"] or ZERO_D
        debit_t = totals_raw["debit"] or ZERO_D
        credit_t = totals_raw["credit"] or ZERO_D
        totals = {
            "opening": opening_t,
            "debit": debit_t,
            "credit": credit_t,
            "closing": opening_t + debit_t - credit_t,
        }

        # 8) Pagination
        paginator = SimpleNumberPagination()
        paginator.page_size = p["pagesize"]
        page = paginator.paginate_queryset(list(qs), request)

        # 9) Shape rows according to group_by and serialize
        rows = []
        for r in page:
            row = dict(
                openingbalance=r["openingbalance"],
                debit=r["debit"],
                credit=r["credit"],
                period_net=r["period_net"],
                abs_movement=r["abs_movement"],
                balancetotal=r["balancetotal"],
                drcr=r["drcr"],
                obdrcr=r["obdrcr"],
                txn_count=r["txn_count"],
                last_txn_date=r["last_txn_date"],
            )
            if group_by in ("head", "head_account"):
                row["head_id"] = r.get("account__accounthead_id")
                row["head_name"] = r.get("account__accounthead__name") or ""
            if group_by in ("account", "head_account"):
                row["account"] = r.get("account_id")
                row["accountname"] = r.get("account__accountname") or ""
                row["links"] = {
                    "detail": f"/api/reports/ledger-detail?entity={entity_id}&account={r.get('account_id')}&from={startdate}&to={enddate}"
                }
            rows.append(row)

        out_ser = LedgerSummaryRowSerializer(rows, many=True)

        # 10) Meta echo & paginated response
        meta_echo = {
            "entity": entity_id,
            "from": str(startdate),
            "to": str(enddate),
            "group_by": group_by,
            "order_by": order_key,
        }
        return paginator.get_paginated_response(out_ser.data, totals=totals, meta_echo=meta_echo)
    



