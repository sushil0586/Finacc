from django.shortcuts import render

# Create your views here.

from itertools import product
from django.http import request,JsonResponse
from django.shortcuts import render
import json

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView,GenericAPIView,RetrieveAPIView,UpdateAPIView
from invoice.models import StockTransactions,closingstock,salesOrderdetails,entry,SalesOderHeader,PurchaseReturn,purchaseorder,salereturn
# from invoice.serializers import SalesOderHeaderSerializer,salesOrderdetailsSerializer,purchaseorderSerializer,PurchaseOrderDetailsSerializer,POSerializer,SOSerializer,journalSerializer,SRSerializer,salesreturnSerializer,salesreturnDetailsSerializer,JournalVSerializer,PurchasereturnSerializer,\
# purchasereturndetailsSerializer,PRSerializer,TrialbalanceSerializer,TrialbalanceSerializerbyaccounthead,TrialbalanceSerializerbyaccount,accountheadserializer,accountHead,accountserializer,accounthserializer, stocktranserilaizer,cashserializer,journalmainSerializer,stockdetailsSerializer,stockmainSerializer,\
# PRSerializer,SRSerializer,stockVSerializer,stockserializer,Purchasebyaccountserializer,Salebyaccountserializer,entitySerializer1,cbserializer,ledgerserializer,ledgersummaryserializer,stockledgersummaryserializer,stockledgerbookserializer,balancesheetserializer,gstr1b2bserializer,gstr1hsnserializer,\
# purchasetaxtypeserializer,tdsmainSerializer,tdsVSerializer,tdstypeSerializer,tdsmaincancelSerializer,salesordercancelSerializer,purchaseordercancelSerializer,purchasereturncancelSerializer,salesreturncancelSerializer,journalcancelSerializer,stockcancelSerializer,SalesOderHeaderpdfSerializer,productionmainSerializer,productionVSerializer,productioncancelSerializer,tdsreturnSerializer,gstorderservicesSerializer,SSSerializer,gstorderservicecancelSerializer,jobworkchallancancelSerializer,JwvoucherSerializer,jobworkchallanSerializer,debitcreditnoteSerializer,dcnoSerializer,debitcreditcancelSerializer,closingstockSerializer

from reports.serializers import closingstockSerializer,stockledgerbookserializer,stockledgersummaryserializer,ledgerserializer,cbserializer,stockserializer,cashserializer
from rest_framework import permissions,status
from django_filters.rest_framework import DjangoFilterBackend
from django.db import DatabaseError, transaction
from rest_framework.response import Response
from django.db.models import Sum,OuterRef,Subquery,F
from django.db.models import Prefetch
from financial.models import account,accountHead
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




class closingstockBalance(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1,stockttype__in = ['P','O','R'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate)).values('stock','stockttype','quantity','entrydatetime','stock__id')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','stockttype','quantity','entrydatetime','stock__id')
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
        dfR = dfR.drop(['_merge','stockttype','entrydatetime'],axis=1) 

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
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

        def FiFo(dfg):
            if dfg[dfg['CS'] < 0]['quantity'].count():
                subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
                dfg['quantity'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['quantity'])
                dfg = dfg[dfg['quantity'] > 0]
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg


        puchases = StockTransactions.objects.filter(Q(isactive =1,stockttype__in = ['P','O','R'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate)).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
        sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = entity1,entrydatetime__lte = enddate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
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
        dfR = dfR.drop(['rate','_merge','stockttype','entrydatetime'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        dfR.rename(columns = {'stock__id':'stockid', 'stock':'stockname'}, inplace = True)

       


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
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg
        

        puchases = StockTransactions.objects.filter(isactive =1,stockttype__in = ['P','R','O'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.enddate).values('stock','stockttype','quantity','entrydatetime','stock__id','rate')
        sales =    StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.enddate).values('stock','stockttype','quantity','entrydatetime','stock__id','rate')

      #  puchases = StockTransactions.objects.filter(Q(isactive =1),Q(stockttype__in = ['P','OS','R']),Q(accounttype = 'DD'),Q(entity = self.entityid),Q(entrydatetime__lt  = self.enddate)).values('stock','stockttype','quantity','entrydatetime','stock__id')
       # sales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lt  = self.enddate).values('stock','stockttype','quantity','entrydatetime','stock__id')

        
        inventory = puchases.union(sales).order_by('entrydatetime')
        closingprice = closingstock.objects.filter(entity = self.entityid).values('stock__id','closingrate')
        #idf1 = read_frame(puchases)
       # print(idf1)
        idf = read_frame(inventory)
        cdf = read_frame(closingprice)

        print(idf)

        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)

        print(idf)
       # idf = read_frame(inventory)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R','O']),'P','S')
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','R','O']), idf['quantity'],-1 * (idf['quantity']))
        idf['quantity'] = idf['quantity'].astype(float).fillna(0)
        idf['CS'] = idf.groupby(['stock__id','stockttype'])['quantity'].cumsum()
        dfR = idf.groupby(['stock__id'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)

        print(dfR)
        return dfR
       

    def getinventorydetails_1(self,dfR_1):

        dfR_1['closingrate'] = np.where(dfR_1['closingrate'] > 0,dfR_1['closingrate'],dfR_1['rate'])
        dfR_1['balance'] = dfR_1['quantity'].astype(float) * -1 * dfR_1['closingrate'].astype(float)
        dfR_1 = dfR_1.drop(['stockttype','entrydatetime','_merge','rate'],axis=1) 
        dfR_1.rename(columns = {'stock__id':'account__id', 'stock':'account__accountname'}, inplace = True)
        dfR_1['accounthead__name'] = 'Closing Stock'
        account_id = accountHead.objects.get(code = 200,entity = self.entityid).id
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
        

        opuchases = StockTransactions.objects.filter(isactive =1,stockttype__in = ['P','R','O'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.startdate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.startdate).values('stock','rate','stockttype','quantity','entrydatetime','stock__id')
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
        odfi['account__accounthead'] = 9000
        return odfi

    def openinginventorydetails_2(self,odfR):
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['rate'].astype(float)
        odfR = odfR.drop(['stock','stockttype','entrydatetime','closingrate','_merge'],axis=1) 
        odfR.rename(columns = {'stock__id':'account__id', 'stock__productname':'account__accountname'}, inplace = True)
        odfR['account__accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = 9000
        return odfR


    def getprofitandloss(self):
        pl1 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gte = 0)
        pl2 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 2).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lte = 0)

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
                if (len(dfg) > 0):
                    dfg['quantity'].iloc[0] = dfg['CS'].iloc[0] + subT
            return dfg
        
        opuchases = StockTransactions.objects.filter(isactive =1,stockttype__in = ['P','O','R'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.startdate).values('stock','stockttype','quantity','entrydatetime','stock__id','rate')
        osales = StockTransactions.objects.filter(isactive =1,stockttype__in = ['S','I'],accounttype = 'DD',entity = self.entityid,entrydatetime__lte = self.startdate).values('stock','stockttype','quantity','entrydatetime','stock__id','rate')

        closingprice = closingstock.objects.filter(entity = self.entityid).values('stock__id','closingrate')
        oinventory = opuchases.union(osales).order_by('entrydatetime')

        cdf = read_frame(closingprice)
        idf = read_frame(oinventory)
        idf = pd.merge(idf,cdf,on='stock__id',how='outer',indicator=True)
        idf['stockttype'] = np.where(idf['stockttype'].isin(['P','R','O']),'P','S')
       # idf['stockttype'] = np.where(idf['stockttype'] == 'I','S',idf['stockttype'])
        idf['quantity'] = np.where(idf['stockttype'].isin(['P','O','R']), idf['quantity'],-1 * (idf['quantity']))
        #print(idf)
        idf['quantity'] = idf['quantity'].astype(float)
        idf['CS'] = idf.groupby(['stock','stockttype'])['quantity'].cumsum()
        #print(idf)
        odfR = idf.groupby(['stock'], as_index=False).apply(FiFo).drop(['CS'], axis=1).reset_index(drop=True)
       #print(dfR)
        odfR['closingrate'] = np.where(odfR['rate'] > 0,odfR['rate'],odfR['closingrate'])
        odfR['balance'] = odfR['quantity'].astype(float)  * odfR['closingrate'].astype(float)
        odfR = odfR.drop(['stockttype','entrydatetime','_merge','rate'],axis=1) 

        #dfi = dfi.drop(['account__id','transactiontype','entrydatetime','account__accountname'],axis=1) 

        odfR.rename(columns = {'stock__id':'account__id', 'stock':'account__accountname'}, inplace = True)
        odfR['accounthead__name'] = 'Opening Stock'
        odfR['account__accounthead'] = 9000

        return odfR
    

    def gettradingdetails(self):
        stk =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'PC').values('accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gte = 0)
        stk2 =StockTransactions.objects.filter(isactive = 1,entity = self.entityid,entrydatetime__range=(self.startdate, self.enddate),account__accounthead__detailsingroup = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'PC').values('accounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__lte = 0)

        plunion = stk.union(stk2)

        pldf = read_frame(plunion)

        return pldf
    

    def getgrossprofit(self,odfR,df, dfR):

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
       # pass

        return df
    
    def getgppandl(self,odfR,df, dfR,pldf):
        frames = [odfR,df, dfR]

        df = pd.concat(frames)

        print(df)

        df['balance'] = df['balance'].astype(float)
        print(df)

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

        return pldf

    


class balancestatement(ListAPIView):

    #serializer_class = balancesheetserializer
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
        dfi = dfRFinal


        # odfR = stk.openinginventorydetails()
        # odfi = stk.openinginventorydetails_1(odfi = odfR)
        # odfR = stk.openinginventorydetails_2(odfR= odfR)

        odfR = stk.getopeningstockdetails()


        print('------Opening ----------')


        print(odfR)

        odfi = odfR

                
        
        df = stk.getstockdetails()

        frames = [odfR,df, dfRFinal]

        df = pd.concat(frames)

      

        df['balance'] = df['balance'].astype(float)


        pldf = stk.getprofitandloss()


        print(pldf)

        

        


        if df['balance'].sum() < 0:
            pldf.loc[len(pldf.index)] = ['Gross Profit', -1, -1, 'Gross Profit',df['balance'].sum()]
        else:
            pldf.loc[len(pldf.index)] = ['Gross Loss', -1, -1, 'Gross Loss',df['balance'].sum()]


        print(pldf)


        bs1 =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__lte = enddate).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('accounthead__name','account__accounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__gt = 0)
        bs2 =StockTransactions.objects.filter(isactive = 1,entity = entity1,entrydatetime__lte = enddate).filter(account__accounthead__detailsingroup = 3).exclude(accounttype = 'MD').values('account__creditaccounthead__name','account__creditaccounthead','account__id','account__accountname').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance__lt = 0)

        bsunion = bs1.union(bs2)

        bsdf = read_frame(bsunion)

        print(bsdf)
       # bsdf = bsdf.drop(['debit','credit'],axis=1)


       

        pldf['balance'] = pldf['balance'].apply(Decimal)

       

        if pldf['balance'].sum() < 0:
            bsdf.loc[len(bsdf.index)] = ['Net Profit', -2, -2, 'Net Profit',pldf['balance'].sum()]
        else:
            bsdf.loc[len(bsdf.index)] = ['Net Loss', -2, -2, 'Net Loss',pldf['balance'].sum()]

        
        frames = [bsdf, dfi,odfi]

        bsdf = pd.concat(frames)

       # print(bsdf)


        bsdf['balance'] = bsdf['balance'].astype(float)
        bsdf['drcr'] = bsdf['balance'].apply(lambda x: 0 if x > 0 else 1)
        bsdf['drcr'] = np.where(bsdf['accounthead__name'] == 'Closing Stock',0,bsdf['drcr'])
        bsdf['drcr'] = np.where(bsdf['accounthead__name'] == 'Opening Stock',1,bsdf['drcr'])
        bsdf.rename(columns = {'accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)
        bsdf = bsdf.sort_values(by=['accounthead'],ascending=False)
        print(bsdf)

        df = bsdf


          
    
     
        return Response(bsdf.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance','quantity']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())
    


class tradingaccountstatement(ListAPIView):

    #serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)

        gf = generalfunctions(entityid = entity1,startdate= startdate,enddate=enddate)
               

        dfR_initial = gf.getinventorydetails()
        dfR = gf.getinventorydetails_1(dfR_1 = dfR_initial)
        ##################################################################

        odfR = gf.getopeningstockdetails()

        ##################################################################

        

        df = gf.gettradingdetails()

        print(df)

        df = gf.getgrossprofit(odfR = odfR,df = df, dfR = dfR)



        df['drcr'] = df['balance'].apply(lambda x: 0 if x >= 0 else 1)

        df['drcr'] = np.where(df['accounthead__name'] == 'Closing Stock',1,df['drcr'])

        print(df)
        df.rename(columns = {'accounthead__name':'accountheadname', 'account__accounthead':'accounthead','account__accountname':'accountname','account__id':'accountid'}, inplace = True)
        df = df.groupby(['accounthead','accountheadname','drcr','accountname','accountid','closingrate'])[['balance','quantity']].sum().abs().reset_index().sort_values(by=['accounthead'],ascending=False)

        return Response(df.T.to_dict().values())
    

class incomeandexpensesstatement(ListAPIView):

   # serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
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


        print(pldf)


     


     




      
    
     
        return Response(pldf.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())
    

class netprofitbalance(ListAPIView):

   # serializer_class = balancesheetserializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entity']

    def get(self, request, format=None):
        entity1 = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
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


     


     




      
    
     
        return Response(pldf.groupby(['accounthead','accountheadname','drcr','accountname','accountid'])[['balance']].sum().abs().reset_index().sort_values(by=['accounthead']).T.to_dict().values())
    
    

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
        stardate = datetime.strptime(self.request.query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
        enddate = datetime.strptime(self.request.query_params.get('enddate'), '%Y-%m-%d') - timedelta(days = 1)

        



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


class ledgersummarylatest(ListAPIView):

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
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
       
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
    


class accountbalance(ListAPIView):

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
        enddate = datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accounthead','account__accountname','account__id','account__accounthead__name','account__accounthead__detailsingroup',).annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0))
        df = read_frame(stk)

        df['balance'] = df['debit'] - df['credit']

        df['debit'] = np.where(df['balance'] >= 0,df['balance'],0)
        df['credit'] = np.where(df['balance'] <= 0,-df['balance'],0)



        df['drcr'] = np.where(df['credit'] > df['debit'],0,1)

        df = df[~((df.credit == 0.0) & (df.debit == 0.0))]

        #df = df.groupby(['accounthead__id','accountname','drcr','account'])[['debit','credit','quantity']].sum().abs().reset_index()
        df.rename(columns = {'account__accountname':'accountname','account__id':'account','account__accounthead': 'accounthead','account__accounthead__name':'accountheadname','account__accounthead__detailsingroup':'accounttype','credit':'creditamount','debit':'debitamount'}, inplace = True)
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())
    

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
        enddate =  datetime.strptime(self.request.query_params.get('enddate') , '%Y-%m-%d') + timedelta(days = 1)



      #  queryset1=StockTransactions.objects.filter(entity=entity,accounttype = 'M').order_by('account').only('account__accountname','transactiontype','drcr','transactionid','desc','debitamount','creditamount')

        queryset=entry.objects.filter(entity=entity,entrydate1__range = (startdate,enddate)).prefetch_related('cashtrans').order_by('entrydate1')

       

     
        
     
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

   #serializer_class = Purchasebyaccountserializer
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
    


class TrialbalanceApiView(ListAPIView):

    #serializer_class = TrialbalanceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        startdate = self.request.query_params.get('startdate')
        enddate =   self.request.query_params.get('enddate')
        #print(enddate)

       # yesterday = date.today() - timedelta(days = 100)

       # startdate1 = self.request.query_params.get('startdate')

       #'account__accounthead__name','account__accounthead'
        #stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0) )
       # stk =StockTransactions.objects.filter(entity = entity,isactive = 1).exclude(accounttype = 'MD').values('account__accounthead__name','account__accounthead','account__creditaccounthead__name','account__creditaccounthead','account_id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))


        obp =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gt = 0)
        obn =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__lt= startdate).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__creditaccounthead__name','account__creditaccounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lt = 0)
        ob = obp.union(obn)

        #print(ob)

        df = read_frame(ob)

        print(df)

        df.rename(columns = {'account__accounthead__name':'accountheadname', 'account__accounthead':'accounthead'}, inplace = True)

        dffinal1 = df.groupby(['accounthead','accountheadname'])[['balance1']].sum().reset_index()

        print(dffinal1)

        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype__in = ['MD']).exclude(transactiontype__in = ['PC']).values('account__accounthead__name','account__accounthead','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0) , balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gt = 0)
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
        if drcrgroup == 'DR':

            ob =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__gt = 0)
            stk =StockTransactions.objects.filter(entity = entity,account__accounthead = accounthead,isactive = 1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0),quantity = Sum('quantity',default = 0)).filter(balance__gt = 0)
            #return stk
        
        elif drcrgroup == 'CR':

            ob =StockTransactions.objects.filter(entity = entity,account__creditaccounthead = accounthead,isactive = 1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('accounthead__id','account__accountname','account__id').annotate(debit = Sum('debitamount',default = 0),credit = Sum('creditamount',default = 0),balance1 = Sum('debitamount',default = 0) - Sum('creditamount',default = 0)).filter(balance1__lt = 0)
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

        df = df[~((df.balance == 0.0) & (df.openingbalance == 0.0))]
        
        return Response(df.sort_values(by=['accountname']).T.to_dict().values())

class TrialbalancebyaccountApiView(ListAPIView):

    #serializer_class = TrialbalanceSerializerbyaccount
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account']


    
    def get(self, request, format=None):
        #entity = self.request.query_params.get('entity')
        entity = self.request.query_params.get('entity')
        account1 = self.request.query_params.get('account')
      #  accountheadp = self.request.query_params.get('accounthead')
        startdate = self.request.query_params.get('startdate')
        enddate = self.request.query_params.get('enddate')
        stk =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__range=(startdate, enddate)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accountname','transactiontype','transactionid','entrydatetime','desc').annotate(debit = Sum('debitamount'),credit = Sum('creditamount'),quantity = Sum('quantity')).order_by('entrydatetime')
        ob =StockTransactions.objects.filter(entity = entity,isactive = 1,account = account1,entrydatetime__lt = startdate).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__accountname').annotate(debit = Sum('debitamount'),credit = Sum('creditamount'),quantity = Sum('quantity')).order_by('entrydatetime')
        df1 = read_frame(ob)
        df1['desc'] = 'Opening Balance'
        df1['entrydatetime'] = startdate


        

        

        df1['quantity'] = df1['quantity'].astype(float).fillna(0)

        df1['debit'] = df1['debit'].astype(float).fillna(0)
        df1['credit'] = df1['credit'].astype(float).fillna(0)
       # df1['balance'] = df1['balance'].astype(float).fillna(0)



        df1 = df1.groupby(['account__accountname','entrydatetime','desc'])[['debit','credit','quantity']].sum().abs().reset_index()


        if len(df1.index) > 0:

           # print('--------------------------------------')
           # print(df1)
            df1['transactionid'] = -1
            df1['balance'] = df1['debit'] - df1['credit']
            df1['balance'] = df1['balance'].astype(float).fillna(0)
           # df1['balance'] = df1['balance'].astype(float).fillna(0)
            df1['debit'] = np.where(df1['balance'] >=0,df1['balance'],0)
            df1['credit'] = np.where(df1['balance'] <=0,df1['balance'],0)
            df1 =  df1.drop(['balance'],axis = 1)




       # df1['balance'] = df1['debit'] - df1['credit']

        #df1['debit'] = np.where(df1['balance'] >=0,df1['balance'],0)
        #df1['credit'] = np.where(df1['balance'] <=0,df1['balance'],0)


        print(len(df1.index)) 

        #df1 =  df1.drop(['balance'],axis = 1)
        #print(df1)
        df = read_frame(stk)    

        df['quantity'] = df['quantity'].astype(float).fillna(0)

        df['debit'] = df['debit'].astype(float).fillna(0)
        df['credit'] = df['credit'].astype(float).fillna(0)

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
        union_dfs['sortdatetime'] = union_dfs['sortdatetime'].astype('datetime64[ns]')

        #astype('datetime64[ns]')
        #union_dfs['entrydatetime'] = union_dfs['desc'].fillna(startdate)
       # print(union_dfs)
        #print(stk)

      #  union_dfs['entrydatetime'] = pd.to_datetime(union_dfs['entrydatetime'])

        

        print(union_dfs.sort_values(by=['entrydatetime']))
        union_dfs = union_dfs.groupby(['account__accountname','sortdatetime','desc','transactionid','transactiontype','entrydatetime'])[['debit','credit','quantity']].sum().abs().reset_index().sort_values(by ='sortdatetime', ascending = 0)
        return Response(union_dfs.T.to_dict().values())
    


