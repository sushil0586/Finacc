from django.http import request
from django.shortcuts import render
from rest_framework import response,status,permissions

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from financial.models import account, accountHead,accounttype
from financial.serializers import accountHeadSerializer,accountSerializer,accountSerializer2,accountHeadSerializer2,accountHeadSerializeraccounts,accountHeadMainSerializer,accountListSerializer,accountservicesSerializeraccounts,accountcodeSerializer,accounttypeserializer
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
import os
import json
from django.db.models import Sum
from django.db.models import Q
import numpy as np
import pandas as pd
from rest_framework.response import Response
from invoice.models import entry,StockTransactions
from django_pandas.io import read_frame
from entity.models import Entity,entityfinancialyear,GstAccountsdetails,Mastergstdetails
from geography.models import country,state,district,city
from entity.views import generateeinvoice


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
    


class accountcodelatestview(ListCreateAPIView):

    serializer_class = accountcodeSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
       
        id = account.objects.filter(entity= entity).last()
        serializer = accountcodeSerializer(id)
        return Response(serializer.data)




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
    



class customApiView4(ListAPIView):

    serializer_class = accountSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'accounthead__code':["in", "exact"]
    
    }

    # def perform_create(self, serializer):
    #     return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        query =  account.objects.filter(entity = entity)

        #print(query.query.__str__())

        return query
    




class customApiView3(ListAPIView):

    serializer_class = accountservicesSerializeraccounts
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


class accounttypeApiView(ListCreateAPIView):

    serializer_class = accounttypeserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['gstno']


    
    def get_queryset(self):
       # entity = self.request.query_params.get('entity')
        return accounttype.objects.filter()



class accountApiView(ListCreateAPIView):

    serializer_class = accountSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['gstno']

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

        currentdates = entityfinancialyear.objects.get(entity = entity,isactive = 1)
        queryset =  account.objects.filter( Q(entity = entity),Q(accounttrans__accounttype__in = ['M','DD'])).values('accountname','city__cityname','id','gstno','pan','accounthead__name','creditaccounthead__name','canbedeleted').annotate(debit = Sum('accounttrans__debitamount',default = 0),credit = Sum('accounttrans__creditamount',default = 0),balance = Sum('accounttrans__debitamount',default = 0) - Sum('accounttrans__creditamount',default = 0))

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
    

class accountbindapiview(ListAPIView):
   # serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        currentdates = entityfinancialyear.objects.get(entity = entity,isactive = 1)


        # if self.request.query_params.get('accounthead'):
        #     accountheads =  [int(x) for x in request.GET.get('accounthead', '').split(',')]
        #     queryset =  StockTransactions.objects.filter(entity = entity,accounthead__in = accountheads).values('account__id','account__accountname').distinct().order_by('account')
        # else:
        queryset =  StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(currentdates.finstartyear, currentdates.finendyear)).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account__id','account__accountname','account__accountcode','account__gstno','account__pan','account__city','account__saccode').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))

        queryset2 =  account.objects.filter(entity = entity).values('id','accountname','accountcode','gstno','pan','city__id','saccode')

           # 'accountname','accountcode','city','gstno','pan','saccode'

        df = read_frame(queryset) 
        dfa = read_frame(queryset2)

        df = df.fillna('')
        dfa = dfa.fillna('')
        dfa['balance'] = 0
        df.rename(columns = {'account__accountname':'accountname','account__id':'id','account__accountcode':'accountcode','account__gstno':'gstno','account__pan':'pan','account__city':'city','account__saccode':'saccode'}, inplace = True)
        dfa.rename(columns = {'city__id':'city'}, inplace = True)

        dfnew = pd.concat([df,dfa]).reset_index()

        #print(dfnew)

        

        dffinal = dfnew.groupby(['id','accountname','accountcode','gstno','saccode','city'])[['balance']].sum().reset_index()


        dffinal['drcr'] = np.where(dffinal['balance'] < 0 , 'CR','DR')

       # print(dffinal)

        return Response(dffinal.sort_values(by=['accountname']).T.to_dict().values())
    


class accountlistnewapiview(ListAPIView):
   # serializer_class = accountListSerializer2
    permission_classes = (permissions.IsAuthenticated,)

    
    
    def get(self, request, format=None):
        entity = self.request.query_params.get('entity')
        currentdates = entityfinancialyear.objects.get(entity = entity,isactive = 1)

        # if self.request.query_params.get('accounthead'):
        #     accountheads =  [int(x) for x in request.GET.get('accounthead', '').split(',')]
        #     queryset =  StockTransactions.objects.filter(entity = entity,accounthead__in = accountheads).values('account__id','account__accountname').distinct().order_by('account')
        # else:
        queryset =  StockTransactions.objects.filter(entity = entity,isactive = 1,entrydatetime__range=(currentdates.finstartyear, currentdates.finendyear)).values('account__id','account__accountname','account__gstno','account__pan','account__city__cityname','account__accounthead__name','account__creditaccounthead__name','account__canbedeleted').annotate(balance = Sum('debitamount',default = 0) - Sum('creditamount',default = 0))
        queryset2 =  account.objects.filter(entity = entity,isactive = 1).values('id','accountname','gstno','pan','city__cityname','accounthead__name','creditaccounthead__name','canbedeleted')

           # 'accountname','accountcode','city','gstno','pan','saccode'

        df = read_frame(queryset) 
        dfa = read_frame(queryset2)
        dfa['balance'] = 0
        df.rename(columns = {'account__accountname':'accountname','account__id':'accountid','account__gstno':'accgst','account__pan':'accpan','account__city__cityname':'cityname','account__accounthead__name':'daccountheadname','account__creditaccounthead__name':'caccountheadname','account__canbedeleted':'canbedeleted'}, inplace = True)
        dfa.rename(columns = {'id':'accountid','gstno':'accgst','pan':'accpan','city__cityname':'cityname','accounthead__name':'daccountheadname','creditaccounthead__name':'caccountheadname'}, inplace = True)
        dfnew = pd.concat([df,dfa]).reset_index()
        dfnew = dfnew.fillna('')
        dffinal = dfnew.groupby(['accountid','accountname','accgst','cityname','accpan','daccountheadname','caccountheadname','canbedeleted'])[['balance']].sum().reset_index()
        dffinal['drcr'] = np.where(dffinal['balance'] < 0 , 'CR','DR')
        dffinal['debit'] = np.where(dffinal['balance'] > 0 , dffinal['balance'],0)
        dffinal['credit'] = np.where(dffinal['balance'] < 0 , dffinal['balance'],0)

        

        return Response(dffinal.sort_values(by=['accountname']).T.to_dict().values())
    


class getgstindetails(ListAPIView):


  
  #  filter_class = accountheadFilter
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id':["in", "exact"]
    
    }
    #filterset_fields = ['id']
    def get(self, request, format=None):

           
        
    
       # acc = self.request.query_params.get('acc')
        entitygst = self.request.query_params.get('entitygst')
      #  accountgst = self.request.query_params.get('accountgst')

        if GstAccountsdetails.objects.filter(gstin = entitygst).count() == 0:

            try:
                mgst = Mastergstdetails.objects.get()
                #mgst = Mastergstdetails.objects.get(gstin = entitygst)
            except Mastergstdetails.DoesNotExist:
                mgst = None
                return 1
          
          #  mgst = Mastergstdetails.objects.get(gstin = entitygst)
            einv = generateeinvoice(mgst)
            r = einv.getauthentication()
            res = r.json()
            print(res)
            gstdetails = einv.getgstdetails(gstaccount = entitygst,authtoken = res["data"]["AuthToken"],useremail = 'sushiljyotibansal@gmail.com' )
            res = gstdetails.json()
            err = json.loads(res["status_desc"])
            if err[0]['ErrorCode'] == '3001':
                return response.Response({'message': "Gst no is not available"},status = status.HTTP_401_UNAUTHORIZED)
            # if json.loads(res["status_desc"])["ErrorCode"] == "3001":
            #     return json.loads(res["status_desc"])

            
            data = res["data"]
            try:
                stateid = state.objects.get(statecode = data['StateCode'])
            except state.DoesNotExist:
                stateid = None
            try:
                cityid = city.objects.get(pincode = data['AddrPncd'])
            except city.DoesNotExist:
                cityid = None
            
            GstAccountsdetails.objects.create(gstin = data['Gstin'],tradeName = data['TradeName'],legalName = data['LegalName'],addrFlno = data['AddrFlno'],addrBnm =data['AddrBnm'],addrBno = data['AddrBno'],addrSt = data['AddrSt'],addrLoc = cityid,stateCode = stateid,addrPncd = data['AddrPncd'],txpType = data['TxpType'],status = data['Status'],blkStatus = data['BlkStatus'],dtReg = data['DtReg'],dtDReg = data['DtDReg'])
        

        gstdetails = GstAccountsdetails.objects.filter(gstin = entitygst).values('gstin','tradeName','legalName','addrFlno','addrBnm','addrBno','addrSt','addrLoc__id','stateCode__id','stateCode__country__id','addrLoc__distt__id','addrPncd','txpType','status','blkStatus','dtReg','dtDReg')

        df = read_frame(gstdetails)
        df.rename(columns = {'Gstin':'gstno','tradeName':'entityname','LegalName':'legalname','addrBnm':'address','addrBno':'address2','addrFlno':'addressfloorno','addrSt':'addressstreet','stateCode__id':'stateid','addrPncd':'pincode','txpType':'gstintype','dtReg':'dateofreg','dtDReg':'dateofdreg','addrLoc__id':'cityid','stateCode__country__id':'countryid','addrLoc__distt__id':'disttid'}, inplace = True)






        


  
        
        

        
  

     
        
     
        return  Response(df.T.to_dict().values())