from django.http import request
from django.shortcuts import render
from rest_framework import response,status,permissions
from django.db import transaction
from rest_framework.viewsets import ModelViewSet

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from financial.models import account, accountHead,accounttype,ShippingDetails,staticacounts,staticacountsmapping,ContactDetails
from financial.serializers import AccountHeadSerializer,AccountSerializer,accountSerializer2,accountHeadSerializer2,accountHeadSerializeraccounts,accountHeadMainSerializer,AccountListSerializer,accountservicesSerializeraccounts,accountcodeSerializer,accounttypeserializer,AccountListtopSerializer,ShippingDetailsSerializer,ShippingDetailsListSerializer,StaticAccountsSerializer,StaticAccountMappingSerializer,ContactDetailsListSerializer,AccountHeadMinimalSerializer,AccountTypeJsonSerializer,AccountBalanceSerializer,AccountHeadListSerializer,ContactDetailsSerializer
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
import xlwt
from django.http import HttpResponse


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
    

class accounttypejsonApiView(ListCreateAPIView):

    serializer_class = AccountTypeJsonSerializer
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
    

class AccountBindApiView(APIView):
    """
    Optimized API view to retrieve account balances and related information.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        entity = request.query_params.get('entity')
        if not entity:
            return Response({"error": "Entity parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fy = entityfinancialyear.objects.get(entity=entity, isactive=1)
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Active financial year not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get transactions with balance
        transactions = StockTransactions.objects.filter(
            entity=entity,
            isactive=1,
            entrydatetime__range=(fy.finstartyear, fy.finendyear)
        ).exclude(
            accounttype='MD'
        ).exclude(
            transactiontype__in=['PC']
        ).values(
            'account__id', 'account__accountname', 'account__accountcode',
            'account__gstno', 'account__pan', 'account__city', 'account__saccode'
        ).annotate(
            balance=Sum('debitamount') - Sum('creditamount')
        )

        # Convert transactions to dict
        transaction_map = {}
        for t in transactions:
            aid = t['account__id']
            transaction_map[aid] = {
                'id': aid,
                'accountname': t['account__accountname'],
                'accountcode': t['account__accountcode'],
                'gstno': t.get('account__gstno') or '',
                'pan': t.get('account__pan') or '',
                'city': t.get('account__city'),
                'saccode': t.get('account__saccode') or '',
                'balance': t['balance'] or 0
            }

        # Include accounts with no transactions (default balance 0)
        accounts = account.objects.filter(entity=entity).values(
            'id', 'accountname', 'accountcode', 'gstno', 'pan', 'city__id', 'saccode'
        )

        for acc in accounts:
            aid = acc['id']
            if aid not in transaction_map:
                transaction_map[aid] = {
                    'id': aid,
                    'accountname': acc['accountname'],
                    'accountcode': acc['accountcode'],
                    'gstno': acc.get('gstno') or '',
                    'pan': acc.get('pan') or '',
                    'city': acc.get('city__id'),
                    'saccode': acc.get('saccode') or '',
                    'balance': 0
                }

        # Add DR/CR field
        final_data = []
        for entry in transaction_map.values():
            entry['drcr'] = 'CR' if entry['balance'] < 0 else 'DR'
            final_data.append(entry)

        # Sort by accountname
        final_data.sort(key=lambda x: x['accountname'])

        # Serialize and return
        serializer = AccountBalanceSerializer(final_data, many=True)
        return Response(serializer.data)
    


class InvoiceBindApiView(APIView):
    """
    Optimized API view to retrieve account balances and related information.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        entity = request.query_params.get('entity')
        if not entity:
            return Response({"error": "Entity parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fy = entityfinancialyear.objects.get(entity=entity, isactive=1)
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Active financial year not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get transactions with balances
        transactions = StockTransactions.objects.filter(
            entity=entity,
            isactive=1,
            account__accounthead__code__in=['4000', '7000', '8000'],
            entrydatetime__range=(fy.finstartyear, fy.finendyear)
        ).exclude(
            accounttype='MD'
        ).exclude(
            transactiontype__in=['PC']
        ).values(
            'account__id',
            'account__accountname',
            'account__accountcode',
            'account__gstno',
            'account__pan',                # ✅ Important for pancode
            'account__city',
            'account__saccode',
            'account__state',              # ✅ Include for state ID
            'account__district',           # ✅ Include for district ID
            'account__pincode'
        ).annotate(
            balance=Sum('debitamount') - Sum('creditamount')
        )

        transaction_map = {}
        for t in transactions:
            aid = t['account__id']
            transaction_map[aid] = {
                'id': aid,
                'accountname': t['account__accountname'],
                'accountcode': t['account__accountcode'],
                'gstno': t.get('account__gstno') or '',
                'pancode': t.get('account__pan') or '',
                'city': t.get('account__city'),
                'state': t.get('account__state'),
                'district': t.get('account__district'),
                'pincode': t.get('account__pincode') or '',
                'saccode': t.get('account__saccode') or '',
                'balance': t['balance'] or 0
            }

        # Accounts with no transactions
        accounts = account.objects.filter(
            entity=entity,
            accounthead__code__in=['4000', '7000', '8000']
        ).values(
            'id',
            'accountname',
            'accountcode',
            'gstno',
            'pan',
            'city__id',
            'state__id',
            'district__id',
            'pincode',
            'saccode'
        )

        for acc in accounts:
            aid = acc['id']
            if aid not in transaction_map:
                transaction_map[aid] = {
                    'id': aid,
                    'accountname': acc['accountname'],
                    'accountcode': acc['accountcode'],
                    'gstno': acc.get('gstno') or '',
                    'pancode': acc.get('pan') or '',
                    'city': acc.get('city__id'),
                    'state': acc.get('state__id'),
                    'district': acc.get('district__id'),
                    'pincode': acc.get('pincode') or '',
                    'saccode': acc.get('saccode') or '',
                    'balance': 0
                }

        final_data = []
        for entry in transaction_map.values():
            entry['drcr'] = 'CR' if entry['balance'] < 0 else 'DR'
            final_data.append(entry)

        final_data.sort(key=lambda x: x['accountname'])

        serializer = AccountBalanceSerializer(final_data, many=True)
        return Response(serializer.data)


    


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
        entity = request.data.get('entity')
        account_ids = request.data.get('account_ids')
        accounthead_ids = request.data.get('accounthead_ids')
        sort_by = request.data.get('sort_by', 'account')
        sort_order = request.data.get('sort_order', 'asc')
        top_n = request.data.get('top_n')
        download = request.query_params.get('download')  # ?download=xls

        if not entity:
            return Response({"error": "Entity is required"}, status=400)

        try:
            current_dates = entityfinancialyear.objects.get(entity=entity, isactive=1)
        except entityfinancialyear.DoesNotExist:
            return Response({"error": "Financial year not found for the entity"}, status=404)

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

        sort_field_map = {
            'account': 'accountname',
            'accounthead': 'daccountheadname'
        }
        sort_key = sort_field_map.get(sort_by, 'accountname')
        reverse_sort = sort_order.lower() == 'desc'
        final_data.sort(key=lambda x: x.get(sort_key, '').lower(), reverse=reverse_sort)

        if top_n:
            try:
                top_n = int(top_n)
                final_data = final_data[:top_n]
            except ValueError:
                pass

        # ======= XLS download logic =======
        if download == 'xls':
            response = HttpResponse(content_type='application/ms-excel')
            response['Content-Disposition'] = 'attachment; filename="account_report.xls"'

            wb = xlwt.Workbook(encoding='utf-8')
            ws = wb.add_sheet('Accounts')

            # Column headers
            columns = ['Account Name', 'Debit', 'Credit', 'GST No', 'PAN', 'City', 'Account Head', 'Credit Account Head', 'Balance', 'DR/CR', 'Can Be Deleted']
            for col_num, column_title in enumerate(columns):
                ws.write(0, col_num, column_title)

            # Data rows
            for row_num, row_data in enumerate(final_data, start=1):
                ws.write(row_num, 0, row_data['accountname'])
                ws.write(row_num, 1, row_data['debit'])
                ws.write(row_num, 2, row_data['credit'])
                ws.write(row_num, 3, row_data['accgst'])
                ws.write(row_num, 4, row_data['accpan'])
                ws.write(row_num, 5, row_data['cityname'])
                ws.write(row_num, 6, row_data['daccountheadname'])
                ws.write(row_num, 7, row_data['caccountheadname'])
                ws.write(row_num, 8, row_data['balance'])
                ws.write(row_num, 9, row_data['drcr'])
                ws.write(row_num, 10, 'Yes' if row_data['accanbedeleted'] else 'No')

            wb.save(response)
            return response

        # ======= JSON response (default) =======
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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Optimize list queries (avoids N+1 for names)
        return ShippingDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )

    def get_serializer_class(self):
        # Use list serializer for GET, base serializer for POST
        if self.request.method == "GET":
            return ShippingDetailsListSerializer
        return ShippingDetailsSerializer

    def perform_create(self, serializer):
        """
        If you want createdby to be set automatically (recommended),
        and entity auto-inferred from account if not passed.
        """
        serializer.save(createdby=self.request.user)

class ShippingDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ShippingDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )

    serializer_class = ShippingDetailsSerializer


class ContactDetailsListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ContactDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ContactDetailsListSerializer
        return ContactDetailsSerializer

    def perform_create(self, serializer):
        serializer.save(createdby=self.request.user)


class ContactDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContactDetailsSerializer

    def get_queryset(self):
        return ContactDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )


class ContactDetailsByAccountView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContactDetailsListSerializer

    def get_queryset(self):
        account_id = self.kwargs.get("account_id")
        return (
            ContactDetails.objects.select_related(
                "account", "entity", "country", "state", "district", "city"
            )
            .filter(account_id=account_id)
            .order_by("-isprimary", "id")
        )

# API View to Get Shipping Details by Account
class ShippingDetailsByAccountView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ShippingDetailsListSerializer

    def get_queryset(self):
        account_id = self.kwargs.get("account_id")

        return (
            ShippingDetails.objects.select_related(
                "account", "entity", "country", "state", "district", "city"
            )
            .filter(account_id=account_id)
            .order_by("-isprimary", "id")
            .only(
                "id", "account_id", "entity_id", "gstno",
                "address1", "address2", "pincode", "phoneno",
                "full_name", "emailid", "isprimary",
                "country_id", "state_id", "district_id", "city_id",
            )
        )


class ContactDetailsByAccountView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContactDetailsListSerializer

    def get_queryset(self):
        account_id = self.kwargs.get("account_id")

        return (
            ContactDetails.objects.select_related(
                "account", "entity", "country", "state", "district", "city"
            )
            .filter(account_id=account_id)
            .order_by("-isprimary", "id")
            .only(
                "id", "account_id", "entity_id",
                "address1", "address2", "pincode", "phoneno",
                "full_name", "emailid", "designation", "isprimary",
                "country_id", "state_id", "district_id", "city_id",
            )
        )


class StaticAccountsViewSet(ModelViewSet):
    """
    Replaces the APIView-based CRUD with proper REST patterns:
    - GET /static-accounts/          (list)
    - POST /static-accounts/         (create)
    - GET /static-accounts/{id}/     (retrieve)
    - PUT/PATCH /static-accounts/{id}/
    - DELETE /static-accounts/{id}/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StaticAccountsSerializer

    def get_queryset(self):
        # select_related avoids N+1 if you show these in UI
        return staticacounts.objects.select_related("accounttype", "entity")

    def perform_create(self, serializer):
        serializer.save(createdby=self.request.user)

    def perform_update(self, serializer):
        serializer.save(createdby=self.request.user)


class StaticAccountsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Avoid N+1
        return staticacounts.objects.select_related("accounttype", "entity")

    def get(self, request, pk=None):
        queryset = self.get_queryset()

        if pk:
            static_account = get_object_or_404(queryset, pk=pk)
            serializer = StaticAccountsSerializer(static_account)
            return Response(serializer.data)

        static_accounts = queryset.order_by("staticaccount")
        serializer = StaticAccountsSerializer(static_accounts, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = StaticAccountsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(createdby=request.user)  # ✅ auto set createdby
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        queryset = self.get_queryset()
        static_account = get_object_or_404(queryset, pk=pk)

        # ✅ allow partial update too (safer for front-end)
        serializer = StaticAccountsSerializer(static_account, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(createdby=request.user)  # ✅ update audit
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        queryset = self.get_queryset()
        static_account = get_object_or_404(queryset, pk=pk)
        static_account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

# =========================
# Static Account Mapping (List + bulk upsert)
# =========================
class StaticAccountMappingListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StaticAccountMappingSerializer

    def get_queryset(self):
        return staticacountsmapping.objects.select_related("staticaccount", "account", "entity")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Supports:
        - single payload {staticaccount, entity, account}
        - bulk payload   [{...}, {...}]

        Behavior:
        - If mapping exists (entity + staticaccount): update it
        - If account is null: delete existing mapping (if any)
        - If mapping doesn't exist and account is null: ignore
        """
        is_many = isinstance(request.data, list)
        data_list = request.data if is_many else [request.data]

        # Validate minimum keys early (fast fail)
        for item in data_list:
            if not item.get("staticaccount") or not item.get("entity"):
                return Response(
                    {"detail": "Both 'staticaccount' and 'entity' are required for each item."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Prefetch existing mappings in one query (OPTIMIZATION)
        static_ids = [i.get("staticaccount") for i in data_list]
        entity_ids = [i.get("entity") for i in data_list]

        existing = {
            (m.staticaccount_id, m.entity_id): m
            for m in staticacountsmapping.objects.filter(
                staticaccount_id__in=static_ids,
                entity_id__in=entity_ids,
            )
        }

        results = []

        for item in data_list:
            key = (item.get("staticaccount"), item.get("entity"))
            account_id = item.get("account", None)

            instance = existing.get(key)

            # Delete if account is null
            if account_id in (None, "", 0):
                if instance:
                    instance.delete()
                continue

            # Update existing
            if instance:
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save(createdby=request.user)
                results.append(serializer.data)
                continue

            # Create new
            serializer = self.get_serializer(data=item)
            serializer.is_valid(raise_exception=True)
            serializer.save(createdby=request.user)
            results.append(serializer.data)

        return Response(results, status=status.HTTP_200_OK)


class StaticAccountMappingRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StaticAccountMappingSerializer

    def get_queryset(self):
        return staticacountsmapping.objects.select_related("staticaccount", "account", "entity")

    def perform_update(self, serializer):
        serializer.save(createdby=self.request.user)



class StaticAccountFlatListView(ListAPIView):
    permission_classes = [IsAuthenticated]

    # returns list(dict) not model instances, so no serializer needed
    serializer_class = None

    def list(self, request, *args, **kwargs):
        entity_id = request.query_params.get("entity")
        accounttype_id = request.query_params.get("accounttype")

        if not entity_id:
            return Response({"detail": "entity is required"}, status=status.HTTP_400_BAD_REQUEST)

        mapping_qs = staticacountsmapping.objects.filter(
            staticaccount=OuterRef("pk"),
            entity_id=entity_id,
        ).values("account_id")[:1]

        base_filter = Q()
        if accounttype_id:
            base_filter &= Q(accounttype_id=accounttype_id)

        qs = (
            staticacounts.objects.filter(base_filter)
            .annotate(
                staticaccountid=F("id"),
                staticaccountname=F("staticaccount"),
                accountid=Subquery(mapping_qs),
            )
            .values("staticaccountid", "staticaccountname", "accountid")
            .order_by("staticaccountname")
        )

        return Response(list(qs))
    

class TopAccountHeadAPIView(APIView):
    def get(self, request):
        accounttype_id = request.query_params.get('accounttype')
        entity_id = request.query_params.get('entityid')

        if not accounttype_id or not entity_id:
            return Response({"detail": "Missing required parameters: accounttype and entityid"}, status=status.HTTP_400_BAD_REQUEST)

        account_head = (
            accountHead.objects
            .filter(accounttype_id=accounttype_id, entity_id=entity_id)
            .order_by('id')  # ensures consistent "first" record
            .first()
        )

        if account_head:
            serializer = AccountHeadMinimalSerializer(account_head)
            return Response(serializer.data)
        else:
            return Response({"detail": "No account head found"}, status=status.HTTP_404_NOT_FOUND)
        



class AccountHeadListByEntityAPIView(APIView):
    def get(self, request, entity_id):
        credit_heads = accountHead.objects.filter(entity_id=entity_id, balanceType='Credit')
        debit_heads = accountHead.objects.filter(entity_id=entity_id, balanceType='Debit')

        credit_data = AccountHeadListSerializer(credit_heads, many=True).data
        debit_data = AccountHeadListSerializer(debit_heads, many=True).data

        return Response({
            "credit": credit_data,
            "debit": debit_data
        }, status=status.HTTP_200_OK)


    

