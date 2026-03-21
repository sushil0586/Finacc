import logging

from django.contrib.auth import authenticate, get_user_model
from rest_framework import permissions, response, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, UpdateAPIView
from rest_framework.response import Response

from Authentication.models import User
from Authentication.serializers import (
    AuthenticatedUserSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RefreshTokenSerializer,
    RegisterSerializer,
    RequestEmailVerificationSerializer,
    ResetPasswordSerializer,
    ResendEmailVerificationSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from Authentication.services import (
    AuthAuditService,
    AuthEmailVerificationService,
    AuthOTPService,
    AuthPasswordService,
    AuthSettings,
    AuthTokenService,
    OTPRateLimitService,
    AuthUserSecurityService,
    LoginRateLimitService,
)
from subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)
User = get_user_model()


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuthApiView(ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserSerializer

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

        intent = getattr(user, "_signup_intent", SubscriptionService.INTENT_STANDARD)
        subscription = SubscriptionService.build_subscription_snapshot(user=user)

        payload = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "email_verified": user.email_verified,
            "intent": intent,
            "trial_started": subscription["subscription"]["is_trial"],
            "message": (
                "Your free trial has started."
                if subscription["subscription"]["is_trial"]
                else "Account created successfully."
            ),
            "subscription": subscription,
        }
        headers = self.get_success_headers(serializer.data)
        return Response(payload, status=status.HTTP_201_CREATED, headers=headers)


class LoginApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        ip_address = _client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        entity_hint = request.headers.get("X-Entity-Id") or request.data.get("entity") or ""

        LoginRateLimitService.check_allowed(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            entity_hint=entity_hint,
        )

        user = authenticate(request, email=email, password=password)
        if not user:
            user = authenticate(request, username=email, password=password)

        if not user:
            LoginRateLimitService.record_failure(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                entity_hint=entity_hint,
            )

            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                AuthUserSecurityService.register_failed_login(existing_user)
                if existing_user.is_locked:
                    AuthAuditService.log(
                        "account_locked",
                        user=existing_user,
                        email=email,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={"reason": "failed_login_threshold"},
                    )

            AuthAuditService.log(
                "login_failed",
                user=existing_user if existing_user else None,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_credentials"},
            )
            raise AuthenticationFailed("Invalid credentials.")

        AuthUserSecurityService.assert_can_login(user)

        session, access_token, refresh_token = AuthTokenService.issue_token_pair(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        LoginRateLimitService.clear(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            entity_hint=entity_hint,
        )
        AuthUserSecurityService.clear_failed_logins(user, ip_address=ip_address)

        AuthAuditService.log(
            "login_success",
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

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
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email_verified": user.email_verified,
                "is_active": user.is_active,
            },
        }
        return response.Response(data, status=status.HTTP_200_OK)


class ChangePasswordView(UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if old_password == new_password:
            return Response(
                {"new_password": ["New password cannot be the same as the old password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        AuthPasswordService.change_password(
            user=user,
            old_password=old_password,
            new_password=new_password,
        )

        return Response(
            {
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Password updated successfully.",
                "data": [],
            },
            status=status.HTTP_200_OK,
        )


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
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email_verified": user.email_verified,
                    "is_active": user.is_active,
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

        email = serializer.validated_data["email"]
        ip_address = _client_ip(request)
        OTPRateLimitService.check_allowed(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="password_reset",
            email=email,
            ip_address=ip_address,
        )
        OTPRateLimitService.record_attempt(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="password_reset",
            email=email,
            ip_address=ip_address,
        )
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            AuthOTPService.create_otp(user=user, email=email, purpose="password_reset")

        return Response(
            {"message": "If the email exists, a password reset OTP has been generated."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        ip_address = _client_ip(request)
        OTPRateLimitService.check_allowed(
            action=OTPRateLimitService.ACTION_VERIFY,
            purpose="password_reset",
            email=email,
            ip_address=ip_address,
        )
        try:
            otp = AuthOTPService.verify_otp(
                email=email,
                purpose="password_reset",
                code=serializer.validated_data["otp"],
            )
        except Exception:
            OTPRateLimitService.record_attempt(
                action=OTPRateLimitService.ACTION_VERIFY,
                purpose="password_reset",
                email=email,
                ip_address=ip_address,
            )
            raise
        OTPRateLimitService.clear(
            action=OTPRateLimitService.ACTION_VERIFY,
            purpose="password_reset",
            email=email,
            ip_address=ip_address,
        )
        user = otp.user or User.objects.filter(email__iexact=email).first()

        if user is None:
            raise AuthenticationFailed("User not found.")

        AuthPasswordService.reset_password(
            user=user,
            new_password=serializer.validated_data["new_password"],
        )

        return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)


class RequestEmailVerificationApiView(GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = RequestEmailVerificationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = (serializer.validated_data.get("email") or request.user.email).strip().lower()
        if email != request.user.email.lower():
            raise AuthenticationFailed("You can request verification only for your own email.")

        if request.user.email_verified:
            return Response(
                {"message": "Email is already verified.", "email_verified": True},
                status=status.HTTP_200_OK,
            )

        ip_address = _client_ip(request)
        OTPRateLimitService.check_allowed(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
        OTPRateLimitService.record_attempt(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
        AuthOTPService.create_otp(user=request.user, email=email, purpose="email_verification")
        return Response({"message": "Verification OTP generated."}, status=status.HTTP_200_OK)


class ResendEmailVerificationApiView(GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []
    serializer_class = ResendEmailVerificationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        ip_address = _client_ip(request)
        OTPRateLimitService.check_allowed(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
        OTPRateLimitService.record_attempt(
            action=OTPRateLimitService.ACTION_SEND,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
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

        email = serializer.validated_data["email"]
        ip_address = _client_ip(request)
        OTPRateLimitService.check_allowed(
            action=OTPRateLimitService.ACTION_VERIFY,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
        try:
            otp = AuthOTPService.verify_otp(
                email=email,
                purpose="email_verification",
                code=serializer.validated_data["otp"],
            )
        except Exception:
            OTPRateLimitService.record_attempt(
                action=OTPRateLimitService.ACTION_VERIFY,
                purpose="email_verification",
                email=email,
                ip_address=ip_address,
            )
            raise
        OTPRateLimitService.clear(
            action=OTPRateLimitService.ACTION_VERIFY,
            purpose="email_verification",
            email=email,
            ip_address=ip_address,
        )
        user = otp.user or User.objects.filter(email__iexact=email).first()

        if user is None:
            raise AuthenticationFailed("User not found.")

        AuthEmailVerificationService.verify_user_email(user)

        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)


