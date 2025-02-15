
#import imp
from itertools import product
from os import device_encoding
from pprint import isreadable
from select import select
from rest_framework import serializers
from invoice.models import SalesOderHeader,SalesOder,salesOrderdetails,salesOrderdetail,purchaseorder,PurchaseOrderDetails,\
    journal,salereturn,salereturnDetails,Transactions,StockTransactions,PurchaseReturn,Purchasereturndetails,journalmain,journaldetails,entry,goodstransaction,stockdetails,stockmain,accountentry,purchasetaxtype,tdsmain,tdstype,productionmain,productiondetails,tdsreturns,gstorderservices,gstorderservicesdetails,jobworkchalan,jobworkchalanDetails,debitcreditnote,closingstock,saleothercharges,purchaseothercharges,salereturnothercharges,Purchasereturnothercharges,purchaseotherimportcharges,purchaseorderimport,PurchaseOrderimportdetails,newPurchaseOrderDetails,newpurchaseorder,InvoiceType,PurchaseOrderAttachment
from financial.models import account,accountHead
from inventory.models import Product
from django.db.models import Sum,Count,F, Case, When, FloatField, Q
from datetime import timedelta,date,datetime
from entity.models import Entity,entityfinancialyear,Mastergstdetails
from django.db.models.functions import Abs
from num2words import num2words
import string
from django.db import  transaction
from django_filters.rest_framework import DjangoFilterBackend
import requests
import json
import pandas as pd
from django_pandas.io import read_frame
import numpy as np
import entity.views as entityview
from django.db.models import Prefetch
#from entity.views import generateeinvoice
#from entity.serializers import entityfinancialyearSerializer



class InvoiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceType
        fields = ['id', 'invoicetype', 'invoicetypecode', 'entity', 'createdby']
        read_only_fields = ['id', 'createdby']



# Base Serializer to handle common update logic
class BaseCancelSerializer(serializers.ModelSerializer):
    fields_to_update = ['isactive', 'createdby']

    def update(self, instance, validated_data):
        # Efficiently update only the fields present in validated_data
        for field in self.fields_to_update:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        
        # Save instance only if necessary
        if any(getattr(instance, field) != validated_data.get(field) for field in self.fields_to_update):
            instance.save()

        return instance

# Serializer for each model
class TdsmaincancelSerializer(BaseCancelSerializer):
    class Meta:
        model = tdsmain
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Efficiently update entry if necessary
        entry.objects.update_or_create(
            entrydate1=instance.voucherdate,
            entity=instance.entityid,
            defaults={'created': instance.created}
        )

        # Efficiently update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entityid,
            transactionid=instance.id,
            transactiontype='T'
        ).update(isactive=instance.isactive)

        return instance

class SaleinvoicecancelSerializer(BaseCancelSerializer):
    class Meta:
        model = SalesOderHeader
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='S'
        ).update(isactive=instance.isactive)

        return instance

class SalesordercancelSerializer(BaseCancelSerializer):
    class Meta:
        model = SalesOder
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)
        return instance

class GstorderservicecancelSerializer(BaseCancelSerializer):
    class Meta:
        model = gstorderservices
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Create or update entry
        entry.objects.get_or_create(entrydate1=instance.orderdate, entity=instance.entity)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype=instance.orderType
        ).update(isactive=instance.isactive)

        return instance

class PurchaseinvoicecancelSerializer(BaseCancelSerializer):
    class Meta:
        model = purchaseorder
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='P'
        ).update(isactive=instance.isactive)

        return instance

class PurchaseordercancelSerializer(BaseCancelSerializer):
    class Meta:
        model = purchaseorder
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)
        return instance

class PurchaseimportcancelSerializer(BaseCancelSerializer):
    class Meta:
        model = purchaseorderimport
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='P'
        ).update(isactive=instance.isactive)

        return instance

class JobworkchallancancelSerializer(BaseCancelSerializer):
    class Meta:
        model = jobworkchalan
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)
        return instance

class PurchasereturncancelSerializer(BaseCancelSerializer):
    class Meta:
        model = PurchaseReturn
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='PR'
        ).update(isactive=instance.isactive)

        return instance

class SalesreturncancelSerializer(BaseCancelSerializer):
    class Meta:
        model = salereturn
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='SR'
        ).update(isactive=instance.isactive)

        return instance

class JournalcancelSerializer(BaseCancelSerializer):
    class Meta:
        model = journalmain
        fields = ('isactive', 'vouchertype')

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions based on voucher type
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype=instance.vouchertype
        ).update(isactive=instance.isactive)

        return instance

class ProductioncancelSerializer(BaseCancelSerializer):
    class Meta:
        model = productionmain
        fields = ('isactive', 'vouchertype')

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions based on voucher type
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype=instance.vouchertype
        ).update(isactive=instance.isactive)

        return instance

class StockcancelSerializer(BaseCancelSerializer):
    class Meta:
        model = stockmain
        fields = ('isactive',)

    def update(self, instance, validated_data):
        super().update(instance, validated_data)

        # Update stock transactions
        StockTransactions.objects.filter(
            entity=instance.entity,
            transactionid=instance.id,
            transactiontype='PC'
        ).update(isactive=instance.isactive)

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

    def getcgst(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6001)
    
    def getsgst(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6002)
    
    def getigst(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6003)
    
    def getcgstr(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6005)
    
    def getsgstr(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6006)
    
    def getigstr(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6007)
    
    def getcessid(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 6004)
    
    def gettcs206c1ch2id(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 8050)

    def gettcs206C2id(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 8051)
    
    def gettds194q1id(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 8100)
    
    def getexpensesid(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 8300)
    
    def getcashid(self,pentity):
        return account.objects.get(entity =pentity,accountcode = 4000)
    
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
        

    





class stocktransaction:
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

        cgstid = const.getcgst(pentity)
        igstid = const.getigst(pentity)
        sgstid = const.getsgst(pentity)
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
        if cgst > 0:
            StockTransactions.objects.create(accounthead = cgstid.accounthead, account= cgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        if sgst > 0:
            StockTransactions.objects.create(accounthead = sgstid.accounthead,account= sgstid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno),drcr=self.debit,debitamount=sgst,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        if cess > 0:
            StockTransactions.objects.create(accounthead = cessid.accounthead, account= cessid,transactiontype = self.transactiontype,transactionid = id,desc = self.description + ' ' + str(self.order.voucherno) ,drcr=self.debit,debitamount=cess,entity=pentity,createdby= self.order.createdby,entry =entryid,entrydatetime = self.order.billdate,voucherno = self.order.voucherno)
        
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

        details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
        details1 = StockTransactions.objects.create(accounthead= self.order.account.accounthead,account= self.order.account,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'MD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
        return details

    
    def createothertransactiondetails(self,detail,stocktype):

        

        entryid,created  = entry.objects.get_or_create(entrydate1 = self.order.billdate,entity=self.order.entity)

      #  details = StockTransactions.objects.create(accounthead = detail.product.purchaseaccount.accounthead,account= detail.product.purchaseaccount,stock=detail.product,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,quantity = qty,drcr = self.debit,debitamount = detail.amount - detail.othercharges,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'DD',isactive = self.order.isactive,rate = detail.rate,voucherno = self.order.voucherno)
        details1 = StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = self.transactiontype,transactionid = self.order.id,desc = self.description + ' '  + str(self.order.voucherno),stockttype = stocktype,drcr = self.debit,debitamount = detail.amount ,entrydate = self.order.billdate,entity = self.order.entity,createdby = self.order.createdby,entry = entryid,entrydatetime = self.order.billdate,accounttype = 'M',isactive = self.order.isactive,voucherno = self.order.voucherno)
        return details1
    

    

    



class stocktransactionsale:
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
        cess = self.order.cess
        tcs206c1ch2 = self.order.tcs206c1ch2
        tcs206C2 = self.order.tcs206C2
        tds194q1 = self.order.tds194q1
        expenses = self.order.expenses
        gtotal = self.order.gtotal - round(tcs206c1ch2) - round(tcs206C2)
        pentity = self.order.entity
        const = stocktransconstant()

        cgstid = const.getcgst(pentity)
        igstid = const.getigst(pentity)
        sgstid = const.getsgst(pentity)
        cessid = const.getcessid(pentity)
        tcs206c1ch2id = const.gettcs206c1ch2id(pentity)
        tcs206C2id = const.gettcs206C2id(pentity)
        tds194q1id = const.gettds194q1id(pentity)
        expensesid = const.getexpensesid(pentity)
        entryid, _ = entry.objects.get_or_create(entrydate1=self.order.sorderdate, entity=self.order.entity)

        if self.order.totalquanity == 0.00:
            qty = self.order.totalpieces
        else:
            qty = self.order.totalquanity

        if self.entrytype == 'U':
            StockTransactions.objects.filter(entity=pentity, transactiontype=self.transactiontype, transactionid=id).delete()
            tdsmain.objects.filter(entityid=pentity, transactiontype=self.transactiontype, transactionno=id).delete()

        iscash = False

        if self.order.billcash == 0:
            iscash = True
            cash = const.getcashid(pentity)
            StockTransactions.objects.create(accounthead=cash.accounthead, account=cash, transactiontype=self.transactiontype, transactionid=id, desc='Cash Receipt Sale Bill.No : ' + str(self.order.billno), drcr=1, debitamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='CIH', iscashtransaction=iscash, voucherno=self.order.billno)
            StockTransactions.objects.create(accounthead=self.order.accountid.accounthead, account=self.order.accountid, transactiontype=self.transactiontype, transactionid=id, desc=' Cash sale By Bill.No : ' + str(self.order.billno), drcr=0, creditamount=gtotal, entity=pentity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='M', iscashtransaction=iscash, voucherno=self.order.billno)

        StockTransactions.objects.create(accounthead=self.order.accountid.accounthead, account=self.order.accountid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.debit, debitamount=gtotal, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='M', quantity=qty, voucherno=self.order.billno)
        
        if tcs206C2 > 0:
            StockTransactions.objects.create(accounthead=tcs206C2id.accounthead, account=tcs206C2id, transactiontype=self.transactiontype, transactionid=id, desc='TCS :' + str(self.description) + ' ' + str(self.order.billno), drcr=self.credit, creditamount=tcs206C2, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
            StockTransactions.objects.create(accounthead=self.order.accountid.accounthead, account=self.order.accountid, transactiontype=self.transactiontype, transactionid=id, desc='TCS :' + str(self.description) + ' ' + str(self.order.billno), drcr=self.debit, debitamount=tcs206C2, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='M', voucherno=self.order.billno)
        
        if tcs206c1ch2 > 0:
            StockTransactions.objects.create(accounthead=tcs206c1ch2id.accounthead, account=tcs206c1ch2id, transactiontype=self.transactiontype, transactionid=id, desc='TCS :' + str(self.description) + ' ' + str(self.order.billno), drcr=self.credit, creditamount=tcs206c1ch2, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
            StockTransactions.objects.create(accounthead=self.order.accountid.accounthead, account=self.order.accountid, transactiontype=self.transactiontype, transactionid=id, desc='TCS :' + str(self.description) + ' ' + str(self.order.billno), drcr=self.debit, debitamount=tcs206c1ch2, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='M', voucherno=self.order.billno)
        
        if expenses > 0:
            StockTransactions.objects.create(accounthead=expensesid.accounthead, account=expensesid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=expenses, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
        
        if tds194q1 > 0:
            tdsvbo = const.gettdsvbono(pentity)
            tdsreturnid = const.gettdsreturnid()
            tdstypeid = const.gettdstypeid()
            tdsmain.objects.create(voucherdate=self.order.sorderdate, voucherno=tdsvbo, creditaccountid=self.order.accountid, debitaccountid=tds194q1id, tdsaccountid=tds194q1id, tdsreturnccountid=tdsreturnid, tdstype=tdstypeid, debitamount=subtotal, tdsrate=self.order.tds194q, entityid=pentity, transactiontype=self.transactiontype, transactionno=id, tdsvalue=tds194q1)
            StockTransactions.objects.create(accounthead=tds194q1id.accounthead, account=tds194q1id, transactiontype=self.transactiontype, transactionid=id, desc='TD194Q:' + str(self.description) + ' ' + str(self.order.billno), drcr=self.debit, debitamount=tds194q1, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
            StockTransactions.objects.create(accounthead=self.order.accountid.accounthead, account=self.order.accountid, transactiontype=self.transactiontype, transactionid=id, desc='TDS194Q:' + str(self.description) + ' ' + str(self.order.billno), drcr=self.credit, creditamount=tds194q1, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, accounttype='M', voucherno=self.order.billno)

        if igst > 0:
            StockTransactions.objects.create(accounthead=igstid.accounthead, account=igstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=igst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
        
        if cgst > 0:
            StockTransactions.objects.create(accounthead=cgstid.accounthead, account=cgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=cgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
        
        if sgst > 0:
            StockTransactions.objects.create(accounthead=sgstid.accounthead, account=sgstid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=sgst, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
        
        if cess > 0:
            StockTransactions.objects.create(accounthead=cessid.accounthead, account=cessid, transactiontype=self.transactiontype, transactionid=id, desc=self.description + ' ' + str(self.order.billno), drcr=self.credit, creditamount=cess, entity=self.order.entity, createdby=self.order.createdby, entry=entryid, entrydatetime=self.order.sorderdate, voucherno=self.order.billno)
            
        return id

    


    def createtransactiondetails(self, detail, stocktype):
        if detail.orderqty == 0.00:
            qty = detail.pieces
        else:
            qty = detail.orderqty

        entryid, created = entry.objects.get_or_create(entrydate1=self.order.sorderdate, entity=self.order.entity)

        sale_account = detail.product.saleaccount
        purchase_account = detail.product.purchaseaccount

        details = StockTransactions.objects.create(
            accounthead=sale_account.creditaccounthead,
            account=sale_account,
            stock=detail.product,
            transactiontype=self.transactiontype,
            transactionid=self.order.id,
            desc=self.description + ' ' + str(self.order.billno),
            stockttype=stocktype,
            quantity=qty,
            drcr=self.credit,
            creditamount=detail.amount - detail.othercharges,
            entrydate=self.order.sorderdate,
            entity=self.order.entity,
            createdby=self.order.createdby,
            entry=entryid,
            accounttype='DD',
            isactive=self.order.isactive,
            rate=detail.rate,
            entrydatetime=self.order.sorderdate,
            voucherno=self.order.billno
        )

        details1 = StockTransactions.objects.create(
            accounthead=self.order.accountid.creditaccounthead,
            account=self.order.accountid,
            stock=detail.product,
            transactiontype=self.transactiontype,
            transactionid=self.order.id,
            desc=self.description + ' ' + str(self.order.billno),
            stockttype=stocktype,
            quantity=qty,
            drcr=self.credit,
            creditamount=detail.amount - detail.othercharges,
            entrydate=self.order.sorderdate,
            entity=self.order.entity,
            createdby=self.order.createdby,
            entry=entryid,
            accounttype='MD',
            isactive=self.order.isactive,
            rate=detail.rate,
            entrydatetime=self.order.sorderdate,
            voucherno=self.order.billno
        )

        return details, details1

    def createothertransactiondetails(self, detail, stocktype):
        entryid, created = entry.objects.get_or_create(entrydate1=self.order.sorderdate, entity=self.order.entity)
        details1 = StockTransactions.objects.create(
            accounthead=detail.account.creditaccounthead,
            account=detail.account,
            transactiontype=self.transactiontype,
            transactionid=self.order.id,
            desc=self.description + ' ' + str(self.order.billno),
            stockttype=stocktype,
            drcr=self.credit,
            creditamount=detail.amount,
            entrydate=self.order.sorderdate,
            entity=self.order.entity,
            createdby=self.order.createdby,
            entry=entryid,
            accounttype='M',
            isactive=self.order.isactive,
            entrydatetime=self.order.sorderdate,
            voucherno=self.order.billno
        )
        return details1




    



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
    #entityUser = entityUserSerializer(many=True)
    id = serializers.IntegerField(required=False)
    accountname = serializers.SerializerMethodField()

    class Meta:
        model = journaldetails
        fields =  ('id','account','accountname','desc','drcr','debitamount','creditamount','discount','bankcharges','tds','chqbank','entity',)

    def get_accountname(self,obj):
         return obj.account.accountname



class journalmainSerializer(serializers.ModelSerializer):
    journaldetails = journaldetailsSerializer(many=True)
    class Meta:
        model = journalmain
        fields = ('id','voucherdate','voucherno','vouchertype','mainaccountid','entrydate','entityfinid','entity','createdby', 'isactive','journaldetails',)
    def create(self, validated_data):
        journaldetails_data = validated_data.pop('journaldetails')
        with transaction.atomic():
            order = journalmain.objects.create(**validated_data)
            for journaldetail_data in journaldetails_data:
                detail = journaldetails.objects.create(Journalmain = order, **journaldetail_data)
                print(order.entrydate)
                id,created  = entry.objects.get_or_create(entrydate1 = order.entrydate,entity = order.entity)

                narration = ''

                if detail.account.accountcode == 4000:
                    iscash = True
                else:
                    iscash = False
                # accounttype = 'M'

                if order.vouchertype == 'C':
                    iscash = True

                    narration = 'Cash V.No '
                
                if order.vouchertype == 'B':
                    narration = 'Bank V.No '
                
                if order.vouchertype == 'J':
                    narration = 'Journal V.No '
                


               # accountentryid,accountentrycreated  = accountentry.objects.get_or_create(entrydate2 = order.entrydate,account =detail.account,  entity = order.entity)

                if order.vouchertype == 'C':
                # iscash = False
                    iscash = True

                    #if self.order.account.accountcode == 4000:
                        
                    cash = account.objects.get(entity =order.entity,accountcode = 4000)
                    if detail.drcr == 1:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =order.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = order.voucherno)
                    else:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =order.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        
                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = order.voucherno)

                    
                if order.vouchertype == 'B':
                    cash = account.objects.get(id = order.mainaccountid)
                    if detail.drcr == 1:
                        if detail.discount > 0:

                            nnation = ' (discount)'
                            disc = account.objects.get(entity =order.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                        if detail.bankcharges > 0:
                            nnation = ' (B Charges)'
                            bc = account.objects.get(entity =order.entity,accountcode = 8500)
                            StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        if detail.tds > 0:
                            nnation = ' (tds)'
                            tds = account.objects.get(entity =order.entity,accountcode = 8100)
                            StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                    else:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =order.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation ,drcr=0,creditamount=detail.discount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                        if detail.bankcharges > 0:
                            nnation = ' (B Charges)'
                            bc = account.objects.get(entity =order.entity,accountcode = 8500)
                            StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                        if detail.tds > 0:
                            nnation = ' (tds)'
                            tds = account.objects.get(entity =order.entity,accountcode = 8100)
                            StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',voucherno = order.voucherno)

                

                StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = order.vouchertype,transactionid = order.id,desc = narration + str(order.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=order.entity,createdby= order.createdby,entrydate = order.entrydate,entry =id,entrydatetime = order.entrydate,accounttype='M',iscashtransaction= iscash,voucherno = order.voucherno)

          
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','vouchertype','mainaccountid','entrydate','entityfinid', 'entity','createdby','isactive',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        with transaction.atomic():
            instance.save()
        # stk = stocktransactionsale(instance, transactiontype= 'S',debit=1,credit=0,description= 'Sale')
            journaldetails.objects.filter(Journalmain=instance,entity = instance.entity).delete()
            StockTransactions.objects.filter(entity = instance.entity,transactiontype = instance.vouchertype,transactionid = instance.id).delete()
        #   stk.updateransaction()

            journaldetails_data = validated_data.get('journaldetails')

            for journaldetail_data in journaldetails_data:
                detail = journaldetails.objects.create(Journalmain = instance, **journaldetail_data)
                id,created  = entry.objects.get_or_create(entrydate1 = instance.entrydate,entity = instance.entity)
              #  StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = 'Journal V.No' + str(instance.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1)
                #stk.createtransactiondetails(detail=detail,stocktype='S')

                if instance.vouchertype == 'C':
                    iscash = True
                    narration = 'Cash V.No '
                
                if instance.vouchertype == 'B':
                    narration = 'Bank V.No '
                
                if instance.vouchertype == 'J':
                    narration = 'Journal V.No '


                if instance.vouchertype == 'C':
                    iscash = True
                    #if self.order.account.accountcode == 4000:
                        
                    cash = account.objects.get(entity =instance.entity,accountcode = 4000)
                    if detail.drcr == 1:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =instance.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno,iscashtransaction= iscash)
                            

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = instance.voucherno)
                    else:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =instance.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno,iscashtransaction= iscash)
                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='CIH',iscashtransaction= iscash,voucherno = instance.voucherno)

                    
                if instance.vouchertype == 'B':
                    cash = account.objects.get(id = instance.mainaccountid)
                    if detail.drcr == 1:

                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =instance.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                        if detail.bankcharges > 0:
                            nnation = ' (B Charges)'
                            bc = account.objects.get(entity =instance.entity,accountcode = 8500)
                            StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                        
                        if detail.tds > 0:
                            nnation = ' (tds)'
                            tds = account.objects.get(entity =instance.entity,accountcode = 8100)
                            StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=0,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1,voucherno = instance.voucherno)
                    else:
                        if detail.discount > 0:
                            nnation = ' (discount)'
                            disc = account.objects.get(entity =instance.entity,accountcode = 8400)
                            StockTransactions.objects.create(accounthead= disc.accounthead,account= disc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.discount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                        
                        if detail.bankcharges > 0:
                            nnation = ' (B Charges)'
                            bc = account.objects.get(entity =instance.entity,accountcode = 8500)
                            StockTransactions.objects.create(accounthead= bc.accounthead,account= bc,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,creditamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.bankcharges,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

                        if detail.tds > 0:
                            nnation = ' (tds)'
                            tds = account.objects.get(entity =instance.entity,accountcode = 8100)
                            StockTransactions.objects.create(accounthead= tds.accounthead,account= tds,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=1,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)
                            StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno) + nnation,drcr=0,debitamount=detail.tds,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',voucherno = instance.voucherno)

                        StockTransactions.objects.create(accounthead= cash.accounthead,account= cash,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=1,creditamount=detail.debitamount,debitamount=detail.creditamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',isactive = 1,voucherno = instance.voucherno)

                
                if detail.account.accountcode == 4000:
                    iscash = True
                else:
                    iscash = False
                # accounttype = 'M'

                if instance.vouchertype == 'C':
                    iscash = True


              

                StockTransactions.objects.create(accounthead= detail.account.accounthead,account= detail.account,transactiontype = instance.vouchertype,transactionid = instance.id,desc = narration + str(instance.voucherno),drcr=detail.drcr,creditamount=detail.creditamount,debitamount=detail.debitamount,entity=instance.entity,createdby= instance.createdby,entrydate = instance.entrydate,entry =id,entrydatetime = instance.entrydate,accounttype='M',iscashtransaction= iscash,voucherno = instance.voucherno)

        
        return instance



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


            if detail.issuereceived == True:
                StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = order.vouchertype,transactionid = order.id,drcr = detail.issuereceived,quantity = detail.issuedquantity,entrydate = order.entrydate,entrydatetime = order.entrydate, entity = order.entity,createdby = order.createdby,entry = id,stockttype= 'I',accounttype = 'DD',voucherno = order.voucherno,desc = 'Stock V.No ' + str(order.voucherno))
            else:
                StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = order.vouchertype,transactionid = order.id,drcr = detail.issuereceived,quantity = detail.recivedquantity,entrydate = order.entrydate,entrydatetime = order.entrydate,entity = order.entity,createdby = order.createdby,entry = id,stockttype= 'R',accounttype = 'DD',voucherno = order.voucherno,desc = 'Stock V.No ' + str(order.voucherno))

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
        StockTransactions.objects.filter(entity = instance.entity,transactiontype = instance.vouchertype,transactionid = instance.id).delete()
     #   stk.updateransaction()

        journaldetails_data = validated_data.get('stockdetails')
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.entrydate,entity=instance.entity)

        for journaldetail_data in journaldetails_data:
            detail = stockdetails.objects.create(stockmain = instance, **journaldetail_data)
           # goodstransaction.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,stockttype = detail.issuereceived,issuedquantity = detail.issuedquantity,recivedquantity = detail.recivedquantity,entrydate = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid)
            #stk.createtransactiondetails(detail=detail,stocktype='S')
            if detail.issuereceived == True:
                StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,drcr = detail.issuereceived,quantity = detail.issuedquantity,entrydate = instance.entrydate,entrydatetime = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid,stockttype= 'I',accounttype = 'DD',voucherno = instance.voucherno,desc = 'Stock V.No ' + str(instance.voucherno))
            else:
                StockTransactions.objects.create(account= detail.stock.purchaseaccount,stock=detail.stock,transactiontype = instance.vouchertype,transactionid = instance.id,drcr = detail.issuereceived,quantity = detail.recivedquantity,entrydate = instance.entrydate,entrydatetime = instance.entrydate,entity = instance.entity,createdby = instance.createdby,entry = entryid,stockttype= 'R',accounttype = 'DD',voucherno = instance.voucherno,desc = 'Stock V.No   ' + str(instance.voucherno))

        
        return instance



class SalesOrderDetailsPDFSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.CharField(source='product.productname', read_only=True)
    hsn = serializers.CharField(source='product.hsn.hsnCode', read_only=True)
    mrp = serializers.DecimalField(source='product.mrp', max_digits=10, decimal_places=2, read_only=True)
    units = serializers.CharField(source='product.unitofmeasurement.unitname', read_only=True)
    cgstrate = serializers.DecimalField(source='product.cgst', max_digits=5, decimal_places=2, read_only=True)
    sgstrate = serializers.DecimalField(source='product.sgst', max_digits=5, decimal_places=2, read_only=True)
    igstrate = serializers.SerializerMethodField()

    class Meta:
        model = salesOrderdetails
        fields = (
            'id', 'product', 'productname', 'hsn', 'units', 'mrp', 'productdesc', 'orderqty', 'pieces', 
            'ratebefdiscount','orderDiscount', 'rate', 'amount', 'othercharges', 'cgstrate', 'cgst', 'sgstrate', 'sgst', 'igstrate', 
            'igst', 'cess', 'linetotal', 'entity',
        )

    def get_igstrate(self, obj):
        return obj.product.igst if obj.igst else 0


class SalesOrderHeaderPDFSerializer(serializers.ModelSerializer):
   # saleInvoiceDetails1 = serializers.SerializerMethodField()
    saleInvoiceDetails = SalesOrderDetailsPDFSerializer(many=True, read_only=True)
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
    billtopan = serializers.CharField(source='accountid.pan', read_only=True)
    #billtoaddress = serializers.SerializerMethodField()
    billtogst = serializers.CharField(source='accountid.gstno', read_only=True)
    shiptoname = serializers.CharField(source='shippedto.accountname', read_only=True)
    shiptoaddress1 = serializers.CharField(source='shippedto.address1', read_only=True)
    shiptoaddress2 = serializers.CharField(source='shippedto.address2', read_only=True)
    shiptostate = serializers.CharField(source='shippedto.state.statename', read_only=True)
    shiptocity = serializers.CharField(source='shippedto.city.cityname', read_only=True)
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
    gst_summary = serializers.SerializerMethodField()

    class Meta:
        model = SalesOderHeader
        fields = (
            'id', 'sorderdate', 'billno', 'accountid', 'billtoname', 'billtoaddress1',
             'billtoaddress2','billtocity','billtostate','billtogst','billtopan',
            'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype', 'billcash', 'supply',
            'totalquanity', 'totalpieces', 'advance', 'shiptostate', 'shiptoname','shiptocity','shiptoaddress1','shiptoaddress2','shiptopan','shiptogst',
            'remarks', 'transport', 'broker', 'taxid', 'tds194q', 'tds194q1', 'tcs206c1ch1',
            'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1', 'tcs206C2', 'addless', 'duedate','stbefdiscount','discount', 'subtotal',
            'cgst', 'sgst', 'igst', 'cess', 'totalgst', 'expenses', 'gtotal', 'amountinwords',
            'subentity', 'entity', 'entityname', 'entityaddress','entitycityname','entitystate','entitypincode', 'entitygst', 'createdby', 'eway',
            'einvoice', 'einvoicepluseway', 'isactive', 'phoneno', 'phoneno2', 'entitydesc','reversecharge','bankname','bankacno','ifsccode','transportname',
            'entitypan', 'saleInvoiceDetails','gst_summary'
        )

   

    

    def get_amountinwords(self, obj):
        return f"{string.capwords(num2words(obj.gtotal))} only"

    def get_gst_summary(self, obj):
        """
        Fetch and serialize GST summary data for the sales order header.
        """
        salesorderheader_id = obj.id
        aggregated_data = (
            salesOrderdetails.objects.filter(salesorderheader_id=salesorderheader_id)
            .values("salesorderheader")
            .annotate(
                taxPercent=Case(
                    When(igstpercent=0, then=F("cgstpercent") + F("sgstpercent")),
                    default=F("igstpercent"),
                    output_field=FloatField(),
                ),
                taxable_amount=Sum("amount", filter=Q(sgstpercent__isnull=False)),
                total_cgst_amount=Sum("cgst", filter=Q(sgstpercent__isnull=False)),
                total_sgst_amount=Sum("sgst", filter=Q(sgstpercent__isnull=False)),
                total_igst_amount=Sum("igst", filter=Q(igstpercent__isnull=False)),
            )
        )
        return list(aggregated_data)
    
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
   # productname = serializers.SerializerMethodField()

    class Meta:
        model = purchaseorderimport
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','igst','cess','expenses','gtotal','importgtotal','entityfinid','entity','isactive','PurchaseOrderimportdetails',)


    
    


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
        fields = ['voucherdate','voucherno','account','billno','billdate','showledgeraccount','terms','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','igst','cess','expenses','gtotal','importgtotal','entityfinid','entity','isactive']
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


    















class salesOrderdetailsSerializer(serializers.ModelSerializer):
    # Assume that the 'otherchargesdetail' has a related field and needs optimization
    otherchargesdetail = salesotherdetailsSerializer(many=True, required=False)
    id = serializers.IntegerField(required=False)
    productname = serializers.CharField(source='product.productname', read_only=True)
    hsn = serializers.CharField(source='product.hsn.hsnCode', read_only=True)
    mrp = serializers.FloatField(source='product.mrp', read_only=True)

    class Meta:
        model = salesOrderdetails
        fields = (
            'id', 'product', 'productname', 'hsn', 'mrp', 'productdesc', 'orderqty', 'pieces','befDiscountProductAmount','ratebefdiscount','orderDiscount','orderDiscountValue',
            'rate', 'amount', 'othercharges', 'cgst', 'sgst', 'igst','isigst','cgstpercent', 'sgstpercent', 'igstpercent', 'cess', 'linetotal', 
            'subentity', 'entity', 'otherchargesdetail',
        )

    def to_representation(self, instance):
        # Prefetch related data in the 'to_representation' method for optimization
        # Prefetch related 'otherchargesdetail' to reduce query load
        if hasattr(self, 'context') and 'request' in self.context:
            queryset = salesOrderdetails.objects.prefetch_related(
                Prefetch('otherchargesdetail', queryset=saleothercharges.objects.all())
            ).get(id=instance.id)
            
            # Call parent class method to serialize optimized queryset data
            
            return super().to_representation(queryset)
        
        return super().to_representation(instance)
    

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
        fields = ('id','orderdate','billno','account','taxtype','billcash','grno','vehicle','orderType','totalgst','subtotal','expensesbeforetax','cgst','sgst','igst','igstreverse','cgstreverse','sgstreverse','multiplier','expensesaftertax','gtotal','remarks','entityfinid', 'entity','createdby','gstorderservicesdetails','isactive',)


    

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
        fields = ['orderdate','billno','account','taxtype','billcash','grno','vehicle','orderType','totalgst','subtotal','expensesbeforetax','cgst','sgst','igst','igstreverse','cgstreverse','sgstreverse','multiplier','expensesaftertax','gtotal','remarks','entityfinid', 'entity','createdby',]
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


class SalesOderHeaderSerializer(serializers.ModelSerializer):
    saleInvoiceDetails = salesOrderdetailsSerializer(many=True)
    class Meta:
        model = SalesOderHeader
        fields = ('id','sorderdate','billno','accountid','latepaymentalert','grno','terms','vehicle','taxtype','billcash','supply','totalquanity','totalpieces','advance','shippedto','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','addless', 'duedate','stbefdiscount', 'subtotal','discount','cgst','sgst','igst','isigst','invoicetype','reversecharge','cess','totalgst','expenses','gtotal','entityfinid','subentity','entity','createdby','eway','einvoice','einvoicepluseway','isactive','saleInvoiceDetails',)


    

    def create(self, validated_data):
        with transaction.atomic():
            sales_order_details_data = validated_data.pop('saleInvoiceDetails')
            validated_data.pop('billno')

            # Get the last order's billno for the same entity and increment it by 1
            last_order = SalesOderHeader.objects.filter(entity=validated_data['entity'].id).last()
            billno2 = last_order.billno + 1 if last_order else 1

            # Create the sales order header
            order = SalesOderHeader.objects.create(**validated_data, billno=billno2)

            # Initialize stock transaction
            stk = stocktransactionsale(order, transactiontype='S', debit=1, credit=0, description='By Sale Bill No: ', entrytype='I')

            # Process each sales order detail
            for order_detail_data in sales_order_details_data:
                sales_order_other_charges = order_detail_data.pop('otherchargesdetail')

                # Create sales order detail and link to the order
                detail = salesOrderdetails.objects.create(salesorderheader=order, **order_detail_data)

                # Create stock transaction for the detail
                stk.createtransactiondetails(detail=detail, stocktype='S')

                # Process other charges related to the detail
                for other_charge_data in sales_order_other_charges:
                    sale_other_charge = saleothercharges.objects.create(salesorderdetail=detail, **other_charge_data)
                    stk.createothertransactiondetails(detail=sale_other_charge, stocktype='S')

            # Finalize the stock transaction
            stk.createtransaction()

            # Create the e-invoice
            einvoice = einvoicebody(order, invoicetype='INV')
            einvoice.createeinvoce()

            return order

    def update(self, instance, validated_data):
        fields = [
            'sorderdate', 'billno', 'accountid', 'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype', 'billcash',
            'supply', 'totalquanity', 'totalpieces', 'advance', 'shippedto', 'remarks', 'transport', 'broker', 'taxid',
            'tds194q', 'tds194q1', 'tcs206c1ch1', 'tcs206c1ch2', 'tcs206c1ch3', 'tcs206C1', 'tcs206C2', 'addless',
            'duedate','stbefdiscount', 'subtotal', 'discount', 'cgst', 'sgst', 'igst','isigst','invoicetype','reversecharge', 'cess', 'totalgst', 'expenses', 'gtotal', 'isactive',
            'eway', 'einvoice', 'einvoicepluseway', 'entityfinid', 'subentity', 'entity', 'createdby',
        ]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass

        with transaction.atomic():
            instance.save()
            stk = stocktransactionsale(instance, transactiontype='S', debit=1, credit=0, description='By Sale Bill No:', entrytype='U')
            salesOrderdetails.objects.filter(salesorderheader=instance, entity=instance.entity).delete()
            stk.createtransaction()

            salesOrderdetails_data = validated_data.get('saleInvoiceDetails')

            for PurchaseOrderDetail_data in salesOrderdetails_data:
                salesorderdetails_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = salesOrderdetails.objects.create(salesorderheader=instance, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail, stocktype='S')
                for salesorderdetail_data in salesorderdetails_data:
                    detail2 = saleothercharges.objects.create(salesorderdetail=detail, **salesorderdetail_data)
                    stk.createothertransactiondetails(detail=detail2, stocktype='S')

        #  stk.updateransaction()
        return instance

class SalesOrderSerializer(serializers.ModelSerializer):
    salesOrderDetail = saleOrderdetailsSerializer(many=True)

    class Meta:
        model = SalesOder
        fields = ('id', 'sorderdate', 'billno', 'accountid', 'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype',
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
        fields = ['sorderdate', 'billno', 'accountid', 'latepaymentalert', 'grno', 'terms', 'vehicle', 'taxtype',
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
    #entityUser = entityUserSerializer(many=True)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    otherchargesdetail = purchasereturnotherchargesSerializer(many=True)

    class Meta:
        model = Purchasereturndetails
        fields =  ('id','product','productname','productdesc','hsn','mrp','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','cess','isigst','cgstpercent','sgstpercent','igstpercent', 'linetotal','entity','otherchargesdetail',)

    def get_productname(self,obj):
        return obj.product.productname

    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode
    
    def get_mrp(self,obj):
        return obj.product.mrp


class PurchasereturnSerializer(serializers.ModelSerializer):
    purchasereturndetails = purchasereturndetailsSerializer(many=True)

    class Meta:
        model = PurchaseReturn
       # fields = ('id','sorderdate','billno','accountid','latepaymentalert','grno','vehicle','taxtype','billcash','supply','shippedto','remarks','transport','broker','tds194q','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','subtotal','subtotal','cgst','sgst','igst','expenses','gtotal','entity','owner','purchasereturndetails',)
        fields = ('id','sorderdate','billno','accountid','latepaymentalert','grno','terms','vehicle','taxtype','billcash','supply','totalquanity','totalpieces','advance','shippedto','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','addless', 'duedate','subtotal','invoicetype','reversecharge' , 'cgst','sgst','igst','cess','totalgst','expenses','gtotal','entityfinid','subentity','entity','createdby','isactive','purchasereturndetails',)


    def create(self, validated_data):
        #print(validated_data)

        
        salesOrderdetails_data = validated_data.pop('purchasereturndetails')
        validated_data.pop('billno')
        if PurchaseReturn.objects.filter(entity= validated_data['entity'].id).count() == 0:
                billno2 = 1
        else:
                billno2 = (PurchaseReturn.objects.filter(entity= validated_data['entity'].id).last().billno) + 1
        with transaction.atomic():
            order = PurchaseReturn.objects.create(**validated_data,billno = billno2)
            stk = stocktransactionsale(order, transactiontype= 'PR',debit=1,credit=0,description= 'Purchase Return',entrytype= 'I')
            #print(tracks_data)
            
            for PurchaseOrderDetail_data in salesOrderdetails_data:
                otherchargesdetail = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = Purchasereturndetails.objects.create(purchasereturn = order, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='S')
                for otherchargedetail in otherchargesdetail:
                    detail = Purchasereturnothercharges.objects.create(purchasereturnorderdetail = detail, **otherchargedetail)

                

            stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['sorderdate','billno','accountid','latepaymentalert','grno','terms','vehicle','taxtype','billcash','supply','totalquanity','totalpieces','advance','shippedto','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','addless', 'duedate','subtotal','cgst','sgst','igst','cess','totalgst','expenses','gtotal','entityfinid','subentity','entity','createdby','isactive',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        with transaction.atomic():
            instance.save()
            stk = stocktransactionsale(instance, transactiontype= 'PR',debit=1,credit=0,description= 'Purchase Return',entrytype= 'I')
            stk.createtransaction()

            Purchasereturndetails.objects.filter(purchasereturn=instance,entity = instance.entity).delete()

            salesOrderdetails_data = validated_data.get('purchasereturndetails')

            for PurchaseOrderDetail_data in salesOrderdetails_data:
                otherchargesdetail = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = Purchasereturndetails.objects.create(purchasereturn = instance, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='S')
                for otherchargedetail in otherchargesdetail:
                    detail = Purchasereturnothercharges.objects.create(purchasereturnorderdetail = detail, **otherchargedetail)

        
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
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','ordertype','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','entity','isactive','jobworkchalanDetails',)


    
    


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
        fields = ['voucherdate','voucherno','account','billno','billdate','showledgeraccount','terms','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','ordertype', 'grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','entity','isactive']
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




class PurchaseOrderDetailsSerializer(serializers.ModelSerializer):
    otherchargesdetail = purchaseotherdetailsSerializer(many=True,required=False)
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
   # productdesc1 = serializers.SerializerMethodField()
    #entityUser = entityUserSerializer(many=True)

    class Meta:
        model = PurchaseOrderDetails
        fields = ('id','product','productname','productdesc','hsn','mrp','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','cess','cgstpercent','sgstpercent','igstpercent','isigst','linetotal','subentity','entity','otherchargesdetail',)
    
    def get_productname(self,obj):
        return obj.product.productname
    
    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode

    def get_mrp(self,obj):
        return obj.product.mrp
    






    




class PurchaseOrderAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderAttachment
        fields = ['id', 'purchase_order', 'file', 'uploaded_at']


class purchaseorderSerializer(serializers.ModelSerializer):
    purchaseInvoiceDetails = PurchaseOrderDetailsSerializer(many=True)
    attachments = PurchaseOrderAttachmentSerializer(many=True,required=False, allow_null=True)
   # productname = serializers.SerializerMethodField()

    class Meta:
        model = purchaseorder
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','reversecharge','invoicetype','cess','expenses','gtotal','entityfinid','subentity','entity','isactive','purchaseInvoiceDetails','attachments',)


    
    


    def create(self, validated_data):
       # print(validated_data)
        PurchaseOrderDetails_data = validated_data.pop('purchaseInvoiceDetails')
        with transaction.atomic():
            order = purchaseorder.objects.create(**validated_data)
            stk = stocktransaction(order, transactiontype= 'P',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype= 'I')
            #print(order.objects.get("id"))
            #print(tracks_data)
            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
                purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = PurchaseOrderDetails.objects.create(purchaseorder = order, **PurchaseOrderDetail_data)
                for purchaseothercharge_data in purchaseothercharges_data:
                    detail1 = purchaseothercharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                    stk.createothertransactiondetails(detail=detail1,stocktype='P')

            
                stk.createtransactiondetails(detail=detail,stocktype='P')
                
            
            stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','account','billno','billdate','showledgeraccount','terms','taxtype','reversecharge','invoicetype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity', 'entity','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        

        # print(instance.id)
        stk = stocktransaction(instance, transactiontype= 'P',debit=1,credit=0,description= 'To Purchase V.No: ',entrytype='U')
        with transaction.atomic():
            stk.createtransaction()
            
            i = instance.save()

            PurchaseOrderDetails.objects.filter(purchaseorder=instance,entity = instance.entity).delete()
        
            PurchaseOrderDetails_data = validated_data.get('purchaseInvoiceDetails')

            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
                purchaseothercharges_data = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = PurchaseOrderDetails.objects.create(purchaseorder = instance, **PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='P')
                for purchaseothercharge_data in purchaseothercharges_data:
                  
                    detail1 = purchaseothercharges.objects.create(purchaseorderdetail = detail, **purchaseothercharge_data)
                    stk.createothertransactiondetails(detail=detail1,stocktype='P')

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
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity','entity','isactive','purchaseorderdetails',)


    
    


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
        fields = ['voucherdate','voucherno','account','billno','billdate','showledgeraccount','terms','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity', 'entity','isactive']
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





class   cbserializer(serializers.ModelSerializer):


   # cashtrans = stocktranserilaizer(source = 'account_transactions', many=True, read_only=True)

    openingbalance  = serializers.SerializerMethodField()
    reciept  = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    entrydate = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    reciepts = serializers.SerializerMethodField()
    cashinhand = serializers.SerializerMethodField()
    reciepttotal = serializers.SerializerMethodField()
    paymenttotal = serializers.SerializerMethodField()





   # stk = stocktranserilaizer(many=True, read_only=True)
   # select_related_fields = ('accounthead')

    # debit  = serializers.SerializerMethodField()
   # day = serializers.CharField()

    class Meta:
        model = entry
        fields = ['id','entrydate','openingbalance','cashinhand','reciept','payment','reciepttotal','paymenttotal', 'payments','reciepts']

    def get_reciept(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.cashtrans.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']

    def get_payment(self, obj):
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return obj.cashtrans.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']

    def get_openingbalance(self, obj):

        yesterday = obj.entrydate1 - timedelta(days = 1)
        startdate = obj.entrydate1 - timedelta(days = 200)
        debit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']
        credit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']
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

    
    def get_cashinhand(self, obj):

        yesterday = obj.entrydate1 - timedelta(days = 1)
        startdate = obj.entrydate1 - timedelta(days = 200)
        debit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('debitamount'))['debitamount__sum']
        credit = StockTransactions.objects.filter(account__accountcode = 4000,accounttype = 'CIH',iscashtransaction = True,entry__entrydate1__range = (startdate,yesterday),entity = obj.entity,isactive = 1).aggregate(Sum('creditamount'))['creditamount__sum']
        # debit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('debitamount'))['debitamount__sum']
        # credit = obj.cashtrans.filter(accounttype = 'CIH').aggregate(Sum('creditamount'))['creditamount__sum']
        if not debit:
            debit = 0
        if not credit:
            credit = 0
        if not self.get_reciept(obj=obj):
            reciept = 0
        else:
            reciept = self.get_reciept(obj=obj)

        if not self.get_payment(obj=obj):
            payment = 0
        else:
            payment = self.get_payment(obj=obj)



        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return debit - credit + reciept - payment

    def get_entrydate(self,obj):
        return obj.entrydate1.strftime("%d-%m-%Y")

    def get_reciepttotal(self, obj):

        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

        if not self.get_openingbalance(obj):
            balance = 0
        else:
            balance = self.get_openingbalance(obj)
        
        if not self.get_reciept(obj):
            reciept = 0
        else:
            reciept = self.get_reciept(obj)




       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return balance + reciept

    
    def get_paymenttotal(self, obj):

        if not self.get_cashinhand(obj):
            cashinhand = 0
        else:
            cashinhand =self.get_cashinhand(obj)
        
        if not self.get_payment(obj):
            payment = 0
        else:
            payment = self.get_payment(obj)


        # yesterday = obj.entrydate1 - timedelta(days = 0)
        # startdate = obj.entrydate1 - timedelta(days = 10)

       # print(obj.cashtrans('account'))
        # fromDate = parse_datetime(self.context['request'].query_params.get(
        #     'fromDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        # toDate = parse_datetime(self.context['request'].query_params.get(
        #     'toDate') + ' ' + '00:00:00').strftime('%Y-%m-%d %H:%M:%S')
        return cashinhand + payment

    def get_reciepts(self,obj):
        print(self.context['request'])
        
        #stock =  obj.cashtrans.filter(drcr = False).order_by('account')
       # print(stock)

        stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = False,accounttype__in = ['M'],isactive = 1,iscashtransaction= 1)
        #return account1Serializer(accounts,many=True).data
        return stocktranserilaizer(stock, many=True).data

    
    def get_payments(self,obj):
        stock = obj.cashtrans.filter(account__in = obj.cashtrans.values('account'),drcr = True,accounttype__in = ['M'],isactive = 1,iscashtransaction= 1)
        #return account1Serializer(accounts,many=True).data
        return stocktranserilaizer(stock, many=True).data






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




class salesreturnDetailsSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    productname = serializers.SerializerMethodField()
    hsn = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    otherchargesdetail = salereturnotherchargesSerializer(many=True)
    #entityUser = entityUserSerializer(many=True)

    class Meta:
        model = salereturnDetails
        fields = ('id','product','productname','hsn','mrp','productdesc','orderqty','pieces','rate','amount','othercharges','cgst','sgst','igst','isigst','cgstpercent','sgstpercent','igstpercent', 'cess','linetotal','entity','otherchargesdetail',)

    def get_productname(self,obj):
        return obj.product.productname

    def get_hsn(self,obj):
        return obj.product.hsn.hsnCode

    def get_mrp(self,obj):
        return obj.product.mrp




class salesreturnSerializer(serializers.ModelSerializer):
    salereturndetails = salesreturnDetailsSerializer(many=True)

    class Meta:
        model = salereturn
        fields = ('id','voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','invoicetype','reversecharge' ,'addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity','entity','isactive','salereturndetails',)

    
    

 
    def create(self, validated_data):
        #print(validated_data)
        PurchaseOrderDetails_data = validated_data.pop('salereturndetails')

        print(validated_data.get('account'))
        with transaction.atomic():
            order = salereturn.objects.create(**validated_data)
            stk = stocktransaction(order, transactiontype= 'SR',debit=1,credit=0,description= 'Sale Return',entrytype= 'I')
            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
                otherchargesdetail = PurchaseOrderDetail_data.pop('otherchargesdetail')
                
                detail = salereturnDetails.objects.create(salereturn = order,**PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='P')
                for otherchargedetail in otherchargesdetail:
                    detail2 = salereturnothercharges.objects.create(salesreturnorderdetail = detail,**otherchargedetail)
                    stk.createothertransactiondetails(detail=detail2,stocktype='P')
            
            
            stk.createtransaction()
        return order

    def update(self, instance, validated_data):
        fields = ['voucherdate','voucherno','account','billno','billdate','terms','showledgeraccount','taxtype','billcash','totalpieces','totalquanity','advance','remarks','transport','broker','taxid','tds194q','tds194q1','tcs206c1ch1','tcs206c1ch2','tcs206c1ch3','tcs206C1','tcs206C2','duedate','inputdate','vehicle','grno','gstr2astatus','subtotal','addless','cgst','sgst','igst','cess','expenses','gtotal','entityfinid','subentity','entity','isactive']
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        print(instance)
        stk = stocktransaction(instance, transactiontype= 'SR',debit=1,credit=0,description= 'updated',entrytype= 'U')
        with transaction.atomic():
            stk.createtransaction()
            instance.save()
            salereturnDetails.objects.filter(salereturn=instance,entity = instance.entity).delete()

            PurchaseOrderDetails_data = validated_data.get('salereturndetails')

            for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
                otherchargesdetail = PurchaseOrderDetail_data.pop('otherchargesdetail')
                detail = salereturnDetails.objects.create(salereturn = instance,**PurchaseOrderDetail_data)
                stk.createtransactiondetails(detail=detail,stocktype='P')
                for otherchargedetail in otherchargesdetail:
                    detail2 = salereturnothercharges.objects.create(salesreturnorderdetail = detail,**otherchargedetail)
                    stk.createothertransactiondetails(detail=detail2,stocktype='P')

        

        
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















