#import imp
from struct import pack
from rest_framework import serializers
from entity.models import Entity,entity_details,unitType,entityfinancialyear,entityconstitution,Constitution,subentity,Role,Rolepriv,Userrole
from Authentication.models import User,Submenu
from Authentication.serializers import Registerserializers
from financial.models import accountHead,account
from financial.serializers import accountHeadSerializer,accountSerializer,accountHeadSerializer2,accounttypeserializer
from inventory.serializers import Ratecalculateserializer,UOMserializer,TOGserializer,GSTserializer,ProductCategoryMainSerializer
from invoice.serializers import purchasetaxtypeserializer
import os
import json
import collections
from django.contrib.auth.hashers import make_password


#from Authentication.serializers import userserializer








class rolemainSerializer1(serializers.ModelSerializer):
  
    class Meta:
        model = Role
        fields = ('id','rolename','roledesc','rolelevel','entity',)



class roleprivdetailSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = Rolepriv
        fields =  ('role','submenu','entity',)




class rolemainSerializer(serializers.ModelSerializer):
    submenudetails = roleprivdetailSerializer(many=True)
    class Meta:
        model = Role
        fields = ('id','rolename','roledesc','rolelevel','entity','submenudetails',)
    def create(self, validated_data):
        roledetails_data = validated_data.pop('submenudetails')

        roleid = Role.objects.create(**validated_data)
        for roledetail_data in roledetails_data:
            detail = Rolepriv.objects.create(role = roleid, **roledetail_data)
               
          
        return roleid
    
    def update(self, instance, validated_data):
        fields = ['rolename','roledesc','rolelevel','entity',]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:  # validated_data may not contain all fields during HTTP PATCH
                pass
        
        instance.save()
       
        Rolepriv.objects.filter(role=instance,entity = instance.entity).delete()
        roledetails_data = validated_data.get('submenudetails')

        for roledetail_data in roledetails_data:
            detail = Rolepriv.objects.create(role = instance, **roledetail_data)
                

        
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




class entityfinancialyearSerializer(serializers.ModelSerializer):


    entityname = serializers.SerializerMethodField()
    gst = serializers.SerializerMethodField()

    class Meta:
        model = entityfinancialyear
        fields = ('id','entity','entityname','gst','desc','finstartyear','finendyear','createdby','isactive',)


    
    def get_entityname(self,obj):
         
        return obj.entity.entityname
    

    def get_gst(self,obj):
         
        return obj.entity.gstno



    def create(self, validated_data):


        r1 = entityfinancialyear.objects.filter(entity= validated_data['entity'].id).update(isactive=0)



        #entity= validated_data['entity'].id

        fy = entityfinancialyear.objects.create(**validated_data)


        return fy
    


class entityfinancialyearListSerializer(serializers.ModelSerializer):

    class Meta:

        model = entityfinancialyear
        fields = ('id','finstartyear','finendyear','isactive',)


class subentitySerializer(serializers.ModelSerializer):

    class Meta:

        model = subentity
        fields = ('id','subentityname','address','country','state','district','city','pincode','phoneoffice','phoneresidence','email','entity')


class subentitySerializerbyentity(serializers.ModelSerializer):

    class Meta:

        model = subentity
        fields = ('id','subentityname')


    
    


    

    









class entityAddSerializer(serializers.ModelSerializer):

    fy = entityfinancialyearSerializer(many=True)
    constitution = entityconstitutionSerializer(many=True)

    class Meta:
        model = Entity
        #fields = ('id','entityName','fy',)
        fields = ('entityname','address','ownername','country','state','district','city','pincode','phoneoffice','phoneresidence','panno','tds','tdscircle','email','tcs206c1honsale','gstno','gstintype','const','user','fy','constitution','legalname','address2','addressfloorno','addressstreet','blockstatus','dateofreg','dateofdreg',)

   # entity_accountheads = accountHeadSerializer(many=True)

    serializer = accountHeadSerializer
    accounthead = accountHeadSerializer2
    roleserializer = rolemainSerializer1
    rateerializer = Ratecalculateserializer
    uomser = UOMserializer
    TOGSR = TOGserializer
    GSTSR = GSTserializer
    PTaxType = purchasetaxtypeserializer
    pcategory = ProductCategoryMainSerializer
    acounttype = accounttypeserializer
    def create(self, validated_data):


    


      #  print(validated_data)


        #print(validated_data)

        users = validated_data.pop("user")

        fydata = validated_data.pop("fy")
        constitutiondata = validated_data.pop("constitution")
        newentity = Entity.objects.create(**validated_data)
        for PurchaseOrderDetail_data in fydata:
              
                detail = entityfinancialyear.objects.create(entity = newentity, **PurchaseOrderDetail_data,createdby =users[0])

  



        accountdate1 = entityfinancialyear.objects.get(entity = newentity).finstartyear






        






       




        for user in users:
            newentity.user.add(user)

        file_path = os.path.join(os.getcwd(), "account.json")
        with open(file_path, 'r') as jsonfile:
            json_data = json.load(jsonfile)
            for key in json_data["entity_accountheads"]:
                serializer2 = self.serializer(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,owner = users[0],acountdate = accountdate1)

            for key in json_data["accountheads"]:
                serializer2 = self.accounthead(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,owner = users[0])

            for key in json_data["Roles"]:
                serializer2 = self.roleserializer(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity)
                #print(key)

            for key in json_data["Ratecalc"]:
                serializer2 = self.rateerializer(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])

            for key in json_data["UOM"]:
                serializer2 = self.uomser(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])

            for key in json_data["TOG"]:
                serializer2 = self.TOGSR(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])

            for key in json_data["GSTTYPE"]:
                serializer2 = self.GSTSR(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])

            for key in json_data["ACCOUNTTYPE"]:
                serializer2 = self.acounttype(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])

            for key in json_data["PurchaseType"]:
                serializer2 = self.PTaxType(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(entity = newentity,createdby = users[0])
            for key in json_data["productcategory"]:
                serializer2 = self.pcategory(data =key)
                serializer2.is_valid(raise_exception=True)
                serializer2.save(createdby = users[0])

        

        roleid = Role.objects.get(entity = newentity,rolename = 'Admin')
        roleinstance = Userrole.objects.create(entity = newentity,role = roleid,user = users[0])

        subentity.objects.create(subentityname = 'Main-Branch',address = newentity.address,country = newentity.country,state = newentity.state,district = newentity.district,city = newentity.city,pincode = newentity.pincode,phoneoffice = newentity.phoneoffice,phoneresidence = newentity.phoneresidence,entity = newentity)


        


        

        submenus = Submenu.objects.all()
        for submenu in submenus:
            Rolepriv.objects.create(role = roleid,submenu=submenu,entity = newentity )

    
        for PurchaseOrderDetail_data in constitutiondata:

                # print(PurchaseOrderDetail_data)
                    detail = entityconstitution.objects.create(entity = newentity, **PurchaseOrderDetail_data,createdby =users[0])

                    print(newentity.const.constcode)

                    if newentity.const.constcode == "01":
                        achead = accountHead.objects.get(entity = newentity,code = 6200)
                        detail2 = account.objects.create(accounthead = achead,creditaccounthead = achead, accountname = detail.shareholder,pan = detail.pan,entity = newentity,owner = users[0],sharepercentage = detail.sharepercentage,country = newentity.country,state = newentity.state,district = newentity.district,city = newentity.city,emailid = newentity.email,accountdate = accountdate1,)

                    if newentity.const.id == "02":

                        achead = accountHead.objects.get(entity = newentity,code = 6300)
                        detail2 = account.objects.create(accounthead = achead,creditaccounthead = achead,accountname = detail.shareholder,pan = detail.pan,entity = newentity,owner = users[0],sharepercentage = detail.sharepercentage,country = newentity.country,state = newentity.state,district = newentity.district,city = newentity.city,emailid = newentity.email,accountdate = accountdate1,)


        account.objects.filter(accounthead__code = 1000,entity = newentity).update(creditaccounthead = accountHead.objects.get(code = 3000,entity = newentity))
        account.objects.filter(accounthead__code = 6000,entity = newentity).update(creditaccounthead = accountHead.objects.get(code = 6100,entity = newentity))
        account.objects.filter(accounthead__code = 8000,entity = newentity).update(creditaccounthead = accountHead.objects.get(code = 7000,entity = newentity))

        return newentity




    



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
