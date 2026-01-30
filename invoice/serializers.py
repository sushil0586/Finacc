
#import imp
from itertools import product
from os import device_encoding
from pprint import isreadable
import logging
from select import select
from typing import Optional
from .models import account as Account, journaldetails as JournalDetails
from typing import Optional, Any, TYPE_CHECKING

from rest_framework import serializers
from invoice.models import SalesOderHeader,SalesOder,salesOrderdetails,salesOrderdetail,purchaseorder,PurchaseOrderDetails,\
    journal,salereturn,salereturnDetails,Transactions,StockTransactions,PurchaseReturn,Purchasereturndetails,journalmain,journaldetails,entry,goodstransaction,stockdetails,stockmain,accountentry,purchasetaxtype,tdsmain,tdstype,productionmain,productiondetails,tdsreturns,gstorderservices,gstorderservicesdetails,jobworkchalan,jobworkchalanDetails,debitcreditnote,closingstock,saleothercharges,purchaseothercharges,salereturnothercharges,Purchasereturnothercharges,purchaseotherimportcharges,purchaseorderimport,PurchaseOrderimportdetails,newPurchaseOrderDetails,newpurchaseorder,InvoiceType,PurchaseOrderAttachment,gstorderservicesAttachment,purchaseotherimporAttachment,defaultvaluesbyentity,Paymentmodes,SalesInvoiceSettings,PurchaseSettings, ReceiptSettings,doctype,EInvoiceDetails,ExpDtls,RefDtls,AddlDocDtls,PayDtls,EwbDtls,TxnType,SalesQuotationDetail,SalesQuotationHeader,DetailKind,VoucherType 
from financial.models import account,accountHead,ShippingDetails,staticacounts,staticacountsmapping
from catalog.models import Product,ProductPrice,ProductGstRate
from django.db.models import Sum,Count,F, Case, When, FloatField, Q
from datetime import timedelta,date,datetime
from entity.models import Entity,entityfinancialyear,Mastergstdetails,subentity
from django.db.models.functions import Abs
from num2words import num2words
import string
from django.db import  transaction,IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
import requests
import json
import pandas as pd
from django_pandas.io import read_frame
import numpy as np
import entity.views as entityview
from django.db.models import Prefetch,Max
from django.utils import timezone
from helpers.utils.document_number import reset_counter_if_needed, build_document_number
#from entity.views import generateeinvoice
#from entity.serializers import entityfinancialyearSerializer
from django.db import models
from helpers.utils.pdf import render_to_pdf
from helpers.utils.email import send_invoice_email
from helpers.utils.gst_api import gstinvoice,gst_ewaybill,cancel_gst_invoice
from django.contrib.contenttypes.models import ContentType
import base64
import qrcode
from io import BytesIO
from decimal import Decimal,ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from .posting import Poster
from invoice.models import TxnType
from invoice.models import entry as EntryModel  # adjust
from rest_framework.exceptions import ValidationError
from typing import List, Optional
from django.db.models import Sum, F, Value as V
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from django.db.models import (
    Sum, F, Q, Value, DecimalField, Case, When, ExpressionWrapper
)
from django.db.models.functions import Cast, Coalesce

if TYPE_CHECKING:
    from .models import journalmain as JournalMain
    from .models import journaldetails as JournalDetails
    from .models import account as Account

class PaymentmodesSerializer(serializers.ModelSerializer):

    paymentmodeid = serializers.IntegerField(source= 'id', read_only=True)
    paymentmodename = serializers.CharField(source= 'paymentmode', read_only=True)


    class Meta:
        model = Paymentmodes
        fields = ['paymentmodeid', 'paymentmodename']


class InvoiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceType
        fields = ['id', 'invoicetype', 'invoicetypecode', 'entity', 'createdby']
        read_only_fields = ['id', 'createdby']


class DefaultValuesByEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = defaultvaluesbyentity
        fields = '__all__'  # Include all fields


class DefaultValuesByEntitySerializerlist(serializers.ModelSerializer):
    class Meta:
        model = defaultvaluesbyentity
        fields = ('taxtype', 'invoicetype', 'subentity') # Include all fields



# Base Serializer to handle common update logic

# ----------------------------------------------------------------------
# CANCEL / VOID SERIALIZERS (de-duplicated)
# ----------------------------------------------------------------------

class CancelSerializerBase(serializers.ModelSerializer):
    """
    Generic cancel serializer:
      - toggles `isactive`
      - optionally stores `cancelreason` (if the model has it)
      - optional hooks for stock-txn and e-invoice cancellation
    """
    def update(self, instance, validated_data):
        # Update only fields present in payload
        if "isactive" in validated_data:
            instance.isactive = validated_data["isactive"]

        if "cancelreason" in validated_data and hasattr(instance, "cancelreason"):
            instance.cancelreason = validated_data["cancelreason"]

        # some docs use vouchertype/orderType in cancel endpoints
        if "vouchertype" in validated_data and hasattr(instance, "vouchertype"):
            instance.vouchertype = validated_data["vouchertype"]

        instance.save()
        return instance


class StockTxnCancelMixin:
    """
    Updates StockTransactions.isactive for the given transactiontype code.
    Set either:
      - transactiontype_code = 'S'/'P'/'PR'/...
      - or override get_transactiontype_code(instance)
    """
    transactiontype_code = None

    def get_transactiontype_code(self, instance):
        return self.transactiontype_code

    def _update_stock_transactions(self, instance):
        code = self.get_transactiontype_code(instance)
        if not code:
            return

        StockTransactions.objects.filter(
            entity=getattr(instance, "entity", None) or getattr(instance, "entityid", None),
            transactionid=instance.id,
            transactiontype=code
        ).update(isactive=instance.isactive)


class EntryEnsureMixin:
    """
    Ensures an `entry` record exists for a date field (voucherdate/orderdate/etc.).
    Override entry_date_attr and entry_entity_attr if needed.
    """
    entry_date_attr = None
    entry_entity_attr = "entity"

    def _ensure_entry(self, instance):
        if not self.entry_date_attr:
            return
        dt = getattr(instance, self.entry_date_attr, None)
        ent = getattr(instance, self.entry_entity_attr, None)
        if dt and ent:
            entry.objects.get_or_create(entrydate1=dt, entity=ent)


class EInvoiceCancelMixin:
    """
    Cancels IRN on GST portal (if EInvoiceDetails exists for this instance),
    and updates EInvoiceDetails.status/cancelleddate.
    """
    cancel_reason_code = "1"

    def _cancel_einvoice_if_any(self, instance):
        content_type = ContentType.objects.get_for_model(instance)
        einv = EInvoiceDetails.objects.filter(content_type=content_type, object_id=instance.id).first()
        if not einv:
            return

        cancel_remark = getattr(instance, "cancelreason", None) or "Cancelled by user"
        gst_response = cancel_gst_invoice(einv.irn, self.cancel_reason_code, cancel_remark)

        # GST API returns {"status_cd":"1"} on success (per your current implementation)
        if gst_response.get("status_cd") != "1":
            status_desc = gst_response.get("status_desc", "")
            error_message = status_desc or "E-Invoice cancellation failed"

            # Sometimes status_desc is a JSON string: '[{"ErrorCode":"9999","ErrorMessage":"..."}]'
            try:
                import json
                parsed = json.loads(status_desc)
                if isinstance(parsed, list) and parsed:
                    error_message = parsed[0].get("ErrorMessage", error_message)
            except Exception:
                pass

            raise serializers.ValidationError({"error": error_message})

        # Extract cancellation date (best-effort)
        cancel_date = None
        cancel_date_str = (gst_response.get("data", {}) or {}).get("CancelDate")
        if cancel_date_str:
            try:
                cancel_date = datetime.strptime(cancel_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                cancel_date = None

        EInvoiceDetails.objects.update_or_create(
            content_type=content_type,
            object_id=instance.id,
            defaults={"cancelleddate": cancel_date, "status": "CNL"},
        )


# ---- Concrete cancel serializers --------------------------------------

class TdsmaincancelSerializer(EntryEnsureMixin, StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "T"
    entry_date_attr = "voucherdate"
    entry_entity_attr = "entityid"

    class Meta:
        model = tdsmain
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._ensure_entry(instance)
        self._update_stock_transactions(instance)
        return instance


class SaleinvoicecancelSerializer(EInvoiceCancelMixin, StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "S"

    class Meta:
        model = SalesOderHeader
        fields = ("isactive", "cancelreason",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._cancel_einvoice_if_any(instance)
        self._update_stock_transactions(instance)
        return instance


class PurchaseinvoicecancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "P"

    class Meta:
        model = purchaseorder
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance


class PurchasereturncancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "PR"

    class Meta:
        model = PurchaseReturn
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance


class SalesreturncancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "SR"

    class Meta:
        model = salereturn
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance


class PurchaseimportcancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "P"

    class Meta:
        model = purchaseorderimport
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance


class StockcancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    transactiontype_code = "PC"

    class Meta:
        model = closingstock
        fields = ("isactive",)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance




class SalesordercancelSerializer(CancelSerializerBase):
    class Meta:
        model = SalesOder
        fields = ("isactive",)


class PurchaseordercancelSerializer(CancelSerializerBase):
    class Meta:
        model = newpurchaseorder
        fields = ("isactive",)


class JobworkchallancancelSerializer(CancelSerializerBase):
    class Meta:
        model = jobworkchalan
        fields = ("isactive",)


class GstorderservicecancelSerializer(EntryEnsureMixin, StockTxnCancelMixin, CancelSerializerBase):
    entry_date_attr = "orderdate"

    class Meta:
        model = gstorderservices
        fields = ("isactive",)

    def get_transactiontype_code(self, instance):
        return getattr(instance, "orderType", None)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._ensure_entry(instance)
        self._update_stock_transactions(instance)
        return instance


class JournalcancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    class Meta:
        model = journalmain
        fields = ("isactive", "vouchertype",)

    def get_transactiontype_code(self, instance):
        return getattr(instance, "vouchertype", None)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance


class ProductioncancelSerializer(StockTxnCancelMixin, CancelSerializerBase):
    class Meta:
        model = productionmain
        fields = ("isactive", "vouchertype",)

    def get_transactiontype_code(self, instance):
        return getattr(instance, "vouchertype", None)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._update_stock_transactions(instance)
        return instance

class tdsmainSerializer(serializers.ModelSerializer):
    class Meta:
        model = tdsmain
        fields = '__all__'

    def _create_stock_transaction(self, tds, entryid, drcr, creditamount, debitamount):
        return StockTransactions(
            accounthead=tds.creditaccountid.accounthead,
            account=tds.creditaccountid,
            transactiontype='T',
            transactionid=tds.id,
            desc=f'By Tds Voucher no {tds.voucherno}',
            drcr=drcr,
            creditamount=creditamount,
            debitamount=debitamount,
            entity=tds.entityid,
            createdby=tds.createdby,
            entry=entryid,
            entrydatetime=tds.voucherdate,
            accounttype='M',
            voucherno=tds.voucherno
        )

    def _create_or_update_transactions(self, tds, entryid):
        transactions = [
            self._create_stock_transaction(tds, entryid, 0, tds.debitamount, None),  # DR transaction
            self._create_stock_transaction(tds, entryid, 1, None, tds.grandtotal),  # CR transaction
            self._create_stock_transaction(tds, entryid, 1, None, tds.debitamount),  # DR transaction (debit account)
            self._create_stock_transaction(tds, entryid, 0, tds.grandtotal, None)  # CR transaction (TDS account)
        ]
        # Use bulk_create for batch insertion
        StockTransactions.objects.bulk_create(transactions)

    def create(self, validated_data):
        with transaction.atomic():
            tds = tdsmain.objects.create(**validated_data)
            entryid, created = entry.objects.get_or_create(entrydate1=tds.voucherdate, entity=tds.entityid)
            self._create_or_update_transactions(tds, entryid)
        return tds

    def update(self, instance, validated_data):
        fields = [
            'voucherdate', 'voucherno', 'creditaccountid', 'creditdesc', 'debitaccountid', 'debitdesc',
            'tdsaccountid', 'tdsdesc', 'tdsreturnccountid', 'tdsreturndesc', 'tdstype', 'amount', 'debitamount',
            'otherexpenses', 'tdsrate', 'tdsvalue', 'surchargerate', 'surchargevalue', 'cessrate', 'cessvalue',
            'hecessrate', 'hecessvalue', 'grandtotal', 'vehicleno', 'grno', 'invoiceno', 'grdate', 'invoicedate',
            'weight', 'depositdate', 'chequeno', 'ledgerposting', 'chalanno', 'bank', 'entityid', 'isactive', 'createdby'
        ]
        
        # Efficient field assignment
        for field in fields:
            value = validated_data.get(field)
            if value is not None:
                setattr(instance, field, value)

        with transaction.atomic():
            instance.save()
            entryid, created = entry.objects.get_or_create(entrydate1=instance.voucherdate, entity=instance.entityid)
            # Delete old transactions before creating new ones
            StockTransactions.objects.filter(entity=instance.entityid, transactionid=instance.id).delete()
            self._create_or_update_transactions(instance, entryid)

        return instance



class tdstypeSerializer(serializers.ModelSerializer):


   # pcategoryname = serializers.SerializerMethodField()

    class Meta:
        model = tdstype
        fields = ('id','tdstypename','tdssection','tdsreturn',)



class tdsreturnSerializer(serializers.ModelSerializer):


   # pcategoryname = serializers.SerializerMethodField()

    class Meta:
        model = tdsreturns
        fields =('id','tdsreturnname',)








class purchasetaxtypeserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = purchasetaxtype
        fields = ('id','taxtypename','taxtypecode',)


class stocktransconstant:

    def get_account_by_static_code(self, pentity, code):
        try:
            static_account = staticacounts.objects.get(code=code)
            mapping = staticacountsmapping.objects.get(staticaccount=static_account, entity=pentity)
            return mapping.account
        except (staticacounts.DoesNotExist, staticacountsmapping.DoesNotExist):
            return None

    def getcgst(self, pentity):
        return self.get_account_by_static_code(pentity, '6001')

    def getsgst(self, pentity):
        return self.get_account_by_static_code(pentity, '6002')

    def getigst(self, pentity):
        return self.get_account_by_static_code(pentity, '6003')

    def getcgstr(self, pentity):
        return self.get_account_by_static_code(pentity, '6005')

    def getsgstr(self, pentity):
        return self.get_account_by_static_code(pentity, '6006')

    def getigstr(self, pentity):
        return self.get_account_by_static_code(pentity, '6007')

    def getcessid(self, pentity):
        return self.get_account_by_static_code(pentity, '6004')

    def gettcs206c1ch2id(self, pentity):
        return self.get_account_by_static_code(pentity, '8050')

    def gettcs206C2id(self, pentity):
        return self.get_account_by_static_code(pentity, '8051')

    def gettds194q1id(self, pentity):
        return self.get_account_by_static_code(pentity, '8100')

    def getexpensesid(self, pentity):
        return self.get_account_by_static_code(pentity, '8300')

    def getcashid(self, pentity):
        return self.get_account_by_static_code(pentity, '4000')
    
    def getdiscount(self, pentity):
        return self.get_account_by_static_code(pentity, '8400')
    
    def getbankcharges(self, pentity):
        return self.get_account_by_static_code(pentity, '8500')
    
    def getroundoffincome(self, pentity):
        return self.get_account_by_static_code(pentity, '6012')
    
    def getroundoffexpnses(self, pentity):
        return self.get_account_by_static_code(pentity, '6011')

    
    def gettdsreturnid(self):
        return tdsreturns.objects.get(tdsreturnname = '26Q TDS')
    

    def gettdstypeid(self):
        return tdstype.objects.get(tdssection = '194Q')     

    
    def gettdsvbono(self,pentity):
        if tdsmain.objects.filter(entityid= pentity).count() == 0:
                tdsvbo = 1
        else:
                tdsvbo = tdsmain.objects.filter(entityid= pentity).last().voucherno + 1
        
        return tdsvbo



class einvoicebody:
    def __init__(self,order,invoicetype):

        self.order = order
        self.invoicetype = invoicetype




    def transactiondetails(self):

        transdetails = {}
        transdetails['TaxSch'] = 'GST'
        transdetails['SupTyp']  = 'B2B'
        transdetails['RegRev']  = 'Y'
        transdetails['EcmGstin']  = None
        transdetails['IgstOnIntra']  = 'N'


        transdetails = json.dumps(transdetails)

     
        return transdetails
         


         

    
    def docdetails(self):


        docdetails = {}
        docdetails['Typ'] = self.invoicetype
        docdetails['No']  = self.order.billno
        docdetails['Dt']  = '08/08/2024'


        docdetails = json.dumps(docdetails)
   
        return docdetails

    def getsellerdetails(self):

        selldetails = Entity.objects.filter(id = self.order.entity.id).values('gstno','legalname','entityname','address','address2','city__cityname','city__pincode','state__statecode','phoneoffice','email')
        df = read_frame(selldetails)
        df.rename(columns = {'gstno':'Gstin','legalname':'LglNm','entityname':'TrdNm','address':'Addr1','address2':'Addr2','city__cityname':'Loc','city__pincode':'Pin','state__statecode':'Stcd','phoneoffice':'Ph','email':'Em'}, inplace = True)
        sellerdetails = df.to_json(orient='records')
        return sellerdetails
    

    def getbuyerdetails(self):

        buyerdetails = account.objects.filter(id = self.order.accountid.id).values('gstno','legalname','accountname','address1','address2','city__cityname','city__pincode','state__statecode','contactno','emailid')
        df = read_frame(buyerdetails)
        df.rename(columns = {'gstno':'Gstin','legalname':'LglNm','accountname':'TrdNm','address1':'Addr1','address2':'Addr2','city__cityname':'Loc','city__pincode':'Pin','state__statecode':'Stcd','contactno':'Ph','emailid':'Em'}, inplace = True)
        buyerdetails = df.to_json(orient='records')
       # df = pd.DataFrame(entitydetails)
       # df = read_frame(buyerdetails)


        return buyerdetails

    
    def getdispatchdetails(self):

        dispatchdetails = Entity.objects.filter(id = self.order.entity.id).values('entityname','address','address2','city__cityname','city__pincode','state__statecode')
        df = read_frame(dispatchdetails)
        df.rename(columns = {'entityname':'Nm','address':'Addr1','address2':'Addr2','city__cityname':'Loc','city__pincode':'Pin','state__statecode':'Stcd'}, inplace = True)
        dispatchdetails = df.to_json(orient='records')

      
    #    dispatchdetails = df.to_json(orient='records')
      


        return dispatchdetails


    def getshippingdetails(self):

        shippingdetails = account.objects.filter(id = self.order.accountid.id).values('gstno','legalname','accountname','address1','address2','city__cityname','city__pincode','state__statecode')
        df = read_frame(shippingdetails)
        df.rename(columns = {'gstno':'Gstin','legalname':'LglNm','accountname':'TrdNm','address1':'Addr1','address2':'Addr2','city__cityname':'Loc','city__pincode':'Pin','state__statecode':'Stcd'}, inplace = True)
        shippingdetails = df.to_json(orient='records')
        return shippingdetails


        
    def getitemlistdetails(self):

        itemdetails = salesOrderdetails.objects.filter(salesorderheader = self.order.id).values('product','isService','product__hsn__hsnCode','orderqty','pieces','product__unitofmeasurement__unitname','rate','amount','cgst','sgst','igst','cess','product__totalgst','linetotal','othercharges')
        df = pd.DataFrame(itemdetails)
        df.rename(columns = {'product':'PrdDesc','isService':'IsServc','product__hsn__hsnCode':'HsnCd','orderqty':'orderqty','pieces':'pieces','product__unitofmeasurement__unitname':'Unit','rate':'UnitPrice','amount':'TotAmt','cgst':'CgstAmt','sgst':'SgstAmt','igst':'IgstAmt','cess':'CesAmt','linetotal':'TotItemVal','product__totalgst':'GstRt','othercharges':'OthChrg'}, inplace = True)
        df['SlNo'] = np.arange(df.shape[0])
        itemdetails = df.to_json(orient='records')
        return itemdetails
    
    def getvaluedetails(self):
        valuedetails = SalesOderHeader.objects.filter(id = self.order.id).values('subtotal','cgst','sgst','igst','cess','gtotal')
        df = pd.DataFrame(valuedetails)
        df.rename(columns = {'subtotal':'AssVal','cgst':'CgstVal','sgst':'SgstVal','igst':'IgstVal','cess':'CesVal','gtotal':'TotInvVal'}, inplace = True)
        # df['SlNo'] = np.arange(df.shape[0])
        valuedetails = df.to_json(orient='records')
        return valuedetails


                 







    def createeinvoce(self):

        try:
                mgst = Mastergstdetails.objects.get()
                #mgst = Mastergstdetails.objects.get(gstin = entitygst)
        except Mastergstdetails.DoesNotExist:
                mgst = None
                return 1
          
          #  mgst = Mastergstdetails.objects.get(gstin = entitygst)
        einv = entityview.generateeinvoice(mgst)
        response = einv.getauthentication().json()

        authtoken = response["data"]["AuthToken"]

        authheader = einv.getheaderdetails(authtoken)


        print(authheader)



        json_data = {}
        json_data["Version"] = '1.1'
        transactiondetails = self.transactiondetails()
        docdetails = self.docdetails()
        sellerdetails = self.getsellerdetails()
        buyerdetails= self.getbuyerdetails()
        dispatchdetails = self.getdispatchdetails()
        shippingdetails = self.getshippingdetails()
        itemdetails = self.getitemlistdetails()
        valuedetails = self.getvaluedetails()

        json_data['TranDtls'] = json.loads(transactiondetails)
        json_data['DocDtls'] = json.loads(docdetails)
        json_data['SellerDtls'] = json.loads(sellerdetails)[0]
        json_data['BuyerDtls'] = json.loads(buyerdetails)[0]
        json_data['dispatchdetails'] = json.loads(dispatchdetails)[0]
        json_data['shippingdetails'] = json.loads(shippingdetails)[0]
        json_data['itemdetails'] = json.loads(itemdetails)
        json_data['ValDtls'] = json.loads(valuedetails)[0]


        print(json_data)



        url = "https://api.mastergst.com/einvoice/type/GENERATE/version/V1_03?email=sushiljyotibansal@gmail.com"

        print(url)



        response = requests.post(url,headers= authheader,json=json.dumps(json_data))

        # print(type(response))


        # print(response.json())



        print(json.dumps(json_data))

     #   print(docdetails)

        return docdetails
        

        







# class generateeinvoice:

#     def __init__(self,mastergst):
#         self.mastergst = mastergst
#         self.ipaddress = '10.105.87.909'
#         self.username = self.mastergst.username
#         self.headers = json.dumps({ 
#                               'Content-Type': 'application/json',
#                               'username':self.username,
#                               'password':self.mastergst.password,
#                               'ip_address': self.ipaddress,
#                               'client_id': self.mastergst.client_id,
#                               'client_secret': self.mastergst.client_secret,
#                               'gstin': self.mastergst.gstin}, indent=4)
        


#         # print(self.headers)
#         # print(type(self.headers))

#         self.headers = json.loads(self.headers)



        

        


#     def getauthentication(self):



#         BASE_URL = 'https://api.mastergst.com/einvoice/authenticate'

    
        

#         print(f"{BASE_URL}?email=aditi.gupta1789@gmail.com")

#         response = requests.get(f"{BASE_URL}?email=aditi.gupta1789@gmail.com", headers= self.headers)

#         print(response)


#         return response

    

      







class stocktransactionimport:
    def __init__(self, order,transactiontype,debit,credit,description,entrytype):
        self.order = order
        self.transactiontype = transactiontype
        self.debit = debit
        self.credit = credit
        self.description = description
        self.entrytype = entrytype
    
    def createtransaction(self):
        id = self.order.id
        subtotal = self.order.subtotal
        # cgst = self.order.cgst
        # sgst = self.order.sgst
        igst = self.order.igst
        # cgstcess = self.order.cgstcess
        # sgstcess = self.order.sgstcess
        cess = self.order.cess
        
        pentity = self.order.entity
        tcs206c1ch2 = self.order.tcs206c1ch2
        tcs206C2 = self.order.tcs206C2
        tds194q1 = self.order.tds194q1
        expenses = self.order.expenses
        gtotal = self.order.gtotal - round(tcs206c1ch2) - round(tcs206C2)

        const = stocktransconstant()

        # cgstid = const.getcgst(pentity)
        igstid = const.getigst(pentity)
        #sgstid = const.getsgst(pentity)
        cessid = const.getcessid(pentity)
        tcs206c1ch2id = const.gettcs206c1ch2id(pentity)
        tcs206C2id = const.gettcs206C2id(pentity)
        tds194q1id = const.gettds194q1id(pentity)
        expensesid = const.getexpensesid(pentity)
        entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

        iscash = False

        if self.entrytype == 'U':
            StockTransactions.objects.filter(entity = pentity,transactiontype = self.transactiontype,transactionid= id).delete()

        if self.order.billcash == 0:
            iscash = True
            cash = const.getcashid(pentity)
                
            StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = self.transactiontype,transactionid = id,desc = 'Cash Credit Purchase V.No : ' + str(self.order.voucherno),drcr=0,creditamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype='CIH',iscashtransaction= iscash,voucherno = self.order.voucherno)
            StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = ' Cash Purchase By V.No : ' + str(self.order.voucherno),drcr=1,debitamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',iscashtransaction = iscash,voucherno = self.order.voucherno)

       
        StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
        #Transactions.objects.create(account= purchaseid,transactiontype = 'P',transactionid = id,desc = 'Purchase from',drcr=1,amount=subtotal,entity=pentity,createdby = order.createdby )
        if igst > 0:
            StockTransactions.objects.create(accounthead = igstid.accounthead, account= igstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=igst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        # if cgst > 0:
        #     StockTransactions.objects.create(accounthead = cgstid.accounthead, account= cgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        # if sgst > 0:
        #     StockTransactions.objects.create(accounthead = sgstid.accounthead,account= sgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.debit,debitamount=sgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        # if cess > 0:
        #     StockTransactions.objects.create(accounthead = cessid.accounthead, account= cessid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cess,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        
        if tcs206c1ch2 > 0:
            StockTransactions.objects.create(accounthead = tcs206c1ch2id.accounthead, account= tcs206c1ch2id,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=tcs206c1ch2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
            StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=tcs206c1ch2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
        
        if tcs206C2 > 0:
            StockTransactions.objects.create(accounthead = tcs206C2id.accounthead, account= tcs206C2id,transactiontype = self.transactiontype,transactionid = id,desc = 'TCS206:' +  self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=tcs206C2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
            StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = 'TCS206:' + self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=tcs206C2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
        if expenses > 0:
            StockTransactions.objects.create(accounthead = expensesid.accounthead, account= expensesid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=expenses,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)

        if tds194q1 > 0:
            tdsvbo  = const.gettdsvbono(pentity)

            # if tdsmain.objects.filter(entityid= pentity).count() == 0:
            #     tdsvbo = 1
            # else:
            #     tdsvbo = tdsmain.objects.filter(entityid= pentity).last().voucherno + 1


            tdsreturnid = const.gettdsreturnid()
            tdstypeid = const.gettdstypeid()
            tds = tdsmain.objects.create(voucherdate = self.order.billdate,voucherno = tdsvbo,creditaccountid= self.order.account,debitaccountid = tds194q1id,tdsaccountid = tds194q1id,tdsreturnccountid =tdsreturnid,tdstype=tdstypeid,debitamount = subtotal,tdsrate = self.order.tds194q,entityid= pentity,transactiontype = self.transactiontype,transactionno = id,tdsvalue = tds194q1)
            StockTransactions.objects.create(accounthead = tds194q1id.accounthead, account= tds194q1id,transactiontype = 'T',transactionid = tds.id,desc = 'TDS194Q:' + self.description + ' ' + str(self.order.voucherno) ,drcr=self.credit,creditamount=tds194q1,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
            StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = 'TDS194Q:' + self.description + ' ' + str(self.order.voucherno),drcr=self.debit,debitamount=tds194q1,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)



        return id

    


    def createtransactiondetails(self,detail,stocktype):

        if (detail.orderqty ==0.00):
                qty = detail.pieces
        else:
                qty = detail.orderqty

        entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

        details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.actualamount,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
        details1 = StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.actualamount,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'MD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
        return details

    
    # def createothertransactiondetails(self,detail,stocktype):

        

    #     entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

    #   #  details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
    #     details1 = StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,drcr = self.debit,debitamount = detail.amount ,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'M',isactive = self.order.isactive,voucherno = self.order.voucherno)
    #     return details1
        

    





# class stocktransaction:
#     def __init__(self, order,transactiontype,debit,credit,description,entrytype):
#         self.order = order
#         self.transactiontype = transactiontype
#         self.debit = debit
#         self.credit = credit
#         self.description = description
#         self.entrytype = entrytype
    
#     def createtransaction(self):
#         id = self.order.id
#         subtotal = self.order.subtotal
#         cgst = self.order.cgst
#         sgst = self.order.sgst
#         igst = self.order.igst
#         # cgstcess = self.order.cgstcess
#         # sgstcess = self.order.sgstcess
#         cess = self.order.cess
        
#         pentity = self.order.entity
#         tcs206c1ch2 = self.order.tcs206c1ch2
#         tcs206C2 = self.order.tcs206C2
#         tds194q1 = self.order.tds194q1
#         expenses = self.order.expenses
#         roundOff = self.order.roundOff
#         gtotal = self.order.gtotal - round(tcs206c1ch2) - round(tcs206C2)

#         const = stocktransconstant()

#         cgstid = const.getcgst(pentity)
#         igstid = const.getigst(pentity)
#         sgstid = const.getsgst(pentity)
#         cessid = const.getcessid(pentity)
#         tcs206c1ch2id = const.gettcs206c1ch2id(pentity)
#         tcs206C2id = const.gettcs206C2id(pentity)
#         tds194q1id = const.gettds194q1id(pentity)
#         expensesid = const.getexpensesid(pentity)
#         entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

#         iscash = False

#         if self.entrytype == 'U':
#             StockTransactions.objects.filter(entity = pentity,transactiontype = self.transactiontype,transactionid= id).delete()

#         if self.order.billcash == 0:
#             iscash = True
#             cash = const.getcashid(pentity)

                
#             StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = self.transactiontype,transactionid = id,desc = 'Cash Credit Purchase V.No : ' + str(self.order.voucherno),drcr=0,creditamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype='CIH',iscashtransaction= iscash,voucherno = self.order.voucherno)
#             StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = ' Cash Purchase By V.No : ' + str(self.order.voucherno),drcr=1,debitamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',iscashtransaction = iscash,voucherno = self.order.voucherno)

#         if roundOff != 0:
#             if roundOff > 0:
#                 roundoffid = const.getroundoffexpnses(pentity)
#                 StockTransactions.objects.create(accounthead = roundoffid.accounthead, account= roundoffid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=abs(roundOff),entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)

#             if roundOff < 0:
#                 roundoffid = const.getroundoffincome(pentity)
#                 StockTransactions.objects.create(accounthead = roundoffid.accounthead, account= roundoffid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.credit,creditamount=abs(roundOff),entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)



#         StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=gtotal,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
#         #Transactions.objects.create(account= purchaseid,transactiontype = 'P',transactionid = id,desc = 'Purchase from',drcr=1,amount=subtotal,entity=pentity,createdby = order.createdby )
#         if igst > 0:
#             StockTransactions.objects.create(accounthead = igstid.accounthead, account= igstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=igst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#         if cgst > 0:
#             StockTransactions.objects.create(accounthead = cgstid.accounthead, account= cgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#         if sgst > 0:
#             StockTransactions.objects.create(accounthead = sgstid.accounthead,account= sgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.debit,debitamount=sgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#         if cess > 0:
#             StockTransactions.objects.create(accounthead = cessid.accounthead, account= cessid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cess,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        
#         if tcs206c1ch2 > 0:
#             StockTransactions.objects.create(accounthead = tcs206c1ch2id.accounthead, account= tcs206c1ch2id,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=tcs206c1ch2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#             StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=tcs206c1ch2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
        
#         if tcs206C2 > 0:
#             StockTransactions.objects.create(accounthead = tcs206C2id.accounthead, account= tcs206C2id,transactiontype = self.transactiontype,transactionid = id,desc = 'TCS206:' +  self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=tcs206C2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#             StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = 'TCS206:' + self.description + ' ' + str(self.order.voucherno),drcr=self.credit,creditamount=tcs206C2,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)
#         if expenses > 0:
#             StockTransactions.objects.create(accounthead = expensesid.accounthead, account= expensesid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=expenses,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)

#         if tds194q1 > 0:
#             tdsvbo  = const.gettdsvbono(pentity)

#             # if tdsmain.objects.filter(entityid= pentity).count() == 0:
#             #     tdsvbo = 1
#             # else:
#             #     tdsvbo = tdsmain.objects.filter(entityid= pentity).last().voucherno + 1


#             tdsreturnid = const.gettdsreturnid()
#             tdstypeid = const.gettdstypeid()
#             tds = tdsmain.objects.create(voucherdate = self.order.billdate,voucherno = tdsvbo,creditaccountid= self.order.account,debitaccountid = tds194q1id,tdsaccountid = tds194q1id,tdsreturnccountid =tdsreturnid,tdstype=tdstypeid,debitamount = subtotal,tdsrate = self.order.tds194q,entityid= pentity,transactiontype = self.transactiontype,transactionno = id,tdsvalue = tds194q1)
#             StockTransactions.objects.create(accounthead = tds194q1id.accounthead, account= tds194q1id,transactiontype = 'T',transactionid = tds.id,desc = 'TDS194Q:' + self.description + ' ' + str(self.order.voucherno) ,drcr=self.credit,creditamount=tds194q1,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
#             StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,transactiontype = self.transactiontype,transactionid = id,desc = 'TDS194Q:' + self.description + ' ' + str(self.order.voucherno),drcr=self.debit,debitamount=tds194q1,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,accounttype = 'M',voucherno = self.order.voucherno)



#         return id

    


#     def createtransactiondetails(self,detail,stocktype):

#         if (detail.orderqty ==0.00):
#                 qty = detail.pieces
#         else:
#                 qty = detail.orderqty

#         entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

#         details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
#         details1 = StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'MD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
#         return details

    
#     def createothertransactiondetails(self,detail,stocktype):

        

#         entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

#       #  details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
#         details1 = StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,drcr = self.debit,debitamount = detail.amount ,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'M',isactive = self.order.isactive,voucherno = self.order.voucherno)
#         return details1
    

    

    



TXN_MAP = {
    'S': TxnType.SALES,
    'SR': TxnType.SALES_RETURN,
    'P': TxnType.PURCHASE,
    'PR': TxnType.PURCHASE_RETURN,
    'J': TxnType.JOURNAL,
}

class stocktransactionsale:
    """
    Sales shim:
      - collects sales details/charges
      - posts only SALES / SALES_RETURN
    """
    def __init__(self, order, transactiontype, debit, credit, description, entrytype):
        self.order = order
        self.txn_str = (transactiontype or 'S')
        self.description = description
        self.entrytype = entrytype
        self._details = []
        self._extra_charges = {}  # {detail_id: [charge,...]}

    def createtransactiondetails(self, detail, stocktype):
        self._details.append(detail)
        return None, None

    def createothertransactiondetails(self, detail, stocktype):
        # charge FK on sales side
        detail_fk = getattr(detail, "salesorderdetail", None) or getattr(detail, "salesorderdetail_id", None)
        detail_id = getattr(detail_fk, "id", None) if detail_fk else detail_fk
        if detail_id:
            self._extra_charges.setdefault(detail_id, []).append(detail)
        return None

    def createtransaction(self):
        order = self.order
        entry_obj, _ = EntryModel.objects.get_or_create(entrydate1=order.sorderdate, entity=order.entity)

        poster = Poster(
            entry=entry_obj,
            entity=order.entity,
            user=order.createdby,
            transactiontype=TXN_MAP.get(str(self.txn_str).upper(), TxnType.SALES),
            transactionid=order.id,
            voucherno=order.billno,
            entrydate=getattr(order.sorderdate, "date", lambda: order.sorderdate)(),
            entrydt=order.sorderdate,
        )

        t = TXN_MAP.get(str(self.txn_str).upper(), TxnType.SALES)
        details = self._details or list(order.saleInvoiceDetails.all())

        if t == TxnType.SALES:
            poster.post_sales(order, details, extra_charges_map=self._extra_charges)
        elif t == TxnType.SALES_RETURN:
            poster.post_sales_return(order, details)
        # No purchase posting here.

        return order.id


from datetime import datetime, time as _time



def _ensure_datetime(dt_or_date, fallback_date=None):
    """
    If dt_or_date is a datetime → return as-is.
    If it's a date → return date @ 00:00.
    If it's None → use fallback_date (date) @ 00:00; if that’s also None, use today @ 00:00.
    """
    if isinstance(dt_or_date, datetime):
        return dt_or_date
    if dt_or_date is not None:  # it's a date
        return datetime.combine(dt_or_date, _time(0, 0, 0))
    # fallback
    if fallback_date is not None:
        return datetime.combine(fallback_date, _time(0, 0, 0))
    today = datetime.now().date()
    return datetime.combine(today, _time(0, 0, 0))


class stocktransaction:
    """
    Posting shim:
      - collects details/charges
      - posts PURCHASE / PURCHASE_RETURN / SALES / SALES_RETURN
      - main date = billdate (fallback voucherdate)
    """

    def __init__(self, order, transactiontype, debit, credit, description, entrytype):
        self.order = order
        self.txn_str = (transactiontype or "P")
        self.description = description
        self.entrytype = entrytype
        self._details = []
        self._extra_charges = {}

    def createtransactiondetails(self, detail, stocktype):
        self._details.append(detail)
        return None, None

    def _resolve_line_id_from_charge(self, charge_detail):
        """
        Map other-charge rows to their base line (detail) id.
        Supports Purchase, Purchase Return, Sales, Sales Return.
        """
        candidates = [
            # PURCHASE / PURCHASE RETURN
            "purchaseorderdetail",
            "purchaseorderdetail_id",
            "purchaseinvoicedetail",
            "purchaseinvoicedetail_id",
            "purchasereturndetail",
            "purchasereturndetail_id",

            # SALES / SALES RETURN
            "salesorderdetail",
            "salesorderdetail_id",
            "salesinvoicedetail",
            "salesinvoicedetail_id",
            "salesreturnorderdetail",
            "salesreturnorderdetail_id",
            "salereturndetail",
            "salereturndetail_id",
        ]

        for attr in candidates:
            fk = getattr(charge_detail, attr, None)
            if fk is None:
                continue
            line_id = getattr(fk, "id", None) if hasattr(fk, "id") else fk
            if line_id:
                return line_id
        return None

    def createothertransactiondetails(self, detail, stocktype):
        """
        Collect other charges and attach them to the correct line id.
        """
        line_id = self._resolve_line_id_from_charge(detail)
        if line_id:
            self._extra_charges.setdefault(line_id, []).append(detail)
        return None

    def createtransaction(self):
        order = self.order

        bill_dt = getattr(order, "billdate", None)
        vouch_d = getattr(order, "voucherdate", None)
        entrydt = _ensure_datetime(bill_dt, fallback_date=vouch_d)
        entrydate = entrydt.date()

        entry_obj, _ = EntryModel.objects.get_or_create(
            entrydate1=entrydate,
            entity=order.entity
        )

        t = TXN_MAP.get(str(self.txn_str).upper(), TxnType.PURCHASE)

        poster = Poster(
            entry=entry_obj,
            entity=order.entity,
            user=getattr(order, "createdby", None),
            transactiontype=t,
            transactionid=order.id,
            voucherno=getattr(order, "voucherno", None),
            entrydate=entrydate,
            entrydt=entrydt,
        )

        # -----------------------------
        # Details (use collected if provided; else reload from DB by type)
        # -----------------------------
        if self._details:
            details = self._details
        else:
            if t == TxnType.PURCHASE:
                # keep your existing purchase related_name
                details = list(order.purchaseInvoiceDetails.all())

            elif t == TxnType.PURCHASE_RETURN:
                # ✅ your actual related_name
                details = list(order.purchasereturndetails.all())

            elif t == TxnType.SALES:
                # only if you use this shim for sales too; else you can remove
                details = list(order.salesorderdetails.all()) if hasattr(order, "salesorderdetails") else []

            elif t == TxnType.SALES_RETURN:
                details = list(order.salereturndetails.all())

            else:
                details = []

        # -----------------------------
        # Dispatch
        # -----------------------------
        if t == TxnType.PURCHASE:
            poster.post_purchase(order, details, extra_charges_map=self._extra_charges)

        elif t == TxnType.PURCHASE_RETURN:
            poster.post_purchase_return(order, details, extra_charges_map=self._extra_charges)

        elif t == TxnType.SALES:
            poster.post_sales(order, details, extra_charges_map=self._extra_charges)

        elif t == TxnType.SALES_RETURN:
            poster.post_sales_return(order, details, extra_charges_map=self._extra_charges)

        return order.id






class subentitySerializerbyentity(serializers.ModelSerializer):

    class Meta:

        model = subentity
        fields = ('id','subentityname',)




    



class gststocktransaction:
    def __init__(self, order,transactiontype,debit,credit,description,entrytype):
        self.order = order
        self.transactiontype = transactiontype
        self.debit = debit
        self.credit = credit
        self.description = description
        self.entrytype = entrytype
    
    def createtransaction(self):
        id = self.order.id
        subtotal = self.order.subtotal
        cgst = self.order.cgst
        sgst = self.order.sgst
        igst = self.order.igst
        cgstr = self.order.cgstreverse
        sgstr = self.order.sgstreverse
        igstr = self.order.igstreverse
        gtotal = self.order.gtotal
        pentity = self.order.entity
        const = stocktransconstant()
        cgstid = const.getcgst(pentity)
        igstid = const.getigst(pentity)
        sgstid = const.getsgst(pentity)
        cgstrid = const.getcgstr(pentity)
        igstrid = const.getigstr(pentity)
        sgstrid = const.getsgstr(pentity)
        entryid, created = entry.objects.get_or_create(entrydate1=self.order.orderdate, entity=self.order.entity)

        if self.transactiontype == 'ss':
            if self.entrytype == 'U':
                StockTransactions.objects.filter(entity=pentity, transactiontype='ss', transactionid=id).delete()

            if self.order.billcash == 0:
                iscash = True
                cash = const.getcashid(pentity)
                StockTransactions.objects.create(accounthead=cash.accounthead, account=cash, transactiontype=self.transactiontype, transactionid=id, desc='Cash Receipt Sale Bill.No : ' + str(self.order.billno), drcr=1, debitamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='CIH', iscashtransaction=iscash, voucherno=self.order.billno)
                StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=' Cash sale By Bill.No : ' + str(self.order.billno), drcr=0, creditamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', iscashtransaction=iscash, voucherno=self.order.billno)

            StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=gtotal, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', voucherno=self.order.billno)

            if igst > 0:
                StockTransactions.objects.create(accounthead=igstid.accounthead, account=igstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=igst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if cgst > 0:
                StockTransactions.objects.create(accounthead=cgstid.accounthead, account=cgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=cgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if sgst > 0:
                StockTransactions.objects.create(accounthead=sgstid.accounthead, account=sgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=sgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)

        if self.transactiontype == 'sp':
            if self.entrytype == 'U':
                StockTransactions.objects.filter(entity=pentity, transactiontype='sp', transactionid=id).delete()

            if self.order.billcash == 0:
                iscash = True
                cash = const.getcashid(pentity)
                StockTransactions.objects.create(accounthead=cash.accounthead, account=cash, transactiontype=self.transactiontype, transactionid=id, desc='Cash Receipt Sale Bill.No : ' + str(self.order.billno), drcr=0, creditamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='CIH', iscashtransaction=iscash, voucherno=self.order.billno)
                StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=' Cash sale By Bill.No : ' + str(self.order.billno), drcr=1, debitamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', iscashtransaction=iscash, voucherno=self.order.billno)

            StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=gtotal, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', voucherno=self.order.billno)

            if igst > 0:
                StockTransactions.objects.create(accounthead=igstid.accounthead, account=igstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=igst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if cgst > 0:
                StockTransactions.objects.create(accounthead=cgstid.accounthead, account=cgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=cgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if sgst > 0:
                StockTransactions.objects.create(accounthead=sgstid.accounthead, account=sgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=sgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)

        if self.transactiontype == 'pr':
            if self.entrytype == 'U':
                StockTransactions.objects.filter(entity=pentity, transactiontype='pr', transactionid=id).delete()

            if self.order.billcash == 0:
                iscash = True
                cash = const.getcashid(pentity)
                StockTransactions.objects.create(accounthead=cash.accounthead, account=cash, transactiontype=self.transactiontype, transactionid=id, desc='Cash Receipt Sale Bill.No : ' + str(self.order.billno), drcr=0, creditamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='CIH', iscashtransaction=iscash, voucherno=self.order.billno)
                StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=' Cash sale By Bill.No : ' + str(self.order.billno), drcr=1, debitamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', iscashtransaction=iscash, voucherno=self.order.billno)

            StockTransactions.objects.create(accounthead=self.order.account.accounthead, account=self.order.account, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=subtotal, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, accounttype='M', voucherno=self.order.billno)

            if igst > 0:
                StockTransactions.objects.create(accounthead=igstid.accounthead, account=igstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=igst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if cgst > 0:
                StockTransactions.objects.create(accounthead=cgstid.accounthead, account=cgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=cgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if sgst > 0:
                StockTransactions.objects.create(accounthead=sgstid.accounthead, account=sgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=sgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)

            if igstr > 0:
                StockTransactions.objects.create(accounthead=igstrid.accounthead, account=igstrid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=igstr, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if cgstr > 0:
                StockTransactions.objects.create(accounthead=cgstrid.accounthead, account=cgstrid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=cgstr, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)
            if sgstr > 0:
                StockTransactions.objects.create(accounthead=sgstrid.accounthead, account=sgstrid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=sgstr, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.orderdate, voucherno=self.order.billno)

        return id

    


    def createtransactiondetails(self, detail, stocktype):
        entryid, created = entry.objects.get_or_create(entrydate1=self.order.orderdate, entity=self.order.entity)
        transaction_type = self.transactiontype

        if transaction_type == 'ss':
            details1 = StockTransactions.objects.create(
                accounthead=detail.account.creditaccounthead,
                account=detail.account,
                transactiontype=transaction_type,
                transactionid=self.order.id,
                desc=self.description + ' ' + str(self.order.billno),
                quantity=detail.multiplier,
                drcr=self.credit,
                creditamount=detail.amount,
                entrydate=self.order.orderdate,
                entity=self.order.entity,
                createdby=self.order.createdby,
                entry=entryid,
                accounttype='M',
                isactive=self.order.isactive,
                rate=detail.rate,
                entrydatetime=self.order.orderdate,
                voucherno=self.order.billno
            )
        elif transaction_type == 'sp':
            details1 = StockTransactions.objects.create(
                accounthead=detail.account.accounthead,
                account=detail.account,
                transactiontype=transaction_type,
                transactionid=self.order.id,
                desc=self.description + ' ' + str(self.order.billno),
                quantity=detail.multiplier,
                drcr=self.debit,
                debitamount=detail.amount,
                entrydate=self.order.orderdate,
                entity=self.order.entity,
                createdby=self.order.createdby,
                entry=entryid,
                accounttype='M',
                isactive=self.order.isactive,
                rate=detail.rate,
                entrydatetime=self.order.orderdate,
                voucherno=self.order.billno
            )
        elif transaction_type == 'pr':
            details1 = StockTransactions.objects.create(
                accounthead=detail.account.accounthead,
                account=detail.account,
                transactiontype=transaction_type,
                transactionid=self.order.id,
                desc=self.description + ' ' + str(self.order.billno),
                quantity=detail.multiplier,
                drcr=self.debit,
                debitamount=detail.amount,
                entrydate=self.order.orderdate,
                entity=self.order.entity,
                createdby=self.order.createdby,
                entry=entryid,
                accounttype='M',
                isactive=self.order.isactive,
                rate=detail.rate,
                entrydatetime=self.order.orderdate,
                voucherno=self.order.billno
            )

        return detail



class journaldetailsSerializer(serializers.ModelSerializer):
    # Optional and nullable in API
    cb_account = serializers.PrimaryKeyRelatedField(
        queryset=account.objects.all(),
        required=False,
        allow_null=True,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=journaldetails.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = journaldetails
        fields = "__all__"
        extra_kwargs = {
            "line_kind": {"required": False},  # default on model
        }

    def validate(self, data):
        debit = data.get("debitamount") or ZERO4
        credit = data.get("creditamount") or ZERO4
        drcr = bool(data.get("drcr"))
        if debit < 0 or credit < 0:
            raise serializers.ValidationError("Amounts cannot be negative.")
        # exactly one side
        if (debit == 0) == (credit == 0):
            raise serializers.ValidationError("Provide exactly one of debitamount or creditamount.")
        # drcr must align to non-zero side
        if drcr and debit <= 0:
            raise serializers.ValidationError("drcr=True (Debit) requires debitamount > 0.")
        if (not drcr) and credit <= 0:
            raise serializers.ValidationError("drcr=False (Credit) requires creditamount > 0.")
        return data


class journalmainSerializer(serializers.ModelSerializer):
    journaldetails = journaldetailsSerializer(many=True)

    class Meta:
        model = journalmain
        fields = (
            "id",
            "voucherdate",
            "voucherno",
            "vouchertype",
            "mainaccountid",
            "entrydate",
            "entityfinid",
            "entity",
            "createdby",
            "isactive",
            "journaldetails",
        )

    # ---- header helpers -------------------------------------------------

    def _txn_type_for_header(self, header: journalmain) -> str:
        return {
            VoucherType.CASH:     TxnType.JOURNAL_CASH,
            VoucherType.BANK:     TxnType.JOURNAL_BANK,
            VoucherType.JOURNAL:  TxnType.JOURNAL,
        }[header.vouchertype]

    def _ensure_main_account(self, validated_header: dict) -> Optional["Account"]:
        """
        Cash (C): force cash account from constants.
        Bank (B): require/resolve mainaccountid (int → object).
        Journal (J): force None.
        Returns resolved Account (or None) to optionally stamp into details.
        """
        vt = validated_header.get("vouchertype")
        entity = validated_header.get("entity")
        main_acct = validated_header.get("mainaccountid")

        if vt == "C":
            const = stocktransconstant()
            cash_acct = const.getcashid(entity)
            validated_header["mainaccountid"] = cash_acct
            return cash_acct

        if vt == "B":
            if not main_acct:
                raise serializers.ValidationError({"mainaccountid": "Bank voucher requires mainaccountid."})
            if isinstance(main_acct, int):
                try:
                    main_acct = account.objects.get(id=main_acct)
                except account.DoesNotExist:
                    raise serializers.ValidationError({"mainaccountid": "Invalid bank account id."})
                validated_header["mainaccountid"] = main_acct
            return main_acct

        # Journal vouchers: ensure None
        validated_header["mainaccountid"] = None
        return None

    def _post_with_poster(self, header: journalmain):
        entry_env, _ = EntryModel.objects.get_or_create(entrydate1=header.entrydate, entity=header.entity)
        details_qs = header.journaldetails.select_related("account").filter(line_kind="BASE")
        Poster(
            entry=entry_env,
            entity=header.entity,
            user=self.context["request"].user,
            transactiontype=TxnType.JOURNAL,  # Poster will override to JOURNAL_CASH / JOURNAL_BANK as needed
            transactionid=header.id,
            voucherno=header.voucherno,
            entrydate=header.entrydate,
            entrydt=header.entrydate,
        ).post_journal_voucher(header, details=details_qs)

    # ---- component detail builders --------------------------------------

    def _build_component_rows(
        self,
        *,
        header: "JournalMain",
        base_row: "JournalDetails",
        cb_acct: Optional["Account"],
        const: Any,  # do not annotate as stocktransconstant (not a type)
    ) -> list["JournalDetails"]:
        """
        Create journaldetails rows derived from a saved BASE row:
          - AUTO_CB (if Cash/Bank)
          - DISCOUNT (if > 0)
          - BANK_CHARGES (Bank only, if > 0)
          - TDS (Bank only, if > 0)
        """
        rows: list[journaldetails] = []
        vt = header.vouchertype
        is_dr = bool(base_row.drcr)
        amt = (base_row.debitamount or ZERO4) + (base_row.creditamount or ZERO4)

        # 1) AUTO CB (opposite side of base)
        if vt in ("C", "B") and cb_acct is not None and amt > ZERO4:
            rows.append(
                journaldetails(
                    Journalmain=header,
                    parent=base_row,
                    line_kind=DetailKind.AUTO_CB,
                    account=cb_acct,
                    desc=(base_row.desc or "") + " (auto CB)",
                    drcr=(not is_dr),
                    debitamount=amt if not is_dr else ZERO4,
                    creditamount=amt if is_dr else ZERO4,
                    discount=ZERO4,
                    bankcharges=ZERO4,
                    tds=ZERO4,
                    entity=header.entity,
                    cb_account=cb_acct,
                )
            )

        # 2) DISCOUNT (opposite of base)
        if (base_row.discount or ZERO4) > ZERO4:
            disc_acct = const.getdiscount(header.entity)
            d_amt = base_row.discount
            rows.append(
                journaldetails(
                    Journalmain=header,
                    parent=base_row,
                    line_kind=DetailKind.DISCOUNT,
                    account=disc_acct,
                    desc=(base_row.desc or "") + " (discount)",
                    drcr=(not is_dr),
                    debitamount=d_amt if not is_dr else ZERO4,
                    creditamount=d_amt if is_dr else ZERO4,
                    discount=ZERO4,
                    bankcharges=ZERO4,
                    tds=ZERO4,
                    entity=header.entity,
                    cb_account=cb_acct if vt in ("C", "B") else None,
                )
            )

        # 3) BANK CHARGES (Bank only) — charges account takes DR if base DR, else CR
        if vt == "B" and (base_row.bankcharges or ZERO4) > ZERO4:
            bc_acct = const.getbankcharges(header.entity)
            bc_amt = base_row.bankcharges
            rows.append(
                journaldetails(
                    Journalmain=header,
                    parent=base_row,
                    line_kind=DetailKind.BANK_CHARGES,
                    account=bc_acct,
                    desc=(base_row.desc or "") + " (B Charges)",
                    drcr=True if is_dr else False,
                    debitamount=bc_amt if is_dr else ZERO4,
                    creditamount=bc_amt if not is_dr else ZERO4,
                    discount=ZERO4,
                    bankcharges=ZERO4,
                    tds=ZERO4,
                    entity=header.entity,
                    cb_account=cb_acct,
                )
            )

        # 4) TDS (Bank only) — opposite of base
        if vt == "B" and (base_row.tds or ZERO4) > ZERO4:
            tds_acct = const.gettds194q1id(header.entity)
            tds_amt = base_row.tds
            rows.append(
                journaldetails(
                    Journalmain=header,
                    parent=base_row,
                    line_kind=DetailKind.TDS,
                    account=tds_acct,
                    desc=(base_row.desc or "") + " (tds)",
                    drcr=(not is_dr),
                    debitamount=tds_amt if not is_dr else ZERO4,
                    creditamount=tds_amt if is_dr else ZERO4,
                    discount=ZERO4,
                    bankcharges=ZERO4,
                    tds=ZERO4,
                    entity=header.entity,
                    cb_account=cb_acct,
                )
            )

        return rows

    # ---- create/update ---------------------------------------------------

    @transaction.atomic
    def create(self, validated_data):
        details_payload = validated_data.pop("journaldetails", [])
        self._ensure_main_account(validated_data)  # validates + stamps header

        header = journalmain.objects.create(**validated_data)

        base_rows = [
            journaldetails(Journalmain=header, line_kind=DetailKind.BASE, **d)
            for d in details_payload
        ]
        journaldetails.objects.bulk_create(base_rows)

        self._post_with_poster(header)
        return header

    @transaction.atomic
    def update(self, instance, validated_data):
        details_payload = validated_data.pop("journaldetails", None)
        self._ensure_main_account(validated_data)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if details_payload is not None:
            journaldetails.objects.filter(Journalmain=instance, entity=instance.entity).delete()
            base_rows = [
                journaldetails(Journalmain=instance, line_kind=DetailKind.BASE, **d)
                for d in details_payload
            ]
            journaldetails.objects.bulk_create(base_rows)

        self._post_with_poster(instance)
        return instance

    





# class journaldetailsSerializer(serializers.ModelSerializer):
#     #entityUser = entityUserSerializer(many=True)
#     id = serializers.IntegerField(required=False)
#     accountname = serializers.SerializerMethodField()

#     class Meta:
#         model = journaldetails
#         fields =  ('id','account','accountname','desc','drcr','debitamount','creditamount','discount','bankcharges','tds','chqbank','entity',)

#     def get_accountname(self,obj):
#          return obj.account.accountname



# class journalmainSerializer(serializers.ModelSerializer):
#     journaldetails = journaldetailsSerializer(many=True)
#     class Meta:
#         model = journalmain
#         fields = ('id','voucherdate','voucherno','vouchertype','mainaccountid','entrydate','entityfinid','entity','createdby', 'isactive','journaldetails',)
#     def create(self, validated_data):
#         journaldetails_data = validated_data.pop('journaldetails')
#         const = stocktransconstant()
#         with transaction.atomic():
#             order = journalmain.objects.create(**validated_data)
#             for journaldetail_data in journaldetails_data:
#                 detail = journaldetails.objects.create(Journalmain = order, **journaldetail_data)
#                 print(order.entrydate)
#                 id,created  = entry.objects.get_or_create(entrydate1 = order.entrydate,entity = order.entity)

#                 narration = ''

#                 if detail.account.accountcode == 4000:
#                     iscash = True
#                 else:
#                     iscash = False
#                 # accounttype = 'M'

#                 if order.vouchertype == 'C':
#                     iscash = True

#                     narration = 'Cash V.No '
                
#                 if order.vouchertype == 'B':
#                     narration = 'Bank V.No '
                
#                 if order.vouchertype == 'J':
#                     narration = 'Journal V.No '
                


#                # accountentryid,accountentrycreated  = accountentry.objects.get_or_create(entrydate2 = order.entrydate,account =detail.account,  entity = order.entity)

#                 if order.vouchertype == 'C':
#                 # iscash = False
#                     iscash = True

#                     #if self.order.account.accountcode == 4000:

#                     cash = const.getcashid(order.entity)
                        
#                     #cash = account.objects.get(entity =order.entity,accountcode = 4000)
#                     if detail.drcr == 1:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(order.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = order.voucherno)
#                     else:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(order.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        
#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = order.voucherno)

                    
#                 if order.vouchertype == 'B':
#                     cash = account.objects.get(id = order.mainaccountid)
#                     if detail.drcr == 1:
#                         if detail.discount > 0:

#                             nnation = ' (discount)'
#                             disc = const.getdiscount(order.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                         if detail.bankcharges > 0:
#                             nnation = ' (B Charges)'
#                             bc = const.getbankcharges(order.entity)
#                             StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

#                         if detail.tds > 0:
#                             nnation = ' (tds)'
#                             tds = const.gettds194q1id(order.entity)
#                             StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                     else:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(order.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation ,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                         if detail.bankcharges > 0:
#                             nnation = ' (B Charges)'
#                             bc = const.getbankcharges(order.entity)
#                             StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                         if detail.tds > 0:
#                             nnation = ' (tds)'
#                             tds = const.gettds194q1id(order.entity)
#                             StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                

#                 StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',iscashtransaction= iscash,voucherno = order.voucherno)

          
#         return order

#     def update(self, instance, validated_data):
#         const = stocktransconstant()
#         fields = ['voucherdate','voucherno','vouchertype','mainaccountid','entrydate','entityfinid', 'entity','createdby','isactive',]
#         for field in fields:
#             try:
#                 setattr(instance, field, validated_data[field])
#             except KeyError:  # validated_data may not contain all fields during HTTP PATCH
#                 pass
#         with transaction.atomic():
#             instance.save()
#         # stk = stocktransactionsale(instance, transactiontype= 'S',debit=1,credit=0,description= 'Sale')
#             journaldetails.objects.filter(Journalmain=instance,entity = instance.entity).delete()
#             StockTransactions.objects.filter(entity = instance.entity,transactiontype = instance.vouchertype,transactionid = instance.id).delete()
#         #   stk.updateransaction()

#             journaldetails_data = validated_data.get('journaldetails')

#             for journaldetail_data in journaldetails_data:
#                 detail = journaldetails.objects.create(Journalmain = instance, **journaldetail_data)
#                 id,created  = entry.objects.get_or_create(entrydate1 = instance.entrydate,entity = instance.entity)
#               #  StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = 'Journal V.No' + str(instance.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1)
#                 #stk.createtransactiondetails(detail=detail,stocktype='S')

#                 if instance.vouchertype == 'C':
#                     iscash = True
#                     narration = 'Cash V.No '
                
#                 if instance.vouchertype == 'B':
#                     narration = 'Bank V.No '
                
#                 if instance.vouchertype == 'J':
#                     narration = 'Journal V.No '


#                 if instance.vouchertype == 'C':
#                     iscash = True
#                     #if self.order.account.accountcode == 4000:
                        
#                     cash = const.getcashid(instance.entity)
#                     if detail.drcr == 1:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(instance.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno,iscashtransaction= iscash)
                            

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = instance.voucherno)
#                     else:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(instance.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno,iscashtransaction= iscash)
#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = instance.voucherno)

                    
#                 if instance.vouchertype == 'B':
#                     cash = account.objects.get(id = instance.mainaccountid)
#                     if detail.drcr == 1:

#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(instance.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                         if detail.bankcharges > 0:
#                             nnation = ' (B Charges)'
#                             bc = const.getbankcharges(instance.entity)
#                             StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                        
#                         if detail.tds > 0:
#                             nnation = ' (tds)'
#                             tds = const.gettds194q1id(instance.entity)
#                             StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1,voucherno = instance.voucherno)
#                     else:
#                         if detail.discount > 0:
#                             nnation = ' (discount)'
#                             disc = const.getdiscount(instance.entity)
#                             StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                        
#                         if detail.bankcharges > 0:
#                             nnation = ' (B Charges)'
#                             bc = const.getbankcharges(instance.entity)
#                             StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

#                         if detail.tds > 0:
#                             nnation = ' (tds)'
#                             tds = const.gettds194q1id(instance.entity)
#                             StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
#                             StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

#                         StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1,voucherno = instance.voucherno)

                
#                 if detail.account.accountcode == 4000:
#                     iscash = True
#                 else:
#                     iscash = False
#                 # accounttype = 'M'

#                 if instance.vouchertype == 'C':
#                     iscash = True


              

#                 StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',iscashtransaction= iscash,voucherno = instance.voucherno)

        
#         return instance



class productiondetailsSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    

    class Meta:
        model = productiondetails
        fields =  ('id','stock','productname','desc','quantity','rate','issuereceived','entity',)

    def get_productname(self,obj):
         return obj.stock.productname
    
    # def get_issuereceived(self,obj):
    #      return obj.stock.quantity

    # def get_issuereceived(self,obj):
    #      return obj.stock.quantity



class productionmainSerializer(serializers.ModelSerializer):
    stockdetails = productiondetailsSerializer(many=True)
    class Meta:
        model = productionmain
        fields = ('id','voucherdate','voucherno','vouchertype','entrydate','entityfinid','entity','createdby','stockdetails',)


    

    def create(self, validated_data):
        #print(validated_data)
        journaldetails_data = validated_data.pop('stockdetails')
        order = productionmain.objects.create(**validated_data)
       # stk = stocktransactionsale(order, transactiontype= 'S',debit=1,credit=0,description= 'Sale ')
        #print(tracks_data)
        for journaldetail_data in journaldetails_data:
            detail = productiondetails.objects.create(stockmain = order, **journaldetail_data)
            id,created  = entry.objects.get_or_create(entrydate1 = order.entrydate,entity=order.entity)
            StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = order.vouchertype,transactionid = order.id,drcr = detail.issuereceived,quantity = detail.quantity,entrydate = order.entrydate,entity = order.entity,createdby = order.createdby,entry = id,voucherno = order.voucherno)


           
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','vouchertype','entrydate','entityfinid','entity','createdby',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        instance.save()
       # stk = stocktransactionsale(instance, transactiontype= 'S',debit=1,credit=0,description= 'Sale')
        productiondetails.objects.filter(stockmain=instance,entity = instance.entity).delete()
       # goodstransaction.objects.filter(entity = instance.entity,transactiontype = instance.vouchertype,transactionid = instance.id).delete()
     #   stk.updateransaction()

        journaldetails_data = validated_data.get('stockdetails')
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.entrydate,entity=instance.entity)

        for journaldetail_data in journaldetails_data:
            detail = productiondetails.objects.create(stockmain = instance, **journaldetail_data)
           # goodstransaction.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,stockttype = detail.issuereceived,issuedquantity = detail.issuedquantity,recivedquantity = detail.recivedquantity,entrydate = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid)
            #stk.createtransactiondetails(detail=detail,stocktype='S')

        
        return instance


class stockdetailsSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()

    class Meta:
        model = stockdetails
        fields =  ('id','stock','productname','desc','issuereceived','issuedquantity','recivedquantity','entity',)

    def get_productname(self,obj):
         return obj.stock.productname



class stockmainSerializer(serializers.ModelSerializer):
    stockdetails = stockdetailsSerializer(many=True)
    class Meta:
        model = stockmain
        fields = ('id','voucherdate','voucherno','vouchertype','entrydate','entityfinid', 'entity','createdby','stockdetails',)


    

    def create(self, validated_data):
        #print(validated_data)
        journaldetails_data = validated_data.pop('stockdetails')
        order = stockmain.objects.create(**validated_data)
       # stk = stocktransactionsale(order, transactiontype= 'S',debit=1,credit=0,description= 'Sale ')
        #print(tracks_data)
        for journaldetail_data in journaldetails_data:
            detail = stockdetails.objects.create(stockmain = order, **journaldetail_data)
            id,created  = entry.objects.get_or_create(entrydate1 = order.entrydate,entity=order.entity)


            # if detail.issuereceived == True:
            #     StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = order.vouchertype,transactionid = order.id,drcr = detail.issuereceived,quantity = detail.issuedquantity,entrydate = order.entrydate,entrydatetime = order.entrydate, entity = order.entity,createdby = order.createdby,entry = id,stockttype= 'I',accounttype = 'DD',voucherno = order.voucherno,desc = 'Stock V.No ' + str(order.voucherno))
            # else:
            #     StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = order.vouchertype,transactionid = order.id,drcr = detail.issuereceived,quantity = detail.recivedquantity,entrydate = order.entrydate,entrydatetime = order.entrydate,entity = order.entity,createdby = order.createdby,entry = id,stockttype= 'R',accounttype = 'DD',voucherno = order.voucherno,desc = 'Stock V.No ' + str(order.voucherno))

          #  StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = 'Journal V.No' + str(order.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate)
           # stk.createtransactiondetails(detail=detail,stocktype='S')

            # if(detail.orderqty ==0.00):
            #     qty = detail.pieces
            # else:
            #     qty = detail.orderqty
            # StockTransactions.objects.create(accounthead = detail.product.saleaccount.accounthead,account= detail.product.saleaccount,stock=detail.product,transactiontype = 'S',transactionid = order.id,desc = 'Sale By B.No ' + str(order.billno),stockttype = 'S',salequantity = qty,drcr = 0,creditamount = detail.amount,cgstcr = detail.cgst,sgstcr= detail.sgst,igstcr = detail.igst,entrydate = order.sorderdate,entity = order.entity,createdby = order.owner)

       # stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','vouchertype','entrydate','entityfinid','entity','createdby',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        instance.save()
       # stk = stocktransactionsale(instance, transactiontype= 'S',debit=1,credit=0,description= 'Sale')
        stockdetails.objects.filter(stockmain=instance,entity = instance.entity).delete()
      #  StockTransactions.objects.filter(entity = instance.entity,transactiontype = instance.vouchertype,transactionid = instance.id).delete()
     #   stk.updateransaction()

        journaldetails_data = validated_data.get('stockdetails')
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.entrydate,entity=instance.entity)

        for journaldetail_data in journaldetails_data:
            detail = stockdetails.objects.create(stockmain = instance, **journaldetail_data)
           # goodstransaction.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,stockttype = detail.issuereceived,issuedquantity = detail.issuedquantity,recivedquantity = detail.recivedquantity,entrydate = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid)
            #stk.createtransactiondetails(detail=detail,stocktype='S')
            # if detail.issuereceived == True:
            #    # StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,drcr = detail.issuereceived,quantity = detail.issuedquantity,entrydate = instance.entrydate,entrydatetime = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid,stockttype= 'I',accounttype = 'DD',voucherno = instance.voucherno,desc = 'Stock V.No ' + str(instance.voucherno))
            # else:
               # StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,drcr = detail.issuereceived,quantity = detail.recivedquantity,entrydate = instance.entrydate,entrydatetime = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid,stockttype= 'R',accounttype = 'DD',voucherno = instance.voucherno,desc = 'Stock V.No   ' + str(instance.voucherno))

        
        return instance



class SalesOrderDetailsPDFSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    productname = serializers.CharField(source="product.productname", read_only=True)

    # ✅ from Product.base_uom.code (your model)
    units = serializers.CharField(source="product.base_uom.code", read_only=True)

    # ✅ derived from ProductPrice.mrp
    mrp = serializers.SerializerMethodField()

    # ✅ derived from ProductGstRate.hsn.code (product doesn't have hsn field)
    hsn = serializers.SerializerMethodField()

    # ✅ GST % should come from line fields (applied values)
    cgstrate = serializers.DecimalField(source="cgstpercent", max_digits=5, decimal_places=2, read_only=True)
    sgstrate = serializers.DecimalField(source="sgstpercent", max_digits=5, decimal_places=2, read_only=True)
    igstrate = serializers.SerializerMethodField()

    class Meta:
        model = salesOrderdetails
        fields = (
            "id", "product", "productname", "hsn", "units", "mrp",
            "productdesc", "orderqty", "pieces",
            "ratebefdiscount", "orderDiscount", "rate", "amount",
            "othercharges",
            "cgstrate", "cgst", "sgstrate", "sgst", "igstrate", "igst",
            "cess", "linetotal", "entity",
        )

    # -----------------------------
    # Select best ProductPrice row
    # -----------------------------
    def _pick_price_row(self, product):
        """
        Picks best ProductPrice:
          - active for today (effective_from <= today <= effective_to/null)
          - else latest effective_from
        Filters:
          - pricelist_id (context or header)
          - uom_id (default product.base_uom)
        """
        today = timezone.localdate()

        qs = product.prices.all()  # prefetched
        pricelist_id = self.context.get("pricelist_id")
        uom_id = self.context.get("uom_id") or getattr(product, "base_uom_id", None)

        if pricelist_id:
            qs = qs.filter(pricelist_id=pricelist_id)
        if uom_id:
            qs = qs.filter(uom_id=uom_id)

        active = qs.filter(
            effective_from__lte=today
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).order_by("-effective_from")

        row = active.first()
        return row or qs.order_by("-effective_from").first()

    def get_mrp(self, obj):
        row = self._pick_price_row(obj.product)
        return row.mrp if row else None

    # -----------------------------
    # HSN resolver (new model)
    # -----------------------------
    def _pick_gst_row(self, product):
        """
        Pick ProductGstRate row:
          - isdefault=True preferred
          - else most recent valid_from
        """
        today = timezone.localdate()
        qs = product.gst_rates.all()  # prefetched with hsn

        # active window first (if dates used)
        active = qs.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=today)
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=today)
        )

        default = active.filter(isdefault=True).order_by("-valid_from")
        row = default.first()
        if row:
            return row

        row = active.order_by("-valid_from").first()
        return row or qs.order_by("-valid_from").first()

    def get_hsn(self, obj):
        row = self._pick_gst_row(obj.product)
        return row.hsn.code if (row and row.hsn_id) else None

    def get_igstrate(self, obj):
        # show IGST% only when line is IGST
        try:
            if getattr(obj, "isigst", False) or (obj.igst and obj.igst > 0):
                return obj.igstpercent or 0
            return 0
        except Exception:
            return 0


class SaleReturnDetailsPDFSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.CharField(source='product.productname', read_only=True)
    hsn = serializers.CharField(source='product.hsn.hsnCode', read_only=True)
    mrp = serializers.DecimalField(source='product.mrp', max_digits=10, decimal_places=2, read_only=True)
    units = serializers.CharField(source='product.unitofmeasurement.unitname', read_only=True)
    cgstrate = serializers.DecimalField(source='product.cgst', max_digits=5, decimal_places=2, read_only=True)
    sgstrate = serializers.DecimalField(source='product.sgst', max_digits=5, decimal_places=2, read_only=True)
    igstrate = serializers.SerializerMethodField()

    class Meta:
        model = salereturnDetails
        fields = (
            'id', 'product', 'productname', 'hsn', 'units', 'mrp', 'productdesc', 'orderqty', 'pieces', 
            'rate', 'amount', 'othercharges', 'cgstrate', 'cgst', 'sgstrate', 'sgst', 'igstrate', 
            'igst', 'cess', 'linetotal', 'entity',
        )

    def get_igstrate(self, obj):
        return obj.product.igst if obj.igst else 0


class SaleReturnPDFSerializer(serializers.ModelSerializer):
   # saleInvoiceDetails1 = serializers.SerializerMethodField()
    saleInvoiceDetails = SaleReturnDetailsPDFSerializer(many=True, read_only=True, source='salereturndetails')
    entityname = serializers.CharField(source='entity.entityname', read_only=True)
    entitypan = serializers.CharField(source='entity.panno', read_only=True)
    entitydesc = serializers.CharField(source='entity.entitydesc', read_only=True)
   # entityaddress = serializers.SerializerMethodField()
    entityaddress = serializers.CharField(source='entity.address', read_only=True)
    entitycityname = serializers.CharField(source='entity.city.cityname', read_only=True)
    entitystate = serializers.CharField(source='entity.state.statename', read_only=True)
    entitypincode = serializers.CharField(source='entity.pincode', read_only=True)
    entitygst = serializers.CharField(source='entity.gstno', read_only=True)
    billtoname = serializers.CharField(source='account.accountname', read_only=True)
    billtoaddress1 = serializers.CharField(source='account.address1', read_only=True)
    billtoaddress2 = serializers.CharField(source='account.address2', read_only=True)
    billtostate = serializers.CharField(source='account.state.statename', read_only=True)
    billtocity = serializers.CharField(source='account.city.cityname', read_only=True)
    billtopin = serializers.CharField(source='account.city.pincode', read_only=True)
    billtopan = serializers.CharField(source='account.pan', read_only=True)
    #billtoaddress = serializers.SerializerMethodField()
    billtogst = serializers.CharField(source='account.gstno', read_only=True)
    shiptoname = serializers.CharField(source='subentity.subentityname', read_only=True)
    shiptoaddress1 = serializers.CharField(source='subentity.address', read_only=True)
    shiptoaddress2 = serializers.CharField(source='subentity.address', read_only=True)
    shiptostate = serializers.CharField(source='subentity.state.statename', read_only=True)
    shiptocity = serializers.CharField(source='subentity.city.cityname', read_only=True)
    shiptopin = serializers.CharField(source='subentity.city.pincode', read_only=True)
    shiptopan = serializers.CharField(source='entity.pan', read_only=True)
    shiptogst = serializers.CharField(source='entity.gstno', read_only=True)
    transportname = serializers.CharField(source='transport.accountname', read_only=True)
    #shiptoaddress = serializers.SerializerMethodField()
    amountinwords = serializers.SerializerMethodField()
    phoneno = serializers.CharField(source='entity.phoneoffice', read_only=True)
    phoneno2 = serializers.CharField(source= 'entity.phoneresidence', read_only=True)
    bankname = serializers.CharField(source= 'entity.bank.bankname', read_only=True)
    bankacno = serializers.CharField(source= 'entity.bankacno', read_only=True)
    ifsccode = serializers.CharField(source= 'entity.ifsccode', read_only=True)
    billno = serializers.CharField(source= 'invoicenumber', read_only=True)
    sorderdate = serializers.CharField(source= 'voucherdate', read_only=True)
    gst_summary = serializers.SerializerMethodField()
    totalgst = serializers.SerializerMethodField()
    doctype = serializers.SerializerMethodField()


    einvoice_details = serializers.SerializerMethodField()

    class Meta:
        model = salereturn
        fields = (
            'id', 'sorderdate', 'billno','account', 'billtoname', 'billtoaddress1',
             'billtoaddress2','billtocity','billtostate','billtogst','billtopan','billtopin',
            'grno', 'terms', 'vehicle', 'taxtype', 'billcash',
            'totalquanity', 'totalpieces', 'advance', 'shiptostate', 'shiptoname','shiptocity','shiptoaddress1','shiptoaddress2','shiptopan','shiptogst','shiptopin',
            'remarks', 'transport', 'broker', 'taxid', 'tds194q', 'tds194q1', 'tcs206c1ch1',
            'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1', 'tcs206C2', 'addless', 'duedate', 'subtotal',
            'cgst', 'sgst', 'igst', 'cess','totalgst', 'expenses', 'gtotal', 'amountinwords',
            'subentity', 'entity', 'entityname', 'entityaddress','entitycityname','entitystate','entitypincode', 'entitygst', 'createdby',  'isactive', 'phoneno', 'phoneno2', 'entitydesc','reversecharge','bankname','bankacno','ifsccode','transportname',
            'entitypan', 'saleInvoiceDetails','gst_summary','einvoice_details','doctype'
        )

    def get_einvoice_details(self, obj):
        try:
            content_type = ContentType.objects.get_for_model(salereturn)
            einv = EInvoiceDetails.objects.get(content_type=content_type, object_id=obj.id)
        except EInvoiceDetails.DoesNotExist:
            return None

        qr_image_base64 = None
        if einv.signed_qr_code:
            # Generate QR image from SignedQRCode
            qr = qrcode.make(einv.signed_qr_code)
            buffered = BytesIO()
            qr.save(buffered, format="PNG")
            qr_image_base64 = base64.b64encode(buffered.getvalue()).decode()

        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "qr_image_base64": qr_image_base64,
            "ewb_no": einv.ewb_no,
            "ewb_date": einv.ewb_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_date else None,
            "ewb_valid_till": einv.ewb_valid_till.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_valid_till else None
        }
    

    def get_totalgst(self, obj):
        if obj.igst == 0:
            return float(obj.cgst or 0) + float(obj.sgst or 0)
        return float(obj.igst or 0)

    def get_doctype(self, obj):
        return "Debit Note"

   

    

    def get_amountinwords(self, obj):
        return f"{string.capwords(num2words(obj.gtotal))} only"

    def get_gst_summary(self, obj):
        """
        Fetch and serialize GST summary data for the sales order header.
        """
        salesorderheader_id = obj.id
        aggregated_data = (
            salereturnDetails.objects.filter(salereturn_id=salesorderheader_id)
            .values("salereturn")
            .annotate(
                taxPercent=Case(
                    When(igstpercent=0, then=F("cgstpercent") + F("sgstpercent")),
                    default=F("igstpercent"),
                    output_field=FloatField(),
                ),
                taxable_amount=Sum("amount"),  # <- Removed filter
                total_cgst_amount=Sum("cgst", filter=Q(cgst__isnull=False)),
                total_sgst_amount=Sum("sgst", filter=Q(sgst__isnull=False)),
                total_igst_amount=Sum("igst", filter=Q(igst__isnull=False)),
            )
        )
        return list(aggregated_data)


class PurchaseReturnDetailsPDFSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.CharField(source='product.productname', read_only=True)
    hsn = serializers.CharField(source='product.hsn.hsnCode', read_only=True)
    mrp = serializers.DecimalField(source='product.mrp', max_digits=10, decimal_places=2, read_only=True)
    units = serializers.CharField(source='product.unitofmeasurement.unitname', read_only=True)
    cgstrate = serializers.DecimalField(source='product.cgst', max_digits=5, decimal_places=2, read_only=True)
    sgstrate = serializers.DecimalField(source='product.sgst', max_digits=5, decimal_places=2, read_only=True)
    igstrate = serializers.SerializerMethodField()

    class Meta:
        model = Purchasereturndetails
        fields = (
            'id', 'product', 'productname', 'hsn', 'units', 'mrp', 'productdesc', 'orderqty', 'pieces', 
            'rate', 'amount', 'othercharges', 'cgstrate', 'cgst', 'sgstrate', 'sgst', 'igstrate', 
            'igst', 'cess', 'linetotal', 'entity',
        )

    def get_igstrate(self, obj):
        return obj.product.igst if obj.igst else 0



    

class PurchaseReturnPDFSerializer(serializers.ModelSerializer):
   # saleInvoiceDetails1 = serializers.SerializerMethodField()
    saleInvoiceDetails = PurchaseReturnDetailsPDFSerializer(many=True, read_only=True, source='purchasereturndetails')
    entityname = serializers.CharField(source='entity.entityname', read_only=True)
    entitypan = serializers.CharField(source='entity.panno', read_only=True)
    entitydesc = serializers.CharField(source='entity.entitydesc', read_only=True)
   # entityaddress = serializers.SerializerMethodField()
    entityaddress = serializers.CharField(source='entity.address', read_only=True)
    entitycityname = serializers.CharField(source='entity.city.cityname', read_only=True)
    entitystate = serializers.CharField(source='entity.state.statename', read_only=True)
    entitypincode = serializers.CharField(source='entity.pincode', read_only=True)
    entitygst = serializers.CharField(source='entity.gstno', read_only=True)
    billtoname = serializers.CharField(source='accountid.accountname', read_only=True)
    billtoaddress1 = serializers.CharField(source='accountid.address1', read_only=True)
    billtoaddress2 = serializers.CharField(source='accountid.address2', read_only=True)
    billtostate = serializers.CharField(source='accountid.state.statename', read_only=True)
    billtocity = serializers.CharField(source='accountid.city.cityname', read_only=True)
    billtopin = serializers.CharField(source='accountid.city.pincode', read_only=True)
    billtopan = serializers.CharField(source='accountid.pan', read_only=True)
    #billtoaddress = serializers.SerializerMethodField()
    billtogst = serializers.CharField(source='accountid.gstno', read_only=True)
    shiptoname = serializers.CharField(source='shippedto.full_name', read_only=True)
    shiptoaddress1 = serializers.CharField(source='shippedto.address1', read_only=True)
    shiptoaddress2 = serializers.CharField(source='shippedto.address2', read_only=True)
    shiptostate = serializers.CharField(source='shippedto.state.statename', read_only=True)
    shiptocity = serializers.CharField(source='shippedto.city.cityname', read_only=True)
    shiptopin = serializers.CharField(source='shippedto.city.pincode', read_only=True)
    shiptopan = serializers.CharField(source='shippedto.pan', read_only=True)
    shiptogst = serializers.CharField(source='shippedto.gstno', read_only=True)
    transportname = serializers.CharField(source='transport.accountname', read_only=True)
    #shiptoaddress = serializers.SerializerMethodField()
    amountinwords = serializers.SerializerMethodField()
    phoneno = serializers.CharField(source='entity.phoneoffice', read_only=True)
    phoneno2 = serializers.CharField(source= 'entity.phoneresidence', read_only=True)
    bankname = serializers.CharField(source= 'entity.bank.bankname', read_only=True)
    bankacno = serializers.CharField(source= 'entity.bankacno', read_only=True)
    ifsccode = serializers.CharField(source= 'entity.ifsccode', read_only=True)
    billno = serializers.CharField(source= 'invoicenumber', read_only=True)
    gst_summary = serializers.SerializerMethodField()
    einvoice_details = serializers.SerializerMethodField()
    doctype = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReturn
        fields = (
            'id', 'sorderdate', 'billno','accountid', 'billtoname', 'billtoaddress1',
             'billtoaddress2','billtocity','billtostate','billtogst','billtopan','billtopin',
            'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype', 'billcash', 'supply',
            'totalquanity', 'totalpieces', 'advance', 'shiptostate', 'shiptoname','shiptocity','shiptoaddress1','shiptoaddress2','shiptopan','shiptogst','shiptopin',
            'remarks', 'transport', 'broker', 'taxid', 'tds194q', 'tds194q1', 'tcs206c1ch1',
            'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1', 'tcs206C2', 'addless', 'duedate', 'subtotal',
            'cgst', 'sgst', 'igst', 'cess', 'totalgst', 'expenses', 'gtotal', 'amountinwords',
            'subentity', 'entity', 'entityname', 'entityaddress','entitycityname','entitystate','entitypincode', 'entitygst', 'createdby',  'isactive', 'phoneno', 'phoneno2', 'entitydesc','reversecharge','bankname','bankacno','ifsccode','transportname',
            'entitypan', 'saleInvoiceDetails','gst_summary','einvoice_details','doctype'
        )

    def get_einvoice_details(self, obj):
        try:
            content_type = ContentType.objects.get_for_model(PurchaseReturn)
            einv = EInvoiceDetails.objects.get(content_type=content_type, object_id=obj.id)
        except EInvoiceDetails.DoesNotExist:
            return None

        qr_image_base64 = None
        if einv.signed_qr_code:
            # Generate QR image from SignedQRCode
            qr = qrcode.make(einv.signed_qr_code)
            buffered = BytesIO()
            qr.save(buffered, format="PNG")
            qr_image_base64 = base64.b64encode(buffered.getvalue()).decode()

        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "qr_image_base64": qr_image_base64,
            "ewb_no": einv.ewb_no,
            "ewb_date": einv.ewb_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_date else None,
            "ewb_valid_till": einv.ewb_valid_till.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_valid_till else None
        }


    def get_doctype(self, obj):
        return "Credit Note"

   

    

    def get_amountinwords(self, obj):
        return f"{string.capwords(num2words(obj.gtotal))} only"

    def get_gst_summary(self, obj):
        """
        Fetch and serialize GST summary data for the sales order header.
        """
        salesorderheader_id = obj.id
        aggregated_data = (
            Purchasereturndetails.objects.filter(purchasereturn_id=salesorderheader_id)
            .values("purchasereturn")
            .annotate(
                taxPercent=Case(
                    When(igstpercent=0, then=F("cgstpercent") + F("sgstpercent")),
                    default=F("igstpercent"),
                    output_field=FloatField(),
                ),
                taxable_amount=Sum("amount"),  # <- Removed filter
                total_cgst_amount=Sum("cgst", filter=Q(cgst__isnull=False)),
                total_sgst_amount=Sum("sgst", filter=Q(sgst__isnull=False)),
                total_igst_amount=Sum("igst", filter=Q(igst__isnull=False)),
            )
        )
        return list(aggregated_data)


class SalesOrderHeaderPDFSerializer(serializers.ModelSerializer):
    saleInvoiceDetails = SalesOrderDetailsPDFSerializer(many=True, read_only=True)

    # Entity
    entityname = serializers.CharField(source="entity.entityname", read_only=True)
    entitypan = serializers.CharField(source="entity.panno", read_only=True)
    entitydesc = serializers.CharField(source="entity.entitydesc", read_only=True)
    entityaddress = serializers.CharField(source="entity.address", read_only=True)
    entitycityname = serializers.CharField(source="entity.city.cityname", read_only=True)
    entitystate = serializers.CharField(source="entity.state.statename", read_only=True)
    entitypincode = serializers.CharField(source="entity.pincode", read_only=True)
    entitygst = serializers.CharField(source="entity.gstno", read_only=True)

    # Bill-to
    billtoname = serializers.CharField(source="accountid.accountname", read_only=True)
    billtoaddress1 = serializers.CharField(source="accountid.address1", read_only=True)
    billtoaddress2 = serializers.CharField(source="accountid.address2", read_only=True)
    billtostate = serializers.CharField(source="accountid.state.statename", read_only=True)
    billtocity = serializers.CharField(source="accountid.city.cityname", read_only=True)
    billtopin = serializers.CharField(source="accountid.city.pincode", read_only=True)
    billtopan = serializers.CharField(source="accountid.pan", read_only=True)
    billtogst = serializers.CharField(source="accountid.gstno", read_only=True)

    # Ship-to
    shiptoname = serializers.CharField(source="shippedto.full_name", read_only=True)
    shiptoaddress1 = serializers.CharField(source="shippedto.address1", read_only=True)
    shiptoaddress2 = serializers.CharField(source="shippedto.address2", read_only=True)
    shiptostate = serializers.CharField(source="shippedto.state.statename", read_only=True)
    shiptocity = serializers.CharField(source="shippedto.city.cityname", read_only=True)
    shiptopin = serializers.CharField(source="shippedto.city.pincode", read_only=True)
    shiptopan = serializers.CharField(source="shippedto.pan", read_only=True)
    shiptogst = serializers.CharField(source="shippedto.gstno", read_only=True)

    # Other
    transportname = serializers.CharField(source="transport.accountname", read_only=True)
    phoneno = serializers.CharField(source="entity.phoneoffice", read_only=True)
    phoneno2 = serializers.CharField(source="entity.phoneresidence", read_only=True)
    bankname = serializers.CharField(source="entity.bank.bankname", read_only=True)
    bankacno = serializers.CharField(source="entity.bankacno", read_only=True)
    ifsccode = serializers.CharField(source="entity.ifsccode", read_only=True)

    billno = serializers.CharField(source="invoicenumber", read_only=True)

    amountinwords = serializers.SerializerMethodField()
    gst_summary = serializers.SerializerMethodField()
    einvoice_details = serializers.SerializerMethodField()
    doctype = serializers.SerializerMethodField()

    class Meta:
        model = SalesOderHeader
        fields = (
            "id", "sorderdate", "billno", "accountid",
            "billtoname", "billtoaddress1", "billtoaddress2", "billtocity",
            "billtostate", "billtogst", "billtopan", "billtopin",
            "latepaymentalert", "grno", "terms", "vehicle", "taxtype", "billcash",
            "supply", "totalquanity", "totalpieces", "advance",
            "shiptostate", "shiptoname", "shiptocity", "shiptoaddress1",
            "shiptoaddress2", "shiptopan", "shiptogst", "shiptopin",
            "remarks", "transport", "broker", "taxid", "tds194q", "tds194q1",
            "tcs206c1ch1", "tcs206c1ch2", "tcs206c1ch3", "tcs206C1", "tcs206C2",
            "addless", "duedate", "stbefdiscount", "discount", "subtotal",
            "cgst", "sgst", "igst", "cess", "totalgst", "expenses", "gtotal",
            "amountinwords",
            "subentity", "entity", "entityname", "entityaddress",
            "entitycityname", "entitystate", "entitypincode", "entitygst",
            "createdby", "eway", "einvoice", "einvoicepluseway", "isactive",
            "phoneno", "phoneno2", "entitydesc", "reversecharge",
            "bankname", "bankacno", "ifsccode", "transportname",
            "entitypan", "saleInvoiceDetails", "gst_summary", "einvoice_details",
            "doctype",
        )

    def get_doctype(self, obj):
        return "Tax Invoice"

    def get_amountinwords(self, obj):
        try:
            text = num2words(obj.gtotal or 0, lang="en_IN", to="currency", currency="INR")
            return string.capwords(text)
        except Exception:
            return f"{string.capwords(num2words(obj.gtotal or 0))} only"

    def get_gst_summary(self, obj):
        """
        ✅ PDF-friendly grouping by taxPercent.
        taxPercent = (CGST%+SGST%) when IGST%==0 else IGST%
        """
        qs = salesOrderdetails.objects.filter(salesorderheader_id=obj.id)

        rate_field = DecimalField(max_digits=6, decimal_places=2)
        money_field = DecimalField(max_digits=14, decimal_places=2)

        tax_percent_expr = Case(
            When(
                igstpercent=Value(0),
                then=ExpressionWrapper(
                    Coalesce(Cast(F("cgstpercent"), rate_field), Value(0, output_field=rate_field)) +
                    Coalesce(Cast(F("sgstpercent"), rate_field), Value(0, output_field=rate_field)),
                    output_field=rate_field,
                ),
            ),
            default=Cast(F("igstpercent"), rate_field),
            output_field=rate_field,
        )

        aggregated = (
            qs.annotate(taxPercent=tax_percent_expr)
              .values("taxPercent")
              .annotate(
                  taxable_amount=ExpressionWrapper(
                      Coalesce(Sum(Cast("amount", money_field)), Value(0, output_field=money_field)),
                      output_field=money_field,
                  ),
                  total_cgst_amount=ExpressionWrapper(
                      Coalesce(Sum(Cast("cgst", money_field)), Value(0, output_field=money_field)),
                      output_field=money_field,
                  ),
                  total_sgst_amount=ExpressionWrapper(
                      Coalesce(Sum(Cast("sgst", money_field)), Value(0, output_field=money_field)),
                      output_field=money_field,
                  ),
                  total_igst_amount=ExpressionWrapper(
                      Coalesce(Sum(Cast("igst", money_field)), Value(0, output_field=money_field)),
                      output_field=money_field,
                  ),
              )
              .order_by("taxPercent")
        )
        return list(aggregated)

    def get_einvoice_details(self, obj):
        try:
            ct = ContentType.objects.get_for_model(SalesOderHeader)
            einv = EInvoiceDetails.objects.get(content_type=ct, object_id=obj.id)
        except EInvoiceDetails.DoesNotExist:
            return None

        qr_image_base64 = None
        if einv.signed_qr_code:
            try:
                qr = qrcode.make(einv.signed_qr_code)
                buf = BytesIO()
                qr.save(buf, format="PNG")
                qr_image_base64 = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                qr_image_base64 = None

        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "qr_image_base64": qr_image_base64,
            "ewb_no": einv.ewb_no,
            "ewb_date": einv.ewb_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_date else None,
            "ewb_valid_till": einv.ewb_valid_till.strftime("%d/%m/%Y %H:%M:%S") if einv.ewb_valid_till else None,
        }


# ======================================================================
# VIEW (PDF)
# ======================================================================


    
    # def get_saleInvoiceDetails1(self, obj):
    #     details = obj.saleInvoiceDetails.all()  
    #     serialized_details = SalesOrderDetailsPDFSerializer(details, many=True).data  

    #     paginated_details = []
    #     page = []
    #     page_linetotal = 0
    #     cumulative_linetotal = 0  # Running total across all pages

    #     for index, item in enumerate(serialized_details, start=1):
    #         page.append(item)
    #         page_linetotal += float(item["linetotal"])

    #         if index % 2 == 0 or index == len(serialized_details):  
    #             cumulative_linetotal += page_linetotal  
                
    #             paginated_details.append({
    #                 'items': page,
    #                 'page_linetotal': page_linetotal,  # Current page total
    #                 'cumulative_linetotal': cumulative_linetotal  # Running total including previous pages
    #             })
                
    #             page = []
    #             page_linetotal = 0  

    #     return paginated_details
    


class salesotherdetailsSerializer(serializers.ModelSerializer):
    
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)
    # productname = serializers.SerializerMethodField()
    # hsn = serializers.SerializerMethodField()
    # mrp = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = saleothercharges
        fields =  ('account','amount','name',)

    def get_name(self,obj):
        return obj.account.accountname


class purchaseotherdetailsSerializer(serializers.ModelSerializer):
    
    name = serializers.SerializerMethodField()

    class Meta:
        model = purchaseothercharges
        fields =  ('account','amount','name',)

    def get_name(self,obj):
        return obj.account.accountname
    

class purchaseotherdetailsimportSerializer(serializers.ModelSerializer):
    
    name = serializers.SerializerMethodField()

    class Meta:
        model = purchaseothercharges
        fields =  ('account','amount','name',)

    def get_name(self,obj):
        return obj.account.accountname
    

class PurchaseOrderImportAttachmentSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = purchaseotherimporAttachment
        fields = ['id', 'purchase_order_import','file', 'file_name', 'uploaded_at']

    def get_file_name(self, obj):
        return obj.file.name.split('/')[-1]  # Extract only the file name
    


class purchaseorderdetailimportsserializer(serializers.ModelSerializer):
   # otherchargesdetail = purchaseotherdetailsimportSerializer(many=True,required=False)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
   # productdesc1 = serializers.SerializerMethodField()
    #entityUser = entityUserSerializer(many=True)

    class Meta:
        model = PurchaseOrderimportdetails
        fields = ('id','product','productname','productdesc','hsn','mrp','orderqty','pieces','rate','actualamount','importamount','igst','cess','linetotal','entity',)
    
    def get_productname(self,obj):
        return obj.product.productname
    
    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode

    def get_mrp(self,obj):
        return obj.product.mrp
    


class purchaseorderimportSerializer(serializers.ModelSerializer):
    PurchaseOrderimportdetails = purchaseorderdetailimportsserializer(many=True)
    piattachments = PurchaseOrderImportAttachmentSerializer(many=True,required=False, allow_null=True)
   # productname = serializers.SerializerMethodField()

    class Meta:
        model = purchaseorderimport
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','state','district','city','pincode', 'totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','igst','cess','expenses','gtotal','importgtotal','entityfinid','entity','isactive','PurchaseOrderimportdetails','piattachments',)


    
    


    def create(self, validated_data):
       # print(validated_data)
        PurchaseOrderDetails_data = validated_data.pop('PurchaseOrderimportdetails')
        with transaction.atomic():
            order = purchaseorderimport.objects.create(**validated_data)
            stk = stocktransactionimport(order, transactiontype= 'PI',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype= 'I')
            #print(order.objects.get("id"))
            #print(tracks_data)
            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
               # purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = PurchaseOrderimportdetails.objects.create(purchaseorder = order, **PurchaseOrderDetail_data)
                # for purchaseothercharge_data in purchaseothercharges_data:
                #     detail1 = purchaseotherimportcharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                   #\ stk.createothertransactiondetails(detail=detail1,stocktype='P')

            
                stk.createtransactiondetails(detail=detail,stocktype='P')
                
            
            stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','account','billno','billdate','showledgeraccount','terms','taxtype','state','district','city','pincode', 'billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','igst','cess','expenses','gtotal','importgtotal','entityfinid','entity','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        

        # print(instance.id)
        stk = stocktransactionimport(instance, transactiontype= 'PI',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype='U')
        with transaction.atomic():
            stk.createtransaction()
            
            i = instance.save()

            PurchaseOrderimportdetails.objects.filter(purchaseorder=instance,entity = instance.entity).delete()
        
            PurchaseOrderDetails_data = validated_data.get('PurchaseOrderimportdetails')

            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
               # purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = PurchaseOrderimportdetails.objects.create(purchaseorder = instance, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='P')
                # for purchaseothercharge_data in purchaseothercharges_data:
                  
                #     detail1 = purchaseotherimportcharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                  #  stk.createothertransactiondetails(detail=detail1,stocktype='P')

        return instance


    














ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
AUTO_RECALC_TOTALS = True
AUTO_COMPUTE_ROUNDOFF = True
ROUNDOFF_MODE = "nearest"  # "nearest" | "up" | "down"

def _state_code_from(obj):
    if not obj:
        return None
    for attr in ("gst_state_code", "state_code", "statecode", "code"):
        if hasattr(obj, attr):
            val = getattr(obj, attr)
            if val:
                return str(val)
    return None

def _resolve_entity_state_code(source):
    entity = source.get("entity") if isinstance(source, dict) else getattr(source, "entity", None)
    if entity and getattr(entity, "state", None):
        return _state_code_from(entity.state)
    return None

def _resolve_pos_state_code(source):
    shippedto = source.get("shippedto") if isinstance(source, dict) else getattr(source, "shippedto", None)
    header_state = source.get("state") if isinstance(source, dict) else getattr(source, "state", None)
    if shippedto and getattr(shippedto, "state", None):
        return _state_code_from(shippedto.state)
    if header_state:
        return _state_code_from(header_state)
    return None

def _apply_tax_scheme_to_header_data(payload: dict) -> bool:
    ent = _resolve_entity_state_code(payload)
    pos = _resolve_pos_state_code(payload)
    is_inter = bool(ent and pos and ent != pos)
    payload["isigst"] = is_inter
    for k in ("cgst", "sgst", "igst"):
        payload.setdefault(k, ZERO2)
    if is_inter:
        payload["cgst"] = ZERO2
        payload["sgst"] = ZERO2
    else:
        payload["igst"] = ZERO2
    return is_inter

def _apply_tax_scheme_to_detail_dict(is_inter: bool, row: dict):
    row["isigst"] = is_inter
    for k in ("cgst", "sgst", "igst", "cgstpercent", "sgstpercent", "igstpercent"):
        row.setdefault(k, ZERO2)
    if is_inter:
        row["cgst"] = row["sgst"] = ZERO2
        row["cgstpercent"] = row["sgstpercent"] = ZERO2
    else:
        row["igst"] = ZERO2
        row["igstpercent"] = ZERO2

def _mode(order) -> str:
    if str(order.einvoice).lower() == "true" and str(order.eway).lower() == "true":
        return "both"
    if order.einvoice:
        return "einvoice"
    if order.eway:
        return "eway"
    return "none"


def _mode_from_invoice_mode(obj_or_dict):
    """
    Returns: 'none' | 'einvoice' | 'eway' | 'both'
    Accepts either model instance or validated_data dict.
    """
    if isinstance(obj_or_dict, dict):
        im = obj_or_dict.get("invoiceMode", 0)
    else:
        im = getattr(obj_or_dict, "invoiceMode", 0)

    try:
        im = int(im or 0)
    except (TypeError, ValueError):
        im = 0

    return {
        0: "none",
        1: "eway",
        2: "einvoice",
        3: "both",
    }.get(im, "none")


def _qr_base64_from_signed_qr(signed_qr_code: str):
    if not signed_qr_code:
        return None
    qr = qrcode.make(signed_qr_code)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def _build_adddetails_dict(instance: SalesOderHeader):
    payload = {}
    pay = PayDtls.objects.filter(invoice=instance).first()
    ref = RefDtls.objects.filter(invoice=instance).first()
    ewb = EwbDtls.objects.filter(invoice=instance).first()
    exp = ExpDtls.objects.filter(invoice=instance).first()
    addldocs = AddlDocDtls.objects.filter(invoice=instance)
    if pay:
        payload["paydtls"] = PayDtlsSerializer(pay).data
    if ref:
        payload["refdtls"] = RefDtlsSerializer(ref).data
    if ewb:
        payload["ewbdtls"] = EwbDtlsSerializer(ewb).data
    if exp:
        payload["expdtls"] = ExpDtlsSerializer(exp).data
    payload["addldocdtls"] = AddlDocDtlsSerializer(addldocs, many=True).data
    return payload

def _recompute_header_totals(header: SalesOderHeader):
    rows = salesOrderdetails.objects.filter(salesorderheader=header).values(
        "orderqty", "ratebefdiscount", "rate", "amount",
        "cgst", "sgst", "igst", "cess", "orderDiscountValue"
    )
    stbefdiscount = ZERO2
    discount = ZERO2
    subtotal = ZERO2
    totalgst = ZERO2
    for r in rows:
        qty = r.get("orderqty") or ZERO4
        rbd = r.get("ratebefdiscount") or ZERO2
        rate = r.get("rate") or ZERO2
        amt = r.get("amount") or ZERO2
        cgst = r.get("cgst") or ZERO2
        sgst = r.get("sgst") or ZERO2
        igst = r.get("igst") or ZERO2
        cess = r.get("cess") or ZERO2
        disc_val = r.get("orderDiscountValue")
        stbefdiscount += (rbd * qty)
        if disc_val is not None:
            discount += disc_val
        else:
            diff = rbd - rate
            if diff > ZERO2:
                discount += (diff * qty)
        subtotal += amt
        totalgst += (cgst + sgst + igst + (cess or ZERO2))

    header.stbefdiscount = stbefdiscount
    header.discount = discount
    header.subtotal = subtotal
    header.totalgst = totalgst

    expenses = header.expenses or ZERO2
    addless  = header.addless  or ZERO2
    advance  = header.advance  or ZERO2

    gross = subtotal + totalgst + expenses + addless - advance

    if AUTO_COMPUTE_ROUNDOFF:
        if ROUNDOFF_MODE == "nearest":
            rounded = gross.to_integral_value(rounding=ROUND_HALF_UP)
        elif ROUNDOFF_MODE == "up":
            rounded = gross.to_integral_value(rounding=ROUND_CEILING)
        elif ROUNDOFF_MODE == "down":
            rounded = gross.to_integral_value(rounding=ROUND_FLOOR)
        else:
            rounded = gross.to_integral_value(rounding=ROUND_HALF_UP)
        header.roundOff = (Decimal(rounded) - gross).quantize(Decimal("0.01"))
        header.gtotal   = Decimal(rounded).quantize(Decimal("0.01"))
    else:
        header.gtotal = (gross + (header.roundOff or ZERO2)).quantize(Decimal("0.01"))

Q2 = Decimal("0.01")
def q2(x):
    if x is None or x == "":
        return ZERO2
    return Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP)

def _normalize_on_isigst_flip(instance, new_isigst: bool):
    """
    Make existing data comply with header/detail CheckConstraints when flipping regime.
    """
    from .models import salesOrderdetails as _Detail
    if new_isigst:
        instance.cgst = ZERO2
        instance.sgst = ZERO2
        _Detail.objects.filter(salesorderheader=instance).update(isigst=True, cgst=ZERO2, sgst=ZERO2)
    else:
        instance.igst = ZERO2
        _Detail.objects.filter(salesorderheader=instance).update(isigst=False, igst=ZERO2)

def _deduce_isigst_from_payload(validated_header: dict, details_data: list, fallback: bool) -> bool:
    """
    Decide isigst from numbers the client sent when 'isigst' isn't in the payload.
    Priority: header amounts → detail amounts → detail flags → fallback.
    """
    igst = q2(validated_header.get("igst"))
    cgst = q2(validated_header.get("cgst"))
    sgst = q2(validated_header.get("sgst"))

    # Clear, non-ambiguous signals from header:
    if igst > ZERO2 and cgst == ZERO2 and sgst == ZERO2:
        return True
    if (cgst > ZERO2 or sgst > ZERO2) and igst == ZERO2:
        return False

    # Look at details:
    any_igst_amt = any(q2(d.get("igst")) > ZERO2 for d in details_data)
    any_cgsg_amt = any(q2(d.get("cgst")) > ZERO2 or q2(d.get("sgst")) > ZERO2 for d in details_data)
    if any_igst_amt and not any_cgsg_amt:
        return True
    if any_cgsg_amt and not any_igst_amt:
        return False

    # Look at detail flags (majority):
    flags = [bool(d.get("isigst")) for d in details_data if d.get("isigst") is not None]
    if flags:
        trues = sum(1 for f in flags if f)
        falses = len(flags) - trues
        if trues > falses:
            return True
        if falses > trues:
            return False

    return bool(fallback)

def _ensure_line_totals_in_payload(row: dict) -> None:
    """If linetotal missing, compute it from amounts—no regime logic."""
    amount = q2(row.get("amount"))
    cgst   = q2(row.get("cgst"))
    sgst   = q2(row.get("sgst"))
    igst   = q2(row.get("igst"))
    cess   = q2(row.get("cess"))
    ochg   = q2(row.get("othercharges"))
    if row.get("linetotal") in (None, ""):
        row["linetotal"] = q2(amount + cgst + sgst + igst + cess + ochg)

def _rollup_component_taxes_to_header(hdr):
    agg = hdr.saleInvoiceDetails.aggregate(
        sub=Sum("amount"), cg=Sum("cgst"), sg=Sum("sgst"), ig=Sum("igst"), ce=Sum("cess"),
        stbef=Sum("befDiscountProductAmount"), discv=Sum("orderDiscountValue"),
    )
    hdr.subtotal      = q2(agg["sub"] or ZERO2)
    hdr.cgst          = q2(agg["cg"] or ZERO2)
    hdr.sgst          = q2(agg["sg"] or ZERO2)
    hdr.igst          = q2(agg["ig"] or ZERO2)
    hdr.cess          = q2(agg["ce"] or ZERO2)
    hdr.totalgst      = q2(hdr.cgst + hdr.sgst + hdr.igst + hdr.cess)
    hdr.stbefdiscount = q2(agg["stbef"] or ZERO2)
    hdr.discount      = q2(agg["discv"] or ZERO2)

def _recompute_header_totals(hdr):
    addless  = q2(hdr.addless or ZERO2)
    expenses = q2(hdr.expenses or ZERO2)
    advance  = q2(hdr.advance or ZERO2)
    gross = q2(hdr.subtotal + hdr.totalgst + addless + expenses)
    net   = q2(gross - advance)
    hdr.roundOff = net
    hdr.gtotal   = net


class salesOrderdetailsSerializer(serializers.ModelSerializer):
    # nested other charges
    otherchargesdetail = serializers.ListSerializer(
        child=serializers.DictField(),
        required=False,
    )

    id = serializers.IntegerField(required=False)

    # Read-only convenience fields from related product (new structure)
    productname = serializers.CharField(
        source='product.productname',
        read_only=True,
        allow_null=True,
    )

    # Derived via ProductGstRate -> HsnSac.code
    hsn = serializers.SerializerMethodField(read_only=True)

    # MRP from related ProductPrice (or similar) instead of old product.mrp
    mrp = serializers.SerializerMethodField(read_only=True)

    # validators (still optional; model defaults handle omissions)
    orderqty = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    pieces   = serializers.IntegerField(required=False)

    befDiscountProductAmount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    ratebefdiscount          = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    orderDiscount            = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    orderDiscountValue       = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    rate   = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    othercharges = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    cgst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    sgst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    igst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    cess = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    cgstpercent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    sgstpercent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    igstpercent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

    linetotal = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    class Meta:
        model = salesOrderdetails
        fields = (
            'id', 'product', 'productname', 'hsn', 'mrp', 'productdesc',
            'orderqty', 'pieces',
            'befDiscountProductAmount', 'ratebefdiscount',
            'orderDiscount', 'orderDiscountValue',
            'rate', 'amount', 'othercharges',
            'cgst', 'sgst', 'igst', 'isigst',
            'cgstpercent', 'sgstpercent', 'igstpercent', 'cess',
            'linetotal', 'subentity', 'entity',
            'otherchargesdetail',
        )

    # --------------------------
    # Helpers for new GST/HSN
    # --------------------------

    def _get_default_gst_rate(self, product):
        """
        Uses the prefetched gst_rates (from product__gst_rates__hsn)
        purely in Python, no extra DB hits.
        """
        rates_manager = getattr(product, 'gst_rates', None)
        if not rates_manager:
            return None

        # This uses the prefetch cache if available
        rates = list(rates_manager.all())
        if not rates:
            return None

        # Prefer default rate if flagged
        for r in rates:
            if getattr(r, "isdefault", False):
                return r

        # Fallback to first
        return rates[0]

    def get_hsn(self, obj):
        product = getattr(obj, 'product', None)
        if not product:
            return None

        rate = self._get_default_gst_rate(product)
        if not rate or not rate.hsn:
            return None

        # HsnSac.code
        return rate.hsn.code

    def get_mrp(self, obj):
        """
        Best-effort MRP:
        - Assumes product.prices is prefetched (product__prices).
        - Returns price_obj.mrp if present, else price_obj.price, else None.
        """
        product = getattr(obj, 'product', None)
        if not product:
            return None

        prices_manager = getattr(product, 'prices', None)
        if not prices_manager:
            return None

        prices = list(prices_manager.all())
        if not prices:
            return None

        price_obj = prices[0]

        if hasattr(price_obj, 'mrp'):
            return price_obj.mrp
        if hasattr(price_obj, 'price'):
            return price_obj.price
        return None

    # --------------------------
    # Validation / linetotal
    # --------------------------

    def validate(self, attrs):
        # Non-negative sanity (DB constraints also protect this)
        for f in ("amount", "cgst", "sgst", "igst", "cess", "othercharges", "linetotal"):
            if attrs.get(f) is not None and q2(attrs[f]) < ZERO2:
                raise serializers.ValidationError({f: "Must be >= 0.00"})

        # Compute linetotal if missing
        row = dict(attrs)
        _ensure_line_totals_in_payload(row)
        attrs["linetotal"] = row["linetotal"]
        return attrs
    

# class salesOrderdetailsSerializer(serializers.ModelSerializer):
#     #entityUser = entityUserSerializer(many=True)
#     otherchargesdetail = salesotherdetailsSerializer(many=True,required=False)
#     id = serializers.IntegerField(required=False)
#     productname = serializers.SerializerMethodField()
#     hsn = serializers.SerializerMethodField()
#     mrp = serializers.SerializerMethodField()

#     class Meta:
#         model = salesOrderdetails
#         fields =  ('id','product','productname','hsn','mrp','productdesc','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','cess','linetotal','subentity','entity','otherchargesdetail',)

#     def get_productname(self,obj):
#         return obj.product.productname

#     def get_hsn(self,obj):
#         return obj.product.hsn
    
#     def get_mrp(self,obj):
#         return obj.product.mrp
    

class saleOrderdetailsSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
   # otherchargesdetail = salesotherdetailsSerializer(many=True,required=False)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()

    class Meta:
        model = salesOrderdetail
        fields =  ('id','product','productname','hsn','mrp','productdesc','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','cess','linetotal','subentity','entity',)

    def get_productname(self,obj):
        return obj.product.productname

    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode
    
    def get_mrp(self,obj):
        return obj.product.mrp
    

class gstorderservicesdetailsSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
    id = serializers.IntegerField(required=False)
    accountname = serializers.SerializerMethodField()
    saccode = serializers.SerializerMethodField()
    

    class Meta:
        model = gstorderservicesdetails
        fields =  ('id','account','accountname','accountdesc','multiplier','rate','amount','cgst','sgst','igst','igstreverse','cgstreverse','sgstreverse','linetotal','entity','saccode',)

    def get_accountname(self,obj):
        return obj.account.accountname
    
    def get_saccode(self,obj):
        return obj.account.saccode

   





class gstorderservicesSerializer(serializers.ModelSerializer):
    gstorderservicesdetails = gstorderservicesdetailsSerializer(many=True)
    class Meta:
        model = gstorderservices
        fields = ('id','orderdate','billno','account','taxtype','billcash','grno','vehicle','orderType','totalgst','state','district','city','pincode', 'subtotal','expensesbeforetax','cgst','sgst','igst','igstreverse','cgstreverse','sgstreverse','multiplier','expensesaftertax','gtotal','remarks','entityfinid', 'entity','createdby','gstorderservicesdetails','isactive',)


    

    def create(self, validated_data):
        #print(validated_data)
        with transaction.atomic():
            salesOrderdetails_data = validated_data.pop('gstorderservicesdetails')
            validated_data.pop('billno')

            if gstorderservices.objects.filter(entity= validated_data['entity'].id,orderType = validated_data['orderType']).count() == 0:
                billno2 = 1
            else:
                billno2 = (gstorderservices.objects.filter(entity= validated_data['entity'].id).last().billno) + 1


           # print(billno)

           
            order = gstorderservices.objects.create(**validated_data,billno= billno2)
            stk = gststocktransaction(order, transactiontype= validated_data['orderType'],debit=1,credit=0,description= 'By Sale Bill No: ',entrytype= 'I')
           # stk = stocktransactionsale(order, transactiontype= 'S',debit=1,credit=0,description= 'By Sale Bill No: ')
            #print(tracks_data)
            for PurchaseOrderDetail_data in salesOrderdetails_data:
                detail = gstorderservicesdetails.objects.create(gstorderservices = order, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype=validated_data['orderType'])

                # if(detail.orderqty ==0.00):
                #     qty = detail.pieces
                # else:
                #     qty = detail.orderqty
                # StockTransactions.objects.create(accounthead = detail.product.saleaccount.accounthead,account= detail.product.saleaccount,stock=detail.product,transactiontype = 'S',transactionid = order.id,desc = 'Sale By B.No ' + str(order.billno),stockttype = 'S',salequantity = qty,drcr = 0,creditamount = detail.amount,cgstcr = detail.cgst,sgstcr= detail.sgst,igstcr = detail.igst,entrydate = order.sorderdate,entity = order.entity,createdby = order.owner)
            
            stk.createtransaction()
            return order

    def update(self, instance, validated_data):
        fields = ['orderdate','billno','account','taxtype','billcash','grno','vehicle', 'state','district','city','pincode','orderType','totalgst','subtotal','expensesbeforetax','cgst','sgst','igst','igstreverse','cgstreverse','sgstreverse','multiplier','expensesaftertax','gtotal','remarks','entityfinid', 'entity','createdby',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        with transaction.atomic():
            instance.save()
            stk = gststocktransaction(instance, transactiontype= validated_data['orderType'],debit=1,credit=0,description= 'By Sale Bill No:',entrytype = 'U')
            gstorderservicesdetails.objects.filter(gstorderservices=instance,entity = instance.entity).delete()
            stk.createtransaction()

            salesOrderdetails_data = validated_data.get('gstorderservicesdetails')

            for PurchaseOrderDetail_data in salesOrderdetails_data:
                detail = gstorderservicesdetails.objects.create(gstorderservices = instance, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype=validated_data['orderType'])

        #  stk.updateransaction()
            return instance


class PayDtlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayDtls
        exclude = ['invoice','sales_return','purchase_return']

class RefDtlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefDtls
        exclude = ['invoice','sales_return','purchase_return']

class AddlDocDtlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AddlDocDtls
        exclude = ['invoice','sales_return','purchase_return']

class EwbDtlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EwbDtls
        exclude = ['invoice','sales_return','purchase_return']

class ExpDtlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpDtls
        exclude = ['invoice','sales_return','purchase_return']


class AddDetailsSerializer(serializers.Serializer):
    paydtls = PayDtlsSerializer(required=False)
    refdtls = RefDtlsSerializer(required=False)
    ewbdtls = EwbDtlsSerializer(required=False)
    expdtls = ExpDtlsSerializer(required=False)
    addldocdtls = AddlDocDtlsSerializer(many=True, required=False)


def _normalize_sales_detail_taxes_trust_amounts(d: dict, is_inter: bool) -> None:
    """
    Normalize ONE sales detail dict IN-PLACE.
    Priority: USE POSTED AMOUNTS if provided (>0); otherwise compute from %; otherwise 0.
    Enforce regime:
      - Inter-state: IGST only (zero CGST/SGST).
      - Intra-state: CGST+SGST only (zero IGST).
    """
    amt = q2(d.get("amount", ZERO2) or ZERO2)

    # Posted amounts (trusted if > 0)
    cgst_amt = q2(d.get("cgst", ZERO2) or ZERO2)
    sgst_amt = q2(d.get("sgst", ZERO2) or ZERO2)
    igst_amt = q2(d.get("igst", ZERO2) or ZERO2)
    cess_amt = q2(d.get("cess", ZERO2) or ZERO2)

    # Posted percents (used only when corresponding amount is 0)
    c_pct = q2(d.get("cgstpercent", ZERO2) or ZERO2)
    s_pct = q2(d.get("sgstpercent", ZERO2) or ZERO2)
    i_pct = q2(d.get("igstpercent", ZERO2) or ZERO2)

    if is_inter:
        # IGST regime: keep IGST if posted; else compute from igst% ; else merge cgst+sgst if present; else compute from their %
        if igst_amt > ZERO2:
            cgst_amt = sgst_amt = ZERO2
        elif i_pct > ZERO2:
            igst_amt = q2(amt * i_pct / Decimal("100"))
            cgst_amt = sgst_amt = ZERO2
        elif (cgst_amt > ZERO2 or sgst_amt > ZERO2):
            igst_amt = q2(cgst_amt + sgst_amt)
            cgst_amt = sgst_amt = ZERO2
        elif (c_pct > ZERO2 or s_pct > ZERO2):
            igst_amt = q2(amt * (c_pct + s_pct) / Decimal("100"))
            cgst_amt = sgst_amt = ZERO2
        else:
            cgst_amt = sgst_amt = ZERO2  # leave igst as posted (zero)
    else:
        # Intra regime: keep CGST/SGST if posted; else compute from their %; else split IGST (amount or %) into halves
        if (cgst_amt > ZERO2 or sgst_amt > ZERO2):
            igst_amt = ZERO2
            # if only one side posted but percents available, fill the other from % (optional, safe no-op if pct=0)
            if cgst_amt == ZERO2 and c_pct > ZERO2:
                cgst_amt = q2(amt * c_pct / Decimal("100"))
            if sgst_amt == ZERO2 and s_pct > ZERO2:
                sgst_amt = q2(amt * s_pct / Decimal("100"))
        elif (c_pct > ZERO2 or s_pct > ZERO2):
            cgst_amt = q2(amt * c_pct / Decimal("100"))
            sgst_amt = q2(amt * s_pct / Decimal("100"))
            igst_amt = ZERO2
        elif igst_amt > ZERO2:
            half = q2(igst_amt / Decimal("2"))
            cgst_amt, sgst_amt, igst_amt = half, q2(igst_amt - half), ZERO2
        elif i_pct > ZERO2:
            half = q2(i_pct / Decimal("2"))
            cgst_amt = q2(amt * half / Decimal("100"))
            sgst_amt = q2(amt * (i_pct - half) / Decimal("100"))
            igst_amt = ZERO2
        else:
            igst_amt = ZERO2  # leave cgst/sgst as posted (zeros)

    d["cgst"] = cgst_amt
    d["sgst"] = sgst_amt
    d["igst"] = igst_amt
    d["cess"] = cess_amt
    # (optional) reflect regime on the row for downstream logic
    d["isigst"] = bool(is_inter)

def _rollup_component_taxes_to_header(order) -> None:
    from invoice.models import salesOrderdetails
    agg = (salesOrderdetails.objects
           .filter(salesorderheader=order)
           .annotate(
               _cgst=Coalesce(F("cgst"), V(ZERO2)),
               _sgst=Coalesce(F("sgst"), V(ZERO2)),
               _igst=Coalesce(F("igst"), V(ZERO2)),
               _cess=Coalesce(F("cess"), V(ZERO2)),
           ).aggregate(
               sum_cgst=Coalesce(Sum("_cgst"), V(ZERO2)),
               sum_sgst=Coalesce(Sum("_sgst"), V(ZERO2)),
               sum_igst=Coalesce(Sum("_igst"), V(ZERO2)),
               sum_cess=Coalesce(Sum("_cess"), V(ZERO2)),
           ))
    order.cgst = q2(agg["sum_cgst"])
    order.sgst = q2(agg["sum_sgst"])
    order.igst = q2(agg["sum_igst"])
    order.cess = q2(agg["sum_cess"])

def _recompute_header_totals(order) -> None:
    from invoice.models import salesOrderdetails
    agg = (salesOrderdetails.objects
           .filter(salesorderheader=order)
           .annotate(
               _amt = Coalesce(F("amount"), V(ZERO2)),
               _cgst= Coalesce(F("cgst"),   V(ZERO2)),
               _sgst= Coalesce(F("sgst"),   V(ZERO2)),
               _igst= Coalesce(F("igst"),   V(ZERO2)),
               _cess= Coalesce(F("cess"),   V(ZERO2)),
           ).aggregate(
               total_amount=Coalesce(Sum("_amt"),  V(ZERO2)),
               sum_cgst    =Coalesce(Sum("_cgst"), V(ZERO2)),
               sum_sgst    =Coalesce(Sum("_sgst"), V(ZERO2)),
               sum_igst    =Coalesce(Sum("_igst"), V(ZERO2)),
               sum_cess    =Coalesce(Sum("_cess"), V(ZERO2)),
           ))

    subtotal = q2(agg["total_amount"])
    totalgst = q2(agg["sum_cgst"] + agg["sum_sgst"] + agg["sum_igst"] + agg["sum_cess"])
    discount = q2(order.discount or ZERO2)
    addless  = q2(order.addless  or ZERO2)
    expenses = q2(order.expenses or ZERO2)

    order.stbefdiscount = subtotal
    order.subtotal      = subtotal
    order.totalgst      = totalgst
    order.gtotal        = q2(subtotal - discount + addless + totalgst + expenses)

def _estimate_unit_cost(product) -> Decimal:
    """
    Best-effort fallback for InventoryMove.unit_cost on SALES (COGS).
    Tries common field names; returns ZERO4 if nothing found.
    """
    for attr in (
        "standardcost", "std_cost", "average_cost", "avgcost",
        "last_purchase_rate", "lastpurchaserate", "purchase_rate", "purchaserate",
    ):
        val = getattr(product, attr, None)
        try:
            val = Decimal(str(val))
        except Exception:
            val = None
        if val and val > ZERO4:
            return val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return ZERO4






# serializers.py (only relevant parts changed)
from django.db import transaction
from django.db.models import Max
from django.contrib.contenttypes.models import ContentType

# keep your existing imports...
# IMPORTANT: ensure stocktransactionsale is imported where it lives
# from Finacc.invoice.posting import stocktransactionsale  # adjust path if needed

MASTERGST_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)

logger = logging.getLogger(__name__)


class SalesOderHeaderSerializer(serializers.ModelSerializer):
    # ---------- nested ----------
    saleInvoiceDetails = salesOrderdetailsSerializer(many=True)
    adddetails = serializers.DictField(required=False, write_only=True)

    # ---------- read-only helpers ----------
    originalinvoice_number = serializers.SerializerMethodField()
    einvoice_details       = serializers.SerializerMethodField()

    # ---------- optional numeric fields ----------
    stbefdiscount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    discount      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    subtotal      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    totalgst      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    expenses      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    addless       = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    advance       = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    gtotal        = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    roundOff      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    class Meta:
        model = SalesOderHeader
        fields = (
            'id','sorderdate','billno','accountid','latepaymentalert','grno','state','district','city',
            'pincode','terms','vehicle','taxtype','billcash','supply','totalquanity','totalpieces','advance',
            'shippedto','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1',
            'tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','addless','duedate','stbefdiscount','subtotal',
            'discount','cgst','sgst','igst','isigst','invoicetype','reversecharge','cess','totalgst',
            'expenses','gtotal','roundOff','entityfinid','subentity','entity','createdby','eway','einvoice',
            'isammended','originalinvoice','originalinvoice_number','einvoicepluseway','isactive',
            'saleInvoiceDetails','adddetails','einvoice_details','isadditionaldetail','invoicenumber','invoiceMode',
        )

    # ===== utilities ==========================================================

    @staticmethod
    def _pk_or_none(val):
        """Return positive int PK, else None for 0/'0'/None/''/negatives."""
        try:
            i = int(val)
            return i if i > 0 else None
        except Exception:
            return None

    @classmethod
    def _strip_pk(cls, d: dict):
        """Remove 'id' key if it's falsy or non-positive."""
        if 'id' in d and cls._pk_or_none(d['id']) is None:
            d.pop('id', None)
        return d

    @staticmethod
    def _header_update_fields():
        return [
            'sorderdate','billno','accountid','latepaymentalert','grno','terms','vehicle','taxtype','billcash',
            'supply','totalquanity','totalpieces','advance','shippedto','remarks','transport','broker','taxid',
            'tds194q','tds194q1','tcs206c1ch1','state','district','city','pincode','tcs206c1ch2','tcs206c1ch3',
            'tcs206C1','tcs206C2','addless','duedate','stbefdiscount','subtotal','discount',
            'cgst','sgst','igst','isigst','invoicetype','reversecharge','cess','totalgst','expenses','gtotal',
            'roundOff','isactive','eway','einvoice','einvoicepluseway','entityfinid','subentity','entity',
            'createdby','isadditionaldetail','invoicenumber',
        ]

    # ===== read helpers =======================================================

    def get_originalinvoice_number(self, obj):
        return getattr(getattr(obj, "originalinvoice", None), "invoicenumber", None)

    def get_einvoice_details(self, obj):
        ct = ContentType.objects.get_for_model(obj, for_concrete_model=False)
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=obj.id).first()
        if not einv:
            return None
        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "qr_image_base64": _qr_base64_from_signed_qr(einv.signed_qr_code) if einv.signed_qr_code else None,
        }

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        try:
            rep["adddetails"] = _build_adddetails_dict(instance)
        except Exception:
            rep["adddetails"] = None
        return rep

    def validate(self, attrs):
        return attrs

    # -------------------------------------------------------------------------
    # Your existing private methods (kept as-is in your project)
    # - _decide_and_enforce_isigst
    # - _upsert_details
    # - _recalc_totals
    # - _post_once_via_shim
    # - other helpers: _deduce_isigst_from_payload, _normalize_on_isigst_flip, etc.
    # -------------------------------------------------------------------------


    def _decide_and_enforce_isigst(self, inst_or_data, details_data, is_create: bool) -> bool:
        """
        Decide effective 'isigst' and zero opposite header tax fields to satisfy
        DB CheckConstraint before save.
        """
        if is_create:
            provided = inst_or_data.get('isigst', None)
            new_isigst = _deduce_isigst_from_payload(inst_or_data, details_data, fallback=bool(provided or False)) \
                         if provided is None else bool(provided)
            inst_or_data['isigst'] = new_isigst
            if new_isigst:
                inst_or_data['cgst'] = ZERO2
                inst_or_data['sgst'] = ZERO2
            else:
                inst_or_data['igst'] = ZERO2
            return new_isigst

        # update-path
        instance, payload = inst_or_data
        provided = payload.get('isigst', None)
        new_isigst = _deduce_isigst_from_payload(payload, details_data, fallback=instance.isigst) \
                     if provided is None else bool(provided)

        # if flipping or payload would violate constraint -> normalize first
        need_normalize = (
            new_isigst != bool(instance.isigst)
            or (new_isigst and (q2(payload.get('cgst', instance.cgst)) > ZERO2 or
                                q2(payload.get('sgst', instance.sgst)) > ZERO2))
            or ((not new_isigst) and q2(payload.get('igst', instance.igst)) > ZERO2)
        )
        if need_normalize:
            _normalize_on_isigst_flip(instance, new_isigst)

        # enforce opposite zeros in payload we're about to save
        if new_isigst:
            payload['cgst'] = ZERO2
            payload['sgst'] = ZERO2
        else:
            payload['igst'] = ZERO2
        payload['isigst'] = new_isigst
        return new_isigst
    
    def _upsert_details(self, order, details_data: list, is_update: bool):
        """
        Trust amounts/percents from client, compute linetotal if missing.
        On update: upsert and delete removed lines. No stock posting here.
        """
        if not is_update:
            for row in details_data:
                self._strip_pk(row)
                other_charges = row.pop('otherchargesdetail', [])
                for oc in other_charges:
                    self._strip_pk(oc)
                _ensure_line_totals_in_payload(row)
                d = salesOrderdetails.objects.create(salesorderheader=order, **row)
                if other_charges:
                    for oc in other_charges:
                        oc['salesorderdetail'] = d
                    saleothercharges.objects.bulk_create([
                        saleothercharges(**oc) for oc in other_charges
                    ])
            return

        # update path
        existing_map = {d.id: d for d in salesOrderdetails.objects.filter(salesorderheader=order)}
        existing_ids = set(existing_map.keys())
        seen_ids     = set()

        for row in details_data:
            detail_id = self._pk_or_none(row.get('id'))
            row.pop('id', None)
            other_charges = row.pop('otherchargesdetail', [])
            for oc in other_charges:
                self._strip_pk(oc)

            _ensure_line_totals_in_payload(row)

            if detail_id is None:
                d = salesOrderdetails.objects.create(salesorderheader=order, **row)
            else:
                d = existing_map.get(detail_id)
                if d:
                    seen_ids.add(detail_id)
                    for k, v in row.items():
                        setattr(d, k, v)
                    d.save()
                else:
                    d = salesOrderdetails.objects.create(salesorderheader=order, **row)

            # refresh charges
            saleothercharges.objects.filter(salesorderdetail=d).delete()
            if other_charges:
                for oc in other_charges:
                    oc['salesorderdetail'] = d
                saleothercharges.objects.bulk_create([
                    saleothercharges(**oc) for oc in other_charges
                ])

        # delete removed detail lines
        ids_to_delete = existing_ids - seen_ids
        if ids_to_delete:
            salesOrderdetails.objects.filter(id__in=ids_to_delete).delete()

    def _recalc_totals(self, order: SalesOderHeader):
        _rollup_component_taxes_to_header(order)
        _recompute_header_totals(order)
        order.save(update_fields=[
            "cgst","sgst","igst","cess",
            "stbefdiscount","discount","subtotal","totalgst","roundOff","gtotal"
        ])

    def _post_once_via_shim(self, order: SalesOderHeader, entrytype: str):
        """
        Single authoritative posting (creates JL & IM).
        DO NOT call createtransactiondetails per-line; shim re-queries.
        """
        stk = stocktransactionsale(order, transactiontype='S', debit=1, credit=0,
                                   description='By Sale Bill No:', entrytype=entrytype)
        stk.createtransaction()

    

    # ✅ INCLUDED: _upsert_adddetails (your function, improved safely)
    def _upsert_adddetails(self, order, adddetails_data: dict, is_update: bool):
        """Create/Update Pay/Ref/Ewb/Exp and AddlDoc lines."""
        adddetails_data = adddetails_data or {}

        # Copy so we don't mutate incoming request dict
        paydtls_data     = dict(adddetails_data.get('paydtls') or {}) or None
        refdtls_data     = dict(adddetails_data.get('refdtls') or {}) or None
        ewbdtls_data     = dict(adddetails_data.get('ewbdtls') or {}) or None
        expdtls_data     = dict(adddetails_data.get('expdtls') or {}) or None
        addldocdtls_list = list(adddetails_data.get('addldocdtls') or [])

        # ---------- PayDtls ----------
        if paydtls_data:
            paydtls_data.pop('id', None)
            if is_update:
                PayDtls.objects.update_or_create(invoice=order, defaults=paydtls_data)
            else:
                PayDtls.objects.create(invoice=order, **paydtls_data)

        # ---------- RefDtls ----------
        if refdtls_data:
            refdtls_data.pop('id', None)
            if is_update:
                RefDtls.objects.update_or_create(invoice=order, defaults=refdtls_data)
            else:
                RefDtls.objects.create(invoice=order, **refdtls_data)

        # ---------- EwbDtls ----------
        if ewbdtls_data:
            ewbdtls_data.pop('id', None)
            if is_update:
                EwbDtls.objects.update_or_create(invoice=order, defaults=ewbdtls_data)
            else:
                EwbDtls.objects.create(invoice=order, **ewbdtls_data)

        # ---------- ExpDtls ----------
        if expdtls_data:
            expdtls_data.pop('id', None)
            if is_update:
                ExpDtls.objects.update_or_create(invoice=order, defaults=expdtls_data)
            else:
                ExpDtls.objects.create(invoice=order, **expdtls_data)

        # ---------- AddlDocDtls ----------
        if is_update:
            existing_qs = AddlDocDtls.objects.filter(invoice=order)
            existing_map = {d.id: d for d in existing_qs}
            existing_ids = set(existing_map.keys())
            incoming_ids = set()

            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc_id = self._pk_or_none(doc.get('id'))
                clean = {k: v for k, v in doc.items() if k != "id"}

                if doc_id and doc_id in existing_ids:
                    obj = existing_map[doc_id]
                    for k, v in clean.items():
                        setattr(obj, k, v)
                    obj.save()
                    incoming_ids.add(doc_id)
                else:
                    AddlDocDtls.objects.create(invoice=order, **clean)

            to_delete = existing_ids - incoming_ids
            if to_delete:
                AddlDocDtls.objects.filter(id__in=to_delete).delete()
        else:
            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc.pop('id', None)
                AddlDocDtls.objects.create(invoice=order, **doc)

    # -------------------------------------------------------------------------
    # GST/EWAY improvements (safe + after-commit)
    # -------------------------------------------------------------------------

    def _ct_for(self, obj):
        return ContentType.objects.get_for_model(obj, for_concrete_model=False)

    def _parse_mastergst_dt(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        s = str(value).strip()
        for fmt in MASTERGST_DT_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValidationError({"gst": f"Unsupported datetime format from MasterGST: {s}"})

    def _persist_einvoice_details(self, order, ct, data: dict):
        ack_dt = self._parse_mastergst_dt(data.get("AckDt"))
        ewb_dt = self._parse_mastergst_dt(data.get("EwbDt"))
        ewb_valid_till = self._parse_mastergst_dt(data.get("EwbValidTill"))

        irn = data.get("Irn")
        if not irn:
            raise ValidationError({"einvoice": "MasterGST response missing IRN (Irn)."})

        EInvoiceDetails.objects.update_or_create(
            content_type=ct,
            object_id=order.id,
            defaults={
                "irn": irn,
                "ack_no": data.get("AckNo"),
                "ack_date": ack_dt,
                "signed_invoice": data.get("SignedInvoice"),
                "signed_qr_code": data.get("SignedQRCode"),
                "status": data.get("Status", "ACT"),
                "ewb_no": data.get("EwbNo"),
                "ewb_date": ewb_dt,
                "ewb_valid_till": ewb_valid_till,
                "remarks": data.get("Remarks"),
            }
        )

    def _generate_einvoice_if_needed(self, order, mode: str, ct):
        existing = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).only("irn").first()
        if existing and existing.irn:
            return existing.irn

        payload = SalesOrderFullSerializer(order, context={"mode": mode}).data
        gst_response = gstinvoice(order, json.dumps(payload, default=str))

        if not isinstance(gst_response, dict):
            raise ValidationError({"einvoice": "Unexpected response from gstinvoice()."})

        if str(gst_response.get("status_cd")) != "1":
            raise ValidationError({
                "einvoice": gst_response.get("status_desc", "E-Invoice generation failed."),
                "details": gst_response,
            })

        data = gst_response.get("data") or {}
        self._persist_einvoice_details(order, ct, data)
        return data.get("Irn")

    def _generate_eway_from_irn(self, order, ct):
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).first()
        if not (einv and einv.irn):
            raise ValidationError({"eway": "IRN not found for this order. Cannot generate E-Way Bill."})

        ewb = EwbDtls.objects.filter(invoice=order.id).first()
        if not ewb:
            raise ValidationError({"eway": "E-Way Bill details not found for this order."})

        distance = int(getattr(ewb, "Distance", 0) or 0)
        if distance <= 0:
            raise ValidationError({"eway": "Distance must be > 0."})

        payload = {
            "Irn": einv.irn,
            "Distance": distance,
            "TransMode": str(ewb.TransMode),
            "TransId": (ewb.TransId or "").strip(),
            "TransName": (ewb.TransName or "").strip(),
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y") if ewb.TransDocDt else None,
            "TransDocNo": (ewb.TransDocNo or "").strip(),
            "VehNo": (ewb.VehNo or "").strip(),
            "VehType": (ewb.VehType or "").strip(),
        }


        print(payload)

        resp = gst_ewaybill(order, payload)  # pass dict, not string

        if isinstance(resp, dict) and str(resp.get("status_cd")) != "1":
            raise ValidationError({
                "eway": resp.get("status_desc") or "E-Way Bill generation failed.",
                "details": resp
            })

        return resp


    def _post_process_gst(self, order_id: int, mode: str, is_create: bool):
        """
        Runs AFTER DB commit.
        Updates SalesOderHeader.einvoice / eway flags
        based on actual GST outcome.
        """
        order = SalesOderHeader.objects.get(id=order_id)
        ct = self._ct_for(order)

        try:
            if mode == "none":
                return

            # ------------------------
            # E-INVOICE ONLY
            # ------------------------
            if mode == "einvoice":
                self._generate_einvoice_if_needed(order, mode, ct)

                # SUCCESS
                SalesOderHeader.objects.filter(id=order.id).update(
                    einvoice=True,
                    eway=False
                )
                return

            # ------------------------
            # E-WAY ONLY
            # ------------------------
            if mode == "eway":

                print("eway")
                if is_create:
                    return  # payload only on create

                self._generate_eway_from_irn(order, ct)

                SalesOderHeader.objects.filter(id=order.id).update(
                    eway=True
                )
                return

            # ------------------------
            # E-INVOICE + E-WAY
            # ------------------------
            if mode == "both":
                self._generate_einvoice_if_needed(order, mode, ct)
                SalesOderHeader.objects.filter(id=order.id).update(einvoice=True)

                self._generate_eway_from_irn(order, ct)
                SalesOderHeader.objects.filter(id=order.id).update(eway=True)
                return

        except Exception as e:
            logger.exception("GST failed order_id=%s mode=%s", order.id, mode)

            updates = {}
            if mode in ("einvoice", "einvoicepluseway"):
                updates["einvoice"] = False
            if mode in ("eway", "einvoicepluseway"):
                updates["eway"] = False

            if updates:
                SalesOderHeader.objects.filter(id=order.id).update(**updates)

            # IMPORTANT: update-only (no insert)
            EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).update(
                status="ERR",
                remarks=str(e),
            )
            return


    # ===== numbering (improved billno retry) =================================

    def _number_and_create_header(self, validated_data) -> SalesOderHeader:
        validated_data.pop('billno', None)

        settings = (SalesInvoiceSettings.objects
                    .select_for_update()
                    .filter(entity=validated_data['entity'].id,
                            entityfinid=validated_data['entityfinid'].id,
                            doctype__doccode='1001')
                    .first())
        if not settings:
            raise ValidationError({"settings": "SalesInvoiceSettings not configured for this entity/financial year."})

        reset_counter_if_needed(settings)
        number = build_document_number(settings)
        if SalesOderHeader.objects.filter(invoicenumber=number).exists():
            raise ValidationError({"invoicenumber": "Duplicate invoice number generated. Please try again."})

        for _ in range(3):
            max_bill = (SalesOderHeader.objects
                        .filter(entity=validated_data['entity'])
                        .aggregate(m=Max('billno'))['m'] or 0)
            next_bill = max_bill + 1
            try:
                order = SalesOderHeader.objects.create(**validated_data, billno=next_bill, invoicenumber=number)
                settings.current_number += 1
                settings.save()
                return order
            except IntegrityError:
                continue

        raise ValidationError({"billno": "Unable to generate unique billno after retries. Please try again."})

    # ===== CREATE =============================================================

    @transaction.atomic
    def create(self, validated_data):
        details_data    = validated_data.pop('saleInvoiceDetails', [])
        adddetails_data = validated_data.pop('adddetails', {})

        # Decide tax regime
        self._decide_and_enforce_isigst(validated_data, details_data, is_create=True)

        # ✅ decide mode ONCE from request intent (invoiceMode)
        mode = _mode_from_invoice_mode(validated_data)

        # Create order first
        order = self._number_and_create_header(validated_data)

        # ❌ No need to reset einvoice/eway flags if you are not using them anymore
        # If these fields exist and you want them always false as "system truth":
        # SalesOderHeader.objects.filter(id=order.id).update(einvoice=False, eway=False)

        self._upsert_adddetails(order, adddetails_data, is_update=False)
        self._upsert_details(order, details_data, is_update=False)
        self._recalc_totals(order)
        self._post_once_via_shim(order, entrytype='I')

        print(mode)

        # ✅ run GST AFTER commit only if requested
        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(
                    order.id,
                    mode=mode,
                    is_create=True
                )
            )

        return order

    # ===== UPDATE =============================================================

    @transaction.atomic
    def update(self, instance, validated_data):
        details_data    = validated_data.pop('saleInvoiceDetails', [])
        adddetails_data = validated_data.pop('adddetails', {})

        self._decide_and_enforce_isigst((instance, validated_data), details_data, is_create=False)

        touched = []
        for f in self._header_update_fields():
            if f in validated_data:
                setattr(instance, f, validated_data[f])
                touched.append(f)

        instance.save(update_fields=list(set(touched) | {'cgst', 'sgst', 'igst'}))

        # ✅ invoiceMode can come in request OR remain from existing instance
        mode = _mode_from_invoice_mode(validated_data) if "invoiceMode" in validated_data else _mode_from_invoice_mode(instance)

        # ❌ no need to reset einvoice/eway flags if obsolete

        self._upsert_adddetails(instance, adddetails_data, is_update=True)
        self._upsert_details(instance, details_data, is_update=True)
        self._recalc_totals(instance)
        self._post_once_via_shim(instance, entrytype='U')

        print(mode)

        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(
                    instance.id,
                    mode=mode,
                    is_create=False
                )
            )

        return instance







class SalesOrderSerializer(serializers.ModelSerializer):
    salesOrderDetail = saleOrderdetailsSerializer(many=True)

    class Meta:
        model = SalesOder
        fields = ('id', 'sorderdate', 'billno', 'accountid','state','district','city','pincode', 'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype',
                  'billcash', 'supply', 'totalquanity', 'totalpieces', 'advance', 'shippedto', 'remarks', 'transport',
                  'broker', 'taxid', 'tds194q', 'tds194q1', 'tcs206c1ch1', 'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1',
                  'tcs206C2', 'addless', 'duedate', 'subtotal', 'cgst', 'sgst', 'igst', 'cess', 'totalgst',
                  'expenses', 'gtotal', 'entityfinid', 'subentity', 'entity', 'createdby', 'isactive', 'salesOrderDetail',)

    def create(self, validated_data):
        with transaction.atomic():
            salesOrderdetails_data = validated_data.pop('salesOrderDetail')
            validated_data.pop('billno')

            if SalesOder.objects.filter(entity=validated_data['entity'].id).count() == 0:
                billno2 = 1
            else:
                billno2 = (SalesOder.objects.filter(entity=validated_data['entity'].id).last().billno) + 1

            order = SalesOder.objects.create(**validated_data, billno=billno2)

            for PurchaseOrderDetail_data in salesOrderdetails_data:
                detail = salesOrderdetail.objects.create(salesorderheader=order, **PurchaseOrderDetail_data)

            return order

    def update(self, instance, validated_data):
        fields = ['sorderdate', 'billno', 'accountid', 'state','district','city','pincode', 'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype',
                  'billcash', 'supply', 'totalquanity', 'totalpieces', 'advance', 'shippedto', 'remarks', 'transport',
                  'broker', 'taxid', 'tds194q', 'tds194q1', 'tcs206c1ch1', 'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1',
                  'tcs206C2', 'addless', 'duedate', 'subtotal', 'discount', 'cgst', 'sgst', 'igst', 'cess', 'totalgst',
                  'expenses', 'gtotal', 'isactive', 'entityfinid', 'subentity', 'entity', 'createdby', ]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:
                pass
        with transaction.atomic():
            instance.save()
            salesOrderdetail.objects.filter(salesorderheader=instance, entity=instance.entity).delete()

            salesOrderdetails_data = validated_data.get('saleInvoiceDetails')

            for PurchaseOrderDetail_data in salesOrderdetails_data:
                salesorderdetails_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = salesOrderdetail.objects.create(salesorderheader=instance, **PurchaseOrderDetail_data)

            return instance

class SOSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newbillno = serializers.SerializerMethodField()

    def get_newbillno(self, obj):
        if not obj.billno :
            return 1
        else:
            return obj.billno + 1


    class Meta:
        model = SalesOderHeader
        fields =  ['newbillno']

class SOnewSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newbillno = serializers.SerializerMethodField()

    def get_newbillno(self, obj):
        if not obj.billno :
            return 1
        else:
            return obj.billno + 1


    class Meta:
        model = SalesOder
        fields =  ['newbillno']



class SSSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newbillno = serializers.SerializerMethodField()

    def get_newbillno(self, obj):
        if not obj.billno :
            return 1
        else:
            return obj.billno + 1


    class Meta:
        model = gstorderservices
        fields =  ['newbillno']



class PRSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newbillno = serializers.SerializerMethodField()

    def get_newbillno(self, obj):
        if not obj.billno :
            return 1
        else:
            return obj.billno + 1


    class Meta:
        model = PurchaseReturn
        fields =  ['newbillno']



class purchasereturnotherchargesSerializer(serializers.ModelSerializer):
    
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)
    # productname = serializers.SerializerMethodField()
    # hsn = serializers.SerializerMethodField()
    # mrp = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = Purchasereturnothercharges
        fields =  ('account','amount','name',)

    def get_name(self,obj):
        return obj.account.accountname


class purchasereturndetailsSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    otherchargesdetail = purchasereturnotherchargesSerializer(many=True)

    class Meta:
        model = Purchasereturndetails
        fields = (
            'id','product','productname','productdesc','hsn','mrp',
            'orderqty','pieces','rate','amount','othercharges',
            'cgst','sgst','igst','cess','isigst',
            'cgstpercent','sgstpercent','igstpercent','linetotal',
            'entity','otherchargesdetail',
        )

    def get_productname(self, obj):
        return getattr(obj.product, "productname", None)

    def get_hsn(self, obj):
        """
        New structure:
          Product -> gst_rates -> hsn (HsnSac) -> code
        Choose default/most-recent valid rate.
        """
        p = getattr(obj, "product", None)
        if not p:
            return None

        as_of = timezone.now().date()
        qs = p.gst_rates.select_related("hsn").all()

        # validity filters (safe)
        qs = qs.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=as_of)
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=as_of)
        )

        rate = qs.order_by("-isdefault", "-valid_from", "-id").first()
        return rate.hsn.code if rate and rate.hsn else None

    def get_mrp(self, obj):
        """
        New structure:
          Product -> prices (ProductPrice) -> mrp
        Choose default pricelist first, else most recent effective.
        """
        p = getattr(obj, "product", None)
        if not p:
            return None

        as_of = timezone.now().date()
        qs = p.prices.select_related("pricelist").all()

        qs = qs.filter(
            effective_from__lte=as_of
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=as_of)
        )

        price = qs.order_by("-pricelist__isdefault", "-effective_from", "-id").first()
        return getattr(price, "mrp", None) if price else None    


class PurchasereturnSerializer(serializers.ModelSerializer):
    purchasereturndetails = purchasereturndetailsSerializer(many=True)
    adddetails = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = PurchaseReturn
        fields = (
            'id','sorderdate','billno','accountid','state','district','city','pincode',
            'latepaymentalert','grno','terms','vehicle','taxtype','billcash','supply',
            'totalquanity','totalpieces','advance','shippedto','remarks','transport','broker',
            'taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2',
            'addless','duedate','subtotal','invoicetype','reversecharge','roundOff',
            'cgst','sgst','igst','cess','totalgst','expenses','gtotal',
            'entityfinid','subentity','entity','createdby','isactive','isammended','originalinvoice',
            'purchasereturndetails','adddetails','invoiceMode','eway','einvoice','einvoicepluseway',
        )

    # ===== utilities ==========================================================

    @staticmethod
    def _pk_or_none(val):
        try:
            i = int(val)
            return i if i > 0 else None
        except Exception:
            return None

    @classmethod
    def _strip_pk(cls, d: dict):
        if isinstance(d, dict) and 'id' in d and cls._pk_or_none(d.get('id')) is None:
            d.pop('id', None)
        return d

    @staticmethod
    def _header_update_fields():
        return [
            'sorderdate','billno','accountid','state','district','city','pincode','latepaymentalert',
            'grno','terms','vehicle','taxtype','billcash','supply','totalquanity','totalpieces','advance',
            'shippedto','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1',
            'tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','addless','duedate','subtotal',
            'cgst','sgst','igst','cess','totalgst','expenses','gtotal','roundOff',
            'entityfinid','subentity','isammended','originalinvoice','entity','createdby','isactive',
            'invoicetype','reversecharge','invoiceMode','eway','einvoice','einvoicepluseway',
        ]

    def _ct_for(self, obj):
        return ContentType.objects.get_for_model(obj, for_concrete_model=False)

    # ===== adddetails upsert (invoice-style, safe) ===========================

    def _upsert_adddetails(self, order, adddetails_data: dict, is_update: bool):
        adddetails_data = adddetails_data or {}

        paydtls_data     = dict(adddetails_data.get('paydtls') or {}) or None
        refdtls_data     = dict(adddetails_data.get('refdtls') or {}) or None
        ewbdtls_data     = dict(adddetails_data.get('ewbdtls') or {}) or None
        expdtls_data     = dict(adddetails_data.get('expdtls') or {}) or None
        addldocdtls_list = list(adddetails_data.get('addldocdtls') or [])

        # PayDtls
        if paydtls_data:
            paydtls_data.pop('id', None)
            if is_update:
                PayDtls.objects.update_or_create(purchase_return=order, defaults=paydtls_data)
            else:
                PayDtls.objects.create(purchase_return=order, **paydtls_data)

        # RefDtls
        if refdtls_data:
            refdtls_data.pop('id', None)
            if is_update:
                RefDtls.objects.update_or_create(purchase_return=order, defaults=refdtls_data)
            else:
                RefDtls.objects.create(purchase_return=order, **refdtls_data)

        # EwbDtls
        if ewbdtls_data:
            ewbdtls_data.pop('id', None)
            if is_update:
                EwbDtls.objects.update_or_create(purchase_return=order, defaults=ewbdtls_data)
            else:
                EwbDtls.objects.create(purchase_return=order, **ewbdtls_data)

        # ExpDtls
        if expdtls_data:
            expdtls_data.pop('id', None)
            if is_update:
                ExpDtls.objects.update_or_create(purchase_return=order, defaults=expdtls_data)
            else:
                ExpDtls.objects.create(purchase_return=order, **expdtls_data)

        # AddlDocDtls (upsert list)
        if is_update:
            existing_qs  = AddlDocDtls.objects.filter(purchase_return=order)
            existing_map = {d.id: d for d in existing_qs}
            existing_ids = set(existing_map.keys())
            incoming_ids = set()

            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc_id = self._pk_or_none(doc.get("id"))
                clean = {k: v for k, v in doc.items() if k != "id"}

                if doc_id and doc_id in existing_ids:
                    obj = existing_map[doc_id]
                    for k, v in clean.items():
                        setattr(obj, k, v)
                    obj.save()
                    incoming_ids.add(doc_id)
                else:
                    AddlDocDtls.objects.create(purchase_return=order, **clean)

            to_delete = existing_ids - incoming_ids
            if to_delete:
                AddlDocDtls.objects.filter(id__in=to_delete).delete()
        else:
            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc.pop("id", None)
                AddlDocDtls.objects.create(purchase_return=order, **doc)

    # ===== details upsert (NO per-line posting) ===============================

    def _upsert_details(self, order, details_data: list, is_update: bool):
        if not is_update:
            for row in details_data:
                row = dict(row or {})
                self._strip_pk(row)

                othercharges = list(row.pop('otherchargesdetail', []) or [])
                detail = Purchasereturndetails.objects.create(purchasereturn=order, **row)

                for oc in othercharges:
                    oc = dict(oc or {})
                    self._strip_pk(oc)
                    Purchasereturnothercharges.objects.create(purchasereturnorderdetail=detail, **oc)
            return

        existing_map = {d.id: d for d in Purchasereturndetails.objects.filter(purchasereturn=order)}
        existing_ids = set(existing_map.keys())
        seen_ids = set()

        for row in details_data:
            row = dict(row or {})
            detail_id = self._pk_or_none(row.get('id'))
            row.pop('id', None)

            othercharges = list(row.pop('otherchargesdetail', []) or [])

            if detail_id is None:
                d = Purchasereturndetails.objects.create(purchasereturn=order, **row)
            else:
                d = existing_map.get(detail_id)
                if d:
                    seen_ids.add(detail_id)
                    for k, v in row.items():
                        setattr(d, k, v)
                    d.save()
                else:
                    d = Purchasereturndetails.objects.create(purchasereturn=order, **row)

            # refresh othercharges
            Purchasereturnothercharges.objects.filter(purchasereturnorderdetail=d).delete()
            for oc in othercharges:
                oc = dict(oc or {})
                self._strip_pk(oc)
                Purchasereturnothercharges.objects.create(purchasereturnorderdetail=d, **oc)

        to_delete = existing_ids - seen_ids
        if to_delete:
            Purchasereturndetails.objects.filter(id__in=to_delete).delete()

    # ===== posting (single authoritative) ====================================

    def _post_once_via_shim(self, order, entrytype: str):
        """
        IMPORTANT: only call createtransaction() once.
        Your stocktransaction implementation should re-query detail lines + othercharges.
        """
        stk = stocktransaction(order, transactiontype='PR', debit=1, credit=0,
                               description='Purchase Return', entrytype=entrytype)
        stk.createtransaction()

    # ===== GST helpers (after-commit) ========================================

    def _parse_mastergst_dt(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        s = str(value).strip()
        for fmt in MASTERGST_DT_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValidationError({"gst": f"Unsupported datetime format from MasterGST: {s}"})

    def _persist_einvoice_details(self, order, ct, data: dict):
        ack_dt = self._parse_mastergst_dt(data.get("AckDt"))
        ewb_dt = self._parse_mastergst_dt(data.get("EwbDt"))
        ewb_valid_till = self._parse_mastergst_dt(data.get("EwbValidTill"))

        irn = data.get("Irn")
        if not irn:
            raise ValidationError({"einvoice": "MasterGST response missing IRN (Irn)."})

        EInvoiceDetails.objects.update_or_create(
            content_type=ct,
            object_id=order.id,
            defaults={
                "irn": irn,
                "ack_no": data.get("AckNo"),
                "ack_date": ack_dt,
                "signed_invoice": data.get("SignedInvoice"),
                "signed_qr_code": data.get("SignedQRCode"),
                "status": data.get("Status", "ACT"),
                "ewb_no": data.get("EwbNo"),
                "ewb_date": ewb_dt,
                "ewb_valid_till": ewb_valid_till,
                "remarks": data.get("Remarks"),
            }
        )

    def _generate_einvoice_if_needed(self, order, mode: str, ct):
        existing = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).only("irn").first()
        if existing and existing.irn:
            return existing.irn

        payload = PurchasereturnFullSerializer(order, context={"mode": mode}).data
        resp = gstinvoice(order, json.dumps(payload, default=str))

        if not isinstance(resp, dict):
            raise ValidationError({"einvoice": "Unexpected response from gstinvoice()."})

        if str(resp.get("status_cd")) != "1":
            raise ValidationError({
                "einvoice": resp.get("status_desc", "E-Invoice generation failed."),
                "details": resp,
            })

        data = resp.get("data") or {}
        self._persist_einvoice_details(order, ct, data)
        return data.get("Irn")

    def _generate_eway_from_irn(self, order, ct):
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).first()
        if not (einv and einv.irn):
            raise ValidationError({"eway": "IRN not found for this purchase return. Cannot generate E-Way Bill."})

        ewb = EwbDtls.objects.filter(purchase_return=order).first()
        if not ewb:
            raise ValidationError({"eway": "E-Way Bill details not found for this purchase return."})

        distance = int(getattr(ewb, "Distance", 0) or 0)
        if distance <= 0:
            raise ValidationError({"eway": "Distance must be > 0."})

        payload = {
            "Irn": einv.irn,
            "Distance": distance,
            "TransMode": str(getattr(ewb, "TransMode", "") or ""),
            "TransId": (getattr(ewb, "TransId", "") or "").strip(),
            "TransName": (getattr(ewb, "TransName", "") or "").strip(),
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y") if getattr(ewb, "TransDocDt", None) else None,
            "TransDocNo": (getattr(ewb, "TransDocNo", "") or "").strip(),
            "VehNo": (getattr(ewb, "VehNo", "") or "").strip(),
            "VehType": (getattr(ewb, "VehType", "") or "").strip(),
        }

        resp = gst_ewaybill(order, payload)
        if isinstance(resp, dict) and str(resp.get("status_cd")) != "1":
            raise ValidationError({
                "eway": resp.get("status_desc") or "E-Way Bill generation failed.",
                "details": resp
            })
        return resp

    def _post_process_gst(self, order_id: int, mode: str, is_create: bool):
        """
        AFTER COMMIT.
        Updates PurchaseReturn.einvoice / eway flags based on GST outcome.
        """
        order = PurchaseReturn.objects.get(id=order_id)
        ct = self._ct_for(order)

        try:
            if mode == "none":
                return

            if mode == "einvoice":
                self._generate_einvoice_if_needed(order, mode, ct)
                PurchaseReturn.objects.filter(id=order.id).update(einvoice=True, eway=False)
                return

            if mode == "eway":
                if is_create:
                    return  # same behavior as your invoice serializer (eway on update only)
                self._generate_eway_from_irn(order, ct)
                PurchaseReturn.objects.filter(id=order.id).update(eway=True)
                return

            if mode == "both":
                self._generate_einvoice_if_needed(order, mode, ct)
                PurchaseReturn.objects.filter(id=order.id).update(einvoice=True)
                self._generate_eway_from_irn(order, ct)
                PurchaseReturn.objects.filter(id=order.id).update(eway=True)
                return

        except Exception as e:
            logger.exception("GST failed purchase_return_id=%s mode=%s", order.id, mode)

            updates = {}
            if mode in ("einvoice", "both"):
                updates["einvoice"] = False
            if mode in ("eway", "both"):
                updates["eway"] = False
            if updates:
                PurchaseReturn.objects.filter(id=order.id).update(**updates)

            EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).update(
                status="ERR",
                remarks=str(e),
            )
            return

    # ===== numbering (billno retry) ==========================================

    def _number_and_create_header(self, validated_data) -> PurchaseReturn:
        validated_data.pop('billno', None)
        validated_data.pop('invoicenumber', None)

        settings = (SalesInvoiceSettings.objects
                    .select_for_update()
                    .filter(entity=validated_data['entity'].id,
                            entityfinid=validated_data['entityfinid'].id,
                            doctype__doccode='1004')  # Purchase Return doccode
                    .first())
        if not settings:
            raise ValidationError({"settings": "SalesInvoiceSettings not configured for this entity/financial year."})

        reset_counter_if_needed(settings)
        number = build_document_number(settings)

        if PurchaseReturn.objects.filter(invoicenumber=number).exists():
            raise ValidationError({"invoicenumber": "Duplicate invoice number generated. Please try again."})

        for _ in range(3):
            max_bill = (PurchaseReturn.objects
                        .filter(entity=validated_data['entity'])
                        .aggregate(m=Max('billno'))['m'] or 0)
            next_bill = max_bill + 1
            try:
                order = PurchaseReturn.objects.create(**validated_data, billno=next_bill, invoicenumber=number)
                settings.current_number += 1
                settings.save()
                return order
            except IntegrityError:
                continue

        raise ValidationError({"billno": "Unable to generate unique billno after retries. Please try again."})

    # ===== CREATE / UPDATE ====================================================

    @transaction.atomic
    def create(self, validated_data):
        details_data    = validated_data.pop('purchasereturndetails', [])
        adddetails_data = validated_data.pop('adddetails', {}) or {}

        mode = _mode_from_invoice_mode(validated_data)

        order = self._number_and_create_header(validated_data)

        self._upsert_adddetails(order, adddetails_data, is_update=False)
        self._upsert_details(order, details_data, is_update=False)

        # ✅ post once
        self._post_once_via_shim(order, entrytype='I')

        # ✅ GST after commit (only if requested)
        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(order.id, mode=mode, is_create=True)
            )

        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        details_data    = validated_data.pop('purchasereturndetails', [])
        adddetails_data = validated_data.pop('adddetails', {}) or {}

        touched = []
        for f in self._header_update_fields():
            if f in validated_data:
                setattr(instance, f, validated_data[f])
                touched.append(f)

        if touched:
            instance.save(update_fields=list(set(touched)))

        mode = _mode_from_invoice_mode(validated_data) if "invoiceMode" in validated_data else _mode_from_invoice_mode(instance)

        self._upsert_adddetails(instance, adddetails_data, is_update=True)
        self._upsert_details(instance, details_data, is_update=True)

        # ✅ post once
        self._post_once_via_shim(instance, entrytype='U')

        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(instance.id, mode=mode, is_create=False)
            )

        return instance



class PRSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newbillno = serializers.SerializerMethodField()

    def get_newbillno(self, obj):
        if not obj.billno :
            return 1
        else:
            return obj.billno + 1


    class Meta:
        model = PurchaseReturn
        fields =  ['newbillno']




class POSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = purchaseorder
        fields =  ['newvoucher']


class newPOSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = newpurchaseorder
        fields =  ['newvoucher']


class newPOSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = newpurchaseorder
        fields =  ['newvoucher']


class JwvoucherSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = jobworkchalan
        fields =  ['newvoucher']



class SRSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = salereturn
        fields =  ['newvoucher']


class jobworkchallanDetailsSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
   # productdesc1 = serializers.SerializerMethodField()
    #entityUser = entityUserSerializer(many=True)

    class Meta:
        model = jobworkchalanDetails
        fields = ('id','product','productname','productdesc','hsn','mrp','orderqty','pieces','rate','amount','cgst','sgst','igst','cess','linetotal','entity',)
    
    def get_productname(self,obj):
        return obj.product.productname
    
    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode

    def get_mrp(self,obj):
        return obj.product.mrp


class jobworkchallanSerializer(serializers.ModelSerializer):
    jobworkchalanDetails = jobworkchallanDetailsSerializer(many=True)
   # productname = serializers.SerializerMethodField()

    class Meta:
        model = jobworkchalan
        fields = ('id','voucherdate','voucherno','account','state','district','city','pincode', 'billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','ordertype','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','entity','isactive','jobworkchalanDetails',)


    
    


    def create(self, validated_data):
       # print(validated_data)
        jobworkchalanDetails_data = validated_data.pop('jobworkchalanDetails')
        validated_data.pop('voucherno')
        if jobworkchalan.objects.filter(entity= validated_data['entity'].id,ordertype = validated_data['ordertype']).count() == 0:
                billno2 = 1
        else:
                billno2 = (jobworkchalan.objects.filter(entity= validated_data['entity'].id).last().voucherno) + 1
        with transaction.atomic():
            order = jobworkchalan.objects.create(**validated_data,voucherno = billno2)
           
            for PurchaseOrderDetail_data in jobworkchalanDetails_data:
                detail = jobworkchalanDetails.objects.create(jobworkchalan = order, **PurchaseOrderDetail_data)
            
                #stk.createtransactiondetails(detail=detail,stocktype='P')
                
            
            #stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','account', 'state','district','city','pincode','billno','billdate','showledgeraccount','terms','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','ordertype', 'grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','entity','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        

        # print(instance.id)
        #stk = stocktransaction(instance, transactiontype= 'P',debit=1,credit=0,description= 'To Purchase V.No: ')
        with transaction.atomic():
            #stk.updateransaction()
            
            i = instance.save()

            jobworkchalanDetails.objects.filter(jobworkchalan=instance,entity = instance.entity).delete()
        
            jobworkchalanDetails_data = validated_data.get('jobworkchalanDetails')

            for PurchaseOrderDetail_data in jobworkchalanDetails_data:
                detail = jobworkchalanDetails.objects.create(jobworkchalan = instance, **PurchaseOrderDetail_data)
                #stk.createtransactiondetails(detail=detail,stocktype='P')

        return instance


def _norm_dec(x):
    # tolerant Decimal coercion; keeps None → 0
    try:
        return q2(Decimal(x))
    except Exception:
        return q2(Decimal(str(x or "0")))

def _normalize_purchase_detail_taxes(d: dict, is_inter: bool) -> None:
    """
    Normalize one purchase detail dict:
      - Respect posted amounts if present (igst/cgst/sgst/cess).
      - Otherwise derive from *_percent and base 'amount'.
      - Enforce scheme:
          inter   => keep IGST, zero CGST/SGST
          intra   => keep CGST/SGST, zero IGST
    """
    from decimal import Decimal
    amt   = q2(d.get("amount") or ZERO2)

    # posted amounts (if any)
    igst  = q2(d.get("igst") or ZERO2)
    cgst  = q2(d.get("cgst") or ZERO2)
    sgst  = q2(d.get("sgst") or ZERO2)
    cess  = q2(d.get("cess") or ZERO2)

    # percents (used only if not posted)
    igstp = q2(d.get("igstpercent") or ZERO2)
    cgstp = q2(d.get("cgstpercent") or ZERO2)
    sgstp = q2(d.get("sgstpercent") or ZERO2)

    posted_any = (igst > ZERO2) or (cgst > ZERO2) or (sgst > ZERO2) or (cess > ZERO2)

    if is_inter:
        if not posted_any and igstp > ZERO2 and amt > ZERO2:
            igst = q2(amt * igstp / Decimal("100"))
        d["isigst"] = True
        d["igst"]   = igst
        d["cgst"]   = ZERO2
        d["sgst"]   = ZERO2
        d["cess"]   = cess
    else:
        if not posted_any:
            if cgstp > ZERO2 and amt > ZERO2:
                cgst = q2(amt * cgstp / Decimal("100"))
            if sgstp > ZERO2 and amt > ZERO2:
                sgst = q2(amt * sgstp / Decimal("100"))
        d["isigst"] = False
        d["igst"]   = ZERO2
        d["cgst"]   = cgst
        d["sgst"]   = sgst
        d["cess"]   = cess



def _purchase_is_inter(header_like, details_list) -> bool:
    """
    Decide inter vs intra for PURCHASE, prioritizing explicit IGST signals:
      1) If header igst > 0 → inter
      2) Else if any line has isigst=True or igstpercent>0 or igst>0 → inter
      3) Else fall back to sales-style heuristic _apply_tax_scheme_to_header_data
    """
    try:
        igst_hdr = q2((header_like.get("igst") if isinstance(header_like, dict)
                       else getattr(header_like, "igst", ZERO2)) or ZERO2)
    except Exception:
        igst_hdr = ZERO2
    if igst_hdr > ZERO2:
        return True

    for d in (details_list or []):
        if bool(d.get("isigst")):
            return True
        if q2(d.get("igst") or ZERO2) > ZERO2:
            return True
        if q2(d.get("igstpercent") or ZERO2) > ZERO2:
            return True

    # fallback to your existing (sales-style) heuristic
    hdr_copy = dict(header_like) if isinstance(header_like, dict) else {
        "entity": getattr(header_like, "entity", None),
        "shippedto": getattr(header_like, "shippedto", None),
        "state": getattr(header_like, "state", None),
        "cgst": getattr(header_like, "cgst", ZERO2),
        "sgst": getattr(header_like, "sgst", ZERO2),
        "igst": getattr(header_like, "igst", ZERO2),
        "isigst": getattr(header_like, "isigst", None),
    }
    return bool(_apply_tax_scheme_to_header_data(hdr_copy))


class PurchaseOrderDetailsSerializer(serializers.ModelSerializer):
    otherchargesdetail = purchaseotherdetailsSerializer(many=True, required=False)
    id = serializers.IntegerField(required=False)

    productname = serializers.CharField(source="product.productname", read_only=True)
    hsn = serializers.CharField(source="product.hsn.hsnCode", read_only=True)

    # ✅ NEW: derived from ProductPrice model
    mrp = serializers.SerializerMethodField()
    purchase_rate = serializers.SerializerMethodField()
    selling_price = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderDetails
        fields = (
            "id", "product", "productname", "productdesc",
            "hsn", "mrp", "purchase_rate", "selling_price",
            "orderqty", "pieces", "rate", "amount", "othercharges",
            "cgst", "sgst", "igst", "cess",
            "cgstpercent", "sgstpercent", "igstpercent", "isigst",
            "linetotal", "subentity", "entity", "otherchargesdetail",
        )

    # -----------------------------
    # Price picker helpers
    # -----------------------------
    def _pick_price_row(self, product):
        """
        Pick the most relevant ProductPrice row.
        Priority:
          1) effective_from <= today and (effective_to is null or >= today)
          2) latest effective_from
        Optionally filter by pricelist/uom if passed via context.
        """
        today = timezone.localdate()

        prices = getattr(product, "prices", None)
        if prices is None:
            return None

        # If prefetched, `prices.all()` won't hit DB
        qs = prices.all()

        # Optional: filter by pricelist/uom coming from request/context
        pricelist_id = self.context.get("pricelist_id")
        uom_id = self.context.get("uom_id")
        if pricelist_id:
            qs = qs.filter(pricelist_id=pricelist_id)
        if uom_id:
            qs = qs.filter(uom_id=uom_id)

        # active window first
        active = qs.filter(
            effective_from__lte=today
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).order_by("-effective_from")

        row = active.first()
        if row:
            return row

        # fallback: most recent effective_from
        return qs.order_by("-effective_from").first()

    def get_mrp(self, obj):
        row = self._pick_price_row(obj.product)
        return row.mrp if row else None

    def get_purchase_rate(self, obj):
        row = self._pick_price_row(obj.product)
        return row.purchase_rate if row else None

    def get_selling_price(self, obj):
        row = self._pick_price_row(obj.product)
        return row.selling_price if row else None

    @staticmethod
    def setup_eager_loading(queryset):
        """
        ✅ Optimize:
        - product + hsn in select_related
        - prefetch product.prices (ProductPrice rows)
        - prefetch other charges
        """
        return (
            queryset
            .select_related("product", "product__hsn")
            .prefetch_related(
                Prefetch(
                    "product__prices",
                    queryset=ProductPrice.objects.only(
                        "id", "product_id", "pricelist_id", "uom_id",
                        "purchase_rate", "mrp", "selling_price",
                        "effective_from", "effective_to"
                    ).order_by("-effective_from")
                ),
                "otherchargesdetail",  # change if your related_name differs
            )
        )

    






    




class PurchaseOrderAttachmentSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderAttachment
        fields = ['id', 'purchase_order', 'file', 'file_name', 'uploaded_at']

    def get_file_name(self, obj):
        return obj.file.name.split('/')[-1]  # Extract only the file name

    def create(self, validated_data):
        """Handles single file creation"""
        return PurchaseOrderAttachment.objects.create(**validated_data)

TWOPL = Decimal("0.01")
ZERO2 = Decimal("0.00")

def q2(x):
    if isinstance(x, Decimal):
        return x.quantize(TWOPL, rounding=ROUND_HALF_UP)
    return Decimal(str(x or "0")).quantize(TWOPL, rounding=ROUND_HALF_UP)

def _recompute_purchase_totals(po: purchaseorder) -> None:
    """
    Recompute monetary totals for a purchaseorder from saved lines.
    - subtotal  = sum(line.amount)
    - totalgst  = sum(line.cgst + line.sgst + line.igst + line.cess)
    - gtotal    = subtotal - discount + addless + totalgst + expenses
    Round-off is left as-is (policy-specific).
    """
    qs = (PurchaseOrderDetails.objects
          .filter(purchaseorder=po)
          .annotate(
              _amount=Coalesce(F("amount"), V(ZERO2)),
              _cgst=Coalesce(F("cgst"), V(ZERO2)),
              _sgst=Coalesce(F("sgst"), V(ZERO2)),
              _igst=Coalesce(F("igst"), V(ZERO2)),
              _cess=Coalesce(F("cess"), V(ZERO2)),
          ))

    agg = qs.aggregate(
        total_amount=Coalesce(Sum("_amount"), V(ZERO2)),
        sum_cgst=Coalesce(Sum("_cgst"), V(ZERO2)),
        sum_sgst=Coalesce(Sum("_sgst"), V(ZERO2)),
        sum_igst=Coalesce(Sum("_igst"), V(ZERO2)),
        sum_cess=Coalesce(Sum("_cess"), V(ZERO2)),
    )

    subtotal  = q2(agg["total_amount"])
    totalgst  = q2(agg["sum_cgst"] + agg["sum_sgst"] + agg["sum_igst"] + agg["sum_cess"])
    discount  = q2(po.discount or ZERO2)
    addless   = q2(po.addless  or ZERO2)
    expenses  = q2(po.expenses or ZERO2)
    # roundoff = q2(po.roundOff or ZERO2)  # if you want to apply it inside gtotal

    gtotal = q2(subtotal - discount + addless + totalgst + expenses)

    # write back
    po.stbefdiscount = subtotal           # simple parity with sales; adjust if you track befor-discount values
    po.subtotal      = subtotal
    po.totalgst      = totalgst
    po.gtotal        = gtotal
    # po.roundOff    = roundoff           # leave untouched unless you enforce a rounding policy
    # (Optionally mirror totalgst into component buckets; disabled to preserve posted header values)
    # if getattr(po, "isigst", False):
    #     po.igst = totalgst; po.cgst = ZERO2; po.sgst = ZERO2
    # else:
    #     half = q2(totalgst / Decimal("2")); po.cgst = half; po.sgst = totalgst - half; po.igst = ZERO2


class PurchaseSupplierEInvoiceCaptureSerializer(serializers.Serializer):
    irn = serializers.CharField(required=True, max_length=128)
    ack_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=64)
    ack_date = serializers.DateTimeField(required=False, allow_null=True)
    signed_qr_code = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate_irn(self, v):
        v = (v or "").strip()
        if len(v) < 16:
            raise serializers.ValidationError("Invalid IRN.")
        return v


class PurchaseInvoiceEWayCaptureSerializer(serializers.Serializer):
    # Capturing only: EWB number and dates (from supplier/transport docs)
    EwbNo = serializers.CharField(max_length=20, required=True)
    EwbDt = serializers.DateTimeField(required=False, allow_null=True)
    EwbValidTill = serializers.DateTimeField(required=False, allow_null=True)

    # Optional transport fields you may want to store (not mandatory)
    TransId = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    TransName = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    Distance = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    TransDocNo = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    TransMode = serializers.CharField(max_length=1, required=False, allow_null=True, allow_blank=True)
    TransDocDt = serializers.DateTimeField(required=False, allow_null=True)
    VehNo = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    VehType = serializers.CharField(max_length=1, required=False, allow_null=True, allow_blank=True)

    def validate_EwbNo(self, v):
        v = (v or "").strip()
        if len(v) < 8:
            raise serializers.ValidationError("Invalid E-Way Bill number.")
        return v

class purchaseorderSerializer(serializers.ModelSerializer):
    # ---------- nested ----------
    purchaseInvoiceDetails = PurchaseOrderDetailsSerializer(many=True)
    supplier_einvoice_details = serializers.SerializerMethodField(read_only=True)
    eway_details = serializers.SerializerMethodField(read_only=True)
    attachments = PurchaseOrderAttachmentSerializer(many=True, required=False, allow_null=True, default=list)

    # ---------- optional numeric fields ----------
    stbefdiscount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    discount      = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    subtotal      = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    totalgst      = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    expenses      = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    addless       = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    advance       = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    gtotal        = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO2, required=False)
    roundOff      = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

    class Meta:
        model = purchaseorder
        fields = (
            'id','voucherdate','voucherno','account','state','district','city','pincode',
            'billno','billdate','terms','showledgeraccount','taxtype','billcash',
            'totalpieces','totalquanity','advance','remarks','transport','broker','taxid',
            'tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2',
            'duedate','inputdate','vehicle','grno','gstr2astatus',
            'stbefdiscount','discount','subtotal','addless','cgst','sgst','igst','totalgst',
            'reversecharge','invoicetype','cess','expenses','gtotal','roundOff','finalAmount',
            'entityfinid','subentity','entity','isactive',
            'purchaseInvoiceDetails','attachments','supplier_einvoice_details','eway_details',
        )

    def get_supplier_einvoice_details(self, obj):
        ct = ContentType.objects.get_for_model(obj, for_concrete_model=False)
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=obj.id).first()
        if not einv:
            return None
        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "status": einv.status,
            "remarks": einv.remarks,
        }

    def get_eway_details(self, obj):
        ewb = getattr(obj, "ewbdtls3", None)  # related_name we set
        if not ewb:
            return None
        return {
            "EwbNo": getattr(ewb, "EwbNo", None),
            "EwbDt": ewb.EwbDt.strftime("%d/%m/%Y %H:%M:%S") if getattr(ewb, "EwbDt", None) else None,
            "EwbValidTill": ewb.EwbValidTill.strftime("%d/%m/%Y %H:%M:%S") if getattr(ewb, "EwbValidTill", None) else None,
            "TransId": getattr(ewb, "TransId", None),
            "TransName": getattr(ewb, "TransName", None),
            "Distance": str(getattr(ewb, "Distance", "") or "") or None,
            "VehNo": getattr(ewb, "VehNo", None),
            "TransDocNo": getattr(ewb, "TransDocNo", None),
        }

    # ===== utilities ==========================================================

    @staticmethod
    def _pk_or_none(val):
        try:
            i = int(val)
            return i if i > 0 else None
        except Exception:
            return None

    @classmethod
    def _strip_pk(cls, d: dict):
        if isinstance(d, dict) and 'id' in d and cls._pk_or_none(d.get('id')) is None:
            d.pop('id', None)
        return d

    @staticmethod
    def _header_update_fields():
        return [
            'voucherdate','voucherno','account','state','district','city','pincode',
            'billno','billdate','showledgeraccount','terms','taxtype','reversecharge',
            'invoicetype','billcash','totalpieces','totalquanity','advance','remarks',
            'transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2',
            'tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno',
            'gstr2astatus','stbefdiscount','discount','subtotal','addless',
            'cgst','sgst','igst','totalgst','cess','expenses','gtotal','roundOff',
            'finalAmount','entityfinid','subentity','entity','isactive'
        ]

    # ===== tax enforcement (single source of truth) ==========================

    def _decide_and_enforce_is_inter(self, header_like: dict, details_data: list):
        """
        Decide inter/intra and enforce header + detail tax combo to satisfy DB constraints:
        - If inter => IGST kept, CGST/SGST forced 0, details isigst=True, cgst/sgst=0
        - Else     => CGST/SGST kept, IGST forced 0, details isigst=False, igst=0
        """
        is_inter = _purchase_is_inter(header_like, details_data)

        igst_in = q2(header_like.get("igst", ZERO2) or ZERO2)
        cgst_in = q2(header_like.get("cgst", ZERO2) or ZERO2)
        sgst_in = q2(header_like.get("sgst", ZERO2) or ZERO2)

        if is_inter:
            header_like["igst"] = igst_in
            header_like["cgst"] = ZERO2
            header_like["sgst"] = ZERO2
        else:
            header_like["igst"] = ZERO2
            header_like["cgst"] = cgst_in
            header_like["sgst"] = sgst_in

        for d in details_data or []:
            _normalize_purchase_detail_taxes(d, is_inter)

        return is_inter

    def validate(self, attrs):
        # details key present during serializer validation
        details = attrs.get("purchaseInvoiceDetails") or []
        attrs.pop("isigst", None)  # model does not need it

        # enforce taxes based on business rule
        self._decide_and_enforce_is_inter(attrs, details)

        # remove non-model keys in nested dicts if present
        for d in details:
            if isinstance(d, dict):
                d.pop("productname", None)

        return attrs

    # ===== upsert helpers =====================================================

    def _upsert_details(self, order, details_data: list, is_update: bool):
        """
        Create/Update PurchaseOrderDetails and purchaseothercharges.
        No posting here.
        """
        if not is_update:
            for row in details_data:
                row = dict(row or {})
                self._strip_pk(row)
                row.pop("productname", None)

                other_charges = list(row.pop("otherchargesdetail", []) or [])
                d = PurchaseOrderDetails.objects.create(purchaseorder=order, **row)

                for oc in other_charges:
                    oc = dict(oc or {})
                    self._strip_pk(oc)
                    purchaseothercharges.objects.create(purchaseorderdetail=d, **oc)
            return

        existing_map = {d.id: d for d in PurchaseOrderDetails.objects.filter(purchaseorder=order)}
        existing_ids = set(existing_map.keys())
        seen_ids = set()

        for row in details_data:
            row = dict(row or {})
            row.pop("productname", None)

            detail_id = self._pk_or_none(row.get("id"))
            row.pop("id", None)

            other_charges = list(row.pop("otherchargesdetail", []) or [])

            if detail_id is None:
                d = PurchaseOrderDetails.objects.create(purchaseorder=order, **row)
            else:
                d = existing_map.get(detail_id)
                if d:
                    seen_ids.add(detail_id)
                    for k, v in row.items():
                        setattr(d, k, v)
                    d.save()
                else:
                    d = PurchaseOrderDetails.objects.create(purchaseorder=order, **row)

            # refresh othercharges
            purchaseothercharges.objects.filter(purchaseorderdetail=d).delete()
            for oc in other_charges:
                oc = dict(oc or {})
                self._strip_pk(oc)
                purchaseothercharges.objects.create(purchaseorderdetail=d, **oc)

        # delete removed lines
        to_delete = existing_ids - seen_ids
        if to_delete:
            PurchaseOrderDetails.objects.filter(id__in=to_delete).delete()

    def _sync_attachments(self, order, attachments_data: list, is_update: bool):
        """
        Create or diff attachments.
        """
        attachments_data = list(attachments_data or [])

        if not is_update:
            for att in attachments_data:
                att = dict(att or {})
                self._strip_pk(att)
                PurchaseOrderAttachment.objects.create(purchase_order=order, **att)
            return

        existing = list(PurchaseOrderAttachment.objects.filter(purchase_order=order))
        by_id = {a.id: a for a in existing}
        incoming_ids = set()

        for att in attachments_data:
            att = dict(att or {})
            att_id = self._pk_or_none(att.get("id"))
            clean = {k: v for k, v in att.items() if k != "id"}

            if att_id and att_id in by_id:
                a = by_id[att_id]
                for k, v in clean.items():
                    setattr(a, k, v)
                a.save()
                incoming_ids.add(att_id)
            else:
                PurchaseOrderAttachment.objects.create(purchase_order=order, **clean)

        to_delete = set(by_id.keys()) - incoming_ids
        if to_delete:
            PurchaseOrderAttachment.objects.filter(id__in=to_delete).delete()

    # ===== posting (single authoritative) ====================================

    def _post_once(self, order, entrytype: str):
        """
        IMPORTANT: Keep posting INSIDE same atomic for PO (as you requested).
        Post ONCE, let stocktransaction re-query DB rows.
        """
        stk = stocktransaction(
            order, transactiontype='P', debit=1, credit=0,
            description='To Purchase V.No: ', entrytype=entrytype
        )
        stk.createtransaction()

    # ===== CREATE =============================================================

    @transaction.atomic
    def create(self, validated_data):
        details_data = validated_data.pop("purchaseInvoiceDetails", [])
        attachments_data = validated_data.pop("attachments", []) or []

        # enforce taxes again here (safety, DB constraints)
        validated_data.pop("isigst", None)
        self._decide_and_enforce_is_inter(validated_data, details_data)

        # cleanup incoming rows
        for d in details_data:
            if isinstance(d, dict):
                d.pop("id", None)
                d.pop("productname", None)

        order = purchaseorder.objects.create(**validated_data)

        self._upsert_details(order, details_data, is_update=False)
        self._sync_attachments(order, attachments_data, is_update=False)

        if AUTO_RECALC_TOTALS:
            _recompute_purchase_totals(order)
            order.save(update_fields=["stbefdiscount","discount","subtotal","totalgst","roundOff","gtotal"])

        # posting must be in same atomic
        try:
            self._post_once(order, entrytype="I")
        except Exception as e:
            raise ValidationError({"posting": str(e)})

        return order

    # ===== UPDATE =============================================================

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = purchaseorder.objects.select_for_update().get(pk=instance.pk)

        details_data = validated_data.pop("purchaseInvoiceDetails", [])
        attachments_data = validated_data.pop("attachments", []) or []
        validated_data.pop("isigst", None)

        touched = []
        for f in self._header_update_fields():
            if f in validated_data:
                setattr(instance, f, validated_data[f])
                touched.append(f)

        # Decide inter/intra using "current header view" + incoming details
        header_view = {
            "entity": instance.entity,
            "state": instance.state,
            "cgst": q2(getattr(instance, "cgst", ZERO2) or ZERO2),
            "sgst": q2(getattr(instance, "sgst", ZERO2) or ZERO2),
            "igst": q2(getattr(instance, "igst", ZERO2) or ZERO2),
        }
        # overlay incoming header values if provided
        for k in ("state","cgst","sgst","igst","entity"):
            if k in validated_data:
                header_view[k] = validated_data[k]

        self._decide_and_enforce_is_inter(header_view, details_data)

        # apply enforced header tax results onto instance
        instance.igst = header_view["igst"]
        instance.cgst = header_view["cgst"]
        instance.sgst = header_view["sgst"]
        if "igst" not in touched: touched.append("igst")
        if "cgst" not in touched: touched.append("cgst")
        if "sgst" not in touched: touched.append("sgst")

        if touched:
            instance.save(update_fields=list(set(touched)))

        # upsert children
        for d in details_data:
            if isinstance(d, dict):
                d.pop("productname", None)

        self._upsert_details(instance, details_data, is_update=True)
        self._sync_attachments(instance, attachments_data, is_update=True)

        if AUTO_RECALC_TOTALS:
            _recompute_purchase_totals(instance)
            instance.save(update_fields=["stbefdiscount","discount","subtotal","totalgst","roundOff","gtotal"])

        # posting at end (still inside atomic)
        try:
            self._post_once(instance, entrytype="U")
        except Exception as e:
            raise ValidationError({"posting": str(e)})

        return instance







class newPurchaseOrderDetailsSerializer(serializers.ModelSerializer):
   # otherchargesdetail = purchaseotherdetailsSerializer(many=True,required=False)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
   # productdesc1 = serializers.SerializerMethodField()
    #entityUser = entityUserSerializer(many=True)

    class Meta:
        model = newPurchaseOrderDetails
        fields = ('id','product','productname','productdesc','hsn','mrp','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','cess','linetotal','subentity','entity',)
    
    def get_productname(self,obj):
        return obj.product.productname
    
    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode

    def get_mrp(self,obj):
        return obj.product.mrp

class newpurchaseorderSerializer(serializers.ModelSerializer):
    purchaseorderdetails = newPurchaseOrderDetailsSerializer(many=True)
   # productname = serializers.SerializerMethodField()

    class Meta:
        model = newpurchaseorder
        fields = ('id','voucherdate','voucherno','account','state','district','city','pincode', 'billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity','entity','isactive','purchaseorderdetails',)


    
    


    def create(self, validated_data):
       # print(validated_data)
        PurchaseOrderDetails_data = validated_data.pop('purchaseorderdetails')
        with transaction.atomic():
            order = newpurchaseorder.objects.create(**validated_data)
            #stk = stocktransaction(order, transactiontype= 'P',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype= 'I')
            #print(order.objects.get("id"))
            #print(tracks_data)
            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
              #  purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = newPurchaseOrderDetails.objects.create(purchaseorder = order, **PurchaseOrderDetail_data)
                # for purchaseothercharge_data in purchaseothercharges_data:
                #     detail1 = purchaseothercharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                #     stk.createothertransactiondetails(detail=detail1,stocktype='P')

            
              #  stk.createtransactiondetails(detail=detail,stocktype='P')
                
            
           # stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','account','billno','state','district','city','pincode', 'billdate','showledgeraccount','terms','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity', 'entity','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        

        # print(instance.id)
     #   stk = stocktransaction(instance, transactiontype= 'P',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype='U')
        with transaction.atomic():
          #  stk.createtransaction()
            
            i = instance.save()

            newPurchaseOrderDetails.objects.filter(purchaseorder=instance,entity = instance.entity).delete()
        
            PurchaseOrderDetails_data = validated_data.get('purchaseorderdetails')

            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
               # purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = newPurchaseOrderDetails.objects.create(purchaseorder = instance, **PurchaseOrderDetail_data)
              #  stk.createtransactiondetails(detail=detail,stocktype='P')
                # for purchaseothercharge_data in purchaseothercharges_data:
                  
                #     detail1 = purchaseothercharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                #     stk.createothertransactiondetails(detail=detail1,stocktype='P')

        return instance
    




class journalSerializer(serializers.ModelSerializer):
 
    class Meta:
        model = journal
        fields = '__all__'

    def create(self, validated_data):
        order = journal.objects.create(**validated_data)
        if order.drcr == 0:
            creditamount = order.amount
            debitamount = 0
        else:
            debitamount = order.amount
            creditamount = 0
            

    

        print(order.account.accounthead.code)

        if order.account.accounthead.code == 2000:
            accounttype = 'BIH'
        elif order.account.accounthead.code == 4000:
            accounttype = 'CIH'
        else:
            accounttype = 'M'

        StockTransactions.objects.create(accounthead= order.account.accounthead,account= order.account,transactiontype = order.vouchertype,transactionid = order.id,desc = 'Journal V.No' + str(order.voucherno),drcr=order.drcr,creditamount=creditamount,debitamount=debitamount,entity=order.entity,createdby= order.createdby,accounttype = accounttype)
        return order
    
    # def update(self,instance,validated_data):
    #     instance.save()
    #     StockTransactions.objects.filter(transactiontype = instance.vouchertype,account = instance.account,)

    #     pass



class TrialbalanceSerializer(serializers.ModelSerializer):


  #  purchasequantity1 = serializers.DecimalField(max_digits=10,decimal_places=2)

   # creditaccounthead = serializers.IntegerField(source = 'account__creditaccounthead')
   # creditaccountheadname = serializers.CharField(max_length=500,source = 'account__creditaccounthead__name')
    accounthead = serializers.IntegerField(source = 'account__accounthead')
    accountheadname = serializers.CharField(max_length=500,source = 'account__accounthead__name')
    debit = serializers.DecimalField(max_digits=10,decimal_places=2)
    credit = serializers.DecimalField(max_digits=10,decimal_places=2)
    balance = serializers.DecimalField(max_digits=10,decimal_places=2)
   # drcr = serializers.SerializerMethodField()
    

    #debit  = serializers.SerializerMethodField()
   

    class Meta:
        model = StockTransactions
        fields = ['accounthead','accountheadname','debit','credit','balance']

    
    # def get_drcr(self,obj):
    #     if obj['balance'] > 0:
    #         return 'DR'
    #     else:
    #         return 'CR'

    

    

  

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)

    #     #print(instance)

    #     if representation['balance'] > 0:
    #         representation['debit'] = representation['balance']
    #         # representation['accounthead'] = representation['accounthead']
    #         # representation['accountheadname'] = representation['accountheadname']
    #         representation['credit'] = 0

    #         return representation
    #     else:
    #         representation['credit'] = abs(representation['balance'])
    #         representation['debit'] = 0
    #         representation['balance'] = abs(representation['balance'])
    #         # representation['accounthead'] = representation['creditaccounthead']
    #         # representation['accountheadname'] = representation['creditaccountheadname']
    #         return representation




        # if representation['debit'] and representation['credit']:
        #     if float(representation['debit']) - float(representation['credit']) > 0:
        #         representation['debit'] = ("{:0.2f}".format(float(representation['debit']) - float(representation['credit'])))
        #         representation['credit'] = ''
        #         return representation
        #     else:
        #         representation['credit'] = ("{:0.2f}".format(float(representation['credit']) - float(representation['debit'])))
        #         representation['debit'] = ' '
        #         return representation
        # return representation



class TrialbalanceSerializerbyaccounthead(serializers.ModelSerializer):


  #  purchasequantity1 = serializers.DecimalField(max_digits=10,decimal_places=2)

    account = serializers.IntegerField()
    accountname = serializers.CharField(max_length=500,source = 'account__accountname')
    debit = serializers.DecimalField(max_digits=10,decimal_places=2)
    credit = serializers.DecimalField(max_digits=10,decimal_places=2)
    balance = serializers.DecimalField(max_digits=10,decimal_places=2)
    drcr = serializers.SerializerMethodField()
   

    class Meta:
        model = StockTransactions
        fields = ['account','accountname','debit','credit','balance','drcr']

    def get_drcr(self,obj):
        if obj['balance'] > 0:
            return 'DR'
        else:
            return 'CR'
        
        

        



class gstr1b2bserializer(serializers.ModelSerializer):


  #  purchasequantity1 = serializers.DecimalField(max_digits=10,decimal_places=2)

    #account = serializers.IntegerField()
    gstin = serializers.CharField(max_length=500,source = 'account__gstno')
    receiver = serializers.CharField(max_length=500,source = 'account__accountname')
    invoiceno = serializers.CharField(max_length=500,source = 'saleinvoice__billno')
    invoicedate = serializers.CharField(max_length=500,source = 'saleinvoice__sorderdate')


    
   
    invoicevalue = serializers.SerializerMethodField()
    placeofsupply = serializers.SerializerMethodField()
    reversechnarge = serializers.SerializerMethodField()
    taxrate = serializers.SerializerMethodField()
    invoicetype = serializers.SerializerMethodField()
    rate = serializers.SerializerMethodField()
    ecomgstin = serializers.SerializerMethodField()
    taxableamount = serializers.SerializerMethodField()
    cessamount = serializers.SerializerMethodField()
   

    class Meta:
        model = StockTransactions
        fields = ['gstin','receiver','invoiceno','invoicedate','invoicevalue','placeofsupply','reversechnarge','taxrate','invoicetype','rate','ecomgstin','taxableamount','cessamount']

    # def get_gstin(self, obj):
    #      #print(obj)

    #      return obj.account.gstno

    def get_receiver(self, obj):
         #print(obj)

         return obj.account.accountname
    
    def get_invoiceno(self, obj):
         #print(obj)

         return obj.saleinvoice.billno

    
    def get_invoicedate(self, obj):
         #print(obj)

         return obj.saleinvoice.sorderdate

    def get_invoicevalue(self, obj):
         #print(obj)

         return "5000.00"

    def get_placeofsupply(self, obj):
         #print(obj)

         return "03-Punjab"

    def get_reversechnarge(self, obj):
         #print(obj)

         return "N"

    def get_taxrate(self, obj):
         #print(obj)

         return ""

    
    def get_invoicetype(self, obj):
         #print(obj)

         return "regular"

    def get_rate(self, obj):
         #print(obj)

         return "18.00"

    def get_ecomgstin(self, obj):
         #print(obj)

         return ""

    def get_taxableamount(self, obj):
         #print(obj)

         return "1234.00"

    def get_cessamount(self, obj):
         #print(obj)

         return ""


class gstr1hsnserializer(serializers.ModelSerializer):


  #  purchasequantity1 = serializers.DecimalField(max_digits=10,decimal_places=2)

    #account = serializers.IntegerField()
    hsn = serializers.CharField(max_length=500,source = 'stock__hsn')
    description = serializers.CharField(max_length=500,source = 'stock__productdesc')
    uom = serializers.CharField(max_length=500,source = 'stock__unitofmeasurement__unitname')
    totalweight = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'salequantity')
    taxablevalue = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'credit')
    #taxrate = serializers.CharField(max_length=500,source = 'stock__totalgst')
    centraltax = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'cgstdr')
    statetax = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'sgstdr')
    igst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'igstdr')
    # totalvalue= serializers.SerializerMethodField()


    # def get_totalvalue(self, obj):
    #      #print(obj)

    #      return obj.credit

    

    

    

      
   
   
   

    class Meta:
        model = StockTransactions
        fields = ['hsn','description','uom','totalweight','taxablevalue','centraltax','statetax','igst']

    

    
         


         


         


         






class stocktranserilaizer(serializers.ModelSerializer):

    # # debit  = serializers.SerializerMethodField()
    accountname= serializers.SerializerMethodField()
    entrydate= serializers.SerializerMethodField()


    

    def get_accountname(self, obj):
         print(obj)

         return obj.account.accountname
    
    def get_entrydate(self, obj):
         return obj.entry.entrydate1.strftime("%Y-%m-%d")


    class Meta:
        model = StockTransactions
        fields = ['account','accountname','entrydate','transactiontype','transactionid','drcr','desc', 'debitamount','creditamount']


class stocktranledgerserilaizer(serializers.ModelSerializer):

    # # debit  = serializers.SerializerMethodField()
    balance= serializers.SerializerMethodField()
    entrydate= serializers.SerializerMethodField()


    

    
    def get_entrydate(self, obj):
         return obj.entry.entrydate1

    
    def get_dr(self, obj):
         return obj.entry.entrydate1

    
    def get_balance(self, obj):

        yesterday = obj.entry.entrydate1 - timedelta(days = 1)
        startdate = obj.entry.entrydate1 - timedelta(days = 10)
        debit = StockTransactions.objects.filter(account = obj.account, id__lt = obj.id,entity = obj.entity).aggregate(Sum('debitamount'))['debitamount__sum']
        credit = StockTransactions.objects.filter(account = obj.account,id__lt = obj.id,entity = obj.entity).aggregate(Sum('creditamount'))['creditamount__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']
        if not debit:
            debit = 0
        if not credit:
            credit = 0

        if not obj.debitamount:
            debitamount = 0
        else:
            debitamount = obj.debitamount


        if not obj.creditamount:
            creditamount = 0
        else:
            creditamount = obj.creditamount



        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return debit - credit + debitamount - creditamount



    class Meta:
        model = StockTransactions
        fields = ['entrydate','transactiontype','transactionid','drcr','desc', 'debitamount','creditamount','balance']





class goodsserilaizer(serializers.ModelSerializer):

    # # debit  = serializers.SerializerMethodField()
    entrydate = serializers.SerializerMethodField()


    

    def get_entrydate(self, obj):
        return obj.entry.entrydate1


    class Meta:
        model = goodstransaction
        fields = ['account','stock','transactiontype','transactionid','purchasequantity','issuedquantity','recivedquantity','salequantity','entrydatetime','entrydate']



class actserializer(serializers.ModelSerializer):
    accounttrans = stocktranserilaizer(many=True, read_only=True)

  #  dateentry = serializers.SerializerMethodField()

    class Meta:
        model = account
        fields = ['id','accountname','accounttrans']




class Salebyaccountserializer(serializers.ModelSerializer):
  #  accounttrans = stocktranserilaizer(many=True, read_only=True)

    accountname = serializers.SerializerMethodField()
    accountcode = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    entrydate = serializers.SerializerMethodField()
    cgst = serializers.DecimalField(max_digits=10, decimal_places=2,source = 'cgstcr')
    sgst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'sgstcr')
    igst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'igstcr')
    gtotal = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'debitamount')

    def get_accountname(self, obj):
        return obj.account.accountname

    def get_accountcode(self, obj):
        return obj.account.accountcode

    def get_accountcode(self, obj):
        return obj.account.accountcode

    def get_city(self, obj):
        return obj.account.city.cityname
    
    def get_entrydate(self, obj):
        return obj.entry.entrydate1



    class Meta:
        model = StockTransactions
        fields = ['id','transactiontype','transactionid','desc','gtotal','pieces','weightqty','account','accountname','accountcode','city','entrydate',]




class Purchasebyaccountserializer(serializers.ModelSerializer):
  #  accounttrans = stocktranserilaizer(many=True, read_only=True)

    accountname = serializers.SerializerMethodField()
    accountcode = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    entrydate = serializers.SerializerMethodField()
    cgst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'cgstdr')
    sgst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'sgstdr')
    igst = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'igstdr')
    gtotal = serializers.DecimalField(max_digits=10,decimal_places=2,source = 'creditamount')

    

    

    #models.DecimalField(max_digits=10,null = True,decimal_places=3,verbose_name= 'Opening Amount')

    def get_accountname(self, obj):
        return obj.account.accountname

    def get_accountcode(self, obj):
        return obj.account.accountcode

    def get_accountcode(self, obj):
        return obj.account.accountcode

    def get_city(self, obj):
        return obj.account.city.cityname

    def get_entrydate(self, obj):
        return obj.entry.entrydate1



    class Meta:
        model = StockTransactions
        fields = ['id','transactiontype','transactionid','desc','gtotal','cgst','sgst','igst','pieces','weightqty','account','accountname','accountcode','city',"entrydate",]
        
    
   


class cashserializer(serializers.ModelSerializer):


   # cashtrans = stocktranserilaizer(source = 'account_transactions', many=True, read_only=True)
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
    entrydate = serializers.SerializerMethodField()
    cr = serializers.SerializerMethodField()
    dr = serializers.SerializerMethodField()





   # stk = stocktranserilaizer(many=True, read_only=True)
   # select_related_fields = ('accounthead')

    # debit  = serializers.SerializerMethodField()
   # day = serializers.CharField()

    class Meta:
        model = entry
        fields = ['id','entrydate','debit','credit','cr','dr',]

    def get_debit(self, obj):

       # print(obj.cashtrans('account'))
        
        return obj.cashtrans.exclude(accounttype = 'MD',isactive = 0).exclude(transactiontype = 'OS').aggregate(Sum('debitamount'))['debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')

        return obj.cashtrans.filter(accounttype = 'M',isactive = 0).aggregate(Sum('creditamount'))['creditamount__sum']
        #return obj.cashtrans.exclude(accounttype = 'MD',isactive = 0).exclude(transactiontype = 'OS').aggregate(Sum('creditamount'))['creditamount__sum']

    def get_entrydate(self,obj):
        return obj.entrydate1

    def get_cr(self,obj):

        filter_backends = [DjangoFilterBackend]
        filterset_fields = {'cashtrans__transactiontype':["in", "exact"]}
        
        #stock =  obj.cashtrans.filter(drcr = False).order_by('account')
       # print(stock)

        stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False,isactive = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'OS').values('account','entry','transactiontype','transactionid','drcr','desc').annotate(debitamount = Sum('debitamount'),creditamount = Sum('creditamount'))
        #return account1Serializer(accounts,many=True).data
        #stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False)

        stock = stock.annotate(accountname=F('account__accountname')).order_by('account__accountname')

        return stock
      #  return stocktranserilaizer(stock, many=True).data

    
    def get_dr(self,obj):

        filter_backends = [DjangoFilterBackend]
        filterset_fields = {'cashtrans__transactiontype':["in", "exact"]}
        #stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = True)
        stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = True,isactive = 1).exclude(accounttype = 'MD').exclude(transactiontype = 'OS').values('account','entry','transactiontype','transactionid','drcr','desc').annotate(debitamount = Sum('debitamount'),creditamount= Sum('creditamount'))
        #return account1Serializer(accounts,many=True).data
        stock = stock.annotate(accountname=F('account__accountname')).order_by('account__accountname')
        return stock
       # return stocktranserilaizer(stock, many=True).data





# class   cbserializer(serializers.ModelSerializer):


#    # cashtrans = stocktranserilaizer(source = 'account_transactions', many=True, read_only=True)

#     openingbalance  = serializers.SerializerMethodField()
#     reciept  = serializers.SerializerMethodField()
#     payment = serializers.SerializerMethodField()
#     entrydate = serializers.SerializerMethodField()
#     payments = serializers.SerializerMethodField()
#     reciepts = serializers.SerializerMethodField()
#     cashinhand = serializers.SerializerMethodField()
#     reciepttotal = serializers.SerializerMethodField()
#     paymenttotal = serializers.SerializerMethodField()





#    # stk = stocktranserilaizer(many=True, read_only=True)
#    # select_related_fields = ('accounthead')

#     # debit  = serializers.SerializerMethodField()
#    # day = serializers.CharField()

#     class Meta:
#         model = entry
#         fields = ['id','entrydate','openingbalance','cashinhand','reciept','payment','reciepttotal','paymenttotal', 'payments','reciepts']

#     def get_reciept(self, obj):

#         # yesterday = obj.entrydate1 - timedelta(days = 0)
#         # startdate = obj.entrydate1 - timedelta(days = 10)

#        # print(obj.cashtrans('account'))
#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return obj.cashtrans.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']

#     def get_payment(self, obj):
#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return obj.cashtrans.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']

#     def get_openingbalance(self, obj):

#         yesterday = obj.entrydate1 - timedelta(days = 1)
#         startdate = obj.entrydate1 - timedelta(days = 200)
#         debit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']
#         credit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']
#         # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
#         # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']
#         if not debit:
#             debit = 0
#         if not credit:
#             credit = 0


#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return debit - credit

    
#     def get_cashinhand(self, obj):

#         yesterday = obj.entrydate1 - timedelta(days = 1)
#         startdate = obj.entrydate1 - timedelta(days = 200)
#         debit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']
#         credit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']
#         # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
#         # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']
#         if not debit:
#             debit = 0
#         if not credit:
#             credit = 0
#         if not self.get_reciept(obj=obj):
#             reciept = 0
#         else:
#             reciept = self.get_reciept(obj=obj)

#         if not self.get_payment(obj=obj):
#             payment = 0
#         else:
#             payment = self.get_payment(obj=obj)



#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return debit - credit + reciept - payment

#     def get_entrydate(self,obj):
#         return obj.entrydate1.strftime("%d-%m-%Y")

#     def get_reciepttotal(self, obj):

#         # yesterday = obj.entrydate1 - timedelta(days = 0)
#         # startdate = obj.entrydate1 - timedelta(days = 10)

#         if not self.get_openingbalance(obj):
#             balance = 0
#         else:
#             balance = self.get_openingbalance(obj)
        
#         if not self.get_reciept(obj):
#             reciept = 0
#         else:
#             reciept = self.get_reciept(obj)




#        # print(obj.cashtrans('account'))
#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return balance + reciept

    
#     def get_paymenttotal(self, obj):

#         if not self.get_cashinhand(obj):
#             cashinhand = 0
#         else:
#             cashinhand =self.get_cashinhand(obj)
        
#         if not self.get_payment(obj):
#             payment = 0
#         else:
#             payment = self.get_payment(obj)


#         # yesterday = obj.entrydate1 - timedelta(days = 0)
#         # startdate = obj.entrydate1 - timedelta(days = 10)

#        # print(obj.cashtrans('account'))
#         # fromDate = parse_datetime(self.context['request'].query_params.get(
#         #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         # toDate = parse_datetime(self.context['request'].query_params.get(
#         #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
#         return cashinhand + payment

#     def get_reciepts(self,obj):
#         print(self.context['request'])
        
#         #stock =  obj.cashtrans.filter(drcr = False).order_by('account')
#        # print(stock)

#         stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False,accounttype__in = ['M'],isactive = 1,iscashtransaction= 1)
#         #return account1Serializer(accounts,many=True).data
#         return stocktranserilaizer(stock, many=True).data

    
#     def get_payments(self,obj):
#         stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = True,accounttype__in = ['M'],isactive = 1,iscashtransaction= 1)
#         #return account1Serializer(accounts,many=True).data
#         return stocktranserilaizer(stock, many=True).data






class  ledgerserializer(serializers.ModelSerializer):


   # accounttrans = stocktranledgerserilaizer(many=True, read_only=True)

    openingbalance  = serializers.SerializerMethodField()
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
    # entrydate = serializers.SerializerMethodField()
    accounts = serializers.SerializerMethodField()
    # reciepts = serializers.SerializerMethodField()
    # cashinhand = serializers.SerializerMethodField()
    balancetotal = serializers.SerializerMethodField()
    openingquantity = serializers.SerializerMethodField()
    # paymenttotal = serializers.SerializerMethodField()





   # stk = stocktranserilaizer(many=True, read_only=True)
   # select_related_fields = ('accounthead')

    # debit  = serializers.SerializerMethodField()
   # day = serializers.CharField()

    class Meta:
        model = account
        fields = ['id','accountname','debit','credit','openingquantity','openingbalance','balancetotal','accounts',]


    def get_openingquantity(self, obj):

        yesterday = date.today() - timedelta(days = 100)

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        quantity = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('quantity'))['quantity__sum']
        #credit = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('creditamount'))['creditamount__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']

      
        if not quantity:
            quantity = 0
        # if not credit:
        #     credit = 0


        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')

        # print(queryset.query.__str__())
        return quantity

    def get_openingbalance(self, obj):

        yesterday = date.today() - timedelta(days = 100)

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        debit = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('debitamount'))['debitamount__sum']
        credit = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('creditamount'))['creditamount__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']

      
        if not debit:
            debit = 0
        if not credit:
            credit = 0


        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')

        # print(queryset.query.__str__())
        return debit - credit

    def get_debit(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        debit = obj.accounttrans.filter(entry__entrydate1__range = (startdate,enddate),isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('debitamount'))['debitamount__sum']

    

        if self.get_openingbalance(obj=obj) > 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not debit:
            debit = 0
        else:
            debit = debit


        print(debit)
            


       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return debit + ob

    def get_credit(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        credit = obj.accounttrans.filter(entry__entrydate1__range = (startdate,enddate),isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('creditamount'))['creditamount__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not credit:
            credit = 0
        else:
            credit = credit
        
    
        print(credit)

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return credit - ob

    # def get_payment(self, obj):
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     return obj.cashtrans.filter(accounttype = 'CIH',transactiontype = 'C' ).aggregate(Sum('creditamount'))['creditamount__sum']

  

    
   

    def get_balancetotal(self,obj):

        if not self.get_openingbalance(obj):
            opening = 0
        else:
            opening = self.get_openingbalance(obj)

        if not self.get_debit(obj):
            debit = 0
        else:
            debit = self.get_debit(obj)

        if not self.get_credit(obj):
            credit = 0
        else:
            credit = self.get_credit(obj)


        
        #stock =  obj.cashtrans.filter(drcr = False).order_by('account')
       # print(stock)

       # stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False,accounttype = 'M')
        #return account1Serializer(accounts,many=True).data
        return  debit - credit

    
    def get_accounts(self,obj):

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        stock = obj.accounttrans.filter(entry__entrydate1__range = (startdate,enddate),isactive = 1).exclude(accounttype = 'MD').exclude(transactiontype__in = ['PC']).values('account','entry','transactiontype','transactionid','drcr','desc').annotate(debitamount = Sum('debitamount'),creditamount = Sum('creditamount'),quantity = Sum('quantity')).order_by('entry__entrydate1')
        #return account1Serializer(accounts,many=True).data
        #return account1Serializer(accounts,many=True).data
        #stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False)

        stock = stock.annotate(accountname=F('account__accountname'),entrydate = F('entry__entrydate1'))
        return stock
        #return stocktranledgerserilaizer(stock, many=True).data



class  ledgersummaryserializer(serializers.ModelSerializer):


   # accounttrans = stocktranledgerserilaizer(many=True, read_only=True)

    openingbalance  = serializers.SerializerMethodField()
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
    # entrydate = serializers.SerializerMethodField()
  #  accounts = serializers.SerializerMethodField()
    # reciepts = serializers.SerializerMethodField()
    # cashinhand = serializers.SerializerMethodField()
    balancetotal = serializers.SerializerMethodField()
    # paymenttotal = serializers.SerializerMethodField()





   # stk = stocktranserilaizer(many=True, read_only=True)
   # select_related_fields = ('accounthead')

    # debit  = serializers.SerializerMethodField()
   # day = serializers.CharField()

    class Meta:
        model = account
        fields = ['id','accountname','debit','credit', 'openingbalance','balancetotal',]

    def get_openingbalance(self, obj):

        yesterday = date.today() - timedelta(days = 100)

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        debit = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('debitamount'))['debitamount__sum']
        credit = obj.accounttrans.filter(account = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('creditamount'))['creditamount__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']

      
        if not debit:
            debit = 0
        if not credit:
            credit = 0


        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return debit - credit

    def get_debit(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        debit = obj.accounttrans.filter(entry__entrydate1__range = (startdate,enddate),isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('debitamount'))['debitamount__sum']

        if self.get_openingbalance(obj=obj) > 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not debit:
            debit = 0
        else:
            debit = debit
            


       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return debit

    def get_credit(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        credit = obj.accounttrans.filter(entry__entrydate1__range = (startdate,enddate),isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('creditamount'))['creditamount__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not credit:
            credit = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return credit


    def get_balancetotal(self,obj):
        if not self.get_openingbalance(obj):
            opening = 0
        else:
            opening = self.get_openingbalance(obj)

        if not self.get_debit(obj):
            debit = 0
        else:
            debit = self.get_debit(obj)

        if not self.get_credit(obj):
            credit = 0
        else:
            credit = self.get_credit(obj)
        
        return opening + debit - credit

    # def get_payment(self, obj):
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     return obj.cashtrans.filter(accounttype = 'CIH',transactiontype = 'C' ).aggregate(Sum('creditamount'))['creditamount__sum']

class  stockledgersummaryserializer(serializers.ModelSerializer):


   # accounttrans = stocktranledgerserilaizer(many=True, read_only=True)

    openingbalance  = serializers.SerializerMethodField()
    sale  = serializers.SerializerMethodField()
    purchase = serializers.SerializerMethodField()
    issued  = serializers.SerializerMethodField()
    recieved = serializers.SerializerMethodField()
 
    balancetotal = serializers.SerializerMethodField()
    # paymenttotal = serializers.SerializerMethodField()





    class Meta:
        model = Product
        fields = ['id','productname','sale','purchase','issued','recieved','openingbalance','balancetotal',]

    def get_openingbalance(self, obj):

        yesterday = date.today() - timedelta(days = 100)

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        sale = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'S',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        purchase = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'P',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        issued = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'I',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        recived = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'R',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']

      
        if not sale:
            sale = 0
        if not purchase:
            purchase = 0
        if not issued:
            issued = 0
        if not recived:
            recived = 0


        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return purchase + recived - sale - issued

    def get_sale(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        sale = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'S',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) > 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not sale:
            sale = 0
        else:
            sale = sale
            


      
        return sale

    def get_purchase(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        purchase = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'P',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not purchase:
            purchase = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return purchase


    def get_issued(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        issued = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'I',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not issued:
            issued = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return issued


    def get_recieved(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        recieved = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'R',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not recieved:
            recieved = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return recieved




    
   

    def get_balancetotal(self,obj):

        if not self.get_openingbalance(obj):
            opening = 0
        else:
            opening = self.get_openingbalance(obj)

        if not self.get_sale(obj):
            sale = 0
        else:
            sale = self.get_sale(obj)

        if not self.get_purchase(obj):
            purchase = 0
        else:
            purchase = self.get_purchase(obj)
        
        if not self.get_issued(obj):
            issued = 0
        else:
            issued = self.get_issued(obj)

        if not self.get_recieved(obj):
            recived = 0
        else:
            recived = self.get_recieved(obj)

        return  opening + purchase - sale + recived  -issued


class  stockledgerbookserializer(serializers.ModelSerializer):


   # accounttrans = stocktranledgerserilaizer(many=True, read_only=True)

    openingbalance  = serializers.SerializerMethodField()
    sale  = serializers.SerializerMethodField()
    purchase = serializers.SerializerMethodField()
    issued  = serializers.SerializerMethodField()
    recieved = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
 
    balancetotal = serializers.SerializerMethodField()
    # paymenttotal = serializers.SerializerMethodField()





    class Meta:
        model = Product
        fields = ['id','productname','sale','purchase','issued','recieved','openingbalance','balancetotal','stock',]

    def get_openingbalance(self, obj):

        yesterday = date.today() - timedelta(days = 100)

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        sale = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'S',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        purchase = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'P',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        issued = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'I',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        recived = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (yesterday,startdate),entity = obj.entity,accounttype = 'DD',stockttype = 'R',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']

      
        if not sale:
            sale = 0
        if not purchase:
            purchase = 0
        if not issued:
            issued = 0
        if not recived:
            recived = 0


        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return purchase + recived - sale - issued

    def get_sale(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        sale = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'S',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) > 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not sale:
            sale = 0
        else:
            sale = sale
            


      
        return sale

    def get_purchase(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        purchase = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'P',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not purchase:
            purchase = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return purchase


    def get_issued(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        issued = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'I',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not issued:
            issued = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return issued


    def get_recieved(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        recieved = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',stockttype = 'R',isactive = 1).aggregate(Sum('quantity'))['quantity__sum']

        if self.get_openingbalance(obj=obj) < 0:
            ob = self.get_openingbalance(obj=obj)
        else:
            ob = 0

        if not recieved:
            recieved = 0
        

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return recieved




    
   

    def get_balancetotal(self,obj):

        if not self.get_openingbalance(obj):
            opening = 0
        else:
            opening = self.get_openingbalance(obj)

        if not self.get_sale(obj):
            sale = 0
        else:
            sale = self.get_sale(obj)

        if not self.get_purchase(obj):
            purchase = 0
        else:
            purchase = self.get_purchase(obj)
        
        if not self.get_issued(obj):
            issued = 0
        else:
            issued = self.get_issued(obj)

        if not self.get_recieved(obj):
            recived = 0
        else:
            recived = self.get_recieved(obj)

        return  opening + purchase - sale + recived  -issued


    def get_stock(self,obj):

        startdate = self.context['request'].query_params.get('startdate')
        enddate = self.context['request'].query_params.get('enddate')

        stock = obj.stocktrans.filter(stock = obj.id,entry__entrydate1__range = (startdate,enddate),accounttype = 'DD',isactive = 1).values('stock','entry','transactiontype','transactionid','stockttype','desc').annotate(salequantity = Sum('quantity'),purchasequantity = Sum('quantity'),issuedquantity = Sum('quantity'),recivedquantity = Sum('quantity')).order_by('entry__entrydate1')
        #return account1Serializer(accounts,many=True).data
        #return account1Serializer(accounts,many=True).data
        #stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False)

        stock = stock.annotate(productname=F('stock__productname'),entrydate = F('entry__entrydate1'))
        return stock




        





class stockserializer(serializers.ModelSerializer):


   # goods = goodsserilaizer(source = 'account_transactions', many=True, read_only=True)
    salequantity  = serializers.SerializerMethodField()
    purchasequantity = serializers.SerializerMethodField()
    issuedquantity  = serializers.SerializerMethodField()
    recivedquantity = serializers.SerializerMethodField()


   # stk = stocktranserilaizer(many=True, read_only=True)
   # select_related_fields = ('accounthead')

    # debit  = serializers.SerializerMethodField()
   # day = serializers.CharField()

    class Meta:
        model = Product
        fields = ['productname','salequantity','purchasequantity','issuedquantity','recivedquantity']

    def get_salequantity(self, obj):

        print(obj)
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.stocktrans.filter(transactiontype = 'S',drcr = False).aggregate(Sum('quantity'))['quantity__sum']

    def get_purchasequantity(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.stocktrans.filter(transactiontype = 'P',drcr = True).aggregate(Sum('quantity'))['quantity__sum']

    def get_issuedquantity(self, obj):
        return obj.stocktrans.filter(transactiontype = 'PC',drcr = True).aggregate(Sum('quantity'))['quantity__sum']

    def get_recivedquantity(self, obj):
        return obj.stocktrans.filter(transactiontype = 'PC',drcr = False).aggregate(Sum('quantity'))['quantity__sum']





class stock1DriverSerializer(serializers.ModelSerializer):

    class Meta:
        model = StockTransactions
        fields = '__all__'


class account1Serializer(serializers.ModelSerializer):
    accounttrans = stock1DriverSerializer(many=True, read_only=True)
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()

    class Meta:
        model = account
        fields = ('accountname','accountcode','debit','credit','accounttrans')

    
    def get_debit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.accounttrans.aggregate(Sum('debitamount'))['debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.accounttrans.aggregate(Sum('creditamount'))['creditamount__sum']



class accountheadtranSerializer(serializers.ModelSerializer):
  #  accounttrans = stock1DriverSerializer(many=True, read_only=True)
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ('name','code','debit','credit')

    
    def get_debit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.headtrans.aggregate(Sum('debitamount'))['debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.headtrans.aggregate(Sum('creditamount'))['creditamount__sum']


class entitySerializer1(serializers.ModelSerializer):
    entity_accountheads = accountheadtranSerializer(many=True, read_only=True)
    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
   # amount_of_trucks = serializers.IntegerField()

    class Meta:
        model = Entity
        fields = ('debit','credit','entity_accountheads')

    def get_debit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.entity_accountheads.aggregate(Sum('headtrans__debitamount'))['headtrans__debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.entity_accountheads.aggregate(Sum('headtrans__creditamount'))['headtrans__creditamount__sum']
    





   




class accountheadserializer(serializers.ModelSerializer):
    headtrans = stocktranserilaizer(source = 'accounthead_transactions', many=True, read_only=True)

    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ['id','name','debit','credit','headtrans']

    def get_debit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.headtrans.aggregate(Sum('debitamount'))['debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.headtrans.aggregate(Sum('creditamount'))['creditamount__sum']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
       # print(representation['accounttrans'])
        return representation
        # if representation['is_active'] == True:
            



        
    
    # def get_dateentry(self, obj):

    #   #  print(obj)
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #    # aggregate(Sum('debitamount'))['debitamount__sum']
    #     return obj.accounttrans.values('entrydate').annotate(debit = Sum('debitamount'),credit = Sum('creditamount') )


    # def get_debit(self, obj):

    #  #   print(obj)
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     return obj.accounttrans.aggregate(Sum('debitamount'))['debitamount__sum']

    # def get_credit(self, obj):
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     if not obj.accounttrans.aggregate(Sum('creditamount'))['creditamount__sum']:
    #         return ''
    #     return obj.accounttrans.aggregate(Sum('creditamount'))['creditamount__sum']

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #    # print(representation)
    #     if not representation['accounttrans']:
    #         return None
    #     return representation



class accountserializer(serializers.ModelSerializer):
    accounttrans = stocktranserilaizer(source = 'account_transactions', many=True, read_only=True)

    debit  = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
  #  dateentry = serializers.SerializerMethodField()

    class Meta:
        model = account
        fields = ['id','accountname','debit','credit', 'accounttrans',]
        
    
    def get_dateentry(self, obj):

      #  print(obj)
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
       # aggregate(Sum('debitamount'))['debitamount__sum']
        return obj.accounttrans.values('entrydate').annotate(debit = Sum('debitamount'),credit = Sum('creditamount') )


    def get_debit(self, obj):

     #   print(obj)
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.accounttrans.aggregate(Sum('debitamount'))['debitamount__sum']

    def get_credit(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        if not obj.accounttrans.aggregate(Sum('creditamount'))['creditamount__sum']:
            return ''
        return obj.accounttrans.aggregate(Sum('creditamount'))['creditamount__sum']

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #    # print(representation)
    #     if not representation['accounttrans']:
    #         return None
    #     return representation

    #     # print(representation)
    #     # return representation


class balancesheetserializer(serializers.ModelSerializer):
   # accounthead_accounts = accountserializer(many=True, read_only=True)
   # accounttrans = stocktranserilaizer(many=True, read_only=True)
    creditors = serializers.SerializerMethodField()

    # debit  = serializers.SerializerMethodField()
    # credit = serializers.SerializerMethodField()
  #  dateentry = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ['name','creditors']

    def get_creditors(self, obj):

        stock = obj.accounthead_accounts.filter()
        #return account1Serializer(accounts,many=True).data
        return accountserializer(stock, many=True).data

    
    


class accounthserializer(serializers.ModelSerializer):
    #headtrans = accountserializer(source = 'account_transactions2',many=True, read_only=True)
    #headtrans1 = stocktranserilaizer(source = 'account_transactions',many=True, read_only=True)

    # debit  = serializers.SerializerMethodField()
    # credit = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ['name']

    # def get_debit(self, obj):
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     return obj.headtrans.aggregate(Sum('debitamount'))['debitamount__sum']

    # def get_credit(self, obj):
    #     # fromDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     # toDate = parse_datetime(self.context['request'].query_params.get(
    #     #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
    #     return obj.headtrans.aggregate(Sum('creditamount'))['creditamount__sum']
    
     


class TrialbalanceSerializerbyaccount(serializers.ModelSerializer):


  #  purchasequantity1 = serializers.DecimalField(max_digits=10,decimal_places=2)

   # account = serializers.IntegerField()
    accountname = serializers.CharField(max_length=500,source='account__accountname')
    debit = serializers.DecimalField(max_digits=10,decimal_places=2)
    credit = serializers.DecimalField(max_digits=10,decimal_places=2)
    transactiontype = serializers.CharField(max_length=50)
    transactionid = serializers.IntegerField()
    entrydate = serializers.DateTimeField(source='entrydatetime')
    desc = serializers.CharField(max_length=500)
   

    class Meta:
        model = StockTransactions
        fields = ['accountname','transactiontype','transactionid','debit','credit','entrydate','desc']


        

        # def to_representation(self, instance):
        #     original_representation = super().to_representation(instance)

        #     print(original_representation)

        #     representation = {
                
        #         'detail': original_representation,
        #     }

        #     return representation





    


class JournalVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = journalmain
        fields =  ['newvoucher']


class stockVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = stockmain
        fields =  ['newvoucher']



class stockVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = stockmain
        fields =  ['newvoucher']



class productionVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = stockmain
        fields =  ['newvoucher']




class SRSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = salereturn
        fields =  ['newvoucher']

class PISerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = purchaseorderimport
        fields =  ['newvoucher']



class salereturnotherchargesSerializer(serializers.ModelSerializer):
    
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)
    # productname = serializers.SerializerMethodField()
    # hsn = serializers.SerializerMethodField()
    # mrp = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = salereturnothercharges
        fields =  ('account','amount','name',)

    def get_name(self,obj):
        return obj.account.accountname



def q2(x) -> Decimal:
    if x is None:
        return ZERO2
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def q4(x) -> Decimal:
    if x is None:
        return ZERO4
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

def _sr_is_inter(header_like: dict, details: list) -> bool:
    """
    Decide inter vs intra.
    For SR, typically compare:
      - entity.state (supplier)
      - customer state (header.state)
    """
    entity = header_like.get("entity")
    party_state = header_like.get("state")

    entity_state = getattr(entity, "state", None) if entity else None
    if not entity_state or not party_state:
        # fallback: if any line says isigst True => inter
        for d in details or []:
            if d.get("isigst") is True:
                return True
        return False

    # compare by id (safer than name)
    es_id = getattr(entity_state, "id", None)
    ps_id = getattr(party_state, "id", None)
    return bool(es_id and ps_id and es_id != ps_id)

def _normalize_sr_detail_taxes(d: dict, is_inter: bool):
    """
    Force line taxes consistent with inter/intra.
    """
    igst_in = q2(d.get("igst", ZERO2) or ZERO2)
    cgst_in = q2(d.get("cgst", ZERO2) or ZERO2)
    sgst_in = q2(d.get("sgst", ZERO2) or ZERO2)

    if is_inter:
        d["igst"] = igst_in
        d["cgst"] = ZERO2
        d["sgst"] = ZERO2
        d["isigst"] = True
        # optional: keep percents consistent if you want
        # d["cgstpercent"] = ZERO4; d["sgstpercent"] = ZERO4
    else:
        d["igst"] = ZERO2
        d["cgst"] = cgst_in
        d["sgst"] = sgst_in
        d["isigst"] = False
        # optional: keep percents consistent if you want
        # d["igstpercent"] = ZERO4



def pick_active_gst_row(product):
    """
    Pick most relevant ProductGstRate for a product.
    Priority:
      1) active window + isdefault
      2) active window latest
      3) isdefault latest
      4) latest
    """
    if not product:
        return None

    today = timezone.localdate()
    rel = getattr(product, "gst_rates", None)
    if rel is None:
        return None

    qs = rel.all()

    active = qs.filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=today)
    ).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=today)
    )

    row = active.filter(isdefault=True).order_by("-valid_from", "-id").first()
    if row:
        return row

    row = active.order_by("-valid_from", "-id").first()
    if row:
        return row

    row = qs.filter(isdefault=True).order_by("-valid_from", "-id").first()
    if row:
        return row

    return qs.order_by("-valid_from", "-id").first()


def pick_price_row(product, pricelist_id=None, uom_id=None):
    """
    Pick most relevant ProductPrice row (same logic you use in PurchaseOrderDetailsSerializer).
    """
    if not product:
        return None

    today = timezone.localdate()
    rel = getattr(product, "prices", None)
    if rel is None:
        return None

    qs = rel.all()
    if pricelist_id:
        qs = qs.filter(pricelist_id=pricelist_id)
    if uom_id:
        qs = qs.filter(uom_id=uom_id)

    active = qs.filter(
        effective_from__lte=today
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=today)
    ).order_by("-effective_from")

    row = active.first()
    if row:
        return row

    return qs.order_by("-effective_from").first()




class salesreturnDetailsSerializer(serializers.ModelSerializer):
    otherchargesdetail = salereturnotherchargesSerializer(many=True, required=False)
    id = serializers.IntegerField(required=False)

    productname = serializers.CharField(source="product.productname", read_only=True)

    # ✅ FIX: Product has no `hsn`, so derive from ProductGstRate -> HsnSac.code
    hsn = serializers.SerializerMethodField()

    # ✅ derived from ProductPrice
    mrp = serializers.SerializerMethodField()
    purchase_rate = serializers.SerializerMethodField()
    selling_price = serializers.SerializerMethodField()

    class Meta:
        model = salereturnDetails
        fields = (
            "id",
            "product", "productname", "productdesc",
            "hsn", "mrp", "purchase_rate", "selling_price",
            "orderqty", "pieces", "rate", "amount", "othercharges",
            "cgst", "sgst", "igst", "cess",
            "cgstpercent", "sgstpercent", "igstpercent", "isigst",
            "linetotal", "subentity", "entity",
            "otherchargesdetail",
        )

    def get_hsn(self, obj):
        row = pick_active_gst_row(obj.product)
        return row.hsn.code if (row and row.hsn) else None

    def get_mrp(self, obj):
        row = pick_price_row(
            obj.product,
            pricelist_id=self.context.get("pricelist_id"),
            uom_id=self.context.get("uom_id"),
        )
        return row.mrp if row else None

    def get_purchase_rate(self, obj):
        row = pick_price_row(
            obj.product,
            pricelist_id=self.context.get("pricelist_id"),
            uom_id=self.context.get("uom_id"),
        )
        return row.purchase_rate if row else None

    def get_selling_price(self, obj):
        row = pick_price_row(
            obj.product,
            pricelist_id=self.context.get("pricelist_id"),
            uom_id=self.context.get("uom_id"),
        )
        return row.selling_price if row else None

    @staticmethod
    def setup_eager_loading(queryset):
        """
        ✅ Optimized:
          - product
          - product.prices
          - product.gst_rates + hsn
          - otherchargesdetail
        """
        return (
            queryset
            .select_related("product")
            .prefetch_related(
                Prefetch(
                    "product__prices",
                    queryset=ProductPrice.objects.only(
                        "id", "product_id", "pricelist_id", "uom_id",
                        "purchase_rate", "mrp", "selling_price",
                        "effective_from", "effective_to"
                    ).order_by("-effective_from")
                ),
                Prefetch(
                    "product__gst_rates",
                    queryset=ProductGstRate.objects.select_related("hsn").only(
                        "id", "product_id", "hsn_id",
                        "gst_type", "sgst", "cgst", "igst", "gst_rate",
                        "cess", "cess_type",
                        "valid_from", "valid_to", "isdefault",
                        "hsn__id", "hsn__code"
                    ).order_by("-valid_from", "-id")
                ),
                "otherchargesdetail",
            )
        )





class salesreturnSerializer(serializers.ModelSerializer):
    # ---------- nested ----------
    salereturndetails = salesreturnDetailsSerializer(many=True)
    adddetails = serializers.DictField(required=False, write_only=True)

    # ---------- read-only helpers ----------
    originalinvoice_number = serializers.SerializerMethodField()
    einvoice_details = serializers.SerializerMethodField()

    # OPTIONAL numeric fields (your existing)
    subtotal     = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    cgst         = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    sgst         = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    igst         = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    cess         = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    expenses     = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    gtotal       = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    roundOff     = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
    finalAmount  = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)

    class Meta:
        model = salereturn
        fields = (
            'id',
            'voucherdate','voucherno','invoicenumber',
            'account','state','district','city','pincode',
            'billno','billdate','terms','showledgeraccount','taxtype','billcash',
            'totalpieces','totalquanity','advance','remarks','transport','broker','taxid',
            'tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2',
            'duedate','inputdate','vehicle','grno','gstr2astatus',
            'subtotal','invoicetype','reversecharge','addless',
            'cgst','sgst','igst','cess','expenses','gtotal','roundOff','finalAmount',
            'entityfinid','subentity','entity','isactive',
            'salereturndetails','isammended','originalinvoice','originalinvoice_number',
            'adddetails','invoiceMode','eway','einvoice','einvoicepluseway',
            'einvoice_details',
        )

    # ===== utilities ==========================================================

    @staticmethod
    def _pk_or_none(val):
        """Return positive int PK, else None for 0/'0'/None/''/negatives."""
        try:
            i = int(val)
            return i if i > 0 else None
        except Exception:
            return None

    @classmethod
    def _strip_pk(cls, d: dict):
        """Remove 'id' key if it's falsy or non-positive."""
        if isinstance(d, dict) and 'id' in d and cls._pk_or_none(d.get('id')) is None:
            d.pop('id', None)
        return d

    @staticmethod
    def _header_update_fields():
        return [
            'voucherdate','voucherno','account','billno','state','district','city','pincode','billdate',
            'terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks',
            'transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3',
            'tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus',
            'subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','roundOff','finalAmount',
            'invoicetype','reversecharge',
            'entityfinid','subentity','entity','isactive','isammended','originalinvoice',
            'invoiceMode','eway','einvoice','einvoicepluseway',
        ]

    # ===== read helpers =======================================================

    def get_originalinvoice_number(self, obj):
        return getattr(getattr(obj, "originalinvoice", None), "invoicenumber", None)

    def _ct_for(self, obj):
        return ContentType.objects.get_for_model(obj, for_concrete_model=False)

    def get_einvoice_details(self, obj):
        ct = self._ct_for(obj)
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=obj.id).first()
        if not einv:
            return None
        return {
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date.strftime("%d/%m/%Y %H:%M:%S") if einv.ack_date else None,
            "qr_image_base64": _qr_base64_from_signed_qr(einv.signed_qr_code) if einv.signed_qr_code else None,
            "status": einv.status,
            "remarks": einv.remarks,
        }

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        try:
            # if you already have a shared builder that returns pay/ref/ewb/exp/addldoc as dict
            rep["adddetails"] = _build_adddetails_dict(instance)
        except Exception:
            rep["adddetails"] = None
        return rep

    # ===== tax regime enforcement (same spirit as your SalesOderHeader) =======

    def _enforce_igst_bucket(self, attrs: dict) -> None:
        """
        Your current rule:
          - if header IGST > 0 => force CGST/SGST = 0 and set details isigst=True, cgst/sgst=0
          - else => force IGST = 0 and set details isigst=False, igst=0
        """
        details = attrs.get("salereturndetails") or []

        igst = q2(attrs.get("igst", ZERO2) or ZERO2)
        if igst > ZERO2:
            attrs["cgst"] = ZERO2
            attrs["sgst"] = ZERO2
            for d in details:
                if isinstance(d, dict):
                    d["cgst"] = ZERO2
                    d["sgst"] = ZERO2
                    d["isigst"] = True
        else:
            attrs["igst"] = ZERO2
            for d in details:
                if isinstance(d, dict):
                    d["igst"] = ZERO2
                    d["isigst"] = False

    def validate(self, attrs):
        self._enforce_igst_bucket(attrs)
        return attrs

    # ===== adddetails upsert (invoice-style, safe) ===========================

    def _upsert_adddetails(self, order, adddetails_data: dict, is_update: bool):
        adddetails_data = adddetails_data or {}

        paydtls_data     = dict(adddetails_data.get('paydtls') or {}) or None
        refdtls_data     = dict(adddetails_data.get('refdtls') or {}) or None
        ewbdtls_data     = dict(adddetails_data.get('ewbdtls') or {}) or None
        expdtls_data     = dict(adddetails_data.get('expdtls') or {}) or None
        addldocdtls_list = list(adddetails_data.get('addldocdtls') or [])

        # PayDtls
        if paydtls_data:
            paydtls_data.pop('id', None)
            if is_update:
                PayDtls.objects.update_or_create(sales_return=order, defaults=paydtls_data)
            else:
                PayDtls.objects.create(sales_return=order, **paydtls_data)

        # RefDtls
        if refdtls_data:
            refdtls_data.pop('id', None)
            if is_update:
                RefDtls.objects.update_or_create(sales_return=order, defaults=refdtls_data)
            else:
                RefDtls.objects.create(sales_return=order, **refdtls_data)

        # EwbDtls
        if ewbdtls_data:
            ewbdtls_data.pop('id', None)
            if is_update:
                EwbDtls.objects.update_or_create(sales_return=order, defaults=ewbdtls_data)
            else:
                EwbDtls.objects.create(sales_return=order, **ewbdtls_data)

        # ExpDtls
        if expdtls_data:
            expdtls_data.pop('id', None)
            if is_update:
                ExpDtls.objects.update_or_create(sales_return=order, defaults=expdtls_data)
            else:
                ExpDtls.objects.create(sales_return=order, **expdtls_data)

        # AddlDocDtls (upsert list)
        if is_update:
            existing_qs  = AddlDocDtls.objects.filter(sales_return=order)
            existing_map = {d.id: d for d in existing_qs}
            existing_ids = set(existing_map.keys())
            incoming_ids = set()

            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc_id = self._pk_or_none(doc.get("id"))
                clean = {k: v for k, v in doc.items() if k != "id"}

                if doc_id and doc_id in existing_ids:
                    obj = existing_map[doc_id]
                    for k, v in clean.items():
                        setattr(obj, k, v)
                    obj.save()
                    incoming_ids.add(doc_id)
                else:
                    AddlDocDtls.objects.create(sales_return=order, **clean)

            to_delete = existing_ids - incoming_ids
            if to_delete:
                AddlDocDtls.objects.filter(id__in=to_delete).delete()
        else:
            for doc in addldocdtls_list:
                doc = dict(doc or {})
                doc.pop("id", None)
                AddlDocDtls.objects.create(sales_return=order, **doc)

    # ===== details upsert (invoice-style) ====================================

    def _upsert_details(self, order, details_data: list, is_update: bool):
        if not is_update:
            for row in details_data:
                row = dict(row or {})
                self._strip_pk(row)

                # keep your current "cleanup" behavior
                row.pop('productname', None)
                row.pop('hsn', None)
                row.pop('mrp', None)

                other_charges = row.pop('otherchargesdetail', []) or []
                detail = salereturnDetails.objects.create(salereturn=order, **row)

                for oc in other_charges:
                    oc = dict(oc or {})
                    self._strip_pk(oc)
                    salereturnothercharges.objects.create(salesreturnorderdetail=detail, **oc)
            return

        existing_map = {d.id: d for d in salereturnDetails.objects.filter(salereturn=order)}
        existing_ids = set(existing_map.keys())
        seen_ids = set()

        for row in details_data:
            row = dict(row or {})

            row.pop('productname', None)
            row.pop('hsn', None)
            row.pop('mrp', None)

            detail_id = self._pk_or_none(row.get('id'))
            row.pop('id', None)

            other_charges = row.pop('otherchargesdetail', []) or []

            if detail_id is None:
                d = salereturnDetails.objects.create(salereturn=order, **row)
            else:
                d = existing_map.get(detail_id)
                if d:
                    seen_ids.add(detail_id)
                    for k, v in row.items():
                        setattr(d, k, v)
                    d.save()
                else:
                    d = salereturnDetails.objects.create(salereturn=order, **row)

            # refresh charges
            salereturnothercharges.objects.filter(salesreturnorderdetail=d).delete()
            for oc in other_charges:
                oc = dict(oc or {})
                self._strip_pk(oc)
                salereturnothercharges.objects.create(salesreturnorderdetail=d, **oc)

        to_delete = existing_ids - seen_ids
        if to_delete:
            salereturnDetails.objects.filter(id__in=to_delete).delete()

    # ===== posting (single authoritative) ====================================

    def _post_once_via_shim(self, order, entrytype: str):
        """
        Like your SalesOderHeaderSerializer:
        - One call to createtransaction() which re-queries DB.
        - No per-line createtransactiondetails here.
        """
        stk = stocktransaction(order, transactiontype='SR', debit=1, credit=0,
                               description='To Sales Return V.No: ', entrytype=entrytype)
        stk.createtransaction()

    # ===== GST helpers (same as your invoice) =================================

    def _parse_mastergst_dt(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        s = str(value).strip()
        for fmt in MASTERGST_DT_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValidationError({"gst": f"Unsupported datetime format from MasterGST: {s}"})

    def _persist_einvoice_details(self, order, ct, data: dict):
        ack_dt = self._parse_mastergst_dt(data.get("AckDt"))
        ewb_dt = self._parse_mastergst_dt(data.get("EwbDt"))
        ewb_valid_till = self._parse_mastergst_dt(data.get("EwbValidTill"))

        irn = data.get("Irn")
        if not irn:
            raise ValidationError({"einvoice": "MasterGST response missing IRN (Irn)."})

        EInvoiceDetails.objects.update_or_create(
            content_type=ct,
            object_id=order.id,
            defaults={
                "irn": irn,
                "ack_no": data.get("AckNo"),
                "ack_date": ack_dt,
                "signed_invoice": data.get("SignedInvoice"),
                "signed_qr_code": data.get("SignedQRCode"),
                "status": data.get("Status", "ACT"),
                "ewb_no": data.get("EwbNo"),
                "ewb_date": ewb_dt,
                "ewb_valid_till": ewb_valid_till,
                "remarks": data.get("Remarks"),
            }
        )

    def _generate_einvoice_if_needed(self, order, mode: str, ct):
        existing = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).only("irn").first()
        if existing and existing.irn:
            return existing.irn

        payload = SalereturnFullSerializer(order, context={"mode": mode}).data


        print(payload)
        resp = gstinvoice(order, json.dumps(payload, default=str))

        print(resp)

        if not isinstance(resp, dict):
            raise ValidationError({"einvoice": "Unexpected response from gstinvoice()."})

        if str(resp.get("status_cd")) != "1":
            raise ValidationError({
                "einvoice": resp.get("status_desc", "E-Invoice generation failed."),
                "details": resp,
            })

        data = resp.get("data") or {}
        self._persist_einvoice_details(order, ct, data)
        return data.get("Irn")

    def _generate_eway_from_irn(self, order, ct):
        einv = EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).first()
        if not (einv and einv.irn):
            raise ValidationError({"eway": "IRN not found for this sales return. Cannot generate E-Way Bill."})

        ewb = EwbDtls.objects.filter(sales_return=order).first()
        if not ewb:
            raise ValidationError({"eway": "E-Way Bill details not found for this sales return."})

        distance = int(getattr(ewb, "Distance", 0) or 0)
        if distance <= 0:
            raise ValidationError({"eway": "Distance must be > 0."})

        payload = {
            "Irn": einv.irn,
            "Distance": distance,
            "TransMode": str(getattr(ewb, "TransMode", "") or ""),
            "TransId": (getattr(ewb, "TransId", "") or "").strip(),
            "TransName": (getattr(ewb, "TransName", "") or "").strip(),
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y") if getattr(ewb, "TransDocDt", None) else None,
            "TransDocNo": (getattr(ewb, "TransDocNo", "") or "").strip(),
            "VehNo": (getattr(ewb, "VehNo", "") or "").strip(),
            "VehType": (getattr(ewb, "VehType", "") or "").strip(),
        }

        resp = gst_ewaybill(order, payload)
        if isinstance(resp, dict) and str(resp.get("status_cd")) != "1":
            raise ValidationError({
                "eway": resp.get("status_desc") or "E-Way Bill generation failed.",
                "details": resp
            })
        return resp

    def _post_process_gst(self, order_id: int, mode: str, is_create: bool):
        """
        Runs AFTER DB commit.
        Updates header flags based on outcome.
        Stores ERR status in EInvoiceDetails if GST fails.
        """
        order = salereturn.objects.get(id=order_id)
        ct = self._ct_for(order)

        try:
            if mode == "none":
                return

            if mode == "einvoice":
                self._generate_einvoice_if_needed(order, mode, ct)
                salereturn.objects.filter(id=order.id).update(einvoice=True, eway=False)
                return

            if mode == "eway":
                if is_create:
                    return  # same as your invoice serializer choice
                self._generate_eway_from_irn(order, ct)
                salereturn.objects.filter(id=order.id).update(eway=True)
                return

            if mode == "both":
                self._generate_einvoice_if_needed(order, mode, ct)
                salereturn.objects.filter(id=order.id).update(einvoice=True)
                self._generate_eway_from_irn(order, ct)
                salereturn.objects.filter(id=order.id).update(eway=True)
                return

        except Exception as e:
            logger.exception("GST failed sales_return_id=%s mode=%s", order.id, mode)

            updates = {}
            if mode in ("einvoice", "both"):
                updates["einvoice"] = False
            if mode in ("eway", "both"):
                updates["eway"] = False
            if updates:
                salereturn.objects.filter(id=order.id).update(**updates)

            EInvoiceDetails.objects.filter(content_type=ct, object_id=order.id).update(
                status="ERR",
                remarks=str(e),
            )
            return

    # ===== numbering ==========================================================

    def _number_and_create_header(self, validated_data) -> salereturn:
        validated_data.pop('voucherno', None)
        validated_data.pop('invoicenumber', None)

        settings = (SalesInvoiceSettings.objects
                    .select_for_update()
                    .filter(entity=validated_data['entity'].id,
                            entityfinid=validated_data['entityfinid'].id,
                            doctype__doccode='1005')  # keep your SR doccode
                    .first())
        if not settings:
            raise ValidationError({"settings": "SalesInvoiceSettings not configured for this entity/financial year."})

        reset_counter_if_needed(settings)
        number = build_document_number(settings)
        if salereturn.objects.filter(invoicenumber=number).exists():
            raise ValidationError({"invoicenumber": "Duplicate invoice number generated. Please try again."})

        # voucherno retry (unique-ish)
        for _ in range(3):
            max_vno = (salereturn.objects
                       .filter(entity=validated_data['entity'])
                       .aggregate(m=Max('voucherno'))['m'] or 0)
            next_vno = max_vno + 1
            try:
                order = salereturn.objects.create(**validated_data, voucherno=next_vno, invoicenumber=number)
                settings.current_number += 1
                settings.save()
                return order
            except IntegrityError:
                continue

        raise ValidationError({"voucherno": "Unable to generate unique voucherno after retries. Please try again."})

    # ===== CREATE / UPDATE ====================================================

    @transaction.atomic
    def create(self, validated_data):
        details_data    = validated_data.pop('salereturndetails', [])
        adddetails_data = validated_data.pop('adddetails', {}) or {}

        # enforce header/detail IGST rules (same as validate)
        validated_data["salereturndetails"] = details_data
        self._enforce_igst_bucket(validated_data)
        validated_data.pop("salereturndetails", None)

        mode = _mode_from_invoice_mode(validated_data)

        order = self._number_and_create_header(validated_data)

        self._upsert_adddetails(order, adddetails_data, is_update=False)
        self._upsert_details(order, details_data, is_update=False)

        # single authoritative posting
        self._post_once_via_shim(order, entrytype='I')

        # GST after-commit
        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(order.id, mode=mode, is_create=True)
            )

        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        details_data    = validated_data.pop('salereturndetails', [])
        adddetails_data = validated_data.pop('adddetails', {}) or {}

        # enforce header/detail IGST rules (same as validate)
        validated_data["salereturndetails"] = details_data
        self._enforce_igst_bucket(validated_data)
        validated_data.pop("salereturndetails", None)

        touched = []
        for f in self._header_update_fields():
            if f in validated_data:
                setattr(instance, f, validated_data[f])
                touched.append(f)

        if touched:
            instance.save(update_fields=list(set(touched)))

        mode = _mode_from_invoice_mode(validated_data) if "invoiceMode" in validated_data else _mode_from_invoice_mode(instance)

        self._upsert_adddetails(instance, adddetails_data, is_update=True)
        self._upsert_details(instance, details_data, is_update=True)

        # single authoritative posting
        self._post_once_via_shim(instance, entrytype='U')

        # GST after-commit
        if mode != "none":
            transaction.on_commit(
                lambda: self._post_process_gst(instance.id, mode=mode, is_create=False)
            )

        return instance




class tdsVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = journalmain
        fields =  ['newvoucher']


class debitcreditnoteSerializer(serializers.ModelSerializer):

    

    class Meta:
        model = debitcreditnote
        fields =('id','voucherdate','voucherno','debitaccount','creditaccount','detail','ledgereffect','product','quantity','rate','basicvalue','cndnamount','tdssection','vouchertype','entityfinid','entity','createdby','isactive',)

    def create(self, validated_data):
        #print(validated_data)
        #journaldetails_data = validated_data.pop('journaldetails')
        

        validated_data.pop('voucherno')

        if debitcreditnote.objects.filter(entity= validated_data['entity'].id,vouchertype= validated_data['vouchertype']).count() == 0:
            billno2 = 1
        else:
            billno2 = (debitcreditnote.objects.filter(entity= validated_data['entity'].id,vouchertype= validated_data['vouchertype']).last().voucherno) + 1
        detail = debitcreditnote.objects.create(**validated_data,voucherno = billno2)
        entryid,created  = entry.objects.get_or_create(entrydate1 = detail.voucherdate,entity=detail.entity)

        if validated_data['ledgereffect']:

            if validated_data['vouchertype'] == 'CN':
                desc = 'Credit Note'
            else:
                desc = 'Debit Note'




            StockTransactions.objects.create(accounthead= detail.debitaccount.accounthead,account= detail.debitaccount,transactiontype = validated_data['vouchertype'],transactionid = detail.id,desc =desc + ' ' + str(detail.voucherno),drcr=0,debitamount=detail.cndnamount,entity=detail.entity,createdby= detail.createdby,entry =entryid,entrydatetime = detail.voucherdate,accounttype = 'M',voucherno = detail.voucherno)
            StockTransactions.objects.create(accounthead= detail.creditaccount.accounthead,account= detail.creditaccount,transactiontype = validated_data['vouchertype'],transactionid = detail.id,desc = desc + ' ' + str(detail.voucherno),drcr=1,creditamount=detail.cndnamount,entity=detail.entity,createdby= detail.createdby,entry =entryid,entrydatetime = detail.voucherdate,accounttype = 'M',voucherno = detail.voucherno)

        # if detail.openingbcr > 0 or detail.openingbdr > 0:
        #     if (detail.openingbcr >0.00):
        #             drcr = 0
        #     else:
        #             drcr = 1
        #     details = StockTransactions.objects.create(accounthead= detail.accounthead,account= detail,transactiontype = 'OA',transactionid = detail.id,desc = 'Opening Balance',drcr=drcr,debitamount=detail.openingbdr,creditamount=detail.openingbcr,entity=detail.entity,createdby= detail.owner,entry = entryid,entrydatetime = detail.created_at,accounttype = 'M',isactive = 1)
        #     #return detail
        return detail

    def update(self, instance, validated_data):

        print('abc')
        fields = ['voucherdate','voucherno','debitaccount','creditaccount','detail','ledgereffect','product','quantity','rate','basicvalue','cndnamount','tdssection','vouchertype','entityfinid','entity','createdby','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        # with transaction.atomic():
        instance.save()
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.created_at,entity=instance.entity)
        #     entryid,created  = entry.objects.get_or_create(entrydate1 = instance.voucherdate,entity=instance.entityid)
       # StockTransactions.objects.filter(entity = instance.entity,transactionid = instance.id,transactiontype = 'OA').delete()

        # drcr = 0

        # if instance.openingbcr is None:
        #     instance.openingbcr = 0
        
        # if instance.openingbdr is None:
        #     instance.openingbdr = 0
            

        # if instance.openingbcr > 0:
        #     drcr = 0
        #     StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)
        # if instance.openingbdr > 0:
        #     drcr = 1
        #     StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)



        
        #details = StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)
        #     StockTransactions.objects.create(accounthead= instance.creditaccountid.accounthead,account= instance.creditaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=1,debitamount=instance.grandtotal,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')
        #     StockTransactions.objects.create(accounthead= instance.debitaccountid.accounthead,account= instance.debitaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=1,debitamount=instance.debitamount,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')
        #     StockTransactions.objects.create(accounthead= instance.tdsaccountid.accounthead,account= instance.tdsaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=0,creditamount=instance.grandtotal,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')

        return instance
        

class dcnoSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    voucherno = serializers.SerializerMethodField()

    def get_voucherno(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1


    class Meta:
        model = debitcreditnote
        fields =  ['voucherno']


class debitcreditcancelSerializer(serializers.ModelSerializer):

    class Meta:
        model = debitcreditnote
        fields = ('isactive',)

    
    def update(self, instance, validated_data):

        fields = ['isactive','createdby',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        instance.save()
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.voucherdate,entity=instance.entity)
        StockTransactions.objects.filter(entity = instance.entity,transactionid = instance.id,transactiontype = instance.vouchertype).update(isactive = instance.isactive)
        return instance
    

class profitserilizer(serializers.ModelSerializer):

    balance = serializers.DecimalField(write_only=True,max_digits=10,decimal_places=2)

    class Meta:
        model = StockTransactions
        fields  = ('accounthead','account','stock','transactiontype','transactionid','desc','stockttype','quantity','rate','drcr','debitamount','creditamount','entry','entrydate','entrydatetime','accounttype','balance',)


class stockserilizer(serializers.ModelSerializer):

    balance = serializers.DecimalField(write_only=True,max_digits=10,decimal_places=2)

    #balance = serializers.DecimalField(write_only=True,max_digits=10,decimal_places=2)

    class Meta:
        model = StockTransactions
        fields  = ('accounthead','account','stock','transactiontype','transactionid','desc','stockttype','quantity','rate','drcr','debitamount','creditamount','entry','entrydate','entrydatetime','accounttype','balance',)
    

class StockTransactionsserilizer(serializers.ModelSerializer):

    updatedaccount = serializers.IntegerField(write_only=True)

    class Meta:
        model = StockTransactions
        fields  = ('accounthead','account','stock','transactiontype','transactionid','desc','stockttype','quantity','rate','drcr','debitamount','creditamount','entry','entrydate','entrydatetime','accounttype','updatedaccount',)

class closingstockSerializer(serializers.ModelSerializer):

    

    class Meta:
        model = closingstock
        fields  = ('stockdate','stock','closingrate','entity',)


class entityfinancialyearSerializer(serializers.ModelSerializer):


    entityname = serializers.SerializerMethodField()
    gst = serializers.SerializerMethodField()

    class Meta:
        model = entityfinancialyear
        fields = ('id','entity','entityname','gst','desc','finstartyear','finendyear','createdby','isactive',)


    
    def get_entityname(self,obj):
         
        return obj.entity.entityName
    

    def get_gst(self,obj):
         
        return obj.entity.gstno



    def create(self, validated_data):


        r1 = entityfinancialyear.objects.filter(entity= validated_data['entity'].id).update(isactive=0)



        #entity= validated_data['entity'].id

        fy = entityfinancialyear.objects.create(**validated_data)


        return fy


class balancesheetclosingserializer(serializers.ModelSerializer):
    cashtrans = StockTransactionsserilizer(many=True)
    stocktrans = stockserilizer(many=True,write_only = True)

    profittrans = profitserilizer(many=True,write_only = True)
    startdate = serializers.DateField(write_only=True)
    enddate = serializers.DateField(write_only=True)
    
    #closingdate = serializers.DateField(source = 'entrydate1')
    class Meta:
        model = entry
        fields  = ('entrydate1','entity','cashtrans','startdate','enddate','stocktrans','profittrans',)


    def create(self, validated_data):

        entityfinancialyear.objects.filter(entity= validated_data['entity'].id).update(isactive=0)
        entityfinancialyear.objects.create(entity = validated_data['entity'],finstartyear = validated_data['startdate'],finendyear = validated_data['enddate'],createdby = validated_data['createdby'])


        print(validated_data)

        entryid,created  = entry.objects.get_or_create(entrydate1 = validated_data['entrydate1'],entity=validated_data['entity'])
        #entrydate = validated_data['entrydate1'] + timedelta(days = 1)
        entryid2,created  = entry.objects.get_or_create(entrydate1 = validated_data['startdate'],entity=validated_data['entity'])
        cashtrans_data = validated_data.pop('cashtrans')
        stockrans_data = validated_data.pop('stocktrans')
        profittrans_data = validated_data.pop('profittrans')
        for cashtrans in cashtrans_data:

            print(cashtrans)
            des = 'balance closing '
            des2 = 'Opening Balance'

            if cashtrans['accounttype'] == '3':
                aactype = 'M'
                bs = 1
            else:
                aactype = 'MD'
                bs = 1



            if cashtrans['drcr'] == 1:
                StockTransactions.objects.create(entry = entryid, drcr = 0,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = cashtrans['account'],debitamount = 0,creditamount = cashtrans['debitamount'],accounttype = aactype,transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des,isbalancesheet = 0)
                if cashtrans['accounttype'] == '3':
                    acc = account.objects.get(id = cashtrans['updatedaccount'])
                   
                    StockTransactions.objects.create(entry = entryid2, drcr = 1,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = acc,debitamount = cashtrans['debitamount'],creditamount = 0,accounttype = aactype,transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2)
            
            if cashtrans['drcr'] == 0:
                StockTransactions.objects.create(entry = entryid, drcr = 1,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = cashtrans['account'],debitamount = cashtrans['creditamount'],creditamount = 0,accounttype = aactype,transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des,isbalancesheet = 0)
                if cashtrans['accounttype'] == '3':
                    acc = account.objects.get(id = cashtrans['updatedaccount'])
                    StockTransactions.objects.create(entry = entryid2, drcr = 0,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = acc,debitamount = 0,creditamount = cashtrans['creditamount'],accounttype = aactype,transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2)

        acc = account.objects.get(accountcode = 9000,entity= validated_data['entity'].id)
        acchead = accountHead.objects.get(code = 9000,entity= validated_data['entity'].id)

        acccloose = account.objects.get(accountcode = 200,entity= validated_data['entity'].id)
        accheadclose = accountHead.objects.get(code = 200,entity= validated_data['entity'].id)

        #print(cashtrans)
        des = 'balance closing '
        des2 = 'Opening Balance'

        for cashtrans in stockrans_data:

            

            # if cashtrans['drcr'] == 1:
            StockTransactions.objects.create(entry = entryid, drcr = 0,entity=validated_data['entity'],accounthead = accheadclose,account = acccloose,accounttype = 'DD',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des,quantity = cashtrans['quantity'],stock =cashtrans['stock'],stockttype = 'I',rate = cashtrans['rate'],debitamount = 0 ,creditamount = cashtrans['balance'],isbalancesheet = 0)
            StockTransactions.objects.create(entry = entryid2, drcr = 1,entity=validated_data['entity'],accounthead = acchead,account = acc,accounttype = 'DD',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2,quantity = cashtrans['quantity'],stock= cashtrans['stock'],stockttype = 'R',rate = cashtrans['rate'],debitamount = cashtrans['balance'],creditamount = 0)
            
            # if cashtrans['drcr'] == 0:
            #     StockTransactions.objects.create(entry = entryid, drcr = 1,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = cashtrans['account'],debitamount = cashtrans['creditamount'],creditamount = 0,accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des)
            #     if cashtrans['accounttype'] == '3':
            #         acc = account.objects.get(id = cashtrans['updatedaccount'])
            #         StockTransactions.objects.create(entry = entryid2, drcr = 0,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account = acc,debitamount = 0,creditamount = cashtrans['creditamount'],accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2)

        for cashtrans in profittrans_data:

            

            if cashtrans['drcr'] == 1:
                StockTransactions.objects.create(entry = entryid, drcr = 0,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account =  cashtrans['account'],accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des,debitamount = cashtrans['balance'],creditamount = 0,isbalancesheet = 0)
                StockTransactions.objects.create(entry = entryid2, drcr = 1,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account =  cashtrans['account'],accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2,debitamount = 0,creditamount = cashtrans['balance'])
            else:
                StockTransactions.objects.create(entry = entryid, drcr = 0,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account =  cashtrans['account'],accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['entrydate1'],desc = des,debitamount = 0 ,creditamount = cashtrans['balance'],isbalancesheet = 0)
                StockTransactions.objects.create(entry = entryid2, drcr = 1,entity=validated_data['entity'],accounthead = cashtrans['accounthead'],account =  cashtrans['account'],accounttype = 'M',transactionid = -1,createdby = validated_data['createdby'],entrydatetime = validated_data['startdate'],desc = des2,debitamount = cashtrans['balance'],creditamount = 0)

                


        return entryid


class SalesOrderGSTSummarySerializer(serializers.Serializer):
    salesorderheader = serializers.IntegerField()
    product_cgst_percent = serializers.DecimalField(max_digits=14, decimal_places=2)
    product_sgst_percent = serializers.DecimalField(max_digits=14, decimal_places=2)
    product_igst_percent = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_cgst_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_sgst_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_igst_amount = serializers.DecimalField(max_digits=14, decimal_places=4)

    @staticmethod
    def get_aggregated_data(salesorderheader_id):
        """
        Fetch aggregated GST amounts grouped by percentages and sales order header.
        """
        aggregated_data = (
            salesOrderdetails.objects.filter(salesorderheader_id=salesorderheader_id)
            .select_related("product")  # Fetch related product data efficiently
            .values("salesorderheader")  # Group by sales order header
            .annotate(
                product_cgst_percent=F("product__cgst"),  # Rename product__cgst
                product_sgst_percent=F("product__sgst"),  # Rename product__sgst
                product_igst_percent=F("product__igst"),  # Rename product__igst
                total_cgst_amount=Sum("cgst", filter=Q(product__cgst__isnull=False)),
                total_sgst_amount=Sum("sgst", filter=Q(product__sgst__isnull=False)),
                total_igst_amount=Sum("igst", filter=Q(product__igst__isnull=False)),
            )
        )
        return aggregated_data



# Serializers

class PurchaseOrderDetailsSerializergst(serializers.ModelSerializer):
    gstrate = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    linetotal = serializers.DecimalField(max_digits=14, decimal_places=4)
    cess = serializers.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        model = PurchaseOrderDetails
        fields = ['gstrate', 'amount', 'linetotal','cess']

    def get_gstrate(self, obj):
        if obj.isigst:
            return obj.igstpercent or 0
        return (obj.cgstpercent or 0) + (obj.sgstpercent or 0)
    
class PurchaseOrderHeaderSerializer(serializers.ModelSerializer):
    gstno = serializers.CharField(source='entity.gstno', required=False)
    recivername = serializers.CharField(source='account.accountname', required=False)
    ecomgstno = serializers.CharField(source='ecom.gstno', required=False)
    billno = serializers.IntegerField()
    billdate = serializers.DateTimeField(format='%d-%m-%Y')
    statecode = serializers.CharField(source='account.state.statecode', required=False)
    reversecharge = serializers.BooleanField()
    invoicetype = serializers.CharField(source='invoicetype.invoicetype', required=False)
    apptaxrate = serializers.DecimalField(max_digits=4, decimal_places=2)
    
    purchase_details = PurchaseOrderDetailsSerializergst(source='purchaseInvoiceDetails', many=True)

    class Meta:
        model = purchaseorder
        fields = ['gstno', 'recivername', 'billno', 'billdate', 'statecode','ecomgstno','reversecharge', 'invoicetype', 'purchase_details','apptaxrate']

class SalesOrderDetailsSerializer(serializers.ModelSerializer):
    gstrate = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    linetotal = serializers.DecimalField(max_digits=14, decimal_places=4)
    cess = serializers.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        model = salesOrderdetails
        fields = ['gstrate', 'amount', 'linetotal','cess']

    def get_gstrate(self, obj):
        if obj.isigst:
            return obj.igstpercent or 0
        return (obj.cgstpercent or 0) + (obj.sgstpercent or 0)

class SalesOrderHeaderSerializer(serializers.ModelSerializer):
    gstno = serializers.CharField(source='accountid.gstno', required=False)
    ecomgstno = serializers.CharField(source='ecom.gstno', required=False)
    recivername = serializers.CharField(source='accountid.accountname', required=False)
    billno = serializers.IntegerField()
    sorderdate = serializers.DateTimeField(format='%d-%m-%Y')
    statecode = serializers.CharField(source='accountid.state.statecode', required=False)
    reversecharge = serializers.BooleanField()
    invoicetype = serializers.CharField(source='invoicetype.invoicetype', required=False)
    apptaxrate = serializers.DecimalField(max_digits=4, decimal_places=2)
    sales_details = SalesOrderDetailsSerializer(source='saleInvoiceDetails', many=True)

    class Meta:
        model = SalesOderHeader
        fields = ['gstno', 'recivername', 'billno', 'sorderdate', 'statecode', 'reversecharge','ecomgstno','invoicetype', 'sales_details','apptaxrate']






class PurchaseReturnDetailsSerializergst(serializers.ModelSerializer):
    gstrate = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    linetotal = serializers.DecimalField(max_digits=14, decimal_places=4)
    cess = serializers.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        model = Purchasereturndetails
        fields = ['gstrate', 'amount', 'linetotal','cess']

    def get_gstrate(self, obj):
        if obj.isigst:
            return obj.igstpercent or 0
        return (obj.cgstpercent or 0) + (obj.sgstpercent or 0)
    
class PurchaseReturnSerializer(serializers.ModelSerializer):
    gstno = serializers.CharField(source='accountid.gstno', required=False)
    recivername = serializers.CharField(source='accountid.accountname', required=False)
    ecomgstno = serializers.CharField(source='ecom.gstno', required=False)
    voucherno = serializers.IntegerField(source='billno', required=False)
    sorderdate = serializers.DateTimeField(format='%d-%m-%Y')
    statecode = serializers.CharField(source='accountid.state.statecode', required=False)
    reversecharge = serializers.BooleanField()
    invoicetype = serializers.CharField(source='invoicetype.invoicetype', required=False)
    apptaxrate = serializers.DecimalField(max_digits=4, decimal_places=2)
    
    purchase_details = PurchaseReturnDetailsSerializergst(source='purchasereturndetails', many=True)

    class Meta:
        model = PurchaseReturn
        fields = ['gstno', 'recivername', 'voucherno', 'sorderdate', 'statecode','ecomgstno','reversecharge', 'invoicetype', 'purchase_details','apptaxrate']


class SalesReturnDetailsSerializer(serializers.ModelSerializer):
    gstrate = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    linetotal = serializers.DecimalField(max_digits=14, decimal_places=4)
    cess = serializers.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        model =  salereturnDetails
        fields = ['gstrate', 'amount', 'linetotal','cess']

    def get_gstrate(self, obj):
        if obj.isigst:
            return obj.igstpercent or 0
        return (obj.cgstpercent or 0) + (obj.sgstpercent or 0)

class SalesReturnSerializer(serializers.ModelSerializer):
    gstno = serializers.CharField(source='account.gstno', required=False)
    ecomgstno = serializers.CharField(source='ecom.gstno', required=False)
    recivername = serializers.CharField(source='account.accountname', required=False)
    voucherno = serializers.IntegerField()
    billdate = serializers.DateTimeField(format='%d-%m-%Y')
    statecode = serializers.CharField(source='account.state.statecode', required=False)
    reversecharge = serializers.BooleanField()
    invoicetype = serializers.CharField(source='invoicetype.invoicetype', required=False)
    apptaxrate = serializers.DecimalField(max_digits=4, decimal_places=2)
    sales_details = SalesReturnDetailsSerializer(source='salereturndetails', many=True)

    class Meta:
        model = salereturn
        fields = ['gstno', 'recivername', 'voucherno', 'billdate', 'statecode', 'reversecharge','ecomgstno','invoicetype', 'sales_details','apptaxrate']
  
class SalesOrderDetailSerializerB2C(serializers.Serializer):
    invoicenumber = serializers.IntegerField(source="salesorderheader__billno")
    invoicedate = serializers.SerializerMethodField()  # Custom method for date conversion
    invoicevalue = serializers.DecimalField(max_digits=14, decimal_places=4)
    pos = serializers.CharField(source="salesorderheader__accountid__state__statecode", allow_blank=True)
    apptaxrate = serializers.DecimalField(max_digits=14, decimal_places=4,source="salesorderheader__apptaxrate")
    gstrate = serializers.SerializerMethodField()
    taxablevalue = serializers.DecimalField(max_digits=14, decimal_places=4)
    cess = serializers.DecimalField(max_digits=14, decimal_places=4)
    ecomgstin = serializers.CharField(source="salesorderheader__ecom__gstno", allow_blank=True)

    def get_invoicedate(self, obj):
        """Convert datetime to date format `DD-MM-YYYY`."""
        return obj["salesorderheader__sorderdate"].date().strftime("%d-%m-%Y") if obj["salesorderheader__sorderdate"] else None

    def get_gstrate(self, obj):
        """Calculate GST rate based on `isigst`."""
        if obj["isigst"]:
            return obj["igstpercent"]
        return (obj.get("cgstpercent", 0) or 0) + (obj.get("sgstpercent", 0) or 0)


class SalesOrderDetailsSerializerHSN(serializers.ModelSerializer):
    hsn_code = serializers.CharField(source="product.hsn.hsnCode", read_only=True)
    product_desc = serializers.CharField(source="productdesc", read_only=True)
    unit_code = serializers.CharField(source="product.unitofmeasurement.unitcode", read_only=True)
    
    class Meta:
        model = salesOrderdetails
        fields = [
            'hsn_code',
            'product_desc',
            'unit_code'
        ]

class SalesOrderAggregateSerializer(serializers.Serializer):
    hsn_code = serializers.CharField()
    product_desc = serializers.CharField()
    unit_code = serializers.CharField()
    total_order_qty = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_pieces = serializers.IntegerField()
    total_line_total = serializers.DecimalField(max_digits=14, decimal_places=4)
    gst_rate = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_igst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_sgst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cgst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cess = serializers.DecimalField(max_digits=14, decimal_places=4)



class SalesOrderSummarySerializer(serializers.Serializer):
    hsnCode = serializers.CharField()
    productdesc = serializers.CharField()
    unitcode = serializers.CharField()
    total_orderqty = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_linetotal = serializers.DecimalField(max_digits=14, decimal_places=4)
    gstrate = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_igst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_sgst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cgst = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cess = serializers.DecimalField(max_digits=14, decimal_places=4)



class SalesOrderDetailsSerializerbyhsn(serializers.ModelSerializer):
    class Meta:
        model = salesOrderdetails
        fields = '__all__'


class SalesOrderAggregateSerializersummary(serializers.Serializer):
    salesorderheader__billno = serializers.CharField()
    salesorderheader__sorderdate = serializers.DateField()
    salesorderheader__accountid__state__statecode = serializers.CharField()
    salesorderheader__apptaxrate = serializers.FloatField()
    salesorderheader__ecom__gstno = serializers.CharField(allow_null=True, required=False)
    cgstpercent = serializers.FloatField()
    sgstpercent = serializers.FloatField()
    igstpercent = serializers.FloatField()
    isigst = serializers.BooleanField()
    amount = serializers.FloatField()
    linetotal = serializers.FloatField()
    cess = serializers.FloatField()


class EntitySerializer(serializers.ModelSerializer):
    state_code = serializers.CharField(source="state.statecode", read_only=True)
    city_name = serializers.CharField(source="city.cityname", read_only=True)
    pincode = serializers.CharField(source="city.pincode", read_only=True)

    class Meta:
        model = Entity
        fields = ["legalname", "entityname", "address", "address2", "state_code", "city_name", "pincode"]


class AccountSerializer(serializers.ModelSerializer):
    state_code = serializers.CharField(source="state.statecode", read_only=True)
    city_name = serializers.CharField(source="city.cityname", read_only=True)
    pincode = serializers.CharField(source="city.pincode", read_only=True)

    class Meta:
        model = account
        fields = ["gstno", "legalname", "accountname", "address1", "address2", "state_code", "city_name", "pincode"]


class SalesOrdereinvoiceSerializer(serializers.ModelSerializer):
    seller = serializers.SerializerMethodField()
    buyer = serializers.SerializerMethodField()

    class Meta:
        model = SalesOderHeader
        fields = ["billno", "seller", "buyer"]

    def get_seller(self, obj):
        """Format Seller Details"""
        entity = obj.entity
        return {
            "Gstin": entity.legalname,  # Assuming Gstin = legalname
            "LglNm": entity.legalname,
            "TrdNm": entity.entityname,
            "Addr1": entity.address,
            "Addr2": entity.address2,
            "Loc": entity.city.cityname if entity.city else "",
            "Pin": entity.city.pincode if entity.city else "",
            "Stcd": entity.state.statecode if entity.state else ""
        }

    def get_buyer(self, obj):
        """Format Buyer Details"""
        account = obj.accountid
        return {
            "Gstin": account.gstno,
            "LglNm": account.legalname,
            "TrdNm": account.accountname,
            "Addr1": account.address1,
            "Addr2": account.address2,
            "Loc": account.city.cityname if account.city else "",
            "Pin": account.city.pincode if account.city else "",
            "Stcd": account.state.statecode if account.state else ""
        }


    # Sales Order Item Serializer


class EWayBillItemSerializer(serializers.Serializer):
    productName = serializers.CharField(source='productdesc')
    productDesc = serializers.CharField(source='productdesc')
    hsnCode = serializers.SerializerMethodField()
    quantity = serializers.DecimalField(source='orderqty', max_digits=14, decimal_places=4)
    qtyUnit = serializers.SerializerMethodField()
    taxableAmount = serializers.DecimalField(source='amount', max_digits=14, decimal_places=2)
    sgstRate = serializers.DecimalField(source='sgstpercent', max_digits=14, decimal_places=2)
    cgstRate = serializers.DecimalField(source='cgstpercent', max_digits=14, decimal_places=2)
    igstRate = serializers.DecimalField(source='igstpercent', max_digits=14, decimal_places=2)
    cessRate = serializers.DecimalField(source='cess', max_digits=14, decimal_places=2)

    def get_hsnCode(self, obj):
        return int(obj.product.hsn.hsnCode) if obj.product and obj.product.hsn else None

    def get_qtyUnit(self, obj):
        return obj.product.unitofmeasurement.unitcode if obj.product and obj.product.unitofmeasurement else None


class EwaybillFullSerializer(serializers.ModelSerializer):
    ewaybill_payload = serializers.SerializerMethodField()

    class Meta:
        model = SalesOderHeader
        fields = [
            # Add any other fields as needed
            'ewaybill_payload',
        ]

    def get_ewaybill_payload(self, obj):
        entity = obj.entity
        account = obj.accountid
        dispatch = obj.subentity
        ship = obj.shippedto
        ewbdtls = getattr(obj, 'ewbdtls', None)
        items = obj.saleInvoiceDetails.all()

        payload = {
            "supplyType": "O",
            "subSupplyType": "1",
            "subSupplyDesc": " ",
            "docType": "INV",
            "docNo": obj.invoicenumber,
            "docDate": obj.sorderdate.strftime("%d/%m/%Y") if obj.sorderdate else None,

            # FROM party
            "fromGstin": entity.gstno,
            "fromTrdName": entity.entityname,
            "fromAddr1": entity.address,
            "fromAddr2": entity.address2,
            "fromPlace": entity.city.cityname if entity.city else None,
            "fromPincode": int(entity.city.pincode) if entity.city and entity.city.pincode else None,
            "fromStateCode": int(entity.state.statecode) if entity.state and entity.state.statecode else None,
            "actFromStateCode": int(entity.state.statecode) if entity.state and entity.state.statecode else None,

            # TO party
            "toGstin": account.gstno,
            "toTrdName": account.accountname,
            "toAddr1": account.address1,
            "toAddr2": account.address2,
            "toPlace": account.city.cityname if account.city else None,
            "toPincode": int(account.city.pincode) if account.city and account.city.pincode else None,
            "toStateCode": int(account.state.statecode) if account.state and account.state.statecode else None,
            "actToStateCode": int(account.state.statecode) if account.state and account.state.statecode else None,
            "transactionType": 1,

            # Dispatch / Ship
            # "dispatchFromGSTIN": dispatch.gstno if dispatch else entity.gstno,
            # "dispatchFromTradeName": dispatch.subentityname if dispatch else entity.entityname,
            # "shipToGSTIN": ship.gstno if ship else account.gstno,
            # "shipToTradeName": ship.full_name if ship else account.accountname,

            # Totals
            "totalValue": float(obj.stbefdiscount or 0),
            "cgstValue": float(obj.cgst or 0),
            "sgstValue": float(obj.sgst or 0),
            "igstValue": float(obj.igst or 0),
            "cessValue": float(obj.cess or 0),
            "cessNonAdvolValue": 0,
            "totInvValue": float(obj.gtotal or 0),

            # Transport
            "transMode": ewbdtls.TransMode if ewbdtls else "1",
            "transDistance": str(ewbdtls.Distance if ewbdtls else 1),
            "transporterId": ewbdtls.TransId if ewbdtls else "",
            "transporterName": ewbdtls.TransName if ewbdtls else "",
            "transDocNo": ewbdtls.TransDocNo if ewbdtls else "",
            "transDocDate": ewbdtls.TransDocDt.strftime("%d/%m/%Y") if ewbdtls and ewbdtls.TransDocDt else "",
            "vehicleNo": ewbdtls.VehNo if ewbdtls else "",
            "vehicleType": ewbdtls.VehType if ewbdtls else "R",

            # Items
            "itemList": EWayBillItemSerializer(items, many=True).data
        }

        return payload



class SalesOrderItemSerializer(serializers.ModelSerializer):
    SlNo = serializers.SerializerMethodField()
    IsServc = serializers.SerializerMethodField()
    PrdDesc = serializers.SerializerMethodField()
    HsnCd = serializers.SerializerMethodField()
    Qty = serializers.SerializerMethodField()
    Unit = serializers.SerializerMethodField()
    UnitPrice = serializers.SerializerMethodField()
    TotAmt = serializers.SerializerMethodField()
    Discount = serializers.SerializerMethodField()
    PreTaxVal = serializers.SerializerMethodField()
    AssAmt = serializers.SerializerMethodField()
    GstRt = serializers.SerializerMethodField()
    SgstAmt = serializers.SerializerMethodField()
    IgstAmt = serializers.SerializerMethodField()
    CgstAmt = serializers.SerializerMethodField()
    CesAmt = serializers.SerializerMethodField()
    TotItemVal = serializers.SerializerMethodField()
    OrdLineRef = serializers.SerializerMethodField()

    class Meta:
        model = salesOrderdetails
        fields = [
            "SlNo", "IsServc", "PrdDesc", "HsnCd", "Qty", "Unit", "UnitPrice",
            "TotAmt", "Discount", "PreTaxVal", "AssAmt", "GstRt",
            "SgstAmt", "IgstAmt", "CgstAmt", "CesAmt", "TotItemVal", "OrdLineRef"
        ]

    # ---------------------------------------------------------------------
    # Optional fields (batch, attributes, barcode, etc.)
    # ---------------------------------------------------------------------
    def to_representation(self, instance):
        data = super().to_representation(instance)

        optional_fields = {
            "BchDtls": self.get_BchDtls(instance),
            "AttribDtls": self.get_AttribDtls(instance),
            "Barcde": getattr(instance, "barcode", None),
            "OrgCntry": getattr(instance, "org_country", None),
            "PrdSlNo": getattr(instance, "product_serial_no", None),
        }

        for key, value in optional_fields.items():
            if value is not None:
                data[key] = value

        return data

    def get_BchDtls(self, obj):
        batch = getattr(obj, "batch", None)
        if batch:
            return {
                "Nm": batch.batchcode,
                "Expdt": batch.expirydate.strftime("%d/%m/%Y") if batch.expirydate else None,
                "wrDt": batch.warehousedate.strftime("%d/%m/%Y") if batch.warehousedate else None,
            }
        return None

    def get_AttribDtls(self, obj):
        attrs = getattr(obj, "attributes", None)
        if attrs and hasattr(attrs, "all") and attrs.exists():
            return [{"Nm": attr.name, "Val": attr.value} for attr in attrs.all()]
        return None

    # ---------------------------------------------------------------------
    # Helpers for new GST/HSN structure (ProductGstRate / HsnSac)
    # ---------------------------------------------------------------------
    def _get_default_gst_rate(self, product):
        """
        Use prefetched product.gst_rates (from product__gst_rates__hsn)
        without extra DB hits.
        """
        rates_manager = getattr(product, "gst_rates", None)
        if not rates_manager:
            return None

        rates = list(rates_manager.all())
        if not rates:
            return None

        # Prefer default if flagged
        for r in rates:
            if getattr(r, "isdefault", False):
                return r

        # Fallback to first
        return rates[0]

    # ---------------------------------------------------------------------
    # Basic fields
    # ---------------------------------------------------------------------
    def get_SlNo(self, obj):
        return str(self.context.get("slno", 1))

    def get_IsServc(self, obj):
        product = getattr(obj, "product", None)
        if product is not None and hasattr(product, "is_service"):
            return "Y" if product.is_service else "N"
        # fallback to detail flag if you had one earlier
        if hasattr(obj, "isService"):
            return "Y" if obj.isService else "N"
        return "N"

    def get_PrdDesc(self, obj):
        # Prefer line description, else product name
        if getattr(obj, "productdesc", None):
            return obj.productdesc
        product = getattr(obj, "product", None)
        if product:
            return getattr(product, "productname", None)
        return None

    def get_HsnCd(self, obj):
        product = getattr(obj, "product", None)
        if not product:
            return None

        rate = self._get_default_gst_rate(product)
        if not rate or not rate.hsn:
            return None

        # new HsnSac.code
        return rate.hsn.code

    def get_Qty(self, obj):
        return float(obj.orderqty or 0)

    def get_Unit(self, obj):
        """
        Use Product.base_uom from new model.
        Tries common field names: code / unitcode / name / symbol.
        """
        product = getattr(obj, "product", None)
        if not product:
            return None
        uom = getattr(product, "base_uom", None)
        if not uom:
            return None

        for attr in ("code", "unitcode", "name", "symbol"):
            if hasattr(uom, attr):
                return getattr(uom, attr)
        return None

    def get_UnitPrice(self, obj):
        return float(obj.rate or 0)

    def get_TotAmt(self, obj):
        # value before discount
        return float(obj.befDiscountProductAmount or 0)

    def get_Discount(self, obj):
        return float(obj.orderDiscountValue or 0)

    def get_PreTaxVal(self, obj):
        # value after discount, before tax
        return float(obj.amount or 0)

    def get_AssAmt(self, obj):
        # assessable amount (usually same as PreTaxVal in your logic)
        return float(obj.amount or 0)

    def get_GstRt(self, obj):
        """
        Total GST rate: IGST if isigst, else CGST+SGST.
        Uses line-level percentages (already computed and stored).
        """
        if getattr(obj, "isigst", False):
            return float(obj.igstpercent or 0)
        return float((obj.cgstpercent or 0) + (obj.sgstpercent or 0))

    def get_SgstAmt(self, obj):
        return float(obj.sgst or 0)

    def get_IgstAmt(self, obj):
        return float(obj.igst or 0)

    def get_CgstAmt(self, obj):
        return float(obj.cgst or 0)

    def get_CesAmt(self, obj):
        return float(obj.cess or 0)

    def get_TotItemVal(self, obj):
        return float(obj.linetotal or 0)

    def get_OrdLineRef(self, obj):
        return str(obj.id or "")


   


  



# Sales Order Full Serializer (Including Seller, Buyer & Items)
class SalesOrderFullSerializer(serializers.ModelSerializer):
    TranDtls = serializers.SerializerMethodField()
    DocDtls = serializers.SerializerMethodField()
    SellerDtls = serializers.SerializerMethodField()
    BuyerDtls = serializers.SerializerMethodField()
    DispDtls = serializers.SerializerMethodField()
    ShipDtls = serializers.SerializerMethodField()
    ItemList = serializers.SerializerMethodField()
    ValDtls = serializers.SerializerMethodField()
    PayDtls = serializers.SerializerMethodField()
    RefDtls = serializers.SerializerMethodField()
    AddlDocDtls = serializers.SerializerMethodField()
    EwbDtls = serializers.SerializerMethodField()
    # ExpDtls = serializers.SerializerMethodField()

    class Meta:
        model = SalesOderHeader
        fields = [
            "TranDtls", "DocDtls", "SellerDtls", "BuyerDtls",
            "DispDtls", "ShipDtls", "ItemList", "ValDtls",
            "PayDtls", "RefDtls", "AddlDocDtls", "EwbDtls",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Remove keys with None values
        data = {k: v for k, v in data.items() if v is not None}

        final_data = {"Version": "1.1", **data}

        mode = self.context.get("mode", "both")

        if mode == "einvoice":
            final_data.pop("EwbDtls", None)
        elif mode == "eway":
            ewb = final_data.get("EwbDtls")
            final_data = {"Version": "1.1"}
            if ewb:
                final_data["EwbDtls"] = ewb
        elif mode == "none":
            final_data = {"Version": "1.1"}

        return final_data

    # --- Header-level structures (unchanged) ---

    def get_TranDtls(self, obj):
        return {
            "TaxSch": "GST",
            "SupTyp": obj.invoicetype.invoicetypecode if obj.invoicetype else None,
            "RegRev": "Y" if obj.reversecharge else "N",
            "EcmGstin": obj.ecom.gstno if getattr(obj, "ecom", None) else None,
            "IgstOnIntra": "Y" if obj.isigst else "N",
        }

    def get_DocDtls(self, obj):
        return {
            "Typ": "INV",
            "No": obj.invoicenumber,
            "Dt": obj.sorderdate.strftime("%d/%m/%Y") if obj.sorderdate else None,
        }

    def get_SellerDtls(self, obj):
        entity = obj.entity
        return {
            "Gstin": entity.gstno,
            "LglNm": entity.legalname,
            "TrdNm": entity.entityname,
            "Addr1": entity.address,
            "Addr2": entity.address2,
            "Loc": entity.city.cityname if entity.city else None,
            "Pin": int(entity.city.pincode) if entity.city and entity.city.pincode else None,
            "Stcd": entity.state.statecode if entity.state else None,
            "Ph": entity.phoneoffice,
            "Em": entity.email,
        }

    def get_BuyerDtls(self, obj):
        account = obj.accountid
        return {
            "Gstin": account.gstno,
            "LglNm": account.accountname,
            "TrdNm": account.accountname,
            "Pos": account.state.statecode if account.state else None,
            "Addr1": account.address1,
            "Addr2": account.address2,
            "Loc": account.city.cityname if account.city else None,
            "Pin": int(account.city.pincode) if account.city and account.city.pincode else None,
            "Stcd": account.state.statecode if account.state else None,
            "Ph": getattr(account, "phoneno", None),
            "Em": getattr(account, "emailid", None),
        }

    def get_DispDtls(self, obj):
        dispatch = obj.subentity
        return {
            "Nm": dispatch.subentityname if dispatch else None,
            "Addr1": dispatch.address if dispatch else None,
            "Addr2": dispatch.address if dispatch else None,
            "Loc": dispatch.city.cityname if dispatch and dispatch.city else None,
            "Pin": int(dispatch.pincode) if dispatch and dispatch.pincode else None,
            "Stcd": dispatch.state.statecode if dispatch and dispatch.state else None,
        }

    def get_ShipDtls(self, obj):
        shipping = obj.shippedto
        return {
            "Gstin": shipping.gstno if shipping else None,
            "LglNm": shipping.full_name if shipping else None,
            "TrdNm": shipping.full_name if shipping else None,
            "Addr1": shipping.address1 if shipping else None,
            "Addr2": shipping.address2 if shipping else None,
            "Loc": shipping.city.cityname if shipping and shipping.city else None,
            "Pin": int(shipping.pincode) if shipping and shipping.pincode else None,
            "Stcd": shipping.state.statecode if shipping and shipping.state else None,
        }

    def get_ItemList(self, obj):
        # Uses updated SalesOrderItemSerializer (new Product/GST model aware)
        return [
            SalesOrderItemSerializer(item, context={"slno": idx + 1}).data
            for idx, item in enumerate(obj.saleInvoiceDetails.all())
        ]

    def get_ValDtls(self, obj):
        return {
            "AssVal": obj.stbefdiscount,
            "CgstVal": obj.cgst,
            "SgstVal": obj.sgst,
            "IgstVal": obj.igst,
            "CesVal": obj.cess,
            "StCesVal": 0.0,
            "Discount": obj.discount,
            "OthChrg": obj.expenses,
            "RndOffAmt": obj.roundOff,
            "TotInvVal": obj.gtotal,
            "TotInvValFc": obj.gtotal,
        }

    def get_PayDtls(self, obj):
        pay = getattr(obj, "paydtls", None)
        if not pay:
            return None
        return {
            "Nm": pay.Nm,
            "FinInsBr": pay.FinInsBr,
            "PayTerm": pay.PayTerm,
            "PayInstr": pay.PayInstr,
            "CrTrn": pay.CrTrn,
            "DirDr": pay.DirDr,
            "CrDay": pay.CrDay,
            "PaidAmt": float(pay.PaidAmt) if pay.PaidAmt else None,
            "PayRefNo": pay.PayRefNo,
        }

    def get_RefDtls(self, obj):
        ref = getattr(obj, "refdtls", None)
        if not ref:
            return None
        return {
            "InvRm": ref.InvRm,
            "PrecDocDtls": [
                {
                    "InvNo": ref.PrecDocNo,
                    "InvDt": ref.PrecDocDt.strftime("%d/%m/%Y") if ref.PrecDocDt else None,
                }
            ] if ref.PrecDocNo else [],
            "ContrRefr": ref.ContrRefr,
        }

    def get_AddlDocDtls(self, obj):
        docs = getattr(obj, "addldocdtls", None)
        if not docs:
            return None
        qs = docs.all()
        if not qs:
            return None
        return [{"Url": d.Url, "Docs": d.Docs, "Info": d.Info} for d in qs]

    def get_EwbDtls(self, obj):
        ewb = getattr(obj, "ewbdtls", None)
        if not ewb:
            return None
        return {
            "TransId": ewb.TransId,
            "TransName": ewb.TransName,
            "Distance": int(ewb.Distance),
            "TransDocNo": ewb.TransDocNo,
            "TransMode": ewb.TransMode,
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y"),
            "VehNo": ewb.VehNo,
            "VehType": ewb.VehType,
        }

    # def get_ExpDtls(self, obj):
    #     exp = getattr(obj, 'expdtls', None)
    #     if not exp:
    #         return None
    #     return {
    #         "ShipBNo": exp.ShipBNo,
    #         "ShipBDt": exp.ShipBDt.strftime("%d/%m/%Y") if exp.ShipBDt else None,
    #         "Port": exp.Port,
    #         "RefClm": exp.RefClm,
    #         "ForCur": exp.ForCur,
    #         "CntryCd": exp.CntryCd,
    #         "ExpDuty": "Y" if exp.ExpDuty else "N"
    #     }


class PurchasereturnItemSerializer(serializers.ModelSerializer):
    SlNo = serializers.SerializerMethodField()
    IsServc = serializers.SerializerMethodField()
    PrdDesc = serializers.SerializerMethodField()
    HsnCd = serializers.SerializerMethodField()
    Qty = serializers.SerializerMethodField()
    Unit = serializers.SerializerMethodField()
    UnitPrice = serializers.SerializerMethodField()
    TotAmt = serializers.SerializerMethodField()
    Discount = serializers.SerializerMethodField()
    PreTaxVal = serializers.SerializerMethodField()
    AssAmt = serializers.SerializerMethodField()
    GstRt = serializers.SerializerMethodField()
    SgstAmt = serializers.SerializerMethodField()
    IgstAmt = serializers.SerializerMethodField()
    CgstAmt = serializers.SerializerMethodField()
    CesAmt = serializers.SerializerMethodField()
    TotItemVal = serializers.SerializerMethodField()
    OrdLineRef = serializers.SerializerMethodField()

    class Meta:
        model = Purchasereturndetails
        fields = [
            "SlNo", "IsServc", "PrdDesc", "HsnCd", "Qty", "Unit", "UnitPrice",
            "TotAmt", "Discount", "PreTaxVal", "AssAmt", "GstRt", "SgstAmt", "IgstAmt", "CgstAmt",
            "CesAmt", "TotItemVal", "OrdLineRef"
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        optional_fields = {
            "BchDtls": self.get_BchDtls(instance),
            "AttribDtls": self.get_AttribDtls(instance),
            "Barcde": instance.barcode if hasattr(instance, 'barcode') else None,
            "OrgCntry": instance.org_country if hasattr(instance, 'org_country') else None,
            "PrdSlNo": instance.product_serial_no if hasattr(instance, 'product_serial_no') else None,
        }
        for key, value in optional_fields.items():
            if value is not None:
                data[key] = value

        return data

    def get_BchDtls(self, obj):
        if hasattr(obj, 'batch') and obj.batch:
            return {
                "Nm": obj.batch.batchcode,
                "Expdt": obj.batch.expirydate.strftime("%d/%m/%Y") if obj.batch.expirydate else None,
                "wrDt": obj.batch.warehousedate.strftime("%d/%m/%Y") if obj.batch.warehousedate else None
            }
        return None

    def get_AttribDtls(self, obj):
        if hasattr(obj, 'attributes') and obj.attributes.exists():
            return [{"Nm": attr.name, "Val": attr.value} for attr in obj.attributes.all()]
        return None

    def get_SlNo(self, obj):
        return str(self.context.get('slno', 1))

    def get_IsServc(self, obj):
        return "N"

    def get_PrdDesc(self, obj):
        return obj.productdesc

    def get_HsnCd(self, obj):
        row = pick_active_gst_row(getattr(obj, "product", None))
        return row.hsn.code if (row and row.hsn) else None

    def get_Qty(self, obj):
        return "{0:.2f}".format(float(obj.orderqty or 0))

    def get_Unit(self, obj):
        return obj.product.base_uom.code if (obj.product and obj.product.base_uom) else None

    def get_UnitPrice(self, obj):
        return "{0:.2f}".format(float(obj.rate or 0))

    def get_TotAmt(self, obj):
        qty = float(obj.orderqty or 0)
        rate = float(obj.rate or 0)
        tot_amt = round(qty * rate, 2)
        return "{0:.2f}".format(tot_amt)

    def get_Discount(self, obj):
        return "0.00"

    def get_PreTaxVal(self, obj):
        return self.get_AssAmt(obj)

    def get_AssAmt(self, obj):
        qty = float(obj.orderqty or 0)
        rate = float(obj.rate or 0)
        ass_amt = round(qty * rate, 2)  # No discount, so ass_amt = tot_amt
        return "{0:.2f}".format(ass_amt)

    def get_GstRt(self, obj):
        return "{0:.2f}".format(float(obj.igstpercent if obj.isigst else (obj.cgstpercent or 0) + (obj.sgstpercent or 0)))

    def get_SgstAmt(self, obj):
        return "{0:.2f}".format(float(obj.sgst or 0))

    def get_IgstAmt(self, obj):
        return "{0:.2f}".format(float(obj.igst or 0))

    def get_CgstAmt(self, obj):
        return "{0:.2f}".format(float(obj.cgst or 0))

    def get_CesAmt(self, obj):
        return "{0:.2f}".format(float(obj.cess or 0))

    def get_TotItemVal(self, obj):
        return "{0:.2f}".format(float(obj.linetotal or 0))

    def get_OrdLineRef(self, obj):
        return str(obj.id or "")


    

# Sales Order Full Serializer (Including Seller, Buyer & Items)
class PurchasereturnFullSerializer(serializers.ModelSerializer):
    TranDtls = serializers.SerializerMethodField()
    DocDtls = serializers.SerializerMethodField()
    SellerDtls = serializers.SerializerMethodField()
    BuyerDtls = serializers.SerializerMethodField()
    DispDtls = serializers.SerializerMethodField()
    ShipDtls = serializers.SerializerMethodField()
    ItemList = serializers.SerializerMethodField()
    ValDtls = serializers.SerializerMethodField()
    PayDtls = serializers.SerializerMethodField()
    RefDtls = serializers.SerializerMethodField()
    AddlDocDtls = serializers.SerializerMethodField()
    EwbDtls = serializers.SerializerMethodField()
  #  ExpDtls = serializers.SerializerMethodField()


    class Meta:
        model = PurchaseReturn
        fields = [
            "TranDtls", "DocDtls", "SellerDtls", "BuyerDtls",
            "DispDtls", "ShipDtls", "ItemList", "ValDtls",
            "PayDtls", "RefDtls", "AddlDocDtls", "EwbDtls"
        ]

    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Remove all keys where the value is None
        data = {k: v for k, v in data.items() if v is not None}

        # Insert "Version" at the top of the dictionary
        return {
            "Version": "1.1",
            **data
        }



    def get_TranDtls(self, obj):
        return {
            "TaxSch": "GST",
            "SupTyp": obj.invoicetype.invoicetypecode if obj.invoicetype else None,
            "RegRev": "Y" if obj.reversecharge else "N",
            "EcmGstin": obj.ecom.gstno if obj.ecom else None,
            "IgstOnIntra": "N"
        }


    def get_DocDtls(self, obj):
        return {
            "Typ": "CRN",
            "No": obj.invoicenumber,
            "Dt": obj.sorderdate.strftime("%d/%m/%Y") if obj.sorderdate else None
        }

   
    def get_SellerDtls(self, obj):
        entity = obj.entity
        return {
            "Gstin": entity.gstno,
            "LglNm": entity.legalname,
            "TrdNm": entity.entityname,
            "Addr1": entity.address,
            "Addr2": entity.address2,
            "Loc": entity.city.cityname if entity.city else None,
            "Pin": int(entity.city.pincode) if entity.city and entity.city.pincode else None,
            "Stcd": entity.state.statecode if entity.state else None,
            "Ph": entity.phoneoffice,
            "Em": entity.email
        }

    
    def get_BuyerDtls(self, obj):
        account = obj.accountid
        return {
            "Gstin": account.gstno,
            "LglNm": account.accountname,
            "TrdNm": account.accountname,
            "Pos": account.state.statecode if account.state else None,
            "Addr1": account.address1,
            "Addr2": account.address2,
            "Loc": account.city.cityname if account.city else None,
            "Pin": int(account.city.pincode) if account.city and account.city.pincode else None,
            "Stcd": account.state.statecode if account.state else None,
            "Ph": getattr(account, "phoneno", None),
            "Em": getattr(account, "emailid", None)
        }
    
    def get_DispDtls(self, obj):
        dispatch = obj.subentity
        return {
            "Nm": dispatch.subentityname if dispatch else None,
            "Addr1": dispatch.address if dispatch else None,
            "Addr2": dispatch.address if dispatch else None,
            "Loc": dispatch.city.cityname if dispatch and dispatch.city else None,
            "Pin": int(dispatch.pincode) if dispatch and dispatch.pincode else None,
            "Stcd": dispatch.state.statecode if dispatch and dispatch.state else None
        }
    
    def get_ShipDtls(self, obj):
        ShippingDetails = obj.shippedto
        return {
            "Gstin": ShippingDetails.gstno if ShippingDetails else None,
            "LglNm": ShippingDetails.full_name if ShippingDetails else None,
            "TrdNm": ShippingDetails.full_name if ShippingDetails else None,
            "Addr1": ShippingDetails.address1 if ShippingDetails else None,
            "Addr2": ShippingDetails.address2 if ShippingDetails else None,
            "Loc": ShippingDetails.city.cityname if ShippingDetails and ShippingDetails.city else None,
            "Pin": int(ShippingDetails.pincode) if ShippingDetails and ShippingDetails.pincode else None,
            "Stcd": ShippingDetails.state.statecode if ShippingDetails and ShippingDetails.state else None
        }
    
    def get_ItemList(self, obj):
        return [
            PurchasereturnItemSerializer(item, context={'slno': idx + 1}).data
            for idx, item in enumerate(obj.purchasereturndetails.all())
        ]
    
    def get_ValDtls(self, obj):
        def format_amount(value, allow_negative=False):
            try:
                val = float(value or 0)
            except (TypeError, ValueError):
                val = 0
            if allow_negative:
                return "{0:.2f}".format(val)
            return "{0:.2f}".format(abs(val))

        val = {
            "AssVal": format_amount(obj.subtotal),
            "CgstVal": format_amount(obj.cgst),
            "SgstVal": format_amount(obj.sgst),
            "IgstVal": format_amount(obj.igst),
            "CesVal": format_amount(obj.cess),
            "StCesVal": format_amount(0),
            "Discount": format_amount(0),
            "OthChrg": format_amount(obj.expenses),
            "RndOffAmt": format_amount(obj.roundOff, allow_negative=True),
            "TotInvVal": format_amount(obj.gtotal),
            "TotInvValFc": format_amount(obj.gtotal),
        }
        return val

    
    def get_PayDtls(self, obj):
        pay = getattr(obj, 'paydtls', None)
        if not pay:
            return None
        return {
            "Nm": pay.Nm,
            "FinInsBr": pay.FinInsBr,
            "PayTerm": pay.PayTerm,
            "PayInstr": pay.PayInstr,
            "CrTrn": pay.CrTrn,
            "DirDr": pay.DirDr,
            "CrDay": pay.CrDay,
            "PaidAmt": float(pay.PaidAmt) if pay.PaidAmt else None,
            "PayRefNo": pay.PayRefNo
        }

    def get_RefDtls(self, obj):
        ref = getattr(obj, 'refdtls', None)
        if not ref:
            return None
        return {
            "InvRm": ref.InvRm,
            "PrecDocDtls": [{
                "InvNo": ref.PrecDocNo,
                "InvDt": ref.PrecDocDt.strftime("%d/%m/%Y") if ref.PrecDocDt else None
            }] if ref.PrecDocNo else [],
            "ContrRefr": ref.ContrRefr
        }

    def get_AddlDocDtls(self, obj):
        docs = obj.addldocdtls.all()
        if not docs:
            return None
        return [{"Url": d.Url, "Docs": d.Docs, "Info": d.Info} for d in docs]

    def get_EwbDtls(self, obj):
        ewb = getattr(obj, 'ewbdtls', None)
        if not ewb:
            return None
        return {
            "TransId": ewb.TransId,
            "TransName": ewb.TransName,
            "Distance": int(ewb.Distance),
            "TransDocNo": ewb.TransDocNo,
            "TransMode": ewb.TransMode,
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y"),
            "VehNo": ewb.VehNo,
            "VehType": ewb.VehType
        }


DEC2 = Decimal("0.01")

def q2(v):
    return (Decimal(v) if v is not None else Decimal("0")).quantize(DEC2, rounding=ROUND_HALF_UP)

def fmt2(v):
    return f"{q2(v):.2f}"
    

class SalereturnItemSerializer(serializers.ModelSerializer):
    SlNo = serializers.SerializerMethodField()
    IsServc = serializers.SerializerMethodField()
    PrdDesc = serializers.SerializerMethodField()
    HsnCd = serializers.SerializerMethodField()
    Qty = serializers.SerializerMethodField()
    Unit = serializers.SerializerMethodField()
    UnitPrice = serializers.SerializerMethodField()
    TotAmt = serializers.SerializerMethodField()
    Discount = serializers.SerializerMethodField()
    PreTaxVal = serializers.SerializerMethodField()
    AssAmt = serializers.SerializerMethodField()
    GstRt = serializers.SerializerMethodField()
    SgstAmt = serializers.SerializerMethodField()
    IgstAmt = serializers.SerializerMethodField()
    CgstAmt = serializers.SerializerMethodField()
    CesAmt = serializers.SerializerMethodField()
    TotItemVal = serializers.SerializerMethodField()
    OrdLineRef = serializers.SerializerMethodField()

    class Meta:
        model = salereturnDetails
        fields = [
            "SlNo", "IsServc", "PrdDesc", "HsnCd", "Qty", "Unit", "UnitPrice",
            "TotAmt", "Discount", "PreTaxVal", "AssAmt", "GstRt", "SgstAmt", "IgstAmt", "CgstAmt",
            "CesAmt", "TotItemVal", "OrdLineRef"
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # ---- existing optional fields logic ----
        optional_fields = {
            "BchDtls": self.get_BchDtls(instance),
            "AttribDtls": self.get_AttribDtls(instance),
            "Barcde": instance.barcode if hasattr(instance, 'barcode') else None,
            "OrgCntry": instance.org_country if hasattr(instance, 'org_country') else None,
            "PrdSlNo": instance.product_serial_no if hasattr(instance, 'product_serial_no') else None,
        }
        for key, value in optional_fields.items():
            if value is not None:
                data[key] = value

        # ---- IRP consistency check (CRITICAL) ----
        ass  = Decimal(data["AssAmt"])
        cgst = Decimal(data["CgstAmt"])
        sgst = Decimal(data["SgstAmt"])
        igst = Decimal(data["IgstAmt"])
        cess = Decimal(data["CesAmt"])

        expected = (ass + cgst + sgst + igst + cess).quantize(Decimal("0.01"))
        got = Decimal(data["TotItemVal"]).quantize(Decimal("0.01"))

        if expected != got:
            raise serializers.ValidationError(
                f"Item mismatch (SlNo {data.get('SlNo')}): "
                f"expected TotItemVal {expected} but got {got}"
            )

        return data

    def get_BchDtls(self, obj):
        if hasattr(obj, 'batch') and obj.batch:
            return {
                "Nm": obj.batch.batchcode,
                "Expdt": obj.batch.expirydate.strftime("%d/%m/%Y") if obj.batch.expirydate else None,
                "wrDt": obj.batch.warehousedate.strftime("%d/%m/%Y") if obj.batch.warehousedate else None
            }
        return None

    def get_AttribDtls(self, obj):
        if hasattr(obj, 'attributes') and obj.attributes.exists():
            return [{"Nm": attr.name, "Val": attr.value} for attr in obj.attributes.all()]
        return None

    def get_SlNo(self, obj):
        return str(self.context.get('slno', 1))

    def get_IsServc(self, obj):
        return "N"

    def get_PrdDesc(self, obj):
        return obj.productdesc

    def get_HsnCd(self, obj):
        row = pick_active_gst_row(getattr(obj, "product", None))
        return row.hsn.code if (row and row.hsn) else None

    def get_Qty(self, obj):
        return fmt2(obj.orderqty or 0)

    def get_Unit(self, obj):
        return obj.product.base_uom.code if (obj.product and obj.product.base_uom) else None

    def get_UnitPrice(self, obj):
        return fmt2(obj.rate or 0)

    def get_TotAmt(self, obj):
        # ✅ Use DB taxable amount (do not recompute from qty*rate)
        return fmt2(obj.amount or 0)

    def get_Discount(self, obj):
        return "0.00"

    def get_PreTaxVal(self, obj):
        # ✅ Keep 0 unless you really have pre-tax adjustments
        return "0.00"

    def get_AssAmt(self, obj):
        # ✅ taxable value
        return fmt2(obj.amount or 0)

    def get_GstRt(self, obj):
        return "{0:.2f}".format(float(obj.igstpercent if obj.isigst else (obj.cgstpercent or 0) + (obj.sgstpercent or 0)))

    def get_CgstAmt(self, obj):
        return fmt2(obj.cgst or 0)

    def get_SgstAmt(self, obj):
        return fmt2(obj.sgst or 0)

    def get_IgstAmt(self, obj):
        return fmt2(obj.igst or 0)

    def get_CesAmt(self, obj):
        return fmt2(obj.cess or 0)

    def get_TotItemVal(self, obj):
        # ✅ must equal AssAmt + taxes (+cess)
        return fmt2(obj.linetotal or 0)

    def get_CesAmt(self, obj):
        return "{0:.2f}".format(float(obj.cess or 0))

    

    def get_OrdLineRef(self, obj):
        return str(obj.id or "")


    

# Sales Order Full Serializer (Including Seller, Buyer & Items)
class SalereturnFullSerializer(serializers.ModelSerializer):
    TranDtls = serializers.SerializerMethodField()
    DocDtls = serializers.SerializerMethodField()
    SellerDtls = serializers.SerializerMethodField()
    BuyerDtls = serializers.SerializerMethodField()
    DispDtls = serializers.SerializerMethodField()
   # ShipDtls = serializers.SerializerMethodField()
    ItemList = serializers.SerializerMethodField()
    ValDtls = serializers.SerializerMethodField()
    PayDtls = serializers.SerializerMethodField()
    RefDtls = serializers.SerializerMethodField()
    AddlDocDtls = serializers.SerializerMethodField()
    EwbDtls = serializers.SerializerMethodField()
  #  ExpDtls = serializers.SerializerMethodField()


    class Meta:
        model = salereturn
        fields = [
            "TranDtls", "DocDtls", "SellerDtls", "BuyerDtls",
            "DispDtls", "ItemList", "ValDtls",
            "PayDtls", "RefDtls", "AddlDocDtls", "EwbDtls"
        ]

    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Remove all keys where the value is None
        data = {k: v for k, v in data.items() if v is not None}

        # Insert "Version" at the top of the dictionary
        return {
            "Version": "1.1",
            **data
        }



    def get_TranDtls(self, obj):
        return {
            "TaxSch": "GST",
            "SupTyp": obj.invoicetype.invoicetypecode if obj.invoicetype else None,
            "RegRev": "Y" if obj.reversecharge else "N",
            "EcmGstin": obj.ecom.gstno if obj.ecom else None,
            "IgstOnIntra": "N"
        }


    def get_DocDtls(self, obj):
        return {
            "Typ": "DBN",
            "No": obj.invoicenumber,
            "Dt": obj.voucherdate.strftime("%d/%m/%Y") if obj.voucherdate else None
        }

   
    def get_SellerDtls(self, obj):
        entity = obj.entity
        return {
            "Gstin": entity.gstno,
            "LglNm": entity.legalname,
            "TrdNm": entity.entityname,
            "Addr1": entity.address,
            "Addr2": entity.address2,
            "Loc": entity.city.cityname if entity.city else None,
            "Pin": int(entity.city.pincode) if entity.city and entity.city.pincode else None,
            "Stcd": entity.state.statecode if entity.state else None,
            "Ph": entity.phoneoffice,
            "Em": entity.email
        }

    
    def get_BuyerDtls(self, obj):
        account = obj.account
        return {
            "Gstin": account.gstno,
            "LglNm": account.accountname,
            "TrdNm": account.accountname,
            "Pos": account.state.statecode if account.state else None,
            "Addr1": account.address1,
            "Addr2": account.address2,
            "Loc": account.city.cityname if account.city else None,
            "Pin": int(account.city.pincode) if account.city and account.city.pincode else None,
            "Stcd": account.state.statecode if account.state else None,
            "Ph": getattr(account, "phoneno", None),
            "Em": getattr(account, "emailid", None)
        }
    
    def get_DispDtls(self, obj):
        dispatch = obj.subentity
        return {
            "Nm": dispatch.subentityname if dispatch else None,
            "Addr1": dispatch.address if dispatch else None,
            "Addr2": dispatch.address if dispatch else None,
            "Loc": dispatch.city.cityname if dispatch and dispatch.city else None,
            "Pin": int(dispatch.pincode) if dispatch and dispatch.pincode else None,
            "Stcd": dispatch.state.statecode if dispatch and dispatch.state else None
        }
    
    # def get_ShipDtls(self, obj):
    #     ShippingDetails = obj.subentity
    #     return {
    #         "Gstin": ShippingDetails.gstno if ShippingDetails else None,
    #         "LglNm": ShippingDetails.full_name if ShippingDetails else None,
    #         "TrdNm": ShippingDetails.full_name if ShippingDetails else None,
    #         "Addr1": ShippingDetails.address1 if ShippingDetails else None,
    #         "Addr2": ShippingDetails.address2 if ShippingDetails else None,
    #         "Loc": ShippingDetails.city.cityname if ShippingDetails and ShippingDetails.city else None,
    #         "Pin": int(ShippingDetails.pincode) if ShippingDetails and ShippingDetails.pincode else None,
    #         "Stcd": ShippingDetails.state.statecode if ShippingDetails and ShippingDetails.state else None
    #     }
    
    def get_ItemList(self, obj):
        return [
            SalereturnItemSerializer(item, context={'slno': idx + 1}).data
            for idx, item in enumerate(obj.salereturndetails.all())
        ]
    
    def get_ValDtls(self, obj):
        def format_amount(value, allow_negative=False):
            try:
                val = float(value or 0)
            except (TypeError, ValueError):
                val = 0
            if allow_negative:
                return "{0:.2f}".format(val)
            return "{0:.2f}".format(abs(val))

        val = {
            "AssVal": format_amount(obj.subtotal),
            "CgstVal": format_amount(obj.cgst),
            "SgstVal": format_amount(obj.sgst),
            "IgstVal": format_amount(obj.igst),
            "CesVal": format_amount(obj.cess),
            "StCesVal": format_amount(0),
            "Discount": format_amount(0),
            "OthChrg": format_amount(obj.expenses),
            "RndOffAmt": format_amount(obj.roundOff, allow_negative=True),
            "TotInvVal": format_amount(obj.gtotal),
            "TotInvValFc": format_amount(obj.gtotal),
        }
        return val

    
    def get_PayDtls(self, obj):
        pay = getattr(obj, 'paydtls', None)
        if not pay:
            return None
        return {
            "Nm": pay.Nm,
            "FinInsBr": pay.FinInsBr,
            "PayTerm": pay.PayTerm,
            "PayInstr": pay.PayInstr,
            "CrTrn": pay.CrTrn,
            "DirDr": pay.DirDr,
            "CrDay": pay.CrDay,
            "PaidAmt": float(pay.PaidAmt) if pay.PaidAmt else None,
            "PayRefNo": pay.PayRefNo
        }

    def get_RefDtls(self, obj):
        ref = getattr(obj, 'refdtls', None)
        if not ref:
            return None
        return {
            "InvRm": ref.InvRm,
            "PrecDocDtls": [{
                "InvNo": ref.PrecDocNo,
                "InvDt": ref.PrecDocDt.strftime("%d/%m/%Y") if ref.PrecDocDt else None
            }] if ref.PrecDocNo else [],
            "ContrRefr": ref.ContrRefr
        }

    def get_AddlDocDtls(self, obj):
        docs = obj.addldocdtls.all()
        if not docs:
            return None
        return [{"Url": d.Url, "Docs": d.Docs, "Info": d.Info} for d in docs]

    def get_EwbDtls(self, obj):
        ewb = getattr(obj, 'ewbdtls', None)
        if not ewb:
            return None
        return {
            "TransId": ewb.TransId,
            "TransName": ewb.TransName,
            "Distance": int(ewb.Distance),
            "TransDocNo": ewb.TransDocNo,
            "TransMode": ewb.TransMode,
            "TransDocDt": ewb.TransDocDt.strftime("%d/%m/%Y"),
            "VehNo": ewb.VehNo,
            "VehType": ewb.VehType
        }



    
    
    


        

class SalesInvoiceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoiceSettings
        fields = '__all__'

class PurchaseSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseSettings
        fields = '__all__'

class ReceiptSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptSettings
        fields = '__all__'

class DoctypeSerializer(serializers.ModelSerializer):
    doctypeid = serializers.IntegerField(source='id')
    doctypename = serializers.CharField(source='docname')

    class Meta:
        model = doctype
        fields = ['doctypeid', 'doctypename']


class SalesOrderHeadeListSerializer(serializers.ModelSerializer):
    invoiceno = serializers.SerializerMethodField()
    invoice = serializers.DecimalField(source='id', max_digits=14, decimal_places=4, read_only=True)
    invoiceamount = serializers.DecimalField(source='gtotal', max_digits=14, decimal_places=4, read_only=True)
    invoicedate = serializers.DateTimeField(source='sorderdate', read_only=True)
    pendingamount = serializers.DecimalField(source='pending_amount', max_digits=14, decimal_places=4, read_only=True)  # <-- add source!

    class Meta:
        model = SalesOderHeader
        fields = ['invoice', 'invoiceno', 'invoiceamount', 'invoicedate', 'pendingamount']

    def get_invoiceno(self, obj):
        return obj.invoicenumber if obj.invoicenumber else str(obj.billno)


    




# from decimal import Decimal
# from typing import List, Optional

# from django.db import transaction
# from django.db.models import Prefetch, Q
# from django.utils import timezone

# from rest_framework import serializers, permissions, status, generics
# from rest_framework.response import Response
# from rest_framework.exceptions import ValidationError
# from rest_framework.views import APIView

# --- import your models ---
# from .models import SalesQuotationHeader, SalesQuotationDetail
# from invoice.models import SalesOderHeader, salesOrderdetails  # your existing invoice models
# from accounts.models import Entity, subentity, entityfinancialyear
# from users.models import User


# =============================
# Serializers
# =============================

# ---------------------------
# Line (Detail) Serializer
# ---------------------------
class SalesQuotationLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = SalesQuotationDetail
        fields = [
            "id",
            "product",
            "productdesc",
            "qty",
            "pieces",
            "ratebefdiscount",
            "line_discount",
            "rate",
            "amount",
            "cgstpercent",
            "sgstpercent",
            "igstpercent",
            "cgst",            # now writable
            "sgst",            # now writable
            "igst",            # now writable
            "linetotal",       # now writable (we'll normalize)
            "is_service",
            "subentity",
            "entity",
            "createdby",
        ]
        read_only_fields = ["createdby"]

    def validate(self, data):
        # non-negative basics
        for f in ["qty", "pieces", "ratebefdiscount", "line_discount", "rate", "amount",
                  "cgst", "sgst", "igst"]:
            v = data.get(f)
            if v is not None and v < 0:
                raise ValidationError({f: "Must be ≥ 0"})

        # percent bounds
        for p in ["cgstpercent", "sgstpercent", "igstpercent"]:
            v = data.get(p)
            if v is not None and (v < 0 or v > 100):
                raise ValidationError({p: "Must be between 0 and 100"})

        # If client provided linetotal, ensure it’s consistent (1p tolerance)
        amt = data.get("amount")
        if amt is not None:
            cg = data.get("cgst") or 0
            sg = data.get("sgst") or 0
            ig = data.get("igst") or 0
            lt = data.get("linetotal")
            if lt is not None:
                expected = amt + cg + sg + ig
                if (lt - expected).copy_abs() > Decimal("0.01"):
                    raise ValidationError({"linetotal": "Must equal amount + cgst + sgst + igst"})
        return data


# ---------------------------
# Header Serializer
# ---------------------------
class SalesQuotationHeaderSerializer(serializers.ModelSerializer):
    lines = SalesQuotationLineSerializer(many=True)
    createdby = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = SalesQuotationHeader
        fields = [
            "id",
            "quote_date",
            "quote_no",
            "version",
            "taxtype",
            "Terms",
            "invoicetype",
            "account",
            "contact_name",
            "contact_email",
            "shippedto",
            "valid_until",
            "status",
            "price_list",
            "currency",
            "remarks",
            # money & taxes (now writable)
            "stbefdiscount",
            "discount",
            "subtotal",
            "addless",
            "cess",
            "cgst",
            "sgst",
            "igst",
            "totalgst",
            "isigst",
            "gtotal",
            # scoping
            "subentity",
            "entity",
            "entityfinid",
            "createdby",
            # nested
            "lines",
        ]
        read_only_fields = ("version",)

    def validate(self, data):
        # non-negative checks
        for f in ["stbefdiscount", "discount", "subtotal", "addless", "cess", "cgst", "sgst", "igst", "totalgst", "gtotal"]:
            v = data.get(f)
            if v is not None and v < 0:
                raise ValidationError({f: "Must be ≥ 0"})

        # valid_until rule
        vu = data.get("valid_until")
        if vu and vu < timezone.now().date():
            status_val = data.get("status") or getattr(self.instance, "status", None)
            if status_val and status_val != SalesQuotationHeader.Status.DRAFT:
                raise ValidationError({"valid_until": "Cannot set past valid_until for non-draft quotations"})
        return data

    # ------- nested writes (same as before) -------
    def _upsert_lines(self, header: SalesQuotationHeader, lines_payload: List[dict]):
        seen_ids: List[int] = []
        for item in lines_payload:
            pk = item.get("id")
            item["header"] = header
            if pk:
                try:
                    inst = SalesQuotationDetail.objects.get(id=pk, header=header)
                except SalesQuotationDetail.DoesNotExist:
                    raise ValidationError({"lines": f"Line id {pk} does not exist for this quotation"})
                for k, v in item.items():
                    setattr(inst, k, v)
                inst.save()
                seen_ids.append(inst.id)
            else:
                inst = SalesQuotationDetail.objects.create(**item)
                seen_ids.append(inst.id)
        SalesQuotationDetail.objects.filter(header=header).exclude(id__in=seen_ids).delete()

    # ------- totals roll-up (trust posted taxes if provided, then normalize) -------
    def _recalc_totals(self, header: SalesQuotationHeader):
        """
        Normalization rules:
        - If line tax values (cgst/sgst/igst) are provided, we use them.
        - Otherwise we compute from percents based on header.isigst.
        - We always force tax-mode consistency (isigst=True → cgst=sgst=0; else igst=0)
        - Header totals are overwritten as Σ of line taxes (we don't trust header if mismatched).
        - linetotal is set to amount + taxes (overwrites if off by > 0.01).
        """
        qs = list(header.lines.all())
        ZERO2 = Decimal("0.00")
        ZERO4 = Decimal("0.0000")

        def d(v, fallback=ZERO2):
            return v if v is not None else fallback

        stbef = sum(d(ln.ratebefdiscount) * d(ln.qty, ZERO4) for ln in qs)

        subtotal = ZERO2
        sum_cgst = ZERO2
        sum_sgst = ZERO2
        sum_igst = ZERO2

        for ln in qs:
            qty = d(ln.qty, ZERO4)
            amount = d(ln.amount)
            if amount == ZERO2:
                amount = d(ln.rate) * qty - d(ln.line_discount)

            # Prefer posted taxes; else compute from percents given isIGST mode
            if header.isigst:
                igst = d(ln.igst) if ln.igst is not None else (
                    amount * (d(ln.igstpercent) / Decimal("100")) if ln.igstpercent is not None else ZERO2
                )
                cgst = ZERO2
                sgst = ZERO2
            else:
                cgst = d(ln.cgst) if ln.cgst is not None else (
                    amount * (d(ln.cgstpercent) / Decimal("100")) if ln.cgstpercent is not None else ZERO2
                )
                sgst = d(ln.sgst) if ln.sgst is not None else (
                    amount * (d(ln.sgstpercent) / Decimal("100")) if ln.sgstpercent is not None else ZERO2
                )
                igst = ZERO2

            # Normalize and persist line
            ln.amount = amount
            ln.cgst = cgst
            ln.sgst = sgst
            ln.igst = igst
            lt_expected = amount + cgst + sgst + igst
            if (d(ln.linetotal) - lt_expected).copy_abs() > Decimal("0.01"):
                ln.linetotal = lt_expected
            ln.save(update_fields=["amount", "cgst", "sgst", "igst", "linetotal"])

            subtotal += amount
            sum_cgst += cgst
            sum_sgst += sgst
            sum_igst += igst

        totalgst = sum_cgst + sum_sgst + sum_igst
        discount = d(header.discount)
        addless = d(header.addless)
        cess = d(header.cess)

        header.stbefdiscount = stbef
        header.subtotal = subtotal
        header.cgst = sum_cgst
        header.sgst = sum_sgst
        header.igst = sum_igst
        header.totalgst = totalgst
        header.gtotal = subtotal - discount + addless + totalgst + cess

        header.save(update_fields=[
            "stbefdiscount", "subtotal", "cgst", "sgst", "igst", "totalgst", "gtotal"
        ])

    @transaction.atomic
    def create(self, validated_data):
        lines_payload = validated_data.pop("lines", [])
        hdr = SalesQuotationHeader.objects.create(**validated_data)
        self._upsert_lines(hdr, lines_payload)
        self._recalc_totals(hdr)
        return hdr

    @transaction.atomic
    def update(self, instance, validated_data):
        lines_payload = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines_payload is not None:
            self._upsert_lines(instance, lines_payload)
        self._recalc_totals(instance)
        return instance




















