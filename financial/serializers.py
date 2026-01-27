from sys import implementation
from rest_framework import serializers
from rest_framework.fields import ChoiceField
from financial.models import accountHead,account,accounttype,ShippingDetails,staticacounts,staticacountsmapping,ContactDetails
from invoice.models import entry,StockTransactions
from entity.models import Entity,entityfinancialyear
from django.db import models
from django.db.models import Q, Sum
from financial.helper_posting import repost_opening_balance

from geography.serializers import CityListSerializer
import os
from django.db import transaction


class ShippingDetailsSerializer(serializers.ModelSerializer):
    """
    Single serializer for Create/Update/Get (optimized).
    - account is writable (for list-create endpoint)
    - id is read-only automatically
    """
    class Meta:
        model = ShippingDetails
        fields = (
            "id",
            "account",
            "entity",
            "gstno",
            "address1",
            "address2",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneno",
            "full_name",
            "emailid",
            "isprimary",
        )
        read_only_fields = ("id",)
        extra_kwargs = {
            "account": {"required": False, "allow_null": True},
            "entity": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        """
        Optional: prevent multiple primary on create/update at serializer level.
        (DB unique constraint already enforces it, but this gives cleaner error.)
        """
        isprimary = attrs.get("isprimary", None)

        # Resolve account for update vs create
        account = attrs.get("account", getattr(self.instance, "account", None))
        entity = attrs.get("entity", getattr(self.instance, "entity", None))

        if isprimary is True and account:
            qs = ShippingDetails.objects.filter(account=account, isprimary=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"isprimary": "Primary shipping address already exists for this account."}
                )

        # If entity not provided, inherit from account if possible
        # (only if your Account model has entity FK)
        if entity is None and account and getattr(account, "entity_id", None):
            attrs["entity"] = account.entity

        return attrs


class ShippingDetailsListSerializer(serializers.ModelSerializer):
    """
    List serializer with denormalized names.
    Uses source= instead of SerializerMethodField (faster & cleaner).
    """
    countryName = serializers.CharField(source="country.countryname", read_only=True, allow_null=True)
    stateName = serializers.CharField(source="state.statename", read_only=True, allow_null=True)
    districtName = serializers.CharField(source="district.districtname", read_only=True, allow_null=True)
    cityName = serializers.CharField(source="city.cityname", read_only=True, allow_null=True)

    class Meta:
        model = ShippingDetails
        fields = (
            "id",
            "account",
            "entity",
            "gstno",
            "address1",
            "address2",
            "pincode",
            "phoneno",
            "full_name",
            "emailid",
            "isprimary",
            "country",
            "countryName",
            "state",
            "stateName",
            "district",
            "districtName",
            "city",
            "cityName",
        )
    

class ContactDetailsSerializer(serializers.ModelSerializer):
    """
    Create / Update / Retrieve serializer
    """
    class Meta:
        model = ContactDetails
        fields = (
            "id",
            "account",
            "entity",
            "address1",
            "address2",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneno",
            "emailid",
            "full_name",
            "designation",
            "isprimary",
        )
        read_only_fields = ("id",)
        extra_kwargs = {
            "account": {"required": False, "allow_null": True},
            "entity": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        """
        Prevent multiple primary contacts per account (clean API error).
        DB constraint not required here, but UX improves.
        """
        isprimary = attrs.get("isprimary", None)
        account = attrs.get("account", getattr(self.instance, "account", None))

        if isprimary is True and account:
            qs = ContactDetails.objects.filter(account=account, isprimary=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"isprimary": "Primary contact already exists for this account."}
                )

        # Auto-inherit entity from account if not provided
        entity = attrs.get("entity", None)
        if entity is None and account and getattr(account, "entity_id", None):
            attrs["entity"] = account.entity

        return attrs
    
class ContactDetailsListSerializer(serializers.ModelSerializer):
    countryName = serializers.CharField(source="country.countryname", read_only=True, allow_null=True)
    stateName = serializers.CharField(source="state.statename", read_only=True, allow_null=True)
    districtName = serializers.CharField(source="district.districtname", read_only=True, allow_null=True)
    cityName = serializers.CharField(source="city.cityname", read_only=True, allow_null=True)

    class Meta:
        model = ContactDetails
        fields = (
            "id",
            "account",
            "entity",
            "address1",
            "address2",
            "pincode",
            "phoneno",
            "emailid",
            "full_name",
            "designation",
            "isprimary",
            "country",
            "countryName",
            "state",
            "stateName",
            "district",
            "districtName",
            "city",
            "cityName",
        )


class AccountSerializer(serializers.ModelSerializer):
    shipping_details = ShippingDetailsSerializer(many=True, required=False)
    contact_details = ContactDetailsSerializer(many=True, required=False)

    class Meta:
        model = account
        fields = (
            # core
            "id",
            "entity",
            "accountcode",
            "accountdate",
            "accounttype",
            "accounthead",
            "creditaccounthead",
            "contraaccount",
            "accountname",
            "legalname",
            "iscompany",
            "website",
            "reminders",

            # gst/compliance
            "gstno",
            "gstintype",
            "gstregtype",
            "is_sez",
            "cin",
            "msme",
            "gsttdsno",
            "pan",
            "tdsno",
            "tdsrate",
            "tdssection",
            "tds_threshold",
            "istcsapplicable",
            "tcscode",

            # address
            "address1",
            "address2",
            "addressfloorno",
            "addressstreet",
            "country",
            "state",
            "district",
            "city",
            "pincode",

            # registration dates / status
            "dateofreg",
            "dateofdreg",
            "blockstatus",
            "blockedreason",
            "isactive",
            "approved",

            # contact
            "contactno",
            "contactno2",
            "emailid",
            "contactperson",
            "agent",

            # balances / terms
            "openingbcr",
            "openingbdr",
            "creditlimit",
            "creditdays",
            "paymentterms",
            "currency",
            "partytype",

            # bank
            "bankname",
            "banKAcno",
            "rtgsno",

            # other existing fields
            "adhaarno",
            "saccode",
            "deprate",
            "gstshare",
            "quanity1",
            "quanity2",
            "composition",
            "tobel10cr",
            "isaddsameasbillinf",
            "sharepercentage",

            # audit
            "createdby",

            # nested
            "shipping_details",
            "contact_details",
        )
        read_only_fields = ("id", "accountcode", "createdby")

    # --------------------------
    # CREATE
    # --------------------------
    @transaction.atomic
    def create(self, validated_data):
        shipping_data = validated_data.pop("shipping_details", [])
        contact_data = validated_data.pop("contact_details", [])

        # ignore id=0 from UI payloads
        shipping_data = [s for s in shipping_data if (s.get("id") not in (0, "0"))]
        contact_data = [c for c in contact_data if (c.get("id") not in (0, "0"))]

        entity = validated_data["entity"]

        # accountcode generation (Max is safer than last())
        accountcode = self._generate_account_code(entity)

        # createdby from request
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            validated_data["createdby"] = request.user

        acc = account.objects.create(**validated_data, accountcode=accountcode)

        # nested bulk upsert
        self._upsert_shipping_bulk(acc, shipping_data)
        self._upsert_contact_bulk(acc, contact_data)

        # opening balance posting via JournalLine
        fin_start = self._first_fin_start_date(acc.entity)
        repost_opening_balance(acc, fin_start)

        return acc

    # --------------------------
    # UPDATE (partial safe)
    # --------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        shipping_data = validated_data.pop("shipping_details", None)
        contact_data = validated_data.pop("contact_details", None)

        # update base fields
        for k, v in validated_data.items():
            setattr(instance, k, v)

        # audit
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            instance.createdby = request.user

        instance.save()

        # nested updates only if provided
        if shipping_data is not None:
            self._upsert_shipping_bulk(instance, shipping_data)

        if contact_data is not None:
            self._upsert_contact_bulk(instance, contact_data)

        # opening balance repost
        fin_start = self._first_fin_start_date(instance.entity)
        repost_opening_balance(instance, fin_start)

        return instance

    # --------------------------
    # helpers
    # --------------------------
    def _generate_account_code(self, entity):
        last_code = (
            account.objects.filter(entity=entity)
            .aggregate(models.Max("accountcode"))
            .get("accountcode__max")
        )
        return (last_code or 0) + 1

    def _first_fin_start_date(self, entity):
        return (
            entityfinancialyear.objects.filter(entity=entity)
            .order_by("finstartyear")
            .values_list("finstartyear", flat=True)
            .first()
        )

    def _upsert_shipping_bulk(self, acc, rows):
        rows = [r for r in rows if (r.get("id") not in (0, "0"))]

        request = self.context.get("request")
        user = getattr(request, "user", None)

        to_create = []
        for r in rows:
            sid = r.get("id")
            payload = dict(r)
            payload.pop("id", None)

            # enforce entity/createdby
            payload.setdefault("entity", acc.entity)
            if user and user.is_authenticated:
                payload.setdefault("createdby", user)

            # ✅ If this row is being set as primary, demote others first
            if payload.get("isprimary") is True:
                ShippingDetails.objects.filter(account=acc, isprimary=True).exclude(id=sid or 0).update(isprimary=False)

            if sid:
                # ✅ update existing
                ShippingDetails.objects.filter(id=sid, account=acc).update(**payload)
            else:
                # ✅ create new (primary will work because others are demoted above)
                to_create.append(ShippingDetails(account=acc, **payload))

        if to_create:
            ShippingDetails.objects.bulk_create(to_create)

    def _upsert_contact_bulk(self, acc, rows):
        rows = [r for r in rows if (r.get("id") not in (0, "0"))]

        request = self.context.get("request")
        user = getattr(request, "user", None)

        to_create = []
        for r in rows:
            cid = r.get("id")
            payload = dict(r)
            payload.pop("id", None)

            payload.setdefault("entity", acc.entity)
            if user and user.is_authenticated:
                payload.setdefault("createdby", user)

            # ✅ If this row is being set as primary, demote others first
            if payload.get("isprimary") is True:
                ContactDetails.objects.filter(account=acc, isprimary=True).exclude(id=cid or 0).update(isprimary=False)

            if cid:
                ContactDetails.objects.filter(id=cid, account=acc).update(**payload)
            else:
                to_create.append(ContactDetails(account=acc, **payload))

        if to_create:
            ContactDetails.objects.bulk_create(to_create)

        

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

class StaticAccountsSerializer(serializers.ModelSerializer):
    class Meta:
        model = staticacounts
        fields = (
            "id",
            "accounttype",
            "staticaccount",
            "code",
            "entity",
            "createdby",
        )
        read_only_fields = ("id", "createdby")




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
        fields =  ('id', 'accounthead','accountname','accountcode','state','district','city','pincode', 'gstno','pan','saccode',)



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

# Serializer for the account model
class AccountListtopSerializer(serializers.ModelSerializer):
   
    
    balance = serializers.SerializerMethodField()

    accountid = serializers.IntegerField(source= 'id', read_only=True)
    
    class Meta:
        model = account
        fields = [
            'accountid', 'accountname', 'balance'
        ]
    
    def get_balance(self, obj):
        request = self.context.get('request')
        entity = request.GET.get('entity')
        
        if entity:
            current_dates = entityfinancialyear.objects.get(entity=entity, isactive=1)
            transaction = StockTransactions.objects.filter(
                entity=entity,
                isactive=1,
                entrydatetime__range=(current_dates.finstartyear,current_dates.finendyear)
            ).exclude(
                accounttype='MD'
            ).exclude(
                transactiontype__in=['PC']
            ).filter(
                account=obj
            ).aggregate(
                balance=Sum('debitamount', default=0) - Sum('creditamount', default=0)
            )
            
            return transaction['balance'] or 0  # Ensure None is replaced with 0
        
        return 0
    










class AccountHeadSerializer(serializers.ModelSerializer):
    accountHeadName = serializers.SerializerMethodField()
    accounthead_accounts = AccountSerializer(many=True,required=False)
    accounthead_creditaccounts = AccountSerializer(many=True,required=False)

    class Meta:
        model = accountHead
        fields = (
            'id', 'name', 'code', 'detailsingroup', 'balanceType',
            'drcreffect', 'description', 'accountheadsr', 'entity','accounttype',
            'accountHeadName', 'accounthead_accounts','accounthead_creditaccounts'
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
        user = validated_data.get('createdby')
        account_date = validated_data.pop("acountdate", None)

        # Create the account head
        account_head_instance = accountHead.objects.create(**validated_data)

        # Bulk create related accounts
        accounts_to_create = [
            account(
                accounthead=account_head_instance,
                entity=entity,
                createdby=user,
                accountdate=account_date,
                **detail_data
            )
            for detail_data in account_details_data
        ]
        account.objects.bulk_create(accounts_to_create)

        return account_head_instance
    

class AccountHeadMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = accountHead
        fields = ['id', 'balanceType']


class accountHeadSerializer2(serializers.ModelSerializer):  
    accountHeadName = serializers.SerializerMethodField()
    detailsingroupName = serializers.SerializerMethodField()

    class Meta:
        model = accountHead
        fields = ('id', 'name', 'code', 'detailsingroup', 'balanceType', 'drcreffect', 
                  'description', 'accountheadsr', 'entity', 'accountHeadName','accounttype',
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
    accounttypeid = serializers.IntegerField(source= 'id', read_only=True)
    class Meta:
        model = accounttype
        fields = ('accounttypeid','accounttypename',)


class StaticAccountMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = staticacountsmapping
        fields = (
            "id",
            "staticaccount",
            "account",
            "entity",
            "createdby",
        )
        read_only_fields = ("id", "createdby")




class AccountTypeJsonSerializer(serializers.ModelSerializer):
    accounthead_accounttype = AccountHeadSerializer(many=True, required=False)

    class Meta:
        model = accounttype
        fields = [
            'id', 'accounttypename', 'accounttypecode', 'balanceType',
            'entity', 'createdby', 'accounthead_accounttype'
        ]

    def create(self, validated_data):
        heads_data = validated_data.pop('accounthead_accounttype', [])

        with transaction.atomic():
            acc_type = accounttype.objects.create(**validated_data)
            entity = validated_data.get('entity')
            user = validated_data.get('createdby')

            for head_data in heads_data:
                accounts_data = head_data.pop('accounthead_accounts', [])
                head = accountHead.objects.create(accounttype=acc_type, **head_data,entity = entity,createdby = user)

                for account_data in accounts_data:
                    if head.balanceType == "Credit":  # or 0 if it's integer
                        account.objects.create(creditaccounthead=head, **account_data,entity = entity,createdby = user,accounttype = acc_type)
                    else:
                        account.objects.create(accounthead=head, **account_data,entity = entity,createdby = user,accounttype = acc_type)

        return acc_type
    


class AccountBalanceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    accountname = serializers.CharField()
    accountcode = serializers.CharField()
    gstno = serializers.CharField()
    pancode = serializers.CharField(required=False, allow_blank=True)
    city = serializers.IntegerField(required=False)
    state = serializers.IntegerField(required=False)
    district = serializers.IntegerField(required=False)
    pincode = serializers.CharField(required=False, allow_blank=True)
    saccode = serializers.CharField(required=False, allow_blank=True)
    balance = serializers.FloatField()
    drcr = serializers.CharField()



class AccountHeadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = accountHead
        fields = ['id', 'name', 'code']
           


        
  
    
    

    




