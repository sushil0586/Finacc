import imp
from itertools import product
from os import device_encoding
from pprint import isreadable
from select import select
from rest_framework import serializers
from invoice.models import SalesOderHeader,salesOrderdetails,purchaseorder,PurchaseOrderDetails,\
    journal,salereturn,salereturnDetails,Transactions,StockTransactions,PurchaseReturn,Purchasereturndetails,journalmain,journaldetails,entry,goodstransaction,stockdetails,stockmain,accountentry,purchasetaxtype,tdsmain,tdstype,productionmain,productiondetails,tdsreturns,gstorderservices,gstorderservicesdetails,jobworkchalan,jobworkchalanDetails,debitcreditnote,closingstock
from financial.models import account,accountHead
from inventory.models import Product
from entity.models import entityfinancialyear
from django.db.models import Sum,Count,F
from datetime import timedelta,date,datetime
from entity.models import entity
from django.db.models.functions import Abs
from num2words import num2words
import string
from django.db import  transaction
from django_filters.rest_framework import DjangoFilterBackend



class closingstockSerializer(serializers.ModelSerializer):

    class Meta:
        model = closingstock
        fields  = ('stockdate','stock','closingrate','entity',)


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

        currentdates = entityfinancialyear.objects.get(entity = obj.entity,isactive = 1)

        yesterday = currentdates.finstartyear

        startdate = datetime.strptime(self.context['request'].query_params.get('startdate'), '%Y-%m-%d') - timedelta(days = 1)
       
         
     
       
    
        quantity = obj.accounttrans.filter(account = obj.id,entry__entrydate1__gte  = yesterday, entry__entrydate1__lt  = startdate ,entity = obj.entity,isactive = 1).exclude(accounttype = 'MD').aggregate(Sum('quantity'))['quantity__sum']
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

        currentdates = entityfinancialyear.objects.get(entity = obj.entity,isactive = 1)

        yesterday = currentdates.finstartyear

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

class accountListSerializer(serializers.ModelSerializer):



    
   # accountname =  serializers.CharField(max_length=500,source = 'account__accountname')
    accountid =  serializers.CharField(max_length=500,source = 'account__id')
   

    class Meta:
        model = StockTransactions
        fields =  ('accountid',)