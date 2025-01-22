from sys import implementation
from rest_framework import serializers
from rest_framework.fields import ChoiceField
from financial.models import accountHead,account,accounttype
from invoice.models import entry,StockTransactions
from entity.models import Entity,entityfinancialyear

from geography.serializers import CityListSerializer
import os
from django.db import transaction


class AccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = account
        fields = (
            'id', 'accountcode', 'accountdate', 'accounthead', 'gstno', 'creditaccounthead', 'accountname',
            'legalname', 'address1', 'address2', 'addressfloorno', 'addressstreet', 'gstintype', 'blockstatus',
            'dateofreg', 'dateofdreg', 'country', 'state', 'district', 'city', 'openingbcr', 'openingbdr',
            'contactno', 'pincode', 'emailid', 'agent', 'pan', 'tobel10cr', 'approved', 'tdsno', 'entity', 'rtgsno',
            'bankname', 'Adhaarno', 'saccode', 'contactperson', 'deprate', 'tdsrate', 'gstshare', 'quanity1',
            'quanity2', 'BanKAcno', 'composition', 'accounttype', 'owner',
        )

    def create(self, validated_data):
        # Use a transaction to ensure atomicity of the entire operation
        with transaction.atomic():
            entity = validated_data['entity']
            accountcode = self._generate_account_code(entity)

            # Create account instance
            detail = account.objects.create(**validated_data, accountcode=accountcode)

            # Get the financial year start date
            accountdate1 = entityfinancialyear.objects.get(entity=detail.entity).finstartyear

            # Create entry if not exists
            entryid, created = entry.objects.get_or_create(entrydate1=accountdate1, entity=detail.entity)

            # Handle opening balances
            self._handle_opening_balances(detail, entryid, accountdate1)

        return detail

    def update(self, instance, validated_data):
        fields = [
            'accountdate', 'accounthead', 'gstno', 'creditaccounthead', 'accountname', 'legalname', 'address1',
            'address2', 'addressfloorno', 'addressstreet', 'gstintype', 'blockstatus', 'dateofreg', 'dateofdreg',
            'country', 'state', 'district', 'city', 'openingbcr', 'openingbdr', 'contactno', 'pincode', 'emailid',
            'agent', 'pan', 'tobel10cr', 'approved', 'tdsno', 'entity', 'rtgsno', 'bankname', 'Adhaarno', 'saccode',
            'contactperson', 'deprate', 'tdsrate', 'gstshare', 'quanity1', 'quanity2', 'BanKAcno', 'accounttype',
            'composition', 'owner'
        ]
        
        # Update instance fields
        for field in fields:
            setattr(instance, field, validated_data.get(field, getattr(instance, field)))

        # Save updated instance
        instance.save()

        # Handle stock transactions for opening balances
        StockTransactions.objects.filter(entity=instance.entity, transactionid=instance.id, transactiontype='OA').delete()

        # Handle opening balances after update
        self._handle_opening_balances(instance, entry.objects.get_or_create(entrydate1=instance.accountdate, entity=instance.entity)[0], instance.accountdate)

        return instance

    def _generate_account_code(self, entity):
        """
        Helper method to generate the next account code based on the entity.
        """
        last_account = account.objects.filter(entity=entity).last()
        return last_account.accountcode + 1 if last_account else 1

    def _handle_opening_balances(self, detail, entryid, accountdate1):
        """
        Handle the creation of stock transactions for opening balances (both debit and credit).
        """
        if detail.openingbcr > 0 or detail.openingbdr > 0:
            drcr = 0 if detail.openingbcr > 0 else 1

            # Create debit/credit stock transactions based on opening balances
            StockTransactions.objects.create(
                accounthead=detail.accounthead, account=detail, transactiontype='O', transactionid=detail.id,
                desc='Opening Balance', drcr=drcr, debitamount=detail.openingbdr, creditamount=detail.openingbcr,
                entity=detail.entity, createdby=detail.owner, entry=entryid, entrydatetime=accountdate1,
                accounttype='M', isactive=1
            )
        

class accountcodeSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newcode = serializers.SerializerMethodField()

    def get_newcode(self, obj):
        if not obj.accountcode:
            return 1
        else:
            return obj.accountcode + 1


    class Meta:
        model = account
        fields =  ['newcode']




class AccountListSerializer(serializers.ModelSerializer):
    debit = serializers.DecimalField(max_digits=10, decimal_places=2)
    credit = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2)
    daccountheadname = serializers.CharField(max_length=500, source='accounthead.name')
    caccountheadname = serializers.CharField(max_length=500, source='creditaccounthead.name')
    cityname = serializers.CharField(max_length=500, source='city.cityname')
    accountid = serializers.IntegerField(source='id')
    accgst = serializers.CharField(max_length=500, source='gstno')
    accpan = serializers.CharField(max_length=500, source='pan')
    accanbedeleted = serializers.BooleanField(source='canbedeleted')

    class Meta:
        model = account
        fields = (
            'accountname', 'debit', 'credit', 'accgst', 'accpan', 'cityname', 'accountid',
            'daccountheadname', 'caccountheadname', 'accanbedeleted', 'balance'
        )

    @classmethod
    def setup_eager_loading(cls, queryset):
        """
        Optimize database queries by using select_related for related fields.
        This minimizes the number of database queries by retrieving all related fields
        in a single query.
        """
        return queryset.select_related(
            'accounthead', 'creditaccounthead', 'city'
        )

  
    
   
        



class accountSerializer2(serializers.ModelSerializer):

    

    class Meta:
        model = account
        fields =  ('id', 'accounthead','accountname','accountcode','city','gstno','pan','saccode',)



class accountSerializerservices(serializers.ModelSerializer):

    

    class Meta:
        model = account
        fields =  ('id', 'accounthead','accountname','accountcode','city','gstno','pan','saccode',)
    



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


class accountservicesSerializeraccounts(serializers.ModelSerializer):
    accounthead_accounts = accountSerializerservices(many= True)
    class Meta:
        model = accountHead
        fields = ('code','accounthead_accounts')
        #depth = 1






class AccountHeadSerializer(serializers.ModelSerializer):
    accountHeadName = serializers.SerializerMethodField()
    accounthead_accounts = AccountSerializer(many=True)

    class Meta:
        model = accountHead
        fields = (
            'id', 'name', 'code', 'detailsingroup', 'balanceType',
            'drcreffect', 'description', 'accountheadsr', 'entity',
            'accountHeadName', 'accounthead_accounts',
        )

    def get_accountHeadName(self, obj):
        """
        Retrieves the name of the associated account head if it exists.
        Returns 'null' if accountheadsr is None.
        """
        return obj.accountheadsr.name if obj.accountheadsr else 'null'

    def create(self, validated_data):
        """
        Handles the creation of an account head and associated accounts.
        """
        # Extract nested account details and other fields
        account_details_data = validated_data.pop('accounthead_accounts', [])
        entity = validated_data.get('entity')
        user = validated_data.get('owner')
        account_date = validated_data.pop("acountdate", None)

        # Create the account head
        account_head_instance = accountHead.objects.create(**validated_data)

        # Bulk create related accounts
        accounts_to_create = [
            account(
                accounthead=account_head_instance,
                entity=entity,
                owner=user,
                accountdate=account_date,
                **detail_data
            )
            for detail_data in account_details_data
        ]
        account.objects.bulk_create(accounts_to_create)

        return account_head_instance


class accountHeadSerializer2(serializers.ModelSerializer):  
    accountHeadName = serializers.SerializerMethodField()
    detailsingroupName = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ('id', 'name', 'code', 'detailsingroup', 'balanceType', 'drcreffect', 
                  'description', 'accountheadsr', 'entity', 'accountHeadName', 
                  'detailsingroupName', 'canbedeleted')

    def get_accountHeadName(self, obj):
        # Return the name of accountHeadSr or 'null' if it is None
        return obj.accountheadsr.name if obj.accountheadsr else 'null'

    def get_detailsingroupName(self, obj):
        # Return the corresponding group name based on detailsingroup value
        group_names = {
            1: 'Trading Account',
            2: 'Income and Expenses'
        }
        return group_names.get(obj.detailsingroup, 'Balance Sheet') 
        
class accounttypeserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = accounttype
        fields = ('id','accounttypename','accounttypecode',)
           


        
  
    
    

    




