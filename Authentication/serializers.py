#import imp
from django.db import models
from rest_framework import serializers
from Authentication.models import User,MainMenu,Submenu
from entity.models import UserRole
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
        return user

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True
    )
    uentity = serializers.SerializerMethodField()
  

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password', 'uentity')
        depth = 1

    def get_uentity(self, obj):
        user_roles = UserRole.objects.filter(user=obj).select_related('entity', 'role')
        return [
            {
                "entityid": item.entity_id,
                "entityname": item.entity.entityname if item.entity_id else None,
                "email": obj.email,
                "gstno": item.entity.gstno if item.entity_id else None,
                "role": item.role_id,
                "roleid": item.role_id,
            }
            for item in user_roles
        ]


class AuthenticatedUserSerializer(serializers.ModelSerializer):
    entity_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "email_verified",
            "is_active",
            "is_staff",
            "entity_count",
        )

    def get_entity_count(self, obj):
        return UserRole.objects.filter(user=obj).values("entity_id").distinct().count()

    
    
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


class LogoutSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True)


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(max_length=128, min_length=6)


class RequestEmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)


class ResendEmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


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


       







    






