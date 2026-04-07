#import imp
from struct import pack
from rest_framework import serializers
from entity.models import Entity,EntityDetail,UnitType,EntityFinancialYear,EntityConstitution,Constitution,SubEntity,GstRegistrationType,BankAccount

from Authentication.models import User
from financial.models import Ledger, accountHead
from financial.serializers_catalog_v2 import AccountHeadV2Serializer, AccountTypeV2Serializer
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
import os
import json
import collections
from django.contrib.auth.hashers import make_password
from django.db import transaction
from rbac.models import Role as RBACRole, UserRoleAssignment

#from Authentication.serializers import userserializer

class ConstitutionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Constitution
        fields = '__all__'

class unitTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = UnitType
        fields = '__all__'

class entityconstitutionSerializer(serializers.ModelSerializer):

    class Meta:
        model = EntityConstitution
        fields = '__all__'

class EntityFinancialYearSerializecreate(serializers.ModelSerializer):
    # Derived fields from related 'entity' model
    entityname = serializers.CharField(source='entity.entityname', read_only=True)
    gst = serializers.CharField(source='entity.gstno', read_only=True)

    class Meta:
        model = EntityFinancialYear
        fields = (
            'id', 'entity', 'entityname', 'gst', 'desc',
            'finstartyear', 'finendyear', 'createdby', 'isactive',
        )

    def create(self, validated_data):
        # Use a transaction to ensure atomicity
        with transaction.atomic():
            entity_id = validated_data['entity'].id
            # Update all previous records for the entity to inactive
            EntityFinancialYear.objects.filter(entity=entity_id).update(isactive=False)

            # Create a new financial year record for the entity
            return EntityFinancialYear.objects.create(**validated_data)

class EntityFinancialYearSerializer(serializers.ModelSerializer):
    entityname = serializers.CharField(source='entity.entityname', read_only=True)
    gst = serializers.CharField(source='entity.gstno', read_only=True)
    activestartdate = serializers.DateTimeField(source='finstartyear', read_only=True)
    activeenddate = serializers.DateTimeField(source='finendyear', read_only=True)

    activeyearid = serializers.IntegerField(source='id', read_only=True)

    # New fields for the formatted dates and active year ID
    finstartyear = serializers.SerializerMethodField()
    finendyear = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    isactive = serializers.SerializerMethodField()

    class Meta:
        model = EntityFinancialYear
        fields = (
            'id', 'entity', 'entityname', 'gst', 'desc',
            'finstartyear', 'finendyear', 'createdby', 'isactive',
            'activestartdate', 'activeenddate', 'activeyearid'
        )

    def _get_financialyear(self):
        """Fetch financial year based on financialyearid or active year"""
        financialyearid = self.context.get('financialyearid')
        if financialyearid == 0:
            return EntityFinancialYear.objects.filter(isactive=True).first()
        try:
            return EntityFinancialYear.objects.get(id=financialyearid)
        except EntityFinancialYear.DoesNotExist:
            return None

    def get_finstartyear(self, obj):
        """Fetch activestartdate and format it as DD-MM-YYYY"""
        financialyear = self._get_financialyear() or obj
        return financialyear.finstartyear.strftime("%d-%m-%Y")

    def get_finendyear(self, obj):
        """Fetch activeenddate and format it as DD-MM-YYYY"""
        financialyear = self._get_financialyear() or obj
        return financialyear.finendyear.strftime("%d-%m-%Y")
    
    def get_isactive(self, obj):
        """Fetch activeenddate and format it as DD-MM-YYYY"""
        financialyear = self._get_financialyear() or obj
        return financialyear.isactive
    
    def get_id(self, obj):
        """Return the ID of the active financial year if financialyearid=0"""
        financialyear = self._get_financialyear() or obj
        return financialyear.id

    def create(self, validated_data):
        with transaction.atomic():
            entity_id = validated_data['entity'].id
            EntityFinancialYear.objects.filter(entity=entity_id).update(isactive=False)
            return EntityFinancialYear.objects.create(**validated_data)
    

class entityfinancialyearListSerializer(serializers.ModelSerializer):

    class Meta:

        model = EntityFinancialYear
        fields = ('id','finstartyear','finendyear','isactive',)

class subentitySerializer(serializers.ModelSerializer):

    class Meta:

        model = SubEntity
        fields = ('id','subentityname','address','country','state','district','city','pincode','phoneoffice','phoneresidence','email','ismainentity', 'entity')

class subentitySerializerbyentity(serializers.ModelSerializer):

    class Meta:

        model = SubEntity
        fields = ('id','subentityname','ismainentity',)

    
    

    

    

class entityAddSerializer(serializers.ModelSerializer):

    fy = EntityFinancialYearSerializecreate(many=True)
    constitution = entityconstitutionSerializer(many=True)

    class Meta:
        model = Entity
        #fields = ('id','entityName','fy',)
        fields = ('entityname','address','ownername','country','state','district','city','pincode','phoneoffice','phoneresidence','panno','tds','tdscircle','email','tcs206c1honsale','gstno','gstintype','const','user','constitution','legalname','address2','addressfloorno','addressstreet','blockstatus','dateofreg','dateofdreg','fy',)

   # entity_accountheads = accountHeadSerializer(many=True)

    serializer = AccountHeadV2Serializer
    accounthead = AccountHeadV2Serializer
    acounttype = AccountTypeV2Serializer

    def _create_constitution_party_account(self, *, entity_obj, detail, user, accountdate1):
        constcode = getattr(entity_obj.const, "constcode", None)
        head_code = None
        if constcode == "01":
            head_code = 6200
        elif str(getattr(entity_obj.const, "id", "")) == "02" or constcode == "02":
            head_code = 6300
        if head_code is None:
            return None

        achead = accountHead.objects.get(entity=entity_obj, code=head_code)
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": entity_obj,
                "accountname": detail.shareholder,
                "createdby": user,
                "accountdate": accountdate1,
            },
            ledger_overrides={
                "name": detail.shareholder,
                "accounthead": achead,
                "creditaccounthead": achead,
                "canbedeleted": True,
                "is_party": True,
                "isactive": True,
            },
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"pan": detail.pan} if getattr(detail, "pan", None) else {},
            primary_address_data={
                "country": entity_obj.country_id,
                "state": entity_obj.state_id,
                "district": entity_obj.district_id,
                "city": entity_obj.city_id,
                "line1": getattr(entity_obj, "address", None),
                "line2": getattr(entity_obj, "address2", None),
                "floor_no": getattr(entity_obj, "addressfloorno", None),
                "street": getattr(entity_obj, "addressstreet", None),
                "pincode": getattr(entity_obj, "pincode", None),
            },
            primary_contact_data={
                "emailid": getattr(entity_obj, "email", None),
            },
            createdby=user,
        )
        return acc

    def _apply_default_credit_head_mappings(self, *, entity_obj):
        account_updates = [
            {"code": 1000, "credit_code": 3000},
            {"code": 6000, "credit_code": 6100},
            {"code": 8000, "credit_code": 7000},
        ]
        for update in account_updates:
            credit_head = accountHead.objects.filter(code=update["credit_code"], entity=entity_obj).first()
            if not credit_head:
                continue
            Ledger.objects.filter(
                entity=entity_obj,
                account_profile__isnull=False,
                accounthead__code=update["code"],
            ).update(creditaccounthead=credit_head)

    def process_json_file(self, newentity, users, accountdate1):
        # Load JSON data once
        file_path = os.path.join(os.getcwd(), "account.json")
        with open(file_path, 'r') as jsonfile:
            json_data = json.load(jsonfile)

        # Mapping serializers to corresponding JSON keys
        serializers_mapping = {
            "acconttype": (self.acounttype, {"entity": newentity, "createdby": users[0]}),
        }

        # Iterate through the JSON keys and process data
        for key, (serializer_class, extra_kwargs) in serializers_mapping.items():
            if key in json_data:
                objects_to_create = []
                for item in json_data[key]:
                    serializer = serializer_class(data=item)
                    serializer.is_valid(raise_exception=True)
                    objects_to_create.append(serializer.save(**extra_kwargs))

    def create(self, validated_data):
        # Extract related data
        users = validated_data.pop("user")
        fydata = validated_data.pop("fy", [])
        constitutiondata = validated_data.pop("constitution")
        # Create the main entity
        newentity = Entity.objects.create(**validated_data)

        # Bulk create financial year details
        # Prepare financial year objects

        fy_details = [
            EntityFinancialYear(entity=newentity, **data, createdby=users[0])
            for data in fydata
        ]

        # Bulk create financial years
        if fy_details:
            EntityFinancialYear.objects.bulk_create(fy_details)

        # Retrieve account start date
        accountdate1 = fy_details[0].finstartyear if fy_details else None

        # Add users to the entity
        newentity.user.add(*users)

        # Process additional JSON file logic
        self.process_json_file(newentity=newentity, users=users, accountdate1=accountdate1)

        # Create default subentity
        SubEntity.objects.create(
            subentityname="Main-Branch",
            address=newentity.address,
            country=newentity.country,
            state=newentity.state,
            district=newentity.district,
            city=newentity.city,
            pincode=newentity.pincode,
            phoneoffice=newentity.phoneoffice,
            phoneresidence=newentity.phoneresidence,
            entity=newentity,
        )

        # Process constitution data
        constitution_details = []
        for data in constitutiondata:
            detail = EntityConstitution(entity=newentity, **data, createdby=users[0])
            constitution_details.append(detail)

        EntityConstitution.objects.bulk_create(constitution_details)
        for detail in constitution_details:
            self._create_constitution_party_account(
                entity_obj=newentity,
                detail=detail,
                user=users[0],
                accountdate1=accountdate1,
            )
        self._apply_default_credit_head_mappings(entity_obj=newentity)

        return newentity
    
class EntityFinancialYearSerializerlist(serializers.ModelSerializer):
    id = serializers.IntegerField()
    financial_year = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()

    class Meta:
        model = EntityFinancialYear
        fields = ['id', 'financial_year', 'start_date', 'end_date', 'isactive']

    def get_financial_year(self, obj):
        if obj.finstartyear and obj.finendyear:
            start = obj.finstartyear.strftime('%b-%Y')  # e.g., Jan-2024
            end = obj.finendyear.strftime('%b-%Y')      # e.g., Dec-2024
            return f"{start} - {end}"
        return None

    def get_start_date(self, obj):
        if obj.finstartyear:
            return obj.finstartyear.strftime('%Y-%m-%d')  # e.g., 2024-01-01
        return None

    def get_end_date(self, obj):
        if obj.finendyear:
            return obj.finendyear.strftime('%Y-%m-%d')  # e.g., 2024-12-31
        return None

    

# class entityUserSerializer(serializers.ModelSerializer):

#     user_details = Registerserializers(many=False)

#     class Meta:
#         model = entity_user
#         fields =  ('id','entity','user')
#         depth = 0

# class entityUserAddSerializer(serializers.ModelSerializer):

#     user = Registerserializers(many=False)

#     class Meta:
#         model = entity_user
#         fields = '__all__'
#         #depth = 0

#     def create(self,validated_data):
#         print(validated_data)
#         user_data = self.validated_data.pop('user')

#         print(user_data)
#         user = User.objects.create_user(**user_data)
#         entity_item = entity.objects.get(id=1)
#         entity_user.objects.create(user = user, entity= entity_item)
#         #entity_user.objects.create(user = user,**validated_data)

#         return user

    # def to_representation(self, instance):
    #     rep = super().to_representation(instance)
    #     rep['user'] = (instance.user).data
       
    #     return rep

class entityDetailsSerializer(serializers.ModelSerializer):

    class Meta:
        model = EntityDetail
        fields = ('entity','email',)

   
        
        # #print(tracks_data)
        # for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
        #     PurchaseOrderDetails.objects.create(purchaseOrder = order, **PurchaseOrderDetail_data)
        # return order

# class Userserializer(serializers.ModelSerializer):

#     password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)

#    # userentity = entityUserSerializer(many=True)

#     uentity = entityAddSerializer(many=True)

#     rolename = serializers.SerializerMethodField()

#     class Meta:
#         model = User
#         fields = ('first_name','last_name','email','role','password','uentity','rolename','uentity', )
#        #depth = 1

    
#     def get_rolename(self,obj):
#         if obj.role is None:
#             return 1   
#         else:
#             acc =  obj.role.rolename
#             return acc

class GstRegitrationTypesSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstRegistrationType
        fields = ['id', 'Name', 'Description']

class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            'id',
            'entity',
            'bank_name',
            'branch',
            'account_number',
            'ifsc_code',
            'account_type',
            'is_primary',
        ]

    def validate(self, attrs):
        # Optional: prevent multiple primary accounts for the same entity
        if attrs.get("is_primary") and self.instance is None:
            entity = attrs.get("entity")
            if BankAccount.objects.filter(entity=entity, is_primary=True).exists():
                raise serializers.ValidationError("A primary bank account already exists for this entity.")
        return attrs

class BankAccountNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        exclude = ["entity"]

class SubEntityNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubEntity
        exclude = ["entity"]

class EntityFinancialYearNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityFinancialYear
        exclude = ["entity", "createdby"]  # createdby set from request.user

class EntityConstitutionNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityConstitution
        exclude = ["entity", "createdby"]  # createdby set from request.user

class EntityNewSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountNewSerializer(many=True, required=False)
    subentity = SubEntityNewSerializer(many=True, required=False)
    fy = EntityFinancialYearNewSerializer(many=True, required=False)
    constitution = EntityConstitutionNewSerializer(many=True, required=False)

    class Meta:
        model = Entity
        fields = "__all__"
        read_only_fields = ("id",)  # important

    # mapping for account.json seeding
    serializer = AccountHeadV2Serializer
    accounthead = AccountHeadV2Serializer
    acounttype = AccountTypeV2Serializer

    def _create_constitution_party_account(self, *, entity_obj, detail, user, accountdate):
        constcode = getattr(entity_obj.const, "constcode", None)
        head_code = None
        if constcode == "01":
            head_code = 6200
        elif constcode == "02":
            head_code = 6300
        if head_code is None:
            return None

        achead = accountHead.objects.get(entity=entity_obj, code=head_code)
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": entity_obj,
                "accountname": detail.shareholder,
                "createdby": user,
                "accountdate": accountdate,
            },
            ledger_overrides={
                "name": detail.shareholder,
                "accounthead": achead,
                "creditaccounthead": achead,
                "canbedeleted": True,
                "is_party": True,
                "isactive": True,
            },
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"pan": detail.pan} if getattr(detail, "pan", None) else {},
            primary_address_data={
                "country": entity_obj.country_id,
                "state": entity_obj.state_id,
                "district": entity_obj.district_id,
                "city": entity_obj.city_id,
                "line1": getattr(entity_obj, "address", None),
                "line2": getattr(entity_obj, "address2", None),
                "floor_no": getattr(entity_obj, "addressfloorno", None),
                "street": getattr(entity_obj, "addressstreet", None),
                "pincode": getattr(entity_obj, "pincode", None),
            },
            primary_contact_data={
                "emailid": getattr(entity_obj, "email", None),
            },
            createdby=user,
        )
        return acc

    def _apply_default_credit_head_mappings(self, *, entity_obj):
        account_updates = [
            {"code": 1000, "credit_code": 3000},
            {"code": 6000, "credit_code": 6100},
            {"code": 8000, "credit_code": 7000},
        ]
        for upd in account_updates:
            credit_head = accountHead.objects.filter(code=upd["credit_code"], entity=entity_obj).first()
            if not credit_head:
                print(f"[WARN] Missing credit accountHead code={upd['credit_code']} for entity={entity_obj.id}. Skipping mapping.")
                continue

            updated = Ledger.objects.filter(
                entity=entity_obj,
                account_profile__isnull=False,
                accounthead__code=upd["code"],
            ).update(creditaccounthead=credit_head)
            if updated == 0:
                print(f"[WARN] No ledger rows found for mapping code={upd['code']} for entity={entity_obj.id}.")

    # -------------------------
    # seed masters (account.json)
    # -------------------------
    def process_json_file(self, newentity, user, accountdate1):
        file_path = os.path.join(os.getcwd(), "account.json")
        if not os.path.exists(file_path):
            return

        with open(file_path, "r") as jsonfile:
            json_data = json.load(jsonfile)

        serializers_mapping = {
            "acconttype": (self.acounttype, {"createdby": user}),
        }

        for key, (serializer_class, extra_kwargs) in serializers_mapping.items():
            if key not in json_data:
                continue
            for item in json_data[key]:
                ser = serializer_class(data=item)
                ser.is_valid(raise_exception=True)
                ser.save(**extra_kwargs)

    # -------------------------
    # generic nested upsert
    # -------------------------
    def _upsert_nested(self, model, related_name, parent_instance, parent_field, items, user=None):
        """
        Upsert by id:
        - id exists -> update
        - id missing/0 -> create
        - delete existing rows not included in incoming ids
        """
        if items is None:
            return
        items = items or []
        existing_qs = getattr(parent_instance, related_name).all()
        existing_map = {obj.id: obj for obj in existing_qs}
        keep_ids = set()

        for raw in items:
            data = dict(raw or {})

            # ✅ never allow client to pass parent / createdby
            data.pop(parent_field, None)
            data.pop(f"{parent_field}_id", None)
            data.pop("createdby", None)
            data.pop("updatedby", None)

            obj_id = int(data.get("id") or 0)

            if obj_id and obj_id in existing_map:
                obj = existing_map[obj_id]
                for k, v in data.items():
                    if k == "id":
                        continue
                    setattr(obj, k, v)
                obj.save()
                keep_ids.add(obj_id)
            else:
                data.pop("id", None)
                create_kwargs = {parent_field: parent_instance}
                if user is not None and hasattr(model, "createdby_id"):
                    create_kwargs["createdby"] = user

                obj = model.objects.create(**data, **create_kwargs)
                keep_ids.add(obj.id)

        # delete removed
        for obj_id, obj in existing_map.items():
            if obj_id not in keep_ids:
                obj.delete()

    # -------------------------
    # CREATE
    # -------------------------
   # @transaction.atomic
    @transaction.atomic
    def create(self, validated_data):
        # -------------------------
        # Extract nested payload
        # -------------------------
        bank_data = validated_data.pop("bank_accounts", [])
        subentities_data = validated_data.pop("subentity", [])
        fy_data = validated_data.pop("fy", [])
        constitution_data = validated_data.pop("constitution", [])

        # -------------------------
        # User (MUST be passed from view)
        # serializer.save(createdby=request.user)
        # -------------------------
        user = validated_data.get("createdby")

        # -------------------------
        # HARDEN: never accept system keys from payload
        # -------------------------
        validated_data.pop("id", None)         # UI sends id: 0
        validated_data.pop("pk", None)
        validated_data.pop("createdby", None)  # avoid duplicate createdby

        # -------------------------
        # Create Entity (server-side createdby)
        # -------------------------
        if not user:
            raise serializers.ValidationError({"createdby": "Pass createdby from view: serializer.save(createdby=request.user)"})

        entity = Entity.objects.create(createdby=user, **validated_data)

        # -------------------------
        # Create Financial Years (createdby required in model)
        # -------------------------
        active_fy_count = sum(1 for f in fy_data if bool((f or {}).get("isactive")))
        if active_fy_count > 1:
            raise serializers.ValidationError({"fy": "Only one financial year can be active."})

        for f in fy_data:
            f = dict(f)
            f.pop("id", None)
            f.pop("entity", None)
            f.pop("entity_id", None)
            f.pop("createdby", None)
            EntityFinancialYear.objects.create(entity=entity, createdby=user, **f)

        # optional: used by your downstream seeding/account creation
        accountdate = fy_data[0]["finstartyear"] if fy_data else None

        if fy_data:
            active_fy = (
                EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("-id").first()
            )
            if not active_fy:
                first_fy = EntityFinancialYear.objects.filter(entity=entity).order_by("id").first()
                if first_fy:
                    first_fy.isactive = True
                    first_fy.save(update_fields=["isactive"])

        # -------------------------
        # Seed masters from account.json
        # -------------------------
        self.process_json_file(newentity=entity, user=user, accountdate1=accountdate)

        # -------------------------
        # Assign Admin role to creator
        # -------------------------
        roleid, _ = RBACRole.objects.get_or_create(
            entity=entity,
            code="entity.admin",
            defaults={
                "name": "Admin",
                "description": "System Admin",
                "role_level": RBACRole.LEVEL_ENTITY,
                "is_system_role": True,
            },
        )
        UserRoleAssignment.objects.get_or_create(
            user=user,
            entity=entity,
            role=roleid,
            defaults={"is_primary": True},
        )

        # -------------------------
        # Create Bank Accounts
        # -------------------------
        for b in bank_data:
            b = dict(b)
            b.pop("id", None)
            b.pop("entity", None)
            b.pop("entity_id", None)
            BankAccount.objects.create(entity=entity, **b)

        # -------------------------
        # Create SubEntities
        # -------------------------
        for s in subentities_data:
            s = dict(s)
            s.pop("id", None)
            s.pop("entity", None)
            s.pop("entity_id", None)
            SubEntity.objects.create(entity=entity, **s)

        # -------------------------
        # Create Constitution + Partner/Shareholder Accounts
        # -------------------------
        for c in constitution_data:
            c = dict(c)
            c.pop("id", None)
            c.pop("entity", None)
            c.pop("entity_id", None)
            c.pop("createdby", None)

            detail = EntityConstitution.objects.create(entity=entity, createdby=user, **c)
            self._create_constitution_party_account(
                entity_obj=entity,
                detail=detail,
                user=user,
                accountdate=accountdate,
            )

        self._apply_default_credit_head_mappings(entity_obj=entity)

        return entity

    # -------------------------
    # UPDATE
    # -------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        has_bank_data = "bank_accounts" in validated_data
        has_subentity_data = "subentity" in validated_data
        has_fy_data = "fy" in validated_data
        has_constitution_data = "constitution" in validated_data

        bank_data = validated_data.pop("bank_accounts", None)
        subentity_data = validated_data.pop("subentity", None)
        fy_data = validated_data.pop("fy", None)
        constitution_data = validated_data.pop("constitution", None)

        user = validated_data.get("updatedby") or validated_data.get("createdby")

        # base entity update
        validated_data.pop("id", None)
        validated_data.pop("pk", None)
        validated_data.pop("createdby", None)
        validated_data.pop("updatedby", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # nested upsert
        if has_bank_data:
            self._upsert_nested(BankAccount, "bank_accounts", instance, "entity", bank_data, user=None)
        if has_subentity_data:
            self._upsert_nested(SubEntity, "subentity", instance, "entity", subentity_data, user=None)
        if has_fy_data:
            active_fy_count = sum(1 for f in (fy_data or []) if bool((f or {}).get("isactive")))
            if active_fy_count > 1:
                raise serializers.ValidationError({"fy": "Only one financial year can be active."})
            self._upsert_nested(EntityFinancialYear, "fy", instance, "entity", fy_data, user=user)
            active_fy = EntityFinancialYear.objects.filter(entity=instance, isactive=True).order_by("-id").first()
            if not active_fy:
                first_fy = EntityFinancialYear.objects.filter(entity=instance).order_by("id").first()
                if first_fy:
                    first_fy.isactive = True
                    first_fy.save(update_fields=["isactive"])
        if has_constitution_data:
            self._upsert_nested(EntityConstitution, "constitution", instance, "entity", constitution_data, user=user)

        return instance

