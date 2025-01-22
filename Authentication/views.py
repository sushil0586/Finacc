
from django.shortcuts import render
from rest_framework import response,status,permissions
from rest_framework.generics import GenericAPIView,ListAPIView,UpdateAPIView,ListCreateAPIView
from Authentication.serializers import RegisterSerializer,LoginSerializer,UserSerializer,ChangePasswordSerializer,MainMenuSerializer,SubmenuSerializer
from django.contrib.auth import authenticate,get_user_model
from Authentication.models import User,MainMenu,Submenu
from rest_framework.response import Response






class AuthApiView(ListAPIView):

    permission_classes = (permissions.IsAuthenticated,)

    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return User.objects.filter(email = self.request.user)
    
  








class RegisterApiView(ListCreateAPIView):


    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = RegisterSerializer


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

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        # Validate presence of email and password
        if not email or not password:
            return response.Response(
                {'message': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Try to authenticate user
        user = authenticate(username=email, password=password)

        if user:
            serializer = self.serializer_class(user)
            return response.Response(serializer.data, status=status.HTTP_200_OK)

        return response.Response(
            {'message': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )





User = get_user_model()

class ChangePasswordView(UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    model = User
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, queryset=None):
        # Return the currently authenticated user
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check if the old password is correct
            old_password = serializer.data.get("old_password")
            if not self.object.check_password(old_password):
                return Response(
                    {"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if the new password is different from the old password
            new_password = serializer.data.get("new_password")
            if old_password == new_password:
                return Response(
                    {"new_password": ["New password cannot be the same as the old password."]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Set the new password (it will be hashed automatically)
            self.object.set_password(new_password)
            self.object.save()

            response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Password updated successfully',
                'data': []
            }

            return Response(response, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class MenusApiView(ListCreateAPIView):
    serializer_class = MainMenuSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Use `only` to fetch specific fields and avoid loading unnecessary data
        return MainMenu.objects.only(
            'id', 'mainmenu', 'menuurl', 'menucode', 'order'
        ).order_by('order')
    

class SubMenusApiView(ListCreateAPIView):
    serializer_class = SubmenuSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Use `only` to fetch specific fields and avoid fetching unnecessary data
        return Submenu.objects.only('id', 'submenu', 'submenucode', 'subMenuurl', 'mainmenu', 'order').order_by('order')

       





    





