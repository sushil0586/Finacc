#import imp
from django.db import models
from rest_framework import serializers
from Authentication.models import User,MainMenu,Submenu
#from entity.models import enti
#from entity.serializers import entityUserSerializer

class Registerserializers(serializers.ModelSerializer):

    password = serializers.CharField(max_length = 128, min_length = 6, write_only = True)
  #  id = serializers.IntegerField(required = False)

   


    class Meta:
        model = User
        
        fields = ('username','first_name','last_name','email','password','is_active',)
    #     extra_kwargs = {'id': {'read_only': False},
    #      'username': {'validators': []},
    #      'email': {'validators': []}}

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #     print(representation)
    #    # if representation['is_active'] == True:
    #     return representation
        
        

    # def create(self, validated_data):
    #     groups_data = validated_data.pop('groups')
    #     user = User.objects.create_user(**validated_data)
    #     for group_data in groups_data:
    #          # Group.objects.create(user=user, **group_data)
    #          user.groups.add(group_data)
    #     return user





    
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password')
        # Removed `queryset` as it's not valid in `Meta` for serializers

    def create(self, validated_data):
        # Create a new user instance and hash the password
        user = User.objects.create_user(**validated_data)
        print(user)  # Consider logging instead of printing in production
        return user

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True
    )
  

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password', 'uentity')
        depth = 1

    
    
        # if obj.role is None:
        #     return 'null'   
        # else :
        #     return obj.maincategory.pcategoryname

    
       

class LoginSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True
    )

    class Meta:
        model = User
        fields = ('email', 'password', 'token', 'id')
        read_only_fields = ('token',)


class ChangePasswordSerializer(serializers.Serializer):
    model = User

    """
    Serializer for password change endpoint.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)









class SubmenuSerializer(serializers.ModelSerializer):
    mainmenu = serializers.ReadOnlyField(source='mainmenu.mainmenu')

    class Meta:
        model = Submenu
        fields = ('id', 'submenu', 'submenucode', 'subMenuurl', 'mainmenu')
        ordering = ['order']  # Corrected `order_by` to `ordering` for proper usage

        



class MainMenuSerializer(serializers.ModelSerializer):
    submenu = SubmenuSerializer(many=True)
    #accountname= serializers.SerializerMethodField()
    class Meta:
        model = MainMenu
        fields = ('mainmenu','menuurl','menucode','submenu',)


       







    






