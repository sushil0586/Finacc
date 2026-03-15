
from django.shortcuts import render
from django.utils.decorators import method_decorator

from rest_framework import response,status,permissions
from rest_framework.generics import GenericAPIView,ListAPIView,UpdateAPIView,ListCreateAPIView
from Authentication.serializers import (
    RegisterSerializer,LoginSerializer,UserSerializer,ChangePasswordSerializer,MainMenuSerializer,
    SubmenuSerializer,LogoutSerializer,RefreshTokenSerializer,ForgotPasswordSerializer,
    ResetPasswordSerializer,RequestEmailVerificationSerializer,VerifyEmailSerializer,
    AuthenticatedUserSerializer, ResendEmailVerificationSerializer,
)
from django.contrib.auth import authenticate,get_user_model
from Authentication.models import User,MainMenu,Submenu
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from Authentication.services import AuthAuditService, AuthOTPService, AuthSettings, AuthTokenService, LoginRateLimitService
from subscriptions.services import SubscriptionService






class AuthApiView(ListAPIView):

    permission_classes = (permissions.IsAuthenticated,)

    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return User.objects.filter(pk=self.request.user.pk)


class AuthMeView(GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = AuthenticatedUserSerializer

    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
  








class RegisterApiView(ListCreateAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        intent = getattr(user, '_signup_intent', SubscriptionService.INTENT_STANDARD)
        subscription = SubscriptionService.build_subscription_snapshot(user=user)
        payload = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'intent': intent,
            'trial_started': subscription['subscription']['is_trial'],
            'message': 'Your free trial has started.' if subscription['subscription']['is_trial'] else 'Account created successfully.',
            'subscription': subscription,
        }
        headers = self.get_success_headers(serializer.data)
        return Response(payload, status=status.HTTP_201_CREATED, headers=headers)

from django.shortcuts import get_object_or_404
import logging

logger = logging.getLogger(__name__)

class LoginApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = LoginSerializer

    # Limit to 5 login attempts per minute per IP.
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        ip_address = _client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        entity_hint = request.headers.get("X-Entity-Id") or request.data.get("entity") or ""

        if not email or not password:
            logger.warning("Login attempt with missing email or password")
            return response.Response(
                {'message': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            LoginRateLimitService.check_allowed(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                entity_hint=entity_hint,
            )
            user = authenticate(request, email=email, password=password)
            if not user:
                # Compatibility fallback for backends expecting username kwarg.
                user = authenticate(request, username=email, password=password)
        except Exception as e:
            logger.exception("Error during authentication for email: %s", email)
            return response.Response(
                {'message': 'Internal server error during authentication'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if not user:
            logger.info("Invalid credentials for email: %s", email)
            LoginRateLimitService.record_failure(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                entity_hint=entity_hint,
            )
            AuthAuditService.log(
                "login_failed",
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_credentials"},
            )
            return response.Response(
                {'message': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if AuthSettings.REQUIRE_EMAIL_VERIFIED and not user.email_verified:
            LoginRateLimitService.record_failure(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                entity_hint=entity_hint,
            )
            AuthAuditService.log(
                "login_failed",
                user=user,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "email_not_verified"},
            )
            return response.Response(
                {
                    'message': 'Email is not verified',
                    'code': 'email_not_verified',
                    'next_action': 'verify_email',
                    'email': user.email,
                    'verify_endpoint': '/api/auth/verify-email',
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            session, access_token, refresh_token = AuthTokenService.issue_token_pair(
                user,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        except Exception as e:
            logger.exception("Serialization error for user: %s", email)
            return response.Response(
                {'message': 'Internal server error during token generation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        LoginRateLimitService.clear(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            entity_hint=entity_hint,
        )
        AuthAuditService.log("login_success", user=user, ip_address=ip_address, user_agent=user_agent)

        data = {
            "email": user.email,
            "id": user.id,
            "token": access_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": int((session.expires_at - session.issued_at).total_seconds()),
            "refresh_expires_in": int((session.refresh_expires_at - session.issued_at).total_seconds()),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email_verified": user.email_verified,
            },
        }
        return response.Response(data, status=status.HTTP_200_OK)






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
            old_password = serializer.validated_data.get("old_password")
            if not self.object.check_password(old_password):
                return Response(
                    {"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST
                )
             
            # Check if the new password is different from the old password
            new_password = serializer.validated_data.get("new_password")
            if old_password == new_password:
                return Response(
                    {"new_password": ["New password cannot be the same as the old password."]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Set the new password (it will be hashed automatically)
            self.object.set_password(new_password)
            self.object.save()
            AuthTokenService.bump_token_version(self.object)
            AuthTokenService.revoke_all_for_user(self.object, reason="password_changed")
            AuthAuditService.log(
                "password_changed",
                user=self.object,
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Password updated successfully',
                'data': []
            }

            return Response(response, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LogoutApiView(GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        token = serializer.validated_data.get("token")
        if not token and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if not token:
            raise AuthenticationFailed("Token is required for logout.")
        session = AuthTokenService.revoke_session_by_token(token)
        AuthAuditService.log(
            "logout",
            user=request.user,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            details={"session_key": session.session_key},
        )
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


class RefreshTokenApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = RefreshTokenSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session, access_token, refresh_token = AuthTokenService.rotate_refresh_token(
            serializer.validated_data["refresh_token"],
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_client_ip(request),
        )
        user = session.user
        return Response(
            {
                "token": access_token,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": int((session.expires_at - session.issued_at).total_seconds()),
                "refresh_expires_in": int((session.refresh_expires_at - session.issued_at).total_seconds()),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email_verified": user.email_verified,
                },
            },
            status=status.HTTP_200_OK,
        )


class ForgotPasswordApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            AuthOTPService.create_otp(user=user, email=email, purpose="password_reset")
        return Response({"message": "If the email exists, a password reset OTP has been generated."}, status=status.HTTP_200_OK)


class ResetPasswordApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        otp = AuthOTPService.verify_otp(
            email=email,
            purpose="password_reset",
            code=serializer.validated_data["otp"],
        )
        user = otp.user or User.objects.filter(email__iexact=email).first()
        if user is None:
            raise AuthenticationFailed("User not found.")
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        AuthTokenService.bump_token_version(user)
        AuthTokenService.revoke_all_for_user(user, reason="password_reset")
        AuthAuditService.log(
            "password_changed",
            user=user,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            details={"reason": "password_reset"},
        )
        return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)


class RequestEmailVerificationApiView(GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = RequestEmailVerificationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = (serializer.validated_data.get("email") or request.user.email).lower()
        if email != request.user.email.lower():
            raise AuthenticationFailed("You can request verification only for your own email.")
        AuthOTPService.create_otp(user=request.user, email=email, purpose="email_verification")
        return Response({"message": "Verification OTP generated."}, status=status.HTTP_200_OK)


class ResendEmailVerificationApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = ResendEmailVerificationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and not user.email_verified:
            AuthOTPService.create_otp(user=user, email=email, purpose="email_verification")
            return Response(
                {
                    "message": "Verification OTP generated.",
                    "email": email,
                    "email_verified": False,
                },
                status=status.HTTP_200_OK,
            )
        if user and user.email_verified:
            return Response(
                {
                    "message": "Email is already verified.",
                    "email": email,
                    "email_verified": True,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "message": "If the email exists, a verification OTP has been generated.",
                "email": email,
                "email_verified": False,
            },
            status=status.HTTP_200_OK,
        )


class VerifyEmailApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = VerifyEmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        otp = AuthOTPService.verify_otp(
            email=email,
            purpose="email_verification",
            code=serializer.validated_data["otp"],
        )
        user = otp.user or User.objects.filter(email__iexact=email).first()
        if user is None:
            raise AuthenticationFailed("User not found.")
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified", "updated_at"])
        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)



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

       





    





