import imp
from django.db import models
from rest_framework import serializers
from Authentication.models import User,userRole,MainMenu,Submenu,rolepriv
#from entity.models import enti
#from entity.serializers import entityUserSerializer

class Registerserializers(serializers.ModelSerializer):

    password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)
    id = serializers.IntegerField(required = False)

   


    class Meta:
        model = User
        
        fields = ('id','username','first_name','last_name','email','role','password','is_active',)
        extra_kwargs = {'id': {'read_only': False},
         'username': {'validators': []},
         'email': {'validators': []}}

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        print(representation)
       # if representation['is_active'] == True:
        return representation
        
        

    def create(self, validated_data):
        groups_data = validated_data.pop('groups')
        user = User.objects.create_user(**validated_data)
        for group_data in groups_data:
             # Group.objects.create(user=user, **group_data)
             user.groups.add(group_data)
        return user





    
class Registerserializer(serializers.ModelSerializer):

    password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)

   


    class Meta:
        model = User
        queryset = User.objects.filter(is_active = 1)
        fields = ('username','first_name','last_name','role','email','password',)

        

    def create(self, validated_data):
        user = User.objects.create(**validated_data)
        print(user)
        # groups_data = validated_data.pop('groups')
        # user = User.objects.create_user(**validated_data)
        # for group_data in groups_data:
        #      # Group.objects.create(user=user, **group_data)
        #      user.groups.add(group_data)
        return user

class Userserializer(serializers.ModelSerializer):

    password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)

   # userentity = entityUserSerializer(many=True)

    #userentity = entityUserSerializer(many=True)

    roleid = serializers.SerializerMethodField()


    class Meta:
        model = User
        fields = ('first_name','last_name','email','role','password','uentity','roleid',)
        depth = 1

    
    def get_roleid(self,obj):
        if obj.role is None:
            return 1   
        else:
            acc =  obj.role.id
            return acc
        # if obj.role is None:
        #     return 'null'   
        # else :
        #     return obj.maincategory.pcategoryname

    
       

class LoginSerializer(serializers.ModelSerializer):

    password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)


    class Meta:
        model = User
        fields = ('email','password','token','id',)

        read_only_fields = ['token']


class ChangePasswordSerializer(serializers.Serializer):
    model = User

    """
    Serializer for password change endpoint.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)




class RoleSerializer(serializers.ModelSerializer):

    #password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)


    class Meta:
        model = userRole
        fields = ('id','rolename','roledesc',)




class submenuSerializer(serializers.ModelSerializer):
    mainmenu= serializers.SerializerMethodField()
    def get_mainmenu(self, obj):

            return obj.mainmenu.mainmenu    

    class Meta:
        model = Submenu
        fields =  ( 'id','submenu','submenucode','subMenuurl','mainmenu',)
        order_by = ('order')

        



class mainmenuserializer(serializers.ModelSerializer):
    submenu = submenuSerializer(many=True)
    #accountname= serializers.SerializerMethodField()
    class Meta:
        model = MainMenu
        fields = ('mainmenu','menuurl','menucode','submenu',)


        def get_accountname(self, obj):
         print(obj)

         return obj.account.accountname



class roleprivserializer(serializers.ModelSerializer):
    menus = serializers.SerializerMethodField()

    class Meta:
        model = rolepriv
        fields = ['role','menus','mainmenu']

    
    def get_menus(self,obj):
        print(obj)
        menus =  MainMenu.objects.filter()
        return mainmenuserializer(menus, many=True).data
      #  return menus



    






