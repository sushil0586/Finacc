from django.http import request
from django.shortcuts import render
from rest_framework import response,status,permissions
from django.db import transaction

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from financial.models import account, accountHead,accounttype,ShippingDetails,staticacounts,staticacountsmapping,ContactDetails
from financial.serializers import AccountHeadSerializer,AccountSerializer,accountSerializer2,accountHeadSerializer2,accountHeadSerializeraccounts,accountHeadMainSerializer,AccountListSerializer,accountservicesSerializeraccounts,accountcodeSerializer,accounttypeserializer,AccountListtopSerializer,ShippingDetailsSerializer,ShippingDetailsListSerializer,ShippingDetailsgetSerializer,StaticAccountsSerializer,StaticAccountMappingSerializer,ContactDetailsListSerializer,ContactDetailsgetSerializer
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
import os
import json
from django.db.models import Sum
from django.db.models import Q,OuterRef, Subquery,F
import numpy as np
import pandas as pd
from rest_framework.response import Response
from invoice.models import entry,StockTransactions
from django_pandas.io import read_frame
from entity.models import Entity,entityfinancialyear,GstAccountsdetails,Mastergstdetails
from geography.models import Country,State,District,City
from entity.views import generateeinvoice
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.http import Http404
from django.http import JsonResponse
from helpers.utils.gst_api import get_gst_details
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView


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
        entity = self.request.query_params.get('entity')
        return accounttype.objects.filter(entity = entity)



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
    
    def delete(self, request, pk, *args, **kwargs):
        try:
            instance = account.objects.get(pk=pk)
        except account.DoesNotExist:
            raise Http404  # Return 404 if the object does not exist
        
        try:
            instance.delete()
        except account as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_204_NO_CONTENT)



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
        ).exclude(
                accounttype='MD'
        ).exclude(
                transactiontype__in=['PC']
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
    

class AccountListPostApiView(ListAPIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        # Extract parameters from request
        entity = request.data.get('entity')
        account_ids = request.data.get('account_ids')
        accounthead_ids = request.data.get('accounthead_ids')
        sort_by = request.data.get('sort_by', 'account')
        sort_order = request.data.get('sort_order', 'asc')
        top_n = request.data.get('top_n')

        if not entity:
            return Response({"error": "Entity is required"}, status=400)

        # Get financial year for the entity
        try:
            current_dates = entityfinancialyear.objects.get(entity=entity, isactive=1)
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Financial year not found for the entity"}, status=404)

        # Build dynamic filters for StockTransactions
        stock_filter = {
            "entity": entity,
            "isactive": 1,
            "entrydatetime__range": (current_dates.finstartyear, current_dates.finendyear)
        }
        if account_ids:
            stock_filter["account__id__in"] = account_ids
        if accounthead_ids:
            stock_filter["account__accounthead__id__in"] = accounthead_ids

        stock_queryset = StockTransactions.objects.filter(
            **stock_filter
        ).exclude(
            accounttype='MD'
        ).exclude(
            transactiontype__in=['PC']
        ).values(
            'account__id', 'account__accountname', 'account__gstno', 'account__pan',
            'account__city__cityname', 'account__accounthead__name', 'account__creditaccounthead__name',
            'account__canbedeleted'
        ).annotate(
            balance=Sum('debitamount') - Sum('creditamount')
        )

        # Build dynamic filters for account
        account_filter = {
            "entity": entity,
            "isactive": 1
        }
        if account_ids:
            account_filter["id__in"] = account_ids
        if accounthead_ids:
            account_filter["accounthead__id__in"] = accounthead_ids

        account_queryset = account.objects.filter(
            **account_filter
        ).values(
            'id', 'accountname', 'gstno', 'pan', 'city__cityname',
            'accounthead__name', 'creditaccounthead__name', 'canbedeleted'
        )

        stock_data = list(stock_queryset)
        account_data = list(account_queryset)

        # Merge account and stock data
        final_data = []
        for acc in account_data:
            balance = next((item.get('balance') for item in stock_data if item['account__id'] == acc['id']), 0)
            balance = balance if balance is not None else 0
            drcr = 'CR' if balance < 0 else 'DR'
            debit = max(balance, 0)
            credit = abs(min(balance, 0))

            final_data.append({
                'accountname': acc['accountname'],
                'debit': debit,
                'credit': credit,
                'accgst': acc['gstno'],
                'accpan': acc['pan'],
                'cityname': acc['city__cityname'],
                'accountid': acc['id'],
                'daccountheadname': acc['accounthead__name'],
                'caccountheadname': acc['creditaccounthead__name'],
                'accanbedeleted': acc['canbedeleted'],
                'balance': balance,
                'drcr': drcr
            })

        # Sorting
        sort_field_map = {
            'account': 'accountname',
            'accounthead': 'daccountheadname'
        }
        sort_key = sort_field_map.get(sort_by, 'accountname')
        reverse_sort = sort_order.lower() == 'desc'
        final_data.sort(key=lambda x: x.get(sort_key, '').lower(), reverse=reverse_sort)

        # Top N limit
        if top_n:
            try:
                top_n = int(top_n)
                final_data = final_data[:top_n]
            except ValueError:
                pass  # Ignore invalid top_n values

        return Response(final_data)
    


class GetGstinDetails(ListAPIView):
    """
    API view to retrieve GSTIN details and cache them if not already available.
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {'id': ["in", "exact"]}

        # def get(self, request, format=None):
    #     entitygst = self.request.query_params.get('entitygst')
    #     if not entitygst:
    #         return response.Response({"error": "Entity GST parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

    #     # Check if the GST details already exist
    #     if not GstAccountsdetails.objects.filter(gstin=entitygst).exists():
    #         try:
    #             # Fetch master GST details
    #             mgst = Mastergstdetails.objects.first()
    #             if not mgst:
    #                 return response.Response({"error": "Master GST details not found."}, status=status.HTTP_404_NOT_FOUND)
    #         except Mastergstdetails.DoesNotExist:
    #             return response.Response({"error": "Master GST details not found."}, status=status.HTTP_404_NOT_FOUND)

    #         # Generate e-invoice and fetch GST details
    #         einv = generateeinvoice(mgst)
    #         auth_response = einv.getauthentication()
    #         auth_data = auth_response.json()

    #         gst_details_response = einv.getgstdetails(
    #             gstaccount=entitygst,
    #             authtoken=auth_data["data"]["AuthToken"],
    #             useremail='sushiljyotibansal@gmail.com'
    #         )
    #         gst_data = gst_details_response.json()

    #         # Handle error in GST details fetching
    #         error_desc = json.loads(gst_data.get("status_desc", "[]"))
    #         if error_desc and error_desc[0].get('ErrorCode') == '3001':
    #             return response.Response({"message": "GST number is not available"}, status=status.HTTP_401_UNAUTHORIZED)

    #         # Process the fetched GST details
    #         data = gst_data["data"]

    #         print(data)
    #         try:
    #             state_instance = State.objects.get(statecode=data.get('StateCode'))
    #         except State.DoesNotExist:
    #             state_instance = None

    #         try:
    #             city_instance = City.objects.get(pincode=data.get('AddrPncd'))
    #         except City.DoesNotExist:
    #             city_instance = None

    #         # Save GST details into the database
    #         GstAccountsdetails.objects.create(
    #             gstin=data['Gstin'],
    #             tradeName=data['TradeName'],
    #             legalName=data['LegalName'],
    #             addrFlno=data['AddrFlno'],
    #             addrBnm=data['AddrBnm'],
    #             addrBno=data['AddrBno'],
    #             addrSt=data['AddrSt'],
    #             addrLoc=city_instance,
    #             stateCode=state_instance,
    #             addrPncd=data['AddrPncd'],
    #             txpType=data['TxpType'],
    #             status=data['Status'],
    #             blkStatus=data['BlkStatus'],
    #             dtReg=data['DtReg'],
    #             dtDReg=data['DtDReg']
    #         )

    #     # Retrieve GST details from the database
    #     gstdetails = GstAccountsdetails.objects.filter(gstin=entitygst).values(
    #         'gstin', 'tradeName', 'legalName', 'addrFlno', 'addrBnm', 'addrBno',
    #         'addrSt', 'addrLoc__id', 'stateCode__id', 'stateCode__country__id',
    #         'addrLoc__distt__id', 'addrPncd', 'txpType', 'status', 'blkStatus',
    #         'dtReg', 'dtDReg'
    #     )

    #     # Transform data to desired format without Pandas
    #     result = []
    #     for detail in gstdetails:
    #         result.append({
    #             'gstno': detail['gstin'],
    #             'entityname': detail['tradeName'],
    #             'legalname': detail['legalName'],
    #             'address': detail['addrBnm'],
    #             'address2': detail['addrBno'],
    #             'addressfloorno': detail['addrFlno'],
    #             'addressstreet': detail['addrSt'],
    #             'stateid': detail['stateCode__id'],
    #             'pincode': detail['addrPncd'],
    #             'gstintype': detail['txpType'],
    #             'dateofreg': detail['dtReg'],
    #             'dateofdreg': detail['dtDReg'],
    #             'cityid': detail['addrLoc__id'],
    #             'countryid': detail['stateCode__country__id'],
    #             'disttid': detail['addrLoc__distt__id'],
    #         })

    #     return response.Response(result)

    def get(self, request, format=None):
        entitygst = self.request.query_params.get('entitygst')

       
        if not entitygst:
            return response.Response({"error": "Entity GST parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        gst_data = get_gst_details(entitygst)

        # state_instance = State.objects.get(statecode=gst_data.get('StateCode'))



        print(gst_data)


       
        try:
            state_instance, _ = State.objects.get_or_create(statecode=gst_data['StateCode'])
            city_instance, _ = City.objects.get_or_create(pincode=gst_data['AddrPncd'])
        except Exception as e:
            return {"error": str(e)}

        # Check if GSTIN already exists
        if GstAccountsdetails.objects.filter(gstin=gst_data['Gstin']).exists():
            gstdetails = GstAccountsdetails.objects.filter(gstin=gst_data['Gstin']).values()
        else:
            new_gst = GstAccountsdetails.objects.create(
                gstin=gst_data['Gstin'],
                tradeName=gst_data['TradeName'],
                legalName=gst_data['LegalName'],
                addrFlno=gst_data['AddrFlno'],
                addrBnm=gst_data['AddrBnm'],
                addrBno=gst_data['AddrBno'],
                addrSt=gst_data['AddrSt'],
                addrLoc=city_instance,
                stateCode=state_instance,
                district=city_instance.distt,
                country=state_instance.country,
                addrPncd=gst_data['AddrPncd'],
                txpType=gst_data['TxpType'],
                status=gst_data['Status'],
                blkStatus=gst_data['BlkStatus'],
                dtReg=gst_data['DtReg'],
                dtDReg=gst_data['DtDReg']
            )
            gstdetails = [new_gst]

        # Transform data into the required format
        result = [
        {
            'gstno': detail['gstin'],
            'entityname': detail['tradeName'],
            'legalname': detail['legalName'],
            'address': detail['addrBnm'],
            'address2': detail['addrBno'],
            'addressfloorno': detail['addrFlno'],
            'addressstreet': detail['addrSt'],
            'stateid': detail['stateCode_id'],
            'pincode': detail['addrPncd'],
            'gstintype': detail['txpType'],
            'dateofreg': detail['dtReg'],
            'dateofdreg': detail['dtDReg'],
            'cityid': detail['addrLoc_id'],
            'countryid': detail['country_id'],
            'disttid': detail['district_id'],
        }
        for detail in gstdetails
    ]
    

        #return result

    


       
        return response.Response(result)
    

class AccountListView(ListAPIView):
    serializer_class = AccountListtopSerializer

    def get_queryset(self):
        entity_ids = self.request.GET.get('entity', '')
        accounthead_codes = self.request.GET.get('accounthead', '')
        
        entity_ids = [int(e) for e in entity_ids.split(',') if e.isdigit()] if entity_ids else []
        accounthead_codes = [int(a) for a in accounthead_codes.split(',') if a.isdigit()] if accounthead_codes else []
        
        filters = Q()
        if entity_ids:
            filters &= Q(entity_id__in=entity_ids)
        if accounthead_codes:
            filters &= Q(accounthead__code__in=accounthead_codes)
        
        return account.objects.filter(filters)


class ShippingDetailsListCreateView(ListCreateAPIView):
    queryset = ShippingDetails.objects.all()
    serializer_class = ShippingDetailsgetSerializer

class ShippingDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = ShippingDetails.objects.all()
    serializer_class = ShippingDetailsgetSerializer


class ContactDetailsListCreateView(ListCreateAPIView):
    queryset = ContactDetails.objects.all()
    serializer_class = ContactDetailsgetSerializer

class ContactDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = ContactDetails.objects.all()
    serializer_class = ContactDetailsgetSerializer

# API View to Get Shipping Details by Account
class ShippingDetailsByAccountView(ListAPIView):
    serializer_class = ShippingDetailsListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        account_id = self.kwargs.get('account_id')
        return ShippingDetails.objects.select_related('country', 'state', 'district', 'city').filter(account_id=account_id)
    

class ContactDetailsByAccountView(ListAPIView):
    serializer_class = ContactDetailsListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        account_id = self.kwargs.get('account_id')
        return ContactDetails.objects.select_related('country', 'state', 'district', 'city').filter(account_id=account_id)
    
class StaticAccountsAPIView(APIView):
    
    def get(self, request, pk=None):
        if pk:
            static_account = get_object_or_404(staticacounts, pk=pk)
            serializer = StaticAccountsSerializer(static_account)
            return Response(serializer.data)
        else:
            static_accounts = staticacounts.objects.all()
            serializer = StaticAccountsSerializer(static_accounts, many=True)
            return Response(serializer.data)
    
    def post(self, request):
        serializer = StaticAccountsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        static_account = get_object_or_404(staticacounts, pk=pk)
        serializer = StaticAccountsSerializer(static_account, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        static_account = get_object_or_404(staticacounts, pk=pk)
        static_account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

# GET (list), POST (single/bulk)
class StaticAccountMappingListCreateView(ListCreateAPIView):
    queryset = staticacountsmapping.objects.all()
    serializer_class = StaticAccountMappingSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)
        data_list = request.data if is_many else [request.data]
        results = []

        for item in data_list:
            staticaccount_id = item.get("staticaccount")
            entity_id = item.get("entity")
            account_id = item.get("account")

            if not staticaccount_id or not entity_id:
                return Response(
                    {"detail": "Both 'staticaccount' and 'entity' are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                instance = staticacountsmapping.objects.get(
                    staticaccount_id=staticaccount_id,
                    entity_id=entity_id
                )

                if account_id is None:
                    # Delete if account is null
                    instance.delete()
                    continue

                # Update existing mapping
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                results.append(serializer.data)

            except staticacountsmapping.DoesNotExist:
                if account_id is None:
                    # Don't create if account is null
                    continue
                # Create new mapping
                serializer = self.get_serializer(data=item)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                results.append(serializer.data)

        return Response(results, status=status.HTTP_200_OK)


# GET by ID, PUT, DELETE
class StaticAccountMappingRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = staticacountsmapping.objects.all()
    serializer_class = StaticAccountMappingSerializer


class StaticAccountFlatListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get('entity')
        accounttype_id = request.query_params.get('accounttype')

        if not entity_id:
            return Response({'detail': 'entity is required'}, status=400)

        mapping_qs = staticacountsmapping.objects.filter(
            staticaccount=OuterRef('pk'),
            entity_id=entity_id
        ).values('account_id')[:1]

        base_filter = Q()
        if accounttype_id:
            base_filter &= Q(accounttype_id=accounttype_id)

        queryset = staticacounts.objects.filter(base_filter).annotate(
            staticaccountid=F('id'),
            staticaccountname=F('staticaccount'),
            accountid=Subquery(mapping_qs)
        ).values(
            'staticaccountid', 'staticaccountname', 'accountid'
        )

        return Response(list(queryset))


    

