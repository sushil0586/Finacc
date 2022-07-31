import imp
from struct import pack
from rest_framework import serializers
from entity.models import entity,entity_details,unitType
from Authentication.models import User
from Authentication.serializers import Registerserializers,RoleSerializer
from financial.models import accountHead,account
from financial.serializers import accountHeadSerializer,accountSerializer
from inventory.serializers import Ratecalculateserializer,UOMserializer,TOGserializer,GSTserializer
import os
import json

#from Authentication.serializers import userserializer


class unitTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = unitType
        fields = '__all__'


class entityAddSerializer(serializers.ModelSerializer):

   # entity_accountheads = accountHeadSerializer(many=True)

    serializer = accountHeadSerializer
    roleserializer = RoleSerializer
    rateerializer = Ratecalculateserializer
    uomser = UOMserializer
    TOGSR = TOGserializer
    GSTSR = GSTserializer
    def create(self, validated_data):


        #print(validated_data)

        users = validated_data.pop("user")
        newentity = entity.objects.create(**validated_data)
        for user in users:
            newentity.user.add(user)

        file_path = os.path.join(os.getcwd(), "account.json")
        with open(file_path, 'r') as jsonfile:
            json_data = json.load(jsonfile)
            for key in json_data["entity_accountheads"]:
                serializer2 = self.serializer(data =key)
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
                
                    

        

        # file_path = os.path.join(os.getcwd(), "Roles.json")
        # with open(file_path, 'r') as jsonfile:
        #     json_data = json.load(jsonfile)
        #     print(json_data["Roles"])
            
             


        

        
        
        

        # # pk = (salereturn.objects.last()).voucherno
        # # print(pk)
        # #print(order)
        # for accounthead_data in accountheads_data:
           
        #     accounts = accounthead_data.pop('accounthead_accounts')
           
        #     accountheadid = accountHead.objects.create(entity = newentity,**accounthead_data,owner =users[0])
            
        #     for account1 in accounts:
                
        #         account.objects.create(entity = newentity,accounthead = accountheadid,**account1,owner = users[0])

        return newentity




    class Meta:
        model = entity
        fields = '__all__'



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


class entitySerializer(serializers.ModelSerializer):


    user = Registerserializers(many=True)


    serializer = Registerserializers

    

    class Meta:
        model = entity
        fields = ['user',]
        depth =1

  

    def get_or_create_packages(self, packages):
        package_ids = []
        for package in packages:
            package_instance, created = User.objects.get_or_create(pk=package.get('id'), defaults=package)
            package_ids.append(package_instance.pk)
        return package_ids

    def create_or_update_packages(self, packages):
        package_ids = []
        for package in packages:
            package_id = package.get('id', None)
            print(package_id)

            package_instance, created = User.objects.update_or_create(pk=package.get('id'), defaults=package)
            package_ids.append(package_instance.pk)
        return package_ids

    def create(self, validated_data):
        package = validated_data.pop('user', [])
        order = entity.objects.create(**validated_data)
        order.user.set(self.get_or_create_packages(package))
        return order

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
        fields = ('entity','style','commodity','weightDecimal','email','registrationno','division','collectorate',)


   
        
        # #print(tracks_data)
        # for PurchaseOrderDetail_data in PurchaseOrderDetails_data:
        #     PurchaseOrderDetails.objects.create(purchaseOrder = order, **PurchaseOrderDetail_data)
        # return order