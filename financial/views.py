from django.http import request
from django.shortcuts import render
from rest_framework import response,status,permissions

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from financial.models import account, accountHead,accounttype
from financial.serializers import AccountHeadSerializer,AccountSerializer,accountSerializer2,accountHeadSerializer2,accountHeadSerializeraccounts,accountHeadMainSerializer,AccountListSerializer,accountservicesSerializeraccounts,accountcodeSerializer,accounttypeserializer
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
from geography.models import Country,State,District,City
from entity.views import generateeinvoice
from rest_framework.permissions import IsAuthenticated


class AccountHeadApiView(ListCreateAPIView):
    serializer_class = accountHeadSerializer2
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'name', 'code']

    def perform_create(self, serializer):
        """
        Customizes the creation process to associate the newly created account head with the authenticated user.
        """
        serializer.save(createdby=self.request.user)

    def get_queryset(self):
        """
        Filters the accountHead objects based on the 'entity' query parameter.
        """
        entity = self.request.query_params.get('entity')
        if entity:
            return accountHead.objects.filter(entity=entity)
        return accountHead.objects.all()


class AccountHeadUpdateDeleteApiView(RetrieveUpdateDestroyAPIView):
    """
    Handles retrieve, update, and delete operations for accountHead objects 
    belonging to the authenticated user.
    """
    serializer_class = accountHeadSerializer2
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        """
        Restricts the queryset to accountHead objects owned by the authenticated user.
        """
        return accountHead.objects.filter(createdby=self.request.user)
    


class AccountCodeLatestView(ListCreateAPIView):
    """
    API view to retrieve the latest account code for a given entity.
    """
    serializer_class = accountcodeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    def get(self, request, *args, **kwargs):
        """
        Retrieves the latest account for a given entity and returns serialized data.
        """
        entity = request.query_params.get('entity')
        if not entity:
            return Response(
                {"error": "Entity parameter is required."}, 
                status=400
            )

        latest_account = account.objects.filter(entity=entity).last()
        if not latest_account:
            return Response(
                {"error": f"No accounts found for entity '{entity}'."}, 
                status=404
            )

        serializer = self.get_serializer(latest_account)
        return Response(serializer.data)




class CustomApiView2(ListAPIView):
    """
    API view to list accountHead objects filtered by entity and code.
    """
    serializer_class = accountHeadSerializeraccounts
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        'code': ["in", "exact"],
    }

    def get_queryset(self):
        """
        Filters the accountHead objects by the 'entity' query parameter.
        """
        entity = self.request.query_params.get('entity')
        if not entity:
            return accountHead.objects.none()  # Return an empty queryset if 'entity' is not provided.
        return accountHead.objects.filter(entity=entity)
    



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

    serializer_class = AccountSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['gstno']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return account.objects.filter(entity = entity)



class accountListApiView(ListAPIView):

    serializer_class = AccountListSerializer
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

    serializer_class = AccountSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return account.objects.filter(createdby = self.request.user)



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
    

class AccountBindApiView(ListAPIView):
    """
    API view to retrieve account balances and related information for a given entity.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        # Retrieve entity from query parameters
        entity = self.request.query_params.get('entity')
        if not entity:
            return Response({"error": "Entity parameter is required."}, status=400)

        # Get the financial year for the entity
        try:
            current_dates = entityfinancialyear.objects.get(entity=entity, isactive=1)
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Active financial year not found for the given entity."}, status=404)

        # Query for transactions within the financial year
        transactions = StockTransactions.objects.filter(
            entity=entity,
            isactive=1,
            entrydatetime__range=(current_dates.finstartyear, current_dates.finendyear)
        ).exclude(
            accounttype='MD'
        ).exclude(
            transactiontype__in=['PC']
        ).values(
            'account__id', 'account__accountname', 'account__accountcode',
            'account__gstno', 'account__pan', 'account__city', 'account__saccode'
        ).annotate(
            balance=Sum('debitamount', default=0) - Sum('creditamount', default=0)
        )

        # Query for accounts associated with the entity
        accounts = account.objects.filter(entity=entity).values(
            'id', 'accountname', 'accountcode', 'gstno', 'pan', 'city__id', 'saccode'
        )

        # Convert querysets to DataFrames
        df_transactions = read_frame(transactions).fillna('')
        df_accounts = read_frame(accounts).fillna('')

        # Rename columns for consistency
        df_transactions.rename(columns={
            'account__id': 'id',
            'account__accountname': 'accountname',
            'account__accountcode': 'accountcode',
            'account__gstno': 'gstno',
            'account__pan': 'pan',
            'account__city': 'city',
            'account__saccode': 'saccode'
        }, inplace=True)

        df_accounts.rename(columns={'city__id': 'city'}, inplace=True)
        df_accounts['balance'] = 0  # Add balance column with default 0

        # Combine transactions and accounts data
        combined_df = pd.concat([df_transactions, df_accounts]).reset_index(drop=True)

        # Group by unique account attributes and calculate total balance
        final_df = combined_df.groupby(
            ['id', 'accountname', 'accountcode', 'gstno', 'saccode', 'city']
        )[['balance']].sum().reset_index()

        # Add 'drcr' column based on balance sign
        final_df['drcr'] = np.where(final_df['balance'] < 0, 'CR', 'DR')

        # Return sorted and formatted response
        return Response(final_df.sort_values(by=['accountname']).to_dict(orient='records'))
    


class AccountListNewApiView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    
    def get_queryset(self, entity):
        # Fetch the financial year start and end for the given entity
        current_dates = entityfinancialyear.objects.get(entity=entity, isactive=1)
        
        # Fetch StockTransactions and Account data with aggregation
        stock_queryset = StockTransactions.objects.filter(
            entity=entity,
            isactive=1,
            entrydatetime__range=(current_dates.finstartyear, current_dates.finendyear)
        ).values(
            'account__id', 'account__accountname', 'account__gstno', 'account__pan',
            'account__city__cityname', 'account__accounthead__name', 'account__creditaccounthead__name',
            'account__canbedeleted'
        ).annotate(
            balance=Sum('debitamount', default=0) - Sum('creditamount', default=0)
        )

        account_queryset = account.objects.filter(entity=entity, isactive=1).values(
            'id', 'accountname', 'gstno', 'pan', 'city__cityname', 
            'accounthead__name', 'creditaccounthead__name', 'canbedeleted'
        )

        # Combining stock and account data efficiently by unioning
        return stock_queryset, account_queryset

    def get(self, request, format=None):
        # Get the entity parameter from the request
        entity = request.query_params.get('entity')
        
        # Fetch the data
        stock_queryset, account_queryset = self.get_queryset(entity)
        
        # Prepare the response data directly using aggregation and annotation
        stock_data = list(stock_queryset)
        account_data = list(account_queryset)
        
        # Processing data to create the response structure
        final_data = []
        for account in account_data:
            # Calculate balance and dr/cr in a more optimized way
            balance = next((item['balance'] for item in stock_data if item['account__id'] == account['id']), 0)
            drcr = 'CR' if balance < 0 else 'DR'
            debit = max(balance, 0)
            credit = min(balance, 0)

            final_data.append({
                'accountname': account['accountname'],
                'debit': debit,
                'credit': credit,
                'accgst': account['gstno'],
                'accpan': account['pan'],
                'cityname': account['city__cityname'],
                'accountid': account['id'],
                'daccountheadname': account['accounthead__name'],
                'caccountheadname': account['creditaccounthead__name'],
                'accanbedeleted': account['canbedeleted'],
                'balance': balance,
                'drcr': drcr
            })

        # Sort final data by accountname and return the response
        final_data.sort(key=lambda x: x['accountname'])
        return Response(final_data)
    


class GetGstinDetails(ListAPIView):
    """
    API view to retrieve GSTIN details and cache them if not already available.
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id': ["in", "exact"]}

    def get(self, request, format=None):
        entitygst = self.request.query_params.get('entitygst')
        if not entitygst:
            return response.Response({"error": "Entity GST parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the GST details already exist
        if not GstAccountsdetails.objects.filter(gstin=entitygst).exists():
            try:
                # Fetch master GST details
                mgst = Mastergstdetails.objects.first()
                if not mgst:
                    return response.Response({"error": "Master GST details not found."}, status=status.HTTP_404_NOT_FOUND)
            except Mastergstdetails.DoesNotExist:
                return response.Response({"error": "Master GST details not found."}, status=status.HTTP_404_NOT_FOUND)

            # Generate e-invoice and fetch GST details
            einv = generateeinvoice(mgst)
            auth_response = einv.getauthentication()
            auth_data = auth_response.json()

            gst_details_response = einv.getgstdetails(
                gstaccount=entitygst,
                authtoken=auth_data["data"]["AuthToken"],
                useremail='sushiljyotibansal@gmail.com'
            )
            gst_data = gst_details_response.json()

            # Handle error in GST details fetching
            error_desc = json.loads(gst_data.get("status_desc", "[]"))
            if error_desc and error_desc[0].get('ErrorCode') == '3001':
                return response.Response({"message": "GST number is not available"}, status=status.HTTP_401_UNAUTHORIZED)

            # Process the fetched GST details
            data = gst_data["data"]
            try:
                state_instance = State.objects.get(statecode=data.get('StateCode'))
            except State.DoesNotExist:
                state_instance = None

            try:
                city_instance = City.objects.get(pincode=data.get('AddrPncd'))
            except City.DoesNotExist:
                city_instance = None

            # Save GST details into the database
            GstAccountsdetails.objects.create(
                gstin=data['Gstin'],
                tradeName=data['TradeName'],
                legalName=data['LegalName'],
                addrFlno=data['AddrFlno'],
                addrBnm=data['AddrBnm'],
                addrBno=data['AddrBno'],
                addrSt=data['AddrSt'],
                addrLoc=city_instance,
                stateCode=state_instance,
                addrPncd=data['AddrPncd'],
                txpType=data['TxpType'],
                status=data['Status'],
                blkStatus=data['BlkStatus'],
                dtReg=data['DtReg'],
                dtDReg=data['DtDReg']
            )

        # Retrieve GST details from the database
        gstdetails = GstAccountsdetails.objects.filter(gstin=entitygst).values(
            'gstin', 'tradeName', 'legalName', 'addrFlno', 'addrBnm', 'addrBno',
            'addrSt', 'addrLoc__id', 'stateCode__id', 'stateCode__country__id',
            'addrLoc__distt__id', 'addrPncd', 'txpType', 'status', 'blkStatus',
            'dtReg', 'dtDReg'
        )

        # Transform data to desired format without Pandas
        result = []
        for detail in gstdetails:
            result.append({
                'gstno': detail['gstin'],
                'entityname': detail['tradeName'],
                'legalname': detail['legalName'],
                'address': detail['addrBnm'],
                'address2': detail['addrBno'],
                'addressfloorno': detail['addrFlno'],
                'addressstreet': detail['addrSt'],
                'stateid': detail['stateCode__id'],
                'pincode': detail['addrPncd'],
                'gstintype': detail['txpType'],
                'dateofreg': detail['dtReg'],
                'dateofdreg': detail['dtDReg'],
                'cityid': detail['addrLoc__id'],
                'countryid': detail['stateCode__country__id'],
                'disttid': detail['addrLoc__distt__id'],
            })

        return response.Response(result)