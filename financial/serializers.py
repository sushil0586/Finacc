from sys import implementation
from rest_framework import serializers
from rest_framework.fields import ChoiceField
from financial.models import accountHead,account
from invoice.models import entry,StockTransactions

from geography.serializers import countrySerializer
import os


class accountSerializer(serializers.ModelSerializer):

    

    class Meta:
        model = account
        fields =  ('__all__')

    def create(self, validated_data):
        #print(validated_data)
        #journaldetails_data = validated_data.pop('journaldetails')
        detail = account.objects.create(**validated_data)
        entryid,created  = entry.objects.get_or_create(entrydate1 = detail.created_at,entity=detail.entity)

        if detail.openingbcr > 0 or detail.openingbdr > 0:
            if (detail.openingbcr >0.00):
                    drcr = 0
            else:
                    drcr = 1
            details = StockTransactions.objects.create(accounthead= detail.accounthead,account= detail,transactiontype = 'OA',transactionid = detail.id,desc = 'Opening Balance',drcr=drcr,debitamount=detail.openingbdr,creditamount=detail.openingbcr,entity=detail.entity,createdby= detail.owner,entry = entryid,entrydatetime = detail.created_at,accounttype = 'M',isactive = 1)
            #return detail
        return detail

    def update(self, instance, validated_data):

        print('abc')
        fields = ['accounthead','creditaccounthead','accountcode','gstno','accountname','address1','address2','country','state','district','city','openingbcr','openingbdr','contactno','pincode','emailid','agent','pan','tobel10cr','approved','tdsno','entity','accountno','rtgsno','bankname','Adhaarno','saccode','contactperson','deprate','tdsrate','gstshare','quanity1','quanity2','BanKAcno','composition','owner',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        # with transaction.atomic():
        instance.save()
        entryid,created  = entry.objects.get_or_create(entrydate1 = instance.created_at,entity=instance.entity)
        #     entryid,created  = entry.objects.get_or_create(entrydate1 = instance.voucherdate,entity=instance.entityid)
        StockTransactions.objects.filter(entity = instance.entity,transactionid = instance.id,transactiontype = 'OA').delete()

        drcr = 0

        if instance.openingbcr is None:
            instance.openingbcr = 0
        
        if instance.openingbdr is None:
            instance.openingbdr = 0
            

        if instance.openingbcr > 0:
            drcr = 0
            StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)
        if instance.openingbdr > 0:
            drcr = 1
            StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)



        
        #details = StockTransactions.objects.create(accounthead= instance.accounthead,account= instance,transactiontype = 'OA',transactionid = instance.id,desc = 'Opening Balance',drcr=drcr,debitamount=instance.openingbdr,creditamount=instance.openingbcr,entity=instance.entity,createdby= instance.owner,entrydatetime = instance.created_at,accounttype = 'M',isactive = 1,entry = entryid)
        #     StockTransactions.objects.create(accounthead= instance.creditaccountid.accounthead,account= instance.creditaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=1,debitamount=instance.grandtotal,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')
        #     StockTransactions.objects.create(accounthead= instance.debitaccountid.accounthead,account= instance.debitaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=1,debitamount=instance.debitamount,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')
        #     StockTransactions.objects.create(accounthead= instance.tdsaccountid.accounthead,account= instance.tdsaccountid,transactiontype = 'T',transactionid = instance.id,desc = 'By Tds Voucher no ' + str(instance.voucherno),drcr=0,creditamount=instance.grandtotal,entity=instance.entityid,createdby= instance.createdby,entry =entryid,entrydatetime = instance.voucherdate,accounttype = 'M')

        return instance
        




class accountListSerializer(serializers.ModelSerializer):



    debit = serializers.DecimalField(max_digits=10,decimal_places=2)
    credit = serializers.DecimalField(max_digits=10,decimal_places=2)
    balance = serializers.DecimalField(max_digits=10,decimal_places=2)
    daccountheadname =  serializers.CharField(max_length=500,source = 'accounthead__name')
    caccountheadname =  serializers.CharField(max_length=500,source = 'creditaccounthead__name')
   # accountHeadName = serializers.SerializerMethodField()
    

   # accounttype = serializers.CharField(max_length=500,source = 'accounttrans__accounttype')
   # gstno = serializers.CharField(max_length=500)
   # pan = serializers.CharField(max_length=500)
    cityname = serializers.CharField(max_length=500,source = 'city__cityname')
    accountid = serializers.IntegerField(source = 'id')
    accgst = serializers.CharField(max_length=500,source = 'gstno')
    accpan = serializers.CharField(max_length=500,source = 'pan')
    
    accanbedeleted = serializers.BooleanField(source = 'canbedeleted')

    

    




    

    class Meta:
        model = account
        fields =  ('accountname','debit','credit','accgst','accpan','cityname','accountid','daccountheadname','caccountheadname','accanbedeleted','balance',)

  
    
   
        



class accountSerializer2(serializers.ModelSerializer):

    

    class Meta:
        model = account
        fields =  ('id', 'accounthead','accountname','accountcode','city','gstno','pan',)
    



class accountHeadMainSerializer(serializers.ModelSerializer):

    #detilsinbs = ChoiceField(choices=accountHead.Details_in_BS)
    
    #accountHeadName = serializers.SerializerMethodField()
  
    #balanceType = ChoiceField(choices=accountHead.BALANCE_TYPE)

   
    

    class Meta:
        model = accountHead
        fields = ('id','name',)
        #depth = 1


class accountHeadSerializeraccounts(serializers.ModelSerializer):
    accounthead_accounts = accountSerializer2(many= True)
    class Meta:
        model = accountHead
        fields = ('code','accounthead_accounts')
        #depth = 1





class accountHeadSerializer(serializers.ModelSerializer):

   # detilsinbs = ChoiceField(choices=accountHead.Details_in_BS)
   # accountHeadMain = accountHeadMainSerializer(many=True)
    accountHeadName = serializers.SerializerMethodField()
  
    #balanceType = ChoiceField(choices=accountHead.BALANCE_TYPE)

    accounthead_accounts = accountSerializer(many= True)
    

    class Meta:
        model = accountHead
        fields = ('id','name','code','detailsingroup','balanceType','drcreffect','description','accountheadsr','entity','accountHeadName','accounthead_accounts',)
        #depth = 1


    def get_accountHeadName(self,obj):
       # acc =  obj.accountHeadSr.name
        if obj.accountheadsr is None:
            return 'null'   
        else :
            return obj.accountheadsr.name

    def create(self, validated_data):
        #print(validated_data)
        entity1 = validated_data.get('entity')
        user = validated_data.get('owner')

        PrchaseOrderDetails_data = validated_data.pop('accounthead_accounts')
        order = accountHead.objects.create(**validated_data)
       # print(tracks_data)
        for PurchaseOrderDetail_data in PrchaseOrderDetails_data:
             account.objects.create(accounthead = order,entity=entity1,owner = user, **PurchaseOrderDetail_data)
            
        return order


class accountHeadSerializer2(serializers.ModelSerializer):

    #detilsinbs = ChoiceField(choices=accountHead.Details_in_BS)
   # accountHeadMain = accountHeadMainSerializer(many=True)
    accountHeadName = serializers.SerializerMethodField()

    detailsingroupName = serializers.SerializerMethodField()
  
    #balanceType = ChoiceField(choices=accountHead.BALANCE_TYPE)

   # accounthead_accounts = accountSerializer(many= True)
    

    class Meta:
        model = accountHead
        fields = ('id','name','code','detailsingroup','balanceType','drcreffect','description','accountheadsr','entity','accountHeadName','detailsingroupName','canbedeleted',)
        #depth = 1


    def get_accountHeadName(self,obj):
       # acc =  obj.accountHeadSr.name
        if obj.accountheadsr is None:
            return 'null'   
        else :
            return obj.accountheadsr.name

    
    def get_detailsingroupName(self,obj):
       # acc =  obj.accountHeadSr.name
        if obj.detailsingroup == 1:
            return 'Trading Account'   
        elif obj.detailsingroup == 2:
            return 'Inome and Expenses'
        else:
            return 'Balance Sheet' 
           


        
  
    
    

    




