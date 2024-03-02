
from django.shortcuts import render
from rest_framework import response,status,permissions
from rest_framework.generics import GenericAPIView,ListAPIView,UpdateAPIView,ListCreateAPIView
from Authentication.serializers import Registerserializer,LoginSerializer,Userserializer,ChangePasswordSerializer,RoleSerializer,mainmenuserializer,roleprivserializer,submenuSerializer
from django.contrib.auth import authenticate
from Authentication.models import User,userRole,MainMenu,rolepriv,Submenu
from rest_framework.response import Response





class AuthApiView(ListAPIView):

    permission_classes = (permissions.IsAuthenticated,)

    serializer_class = Userserializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return User.objects.filter(email = self.request.user)
    
  








class RegisterApiView(ListCreateAPIView):


    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = Registerserializer


    def perform_create(self, serializer):
        return serializer.save()

    # def post(self,request):
    #     serializer = self.serializer_class(data = request.data)

    #     if serializer.is_valid():
    #         serializer.save()
    #         return response.Response(serializer.data,status = status.HTTP_200_OK)
    #     return response.Response(serializer.errors,status = status.HTTP_400_BAD_REQUEST)

class LoginApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []

    serializer_class = LoginSerializer


    def post(self,request):
        email = request.data.get('email',None)
        password = request.data.get('password',None)

        user = authenticate(username = email,password = password)

        if user:
            serializer = self.serializer_class(user)
            return response.Response(serializer.data,status = status.HTTP_200_OK)
        return response.Response({'message': "Invalid credentials"},status = status.HTTP_401_UNAUTHORIZED)



class roleapiview(ListAPIView):

    serializer_class = RoleSerializer
   # permission_classes = (permissions.IsAuthenticated,)

   # filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    
    def get_queryset(self): 
        entity = self.request.query_params.get('entity')
        return userRole.objects.filter()

class ChangePasswordView(UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    model = User
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, queryset=None):
        obj = self.request.user
        return obj

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
            # set_password also hashes the password that the user will get
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Password updated successfully',
                'data': []
            }

            return Response(response)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class MenusApiView(ListCreateAPIView):

    serializer_class = mainmenuserializer
    permission_classes = (permissions.IsAuthenticated,)

  #  filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    #def perform_create(self, serializer):
     #   return serializer.save(owner = self.request.user)
    
    def get_queryset(self):

        # menus = rolepriv.objects.filter().select_related('roles')

        # print(menus)

        return MainMenu.objects.filter().order_by('order')

       # entity = self.request.query_params.get('entity')
    

class subMenusApiView(ListCreateAPIView):

    serializer_class = submenuSerializer
    permission_classes = (permissions.IsAuthenticated,)

  #  filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    #def perform_create(self, serializer):
     #   return serializer.save(owner = self.request.user)
    
    def get_queryset(self):

        # menus = rolepriv.objects.filter().select_related('roles')

        # print(menus)

        return Submenu.objects.filter().order_by('order')
       



class roleprivApiView(ListCreateAPIView):

    serializer_class = roleprivserializer
    permission_classes = (permissions.IsAuthenticated,)

  #  filter_backends = [DjangoFilterBackend]
    #filterset_fields = ['id','unitType','entityName']

    #def perform_create(self, serializer):
     #   return serializer.save(owner = self.request.user)
    
    def get_queryset(self):

        menus = rolepriv.objects.filter(role = 1).prefetch_related('role')

        print(roleprivserializer(menus, many=True).data)
        print(menus)

        # menus = rolepriv.objects.filter().select_related('roles')

        # print(menus)

        return menus

    





