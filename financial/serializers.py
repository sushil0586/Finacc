from sys import implementation
from rest_framework import serializers
from rest_framework.fields import ChoiceField
from financial.models import accountHead,account

from geography.serializers import countrySerializer
import os


class accountSerializer(serializers.ModelSerializer):

    

    class Meta:
        model = account
        fields =  '__all__'



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

    detilsinbs = ChoiceField(choices=accountHead.Details_in_BS)
   # accountHeadMain = accountHeadMainSerializer(many=True)
    accountHeadName = serializers.SerializerMethodField()
  
    #balanceType = ChoiceField(choices=accountHead.BALANCE_TYPE)

    accounthead_accounts = accountSerializer(many= True)
    

    class Meta:
        model = accountHead
        fields = ('id','name','code','detilsinbs','balanceType','drcreffect','description','accountheadsr','group','entity','accountHeadName','accounthead_accounts',)
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

    detilsinbs = ChoiceField(choices=accountHead.Details_in_BS)
   # accountHeadMain = accountHeadMainSerializer(many=True)
    accountHeadName = serializers.SerializerMethodField()
  
    #balanceType = ChoiceField(choices=accountHead.BALANCE_TYPE)

   # accounthead_accounts = accountSerializer(many= True)
    

    class Meta:
        model = accountHead
        fields = ('id','name','code','detilsinbs','balanceType','drcreffect','description','accountheadsr','group','entity','accountHeadName',)
        #depth = 1


    def get_accountHeadName(self,obj):
       # acc =  obj.accountHeadSr.name
        if obj.accountheadsr is None:
            return 'null'   
        else :
            return obj.accountheadsr.name


        
  
    
    

    




