#import imp
from struct import pack
from rest_framework import serializers
from entity.models import Entity,EntityDetail,UnitType,EntityFinancialYear,EntityConstitution,Constitution,SubEntity,Role,RolePrivilege,UserRole,GstRegistrationType,BankAccount
from Authentication.models import User,Submenu
from Authentication.serializers import Registerserializers
from financial.models import accountHead,account
from financial.serializers import AccountHeadSerializer,AccountSerializer,accountHeadSerializer2,accounttypeserializer,AccountTypeJsonSerializer
from inventory.serializers import RateCalculateSerializer,UOMSerializer,TOGSerializer,TOGSerializer,ProductCategoryMainSerializer
from invoice.serializers import purchasetaxtypeserializer,InvoiceTypeSerializer
import os
import json
import collections
from django.contrib.auth.hashers import make_password
from django.db import transaction


#from Authentication.serializers import userserializer








class rolemainSerializer1(serializers.ModelSerializer):
  
    class Meta:
        model = Role
        fields = ('id','rolename','roledesc','rolelevel','entity',)



class RolePrivDetailSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = RolePrivilege
        fields =  ('role','submenu','entity',)




class RoleMainSerializer(serializers.ModelSerializer):
    submenudetails = RolePrivDetailSerializer(many=True)

    class Meta:
        model = Role
        fields = ('id', 'rolename', 'roledesc', 'rolelevel', 'entity', 'submenudetails')

    def create(self, validated_data):
        roledetails_data = validated_data.pop('submenudetails', [])
        # Create the role instance
        role = Role.objects.create(**validated_data)
        
        # Bulk create RolePriv instances
        RolePrivilege.objects.bulk_create([
            RolePrivilege(role=role, **roledetail_data) for roledetail_data in roledetails_data
        ])
        
        return role

    def update(self, instance, validated_data):
        fields_to_update = ['rolename', 'roledesc', 'rolelevel', 'entity']
        
        # Update specified fields
        for field in fields_to_update:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()

        # Clear old RolePriv entries and add new ones
        RolePrivilege.objects.filter(role=instance, entity=instance.entity).delete()
        roledetails_data = validated_data.get('submenudetails', [])

        # Bulk create RolePriv instances
        RolePrivilege.objects.bulk_create([
            RolePrivilege(role=instance, **roledetail_data) for roledetail_data in roledetails_data
        ])

        return instance


 



class roleSerializer(serializers.ModelSerializer):

    class Meta:
        model = RolePrivilege
        fields = '__all__'



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

    serializer = AccountHeadSerializer
    accounthead = accountHeadSerializer2
    roleserializer = rolemainSerializer1

 
    rateerializer = RateCalculateSerializer
    uomser = UOMSerializer
    TOGSR = TOGSerializer
    GSTSR = TOGSerializer
    PTaxType = purchasetaxtypeserializer

    InvoiceType = InvoiceTypeSerializer
    pcategory = ProductCategoryMainSerializer
    acounttype = AccountTypeJsonSerializer

    def process_json_file(self, newentity, users, accountdate1):
        # Load JSON data once
        file_path = os.path.join(os.getcwd(), "account.json")
        with open(file_path, 'r') as jsonfile:
            json_data = json.load(jsonfile)

        # Mapping serializers to corresponding JSON keys
        serializers_mapping = {
            "acconttype": (self.acounttype, {"entity": newentity, "createdby": users[0]}),
            # "accountheads": (self.accounthead, {"entity": newentity, "createdby": users[0]}),
            "Roles": (self.roleserializer, {"entity": newentity}),
            "Ratecalc": (self.rateerializer, {"entity": newentity, "createdby": users[0]}),
            "UOM": (self.uomser, {"entity": newentity, "createdby": users[0]}),
            "TOG": (self.TOGSR, {"entity": newentity, "createdby": users[0]}),
            "GSTTYPE": (self.GSTSR, {"entity": newentity, "createdby": users[0]}),
          #  "ACCOUNTTYPE": (self.acounttype, {"entity": newentity, "createdby": users[0]}),
            "PurchaseType": (self.PTaxType, {"entity": newentity, "createdby": users[0]}),
            "InvoiceType": (self.InvoiceType, {"entity": newentity, "createdby": users[0]}),
            "productcategory": (self.pcategory, {"createdby": users[0]}),
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

        # Create admin role and user role
        roleid = Role.objects.get(entity=newentity, rolename="Admin")
        UserRole.objects.create(entity=newentity, role=roleid, user=users[0])

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

        # Bulk create role privileges
        submenus = Submenu.objects.all()
        role_privileges = [
            RolePrivilege(role=roleid, submenu=submenu, entity=newentity) for submenu in submenus
        ]
        RolePrivilege.objects.bulk_create(role_privileges)

        # Process constitution data
        constitution_details = []
        account_details = []

        for data in constitutiondata:
            detail = EntityConstitution(entity=newentity, **data, createdby=users[0])
            constitution_details.append(detail)

            # Logic for account creation based on constitution code
            if newentity.const.constcode == "01":
                achead = accountHead.objects.get(entity=newentity, code=6200)
                account_details.append(
                    account(
                        accounthead=achead,
                        creditaccounthead=achead,
                        accountname=detail.shareholder,
                        pan=detail.pan,
                        entity=newentity,
                        createdby=users[0],
                        sharepercentage=detail.sharepercentage,
                        country=newentity.country,
                        state=newentity.state,
                        district=newentity.district,
                        city=newentity.city,
                        emailid=newentity.email,
                        accountdate=accountdate1,
                    )
                )
            elif newentity.const.id == "02":
                achead = accountHead.objects.get(entity=newentity, code=6300)
                account_details.append(
                    account(
                        accounthead=achead,
                        creditaccounthead=achead,
                        accountname=detail.shareholder,
                        pan=detail.pan,
                        entity=newentity,
                        createdby=users[0],
                        sharepercentage=detail.sharepercentage,
                        country=newentity.country,
                        state=newentity.state,
                        district=newentity.district,
                        city=newentity.city,
                        emailid=newentity.email,
                        accountdate=accountdate1,
                    )
                )

        EntityConstitution.objects.bulk_create(constitution_details)
        account.objects.bulk_create(account_details)

        # Update accounts in bulk
        account_updates = [
            {"code": 1000, "credit_code": 3000},
            {"code": 6000, "credit_code": 6100},
            {"code": 8000, "credit_code": 7000},
        ]
        for update in account_updates:
            account.objects.filter(accounthead__code=update["code"], entity=newentity).update(
                creditaccounthead=accountHead.objects.get(code=update["credit_code"], entity=newentity)
            )

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


class useroleentitySerializer(serializers.ModelSerializer):


    user = Registerserializers(many = False)
      

    class Meta:
        model = UserRole
        fields = ('user','role','entity',)

        

  

    

    

    def create(self, validated_data):
        userdetails = validated_data.pop('user')

        # print(userdetails.get('email'))

        # if  User.objects.get(email = userdetails.get('email')).count() > 0:
        #     return 1
        # else:
        user = User.objects.create(**userdetails)
        userrole = UserRole.objects.create(user = user,**validated_data )
        return userrole

        

    def update(self, instance, validated_data):

        print(validated_data)
        userdetails = validated_data.pop('user')
        print(userdetails.get('email'))

        if User.objects.filter(email = userdetails.get('email')):
            print('1111111111111111111111111111111')
            userdetails = userdetails.pop('email')
            User.objects.filter(id = instance.user__id).update(username = userdetails.get('username'),first_name = userdetails.get('first_name'),last_name = userdetails.get('last_name'))
        else:
            print('222222222222222222222222222')
            User.objects.filter(id = instance.user.id).update(**userdetails)

        
        newuser = UserRole.objects.filter(id = instance.id).update(role = validated_data.get('role'))

        # fields = ['role','entity']
        # for field in fields:
        #     try:
        #         setattr(instance, field, validated_data[field])
        #     except KeyError:  # validated_data may not contain all fields during HTTP PATCH
        #         pass


        

       # User.objects.filter(id = instance.user).update(**userdetails)
        # print(validated_data)
        # package = validated_data.pop('user')
        # role = validated_data.pop('role')
        # package.pop('id')
        # role = Role.objects.get(id = role)
        # for key in range(len(package)):
        #     print(key)
        #     try:
        #         id = User.objects.get(email = package[key]['email'])
        #         instance.user.add(id)
        #         Userrole.objects.filter(entity = instance.id,user = id).update(role = role,entity = instance.id,user = id)
        #     except User.DoesNotExist:
        #          u = User.objects.create(**package[key])
        #          instance.user.add(u)
        #          Userrole.objects.create(role = role,entity = instance.id,user = u)

            
            
        #    # print(package[key])
        
        # # #instance.user.set(self.create_or_update_packages(package))
        # # fields = ['id','unitType','entityName','address','ownerName']
        # # for field in fields:
        # #     try:
        # #         setattr(instance, field, validated_data[field])
        # #     except KeyError:  # validated_data may not contain all fields during HTTP PATCH
        # #         pass
        # # print(instance)
        # # instance.save()
        return newuser
    

class userbyentitySerializer(serializers.ModelSerializer):


    class Meta:
        model = UserRole
        #fields = ('id','entityName','fy',)
        fields = ('username','first_name','last_name','email','password','roleid','entityid',)

    def create(self, validated_data):

        print(validated_data)

        entityid = validated_data.pop('entityid')
        roleid = validated_data.pop('roleid')
        password = make_password(validated_data.pop('password'))

        userid = User.objects.create(**validated_data,password = password)

        roleinstance = UserRole.objects.create(entity = entityid,role = roleid,user =userid)

        
        # package = validated_data.pop('user', [])
        # order = entity.objects.create(**validated_data)
        # order.user.set(self.get_or_create_packages(package))
        # return order
        return userid

    def update(self, instance, validated_data):
        print(validated_data)
        package = validated_data.pop('user', [])
        for key in range(len(package)):
            print(key)
            try:
                id = User.objects.get(email = package[key]['email'])
                instance.user.add(id)
            except User.DoesNotExist:
                 u = User.objects.create(**package[key])
                 instance.user.add(u)

            
            
           # print(package[key])
        
        # #instance.user.set(self.create_or_update_packages(package))
        # fields = ['id','unitType','entityName','address','ownerName']
        # for field in fields:
        #     try:
        #         setattr(instance, field, validated_data[field])
        #     except KeyError:  # validated_data may not contain all fields during HTTP PATCH
        #         pass
        # print(instance)
        # instance.save()
        return instance


# class entitySerializer_load(serializers.ModelSerializer):


#     entityUser = entityUserSerializer(many=True)

    

#     class Meta:
#         model = entity
#         fields = '__all__'
        

   



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
    serializer = AccountHeadSerializer
    accounthead = accountHeadSerializer2

    rateerializer = RateCalculateSerializer
    uomser = UOMSerializer
    TOGSR = TOGSerializer
    GSTSR = TOGSerializer
    PTaxType = purchasetaxtypeserializer

    InvoiceType = InvoiceTypeSerializer
    pcategory = ProductCategoryMainSerializer
    acounttype = AccountTypeJsonSerializer

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
            "Ratecalc": (self.rateerializer, {"entity": newentity, "createdby": user}),
            "UOM": (self.uomser, {"entity": newentity, "createdby": user}),
            "TOG": (self.TOGSR, {"entity": newentity, "createdby": user}),
            "GSTTYPE": (self.GSTSR, {"entity": newentity, "createdby": user}),
            "PurchaseType": (self.PTaxType, {"entity": newentity, "createdby": user}),
            "InvoiceType": (self.InvoiceType, {"entity": newentity, "createdby": user}),
            "productcategory": (self.pcategory, {"createdby": user}),
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
        for f in fy_data:
            f = dict(f)
            f.pop("id", None)
            f.pop("entity", None)
            f.pop("entity_id", None)
            f.pop("createdby", None)
            EntityFinancialYear.objects.create(entity=entity, createdby=user, **f)

        # optional: used by your downstream seeding/account creation
        accountdate = fy_data[0]["finstartyear"] if fy_data else None

        # -------------------------
        # Seed masters from account.json
        # -------------------------
        self.process_json_file(newentity=entity, user=user, accountdate1=accountdate)

        # -------------------------
        # Assign Admin role to creator
        # -------------------------
        roleid, _ = Role.objects.get_or_create(
            entity=entity,
            rolename="Admin",
            defaults={
                "roledesc": "System Admin",
                "rolelevel": 1,
              
            },
        )

        UserRole.objects.create(entity=entity, role=roleid, user=user)

        # -------------------------
        # Give all submenu privileges to Admin
        # -------------------------
        submenus = Submenu.objects.all()
        RolePrivilege.objects.bulk_create(
            [RolePrivilege(role=roleid, submenu=submenu, entity=entity) for submenu in submenus]
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
        account_details = []
        for c in constitution_data:
            c = dict(c)
            c.pop("id", None)
            c.pop("entity", None)
            c.pop("entity_id", None)
            c.pop("createdby", None)

            detail = EntityConstitution.objects.create(entity=entity, createdby=user, **c)

            # Partner/shareholder accounts based on constitution code
            if getattr(entity.const, "constcode", None) == "01":
                achead = accountHead.objects.get(entity=entity, code=6200)
                account_details.append(
                    account(
                        accounthead=achead,
                        creditaccounthead=achead,
                        accountname=detail.shareholder,
                        pan=detail.pan,
                        entity=entity,
                        createdby=user,
                        sharepercentage=detail.sharepercentage,
                        country=entity.country,
                        state=entity.state,
                        district=entity.district,
                        city=entity.city,
                        emailid=entity.email,
                        accountdate=accountdate,
                    )
                )
            elif getattr(entity.const, "constcode", None) == "02":
                achead = accountHead.objects.get(entity=entity, code=6300)
                account_details.append(
                    account(
                        accounthead=achead,
                        creditaccounthead=achead,
                        accountname=detail.shareholder,
                        pan=detail.pan,
                        entity=entity,
                        createdby=user,
                        sharepercentage=detail.sharepercentage,
                        country=entity.country,
                        state=entity.state,
                        district=entity.district,
                        city=entity.city,
                        emailid=entity.email,
                        accountdate=accountdate,
                    )
                )

        if account_details:
            account.objects.bulk_create(account_details)

        # -------------------------
        # Update default credit heads mapping
        # -------------------------
        account_updates = [
            {"code": 1000, "credit_code": 3000},
            {"code": 6000, "credit_code": 6100},
            {"code": 8000, "credit_code": 7000},
        ]
        for upd in account_updates:
            credit_head = accountHead.objects.filter(code=upd["credit_code"], entity=entity).first()
            if not credit_head:
                print(f"[WARN] Missing credit accountHead code={upd['credit_code']} for entity={entity.id}. Skipping mapping.")
                continue

            updated = account.objects.filter(accounthead__code=upd["code"], entity=entity).update(
                creditaccounthead=credit_head
            )
            if updated == 0:
                print(f"[WARN] No account rows found for mapping code={upd['code']} for entity={entity.id}.")

        return entity

    # -------------------------
    # UPDATE
    # -------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        bank_data = validated_data.pop("bank_accounts", [])
        subentity_data = validated_data.pop("subentity", [])
        fy_data = validated_data.pop("fy", [])
        constitution_data = validated_data.pop("constitution", [])

        user = validated_data.get("updatedby") or validated_data.get("createdby")

        # base entity update
        validated_data.pop("id", None)
        validated_data.pop("pk", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # nested upsert
        self._upsert_nested(BankAccount, "bank_accounts", instance, "entity", bank_data, user=None)
        self._upsert_nested(SubEntity, "subentity", instance, "entity", subentity_data, user=None)
        self._upsert_nested(EntityFinancialYear, "fy", instance, "entity", fy_data, user=user)
        self._upsert_nested(EntityConstitution, "constitution", instance, "entity", constitution_data, user=user)

        return instance

class UserEntityRoleSerializer(serializers.ModelSerializer):
    entityid = serializers.IntegerField(source='entity.id')
    entityname = serializers.CharField(source='entity.entityname')
    gstno = serializers.CharField(source='entity.gstno')
    email = serializers.EmailField(source='user.email')
    role = serializers.SerializerMethodField()
    roleid = serializers.IntegerField(source='role.id')

    class Meta:
        model = UserRole
        fields = ['entityid', 'entityname', 'email', 'gstno', 'role', 'roleid']

    def get_role(self, obj):
        return f"{obj.role.rolename} - {obj.entity.entityname}"


class UserSerializerentities(serializers.ModelSerializer):
    userid = serializers.IntegerField(source='id')
    user = serializers.EmailField(source='email')
    uentity = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['userid', 'first_name', 'last_name', 'email', 'user', 'uentity']

    def get_uentity(self, obj):
        userroles = UserRole.objects.filter(user=obj).select_related('entity', 'role')
        return UserEntityRoleSerializer(userroles, many=True).data

