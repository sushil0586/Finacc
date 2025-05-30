#import imp
from struct import pack
from rest_framework import serializers
from entity.models import Entity,entity_details,unitType,entityfinancialyear,entityconstitution,Constitution,subentity,Role,Rolepriv,Userrole,GstRegitrationTypes,BankAccount
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
        model = Rolepriv
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
        Rolepriv.objects.bulk_create([
            Rolepriv(role=role, **roledetail_data) for roledetail_data in roledetails_data
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
        Rolepriv.objects.filter(role=instance, entity=instance.entity).delete()
        roledetails_data = validated_data.get('submenudetails', [])

        # Bulk create RolePriv instances
        Rolepriv.objects.bulk_create([
            Rolepriv(role=instance, **roledetail_data) for roledetail_data in roledetails_data
        ])

        return instance


 



class roleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Rolepriv
        fields = '__all__'



class ConstitutionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Constitution
        fields = '__all__'


class unitTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = unitType
        fields = '__all__'


class entityconstitutionSerializer(serializers.ModelSerializer):

    class Meta:
        model = entityconstitution
        fields = '__all__'


class EntityFinancialYearSerializecreate(serializers.ModelSerializer):
    # Derived fields from related 'entity' model
    entityname = serializers.CharField(source='entity.entityname', read_only=True)
    gst = serializers.CharField(source='entity.gstno', read_only=True)

    class Meta:
        model = entityfinancialyear
        fields = (
            'id', 'entity', 'entityname', 'gst', 'desc',
            'finstartyear', 'finendyear', 'createdby', 'isactive',
        )

    def create(self, validated_data):
        # Use a transaction to ensure atomicity
        with transaction.atomic():
            entity_id = validated_data['entity'].id
            # Update all previous records for the entity to inactive
            entityfinancialyear.objects.filter(entity=entity_id).update(isactive=False)

            # Create a new financial year record for the entity
            return entityfinancialyear.objects.create(**validated_data)






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
        model = entityfinancialyear
        fields = (
            'id', 'entity', 'entityname', 'gst', 'desc',
            'finstartyear', 'finendyear', 'createdby', 'isactive',
            'activestartdate', 'activeenddate', 'activeyearid'
        )

    def _get_financialyear(self):
        """Fetch financial year based on financialyearid or active year"""
        financialyearid = self.context.get('financialyearid')
        if financialyearid == 0:
            return entityfinancialyear.objects.filter(isactive=True).first()
        try:
            return entityfinancialyear.objects.get(id=financialyearid)
        except entityfinancialyear.DoesNotExist:
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
            entityfinancialyear.objects.filter(entity=entity_id).update(isactive=False)
            return entityfinancialyear.objects.create(**validated_data)
    


class entityfinancialyearListSerializer(serializers.ModelSerializer):

    class Meta:

        model = entityfinancialyear
        fields = ('id','finstartyear','finendyear','isactive',)


class subentitySerializer(serializers.ModelSerializer):

    class Meta:

        model = subentity
        fields = ('id','subentityname','address','country','state','district','city','pincode','phoneoffice','phoneresidence','email','ismainentity', 'entity')


class subentitySerializerbyentity(serializers.ModelSerializer):

    class Meta:

        model = subentity
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
            entityfinancialyear(entity=newentity, **data, createdby=users[0])
            for data in fydata
        ]

        # Bulk create financial years
        if fy_details:
            entityfinancialyear.objects.bulk_create(fy_details)

        # Retrieve account start date
        accountdate1 = fy_details[0].finstartyear if fy_details else None

        # Add users to the entity
        newentity.user.add(*users)

        # Process additional JSON file logic
        self.process_json_file(newentity=newentity, users=users, accountdate1=accountdate1)

        # Create admin role and user role
        roleid = Role.objects.get(entity=newentity, rolename="Admin")
        Userrole.objects.create(entity=newentity, role=roleid, user=users[0])

        # Create default subentity
        subentity.objects.create(
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
            Rolepriv(role=roleid, submenu=submenu, entity=newentity) for submenu in submenus
        ]
        Rolepriv.objects.bulk_create(role_privileges)

        # Process constitution data
        constitution_details = []
        account_details = []

        for data in constitutiondata:
            detail = entityconstitution(entity=newentity, **data, createdby=users[0])
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

        entityconstitution.objects.bulk_create(constitution_details)
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
        model = entityfinancialyear
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
        model = Userrole
        fields = ('user','role','entity',)

        

  

    

    

    def create(self, validated_data):
        userdetails = validated_data.pop('user')

        # print(userdetails.get('email'))

        # if  User.objects.get(email = userdetails.get('email')).count() > 0:
        #     return 1
        # else:
        user = User.objects.create(**userdetails)
        userrole = Userrole.objects.create(user = user,**validated_data )
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

        
        newuser = Userrole.objects.filter(id = instance.id).update(role = validated_data.get('role'))

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
        model = Userrole
        #fields = ('id','entityName','fy',)
        fields = ('username','first_name','last_name','email','password','roleid','entityid',)

    def create(self, validated_data):

        print(validated_data)

        entityid = validated_data.pop('entityid')
        roleid = validated_data.pop('roleid')
        password = make_password(validated_data.pop('password'))

        userid = User.objects.create(**validated_data,password = password)

        roleinstance = Userrole.objects.create(entity = entityid,role = roleid,user =userid)

        
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
        model = entity_details
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
        model = GstRegitrationTypes
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
        exclude = ['entity']


class SubEntityNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = subentity
        exclude = ['entity']


class EntityFinancialYearNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = entityfinancialyear
        exclude = ['entity']


class EntityConstitutionNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = entityconstitution
        exclude = ['entity']


class EntityNewSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountNewSerializer(many=True)
    subentity = SubEntityNewSerializer(many=True)
    fy = EntityFinancialYearNewSerializer(many=True)
    constitution = EntityConstitutionNewSerializer(many=True)

    class Meta:
        model = Entity
        fields = '__all__'

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
            "acconttype": (self.acounttype, {"entity": newentity, "createdby": users}),
            # "accountheads": (self.accounthead, {"entity": newentity, "createdby": users[0]}),
            "Roles": (self.roleserializer, {"entity": newentity}),
            "Ratecalc": (self.rateerializer, {"entity": newentity, "createdby": users}),
            "UOM": (self.uomser, {"entity": newentity, "createdby": users}),
            "TOG": (self.TOGSR, {"entity": newentity, "createdby": users}),
            "GSTTYPE": (self.GSTSR, {"entity": newentity, "createdby": users}),
          #  "ACCOUNTTYPE": (self.acounttype, {"entity": newentity, "createdby": users[0]}),
            "PurchaseType": (self.PTaxType, {"entity": newentity, "createdby": users}),
            "InvoiceType": (self.InvoiceType, {"entity": newentity, "createdby": users}),
            "productcategory": (self.pcategory, {"createdby": users}),
        }

        # Iterate through the JSON keys and process data
        for key, (serializer_class, extra_kwargs) in serializers_mapping.items():
            if key in json_data:
                objects_to_create = []
                for item in json_data[key]:
                    serializer = serializer_class(data=item)
                    serializer.is_valid(raise_exception=True)
                    objects_to_create.append(serializer.save(**extra_kwargs))

    from django.db import transaction

    @transaction.atomic
    def create(self, validated_data):
        bank_data = validated_data.pop('bank_accounts', [])
        subentities_data = validated_data.pop('subentity', [])
        financial_years_data = validated_data.pop('fy', [])
        constitutions_data = validated_data.pop('constitution', [])
        user = validated_data.get("createdby")
        account_details = []

        # Create the main entity
        entity = Entity.objects.create(**validated_data)

        # Create related financial years
        for f in financial_years_data:
            entityfinancialyear.objects.create(entity=entity, **f)

        accountdate = financial_years_data[0]['finstartyear'] if financial_years_data else None

        # Process uploaded chart of accounts (if applicable)
        self.process_json_file(newentity=entity, users=user, accountdate1=accountdate)

        # Create Admin role association
        roleid = Role.objects.get(entity=entity, rolename="Admin")
        Userrole.objects.create(entity=entity, role=roleid, user=user)

        # Create related bank accounts
        for b in bank_data:
            BankAccount.objects.create(entity=entity, **b)

        # Create sub-entities
        for s in subentities_data:
            subentity.objects.create(entity=entity, **s)

        # Create constitutions
        for c in constitutions_data:
            detail = entityconstitution.objects.create(entity=entity, **c)

            if entity.const.constcode == "01":
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
            elif entity.const.id == "02":
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
                        accountdate=entity,
                    )
                )

        

        submenus = Submenu.objects.all()
        role_privileges = [
            Rolepriv(role=roleid, submenu=submenu, entity=entity) for submenu in submenus
        ]
        Rolepriv.objects.bulk_create(role_privileges)

        # Process constitution data
        
        

       

            # Logic for account creation based on constitution code
        

       
        account.objects.bulk_create(account_details)

        # Update accounts in bulk
        account_updates = [
            {"code": 1000, "credit_code": 3000},
            {"code": 6000, "credit_code": 6100},
            {"code": 8000, "credit_code": 7000},
        ]
        for update in account_updates:
            account.objects.filter(accounthead__code=update["code"], entity=entity).update(
                creditaccounthead=accountHead.objects.get(code=update["credit_code"], entity=entity)
            )

        return entity

    

    def update(self, instance, validated_data):
        def update_nested_data(model, related_name, child_data, parent_instance, parent_field, lookup_field='id'):
            existing_items = getattr(parent_instance, related_name).all()
            existing_map = {getattr(item, lookup_field): item for item in existing_items}
            new_ids = []

            for item_data in child_data:
                item_id = item_data.get(lookup_field)
                if item_id and item_id in existing_map:
                    # Update existing item
                    child_instance = existing_map[item_id]
                    for attr, value in item_data.items():
                        setattr(child_instance, attr, value)
                    child_instance.save()
                    new_ids.append(item_id)
                else:
                    # Create new item
                    model.objects.create(**item_data, **{parent_field: parent_instance})

            # Delete removed items
            for item_id, item in existing_map.items():
                if item_id not in new_ids:
                    item.delete()

        bank_data = validated_data.pop('bank_accounts', [])
        subentity_data = validated_data.pop('subentity', [])
        fy_data = validated_data.pop('fy', [])
        constitution_data = validated_data.pop('constitution', [])

        # Update base fields of entity
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        update_nested_data(BankAccount, 'bank_accounts', bank_data, instance, parent_field='entity')
        update_nested_data(subentity, 'subentity', subentity_data, instance, parent_field='entity')
        update_nested_data(entityfinancialyear, 'fy', fy_data, instance, parent_field='entity')
        update_nested_data(entityconstitution, 'constitution', constitution_data, instance, parent_field='entity')

        return instance
    

class UserEntityRoleSerializer(serializers.ModelSerializer):
    entityid = serializers.IntegerField(source='entity.id')
    entityname = serializers.CharField(source='entity.entityname')
    gstno = serializers.CharField(source='entity.gstno')
    email = serializers.EmailField(source='user.email')
    role = serializers.SerializerMethodField()
    roleid = serializers.IntegerField(source='role.id')

    class Meta:
        model = Userrole
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
        userroles = Userrole.objects.filter(user=obj).select_related('entity', 'role')
        return UserEntityRoleSerializer(userroles, many=True).data

