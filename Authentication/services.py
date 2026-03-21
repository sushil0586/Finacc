import hashlib
import secrets
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from Authentication.models import AuthAuditLog, AuthOTP, AuthSession


class AuthSettings:
    ISSUER = getattr(settings, "AUTH_TOKEN_ISSUER", "finacc-auth")
    AUDIENCE = getattr(settings, "AUTH_TOKEN_AUDIENCE", "finacc-api")
    ACCESS_TOKEN_HOURS = getattr(settings, "AUTH_ACCESS_TOKEN_HOURS", 12)
    REFRESH_TOKEN_DAYS = getattr(settings, "AUTH_REFRESH_TOKEN_DAYS", 30)

    LOGIN_RATE_LIMIT_ATTEMPTS = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 5)
    LOGIN_RATE_LIMIT_WINDOW = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)

    ACCOUNT_LOCK_THRESHOLD = getattr(settings, "AUTH_ACCOUNT_LOCK_THRESHOLD", 5)
    ACCOUNT_LOCK_MINUTES = getattr(settings, "AUTH_ACCOUNT_LOCK_MINUTES", 15)

    REQUIRE_EMAIL_VERIFIED = getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFIED", True)

    OTP_LENGTH = getattr(settings, "AUTH_OTP_LENGTH", 6)
    OTP_EXPIRY_MINUTES = getattr(settings, "AUTH_OTP_EXPIRY_MINUTES", 15)
    OTP_MAX_ATTEMPTS = getattr(settings, "AUTH_OTP_MAX_ATTEMPTS", 5)
    OTP_SEND_RATE_LIMIT_ATTEMPTS = getattr(settings, "AUTH_OTP_SEND_RATE_LIMIT_ATTEMPTS", 5)
    OTP_SEND_RATE_LIMIT_WINDOW = getattr(settings, "AUTH_OTP_SEND_RATE_LIMIT_WINDOW_SECONDS", 600)
    OTP_VERIFY_RATE_LIMIT_ATTEMPTS = getattr(settings, "AUTH_OTP_VERIFY_RATE_LIMIT_ATTEMPTS", 20)
    OTP_VERIFY_RATE_LIMIT_WINDOW = getattr(settings, "AUTH_OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS", 600)


class AuthAuditService:
    @staticmethod
    def log(event, *, user=None, email="", ip_address=None, user_agent="", details=None):
        AuthAuditLog.objects.create(
            user=user,
            email=(email or getattr(user, "email", "") or "").strip().lower(),
            event=event,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255],
            details=details or {},
        )


class LoginRateLimitService:
    @staticmethod
    def _key(email, ip_address, user_agent="", entity_hint=""):
        agent_key = hashlib.sha256((user_agent or "unknown").encode("utf-8")).hexdigest()[:16]
        return f"auth:login:{(email or '').strip().lower()}:{ip_address or 'unknown'}:{agent_key}:{entity_hint or 'global'}"

    @classmethod
    def check_allowed(cls, *, email, ip_address, user_agent="", entity_hint=""):
        key = cls._key(email, ip_address, user_agent=user_agent, entity_hint=entity_hint)
        attempts = cache.get(key, 0)
        if attempts >= AuthSettings.LOGIN_RATE_LIMIT_ATTEMPTS:
            raise exceptions.AuthenticationFailed("Too many login attempts. Try again later.")

    @classmethod
    def record_failure(cls, *, email, ip_address, user_agent="", entity_hint=""):
        key = cls._key(email, ip_address, user_agent=user_agent, entity_hint=entity_hint)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=AuthSettings.LOGIN_RATE_LIMIT_WINDOW)

    @classmethod
    def clear(cls, *, email, ip_address, user_agent="", entity_hint=""):
        cache.delete(cls._key(email, ip_address, user_agent=user_agent, entity_hint=entity_hint))


class OTPRateLimitService:
    ACTION_SEND = "send"
    ACTION_VERIFY = "verify"

    @staticmethod
    def _key(*, action, purpose, email, ip_address):
        normalized_email = (email or "").strip().lower()
        return f"auth:otp:{action}:{purpose}:{normalized_email}:{ip_address or 'unknown'}"

    @classmethod
    def _config(cls, action):
        if action == cls.ACTION_SEND:
            return AuthSettings.OTP_SEND_RATE_LIMIT_ATTEMPTS, AuthSettings.OTP_SEND_RATE_LIMIT_WINDOW
        return AuthSettings.OTP_VERIFY_RATE_LIMIT_ATTEMPTS, AuthSettings.OTP_VERIFY_RATE_LIMIT_WINDOW

    @classmethod
    def check_allowed(cls, *, action, purpose, email, ip_address):
        key = cls._key(action=action, purpose=purpose, email=email, ip_address=ip_address)
        attempts = cache.get(key, 0)
        limit, window = cls._config(action)
        if attempts >= limit:
            raise exceptions.Throttled(
                wait=window,
                detail="Too many OTP requests. Please try again later.",
            )

    @classmethod
    def record_attempt(cls, *, action, purpose, email, ip_address):
        key = cls._key(action=action, purpose=purpose, email=email, ip_address=ip_address)
        _, window = cls._config(action)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)

    @classmethod
    def clear(cls, *, action, purpose, email, ip_address):
        cache.delete(cls._key(action=action, purpose=purpose, email=email, ip_address=ip_address))


class AuthTokenService:
    @staticmethod
    def _expiry():
        return timezone.now() + timedelta(hours=AuthSettings.ACCESS_TOKEN_HOURS)

    @staticmethod
    def _refresh_expiry():
        return timezone.now() + timedelta(days=AuthSettings.REFRESH_TOKEN_DAYS)

    @staticmethod
    def hash_refresh_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def create_session(cls, user, *, user_agent="", ip_address=None):
        refresh_token = secrets.token_urlsafe(48)
        session = AuthSession.objects.create(
            user=user,
            session_key=secrets.token_hex(32),
            jti=secrets.token_hex(16),
            refresh_token_hash=cls.hash_refresh_token(refresh_token),
            issued_at=timezone.now(),
            expires_at=cls._expiry(),
            refresh_expires_at=cls._refresh_expiry(),
            last_used_at=timezone.now(),
            user_agent=(user_agent or "")[:255],
            ip_address=ip_address,
        )
        return session, refresh_token

    @classmethod
    def build_payload(cls, user, session):
        return {
            "user_id": user.pk,
            "email": user.email,
            "username": user.username,
            "sid": session.session_key,
            "jti": session.jti,
            "ver": user.token_version,
            "type": "access",
            "iss": AuthSettings.ISSUER,
            "aud": AuthSettings.AUDIENCE,
            "iat": int(session.issued_at.timestamp()),
            "exp": int(session.expires_at.timestamp()),
        }

    @classmethod
    def issue_access_token(cls, user, *, user_agent="", ip_address=None):
        session, _refresh_token = cls.create_session(user, user_agent=user_agent, ip_address=ip_address)
        token = jwt.encode(cls.build_payload(user, session), settings.SECRET_KEY, algorithm="HS256")
        return token.decode("utf-8") if isinstance(token, bytes) else token

    @classmethod
    def issue_token_pair(cls, user, *, user_agent="", ip_address=None):
        session, refresh_token = cls.create_session(user, user_agent=user_agent, ip_address=ip_address)
        access_token = jwt.encode(cls.build_payload(user, session), settings.SECRET_KEY, algorithm="HS256")
        access_token = access_token.decode("utf-8") if isinstance(access_token, bytes) else access_token
        return session, access_token, refresh_token

    @classmethod
    def decode_access_token(cls, token):
        try:
            return jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"],
                audience=AuthSettings.AUDIENCE,
                issuer=AuthSettings.ISSUER,
            )
        except jwt.InvalidAudienceError as exc:
            raise exceptions.AuthenticationFailed("Invalid audience.") from exc
        except jwt.ExpiredSignatureError as exc:
            raise exceptions.AuthenticationFailed("Token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise exceptions.AuthenticationFailed("Token not valid.") from exc

    @staticmethod
    def assert_session_active(session, user, payload=None):
        if session.is_revoked:
            raise exceptions.AuthenticationFailed("Session has been revoked.")
        if session.is_expired:
            raise exceptions.AuthenticationFailed("Session has expired.")
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")
        if session.user_id != user.id:
            raise exceptions.AuthenticationFailed("Session not valid for user.")
        if user.token_version <= 0:
            raise exceptions.AuthenticationFailed("Token version invalid.")
        if payload and payload.get("ver") != user.token_version:
            raise exceptions.AuthenticationFailed("Token version mismatch. Please login again.")

    @classmethod
    def get_session_from_refresh_token(cls, refresh_token):
        try:
            session = AuthSession.objects.select_related("user").get(
                refresh_token_hash=cls.hash_refresh_token(refresh_token)
            )
        except AuthSession.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid refresh token.") from exc

        if session.is_revoked:
            raise exceptions.AuthenticationFailed("Session has been revoked.")
        if session.refresh_expires_at and timezone.now() >= session.refresh_expires_at:
            raise exceptions.AuthenticationFailed("Refresh token has expired.")
        if not session.user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")
        if session.user.is_locked:
            raise exceptions.AuthenticationFailed("User account is temporarily locked.")
        return session

    @classmethod
    def rotate_refresh_token(cls, refresh_token, *, user_agent="", ip_address=None):
        session = cls.get_session_from_refresh_token(refresh_token)
        user = session.user
        session.revoke(reason="refresh_rotated")
        return cls.issue_token_pair(
            user,
            user_agent=user_agent or session.user_agent,
            ip_address=ip_address or session.ip_address,
        )

    @classmethod
    def revoke_session_by_token(cls, token, *, reason="manual_logout"):
        payload = cls.decode_access_token(token)
        session_key = payload.get("sid")
        if not session_key:
            raise exceptions.AuthenticationFailed("Token does not contain a session.")
        try:
            session = AuthSession.objects.get(session_key=session_key)
        except AuthSession.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Session not found.") from exc
        session.revoke(reason=reason)
        return session

    @staticmethod
    def revoke_all_for_user(user, *, reason):
        AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now(),
            revoked_reason=reason,
            updated_at=timezone.now(),
        )

    @staticmethod
    def bump_token_version(user):
        user.token_version = (user.token_version or 0) + 1
        user.save(update_fields=["token_version", "updated_at"])


class AuthUserSecurityService:
    @staticmethod
    def register_failed_login(user):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        if user.failed_login_attempts >= AuthSettings.ACCOUNT_LOCK_THRESHOLD:
            user.locked_until = timezone.now() + timedelta(minutes=AuthSettings.ACCOUNT_LOCK_MINUTES)

        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])

    @staticmethod
    def clear_failed_logins(user, *, ip_address=None):
        updates = []
        if user.failed_login_attempts != 0:
            user.failed_login_attempts = 0
            updates.append("failed_login_attempts")
        if user.locked_until is not None:
            user.locked_until = None
            updates.append("locked_until")
        if ip_address and user.last_login_ip != ip_address:
            user.last_login_ip = ip_address
            updates.append("last_login_ip")

        if updates:
            updates.append("updated_at")
            user.save(update_fields=updates)

    @staticmethod
    def assert_can_login(user):
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")
        if user.is_locked:
            raise exceptions.AuthenticationFailed("Account is temporarily locked. Try again later.")
        if AuthSettings.REQUIRE_EMAIL_VERIFIED and not user.email_verified:
            raise exceptions.AuthenticationFailed("Email verification is required before login.")


class AuthOTPService:
    @staticmethod
    def _generate_code():
        return f"{secrets.randbelow(10 ** AuthSettings.OTP_LENGTH):0{AuthSettings.OTP_LENGTH}d}"

    @staticmethod
    def _hash_code(code):
        return make_password(code)

    @staticmethod
    def _verify_code(raw_code, code_hash):
        return check_password(raw_code, code_hash)

    @classmethod
    @transaction.atomic
    def create_otp(cls, *, user=None, email, purpose):
        normalized_email = (email or "").strip().lower()

        AuthOTP.objects.filter(
            email__iexact=normalized_email,
            purpose=purpose,
            consumed_at__isnull=True,
        ).update(
            consumed_at=timezone.now(),
            updated_at=timezone.now(),
        )

        raw_code = cls._generate_code()
        otp = AuthOTP.objects.create(
            user=user,
            email=normalized_email,
            purpose=purpose,
            code_hash=cls._hash_code(raw_code),
            expires_at=timezone.now() + timedelta(minutes=AuthSettings.OTP_EXPIRY_MINUTES),
        )

        cls.send_otp_email(email=otp.email, purpose=otp.purpose, code=raw_code)

        AuthAuditService.log(
            "otp_sent",
            user=user,
            email=otp.email,
            details={"purpose": purpose},
        )
        return otp

    @staticmethod
    def send_otp_email(*, email, purpose, code):
        purpose_label = dict(AuthOTP.PURPOSE_CHOICES).get(purpose, purpose)
        send_mail(
            subject=f"Finacc {purpose_label} OTP",
            message=(
                f"Your Finacc OTP for {purpose_label.lower()} is {code}. "
                f"It expires in {AuthSettings.OTP_EXPIRY_MINUTES} minutes."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=False,
        )

    @staticmethod
    @transaction.atomic
    def verify_otp(*, email, purpose, code):
        normalized_email = (email or "").strip().lower()

        otp = (
            AuthOTP.objects.select_related("user")
            .filter(email__iexact=normalized_email, purpose=purpose)
            .order_by("-created_at")
            .first()
        )

        if otp is None:
            raise exceptions.ValidationError({"otp": ["OTP not found."]})
        if otp.is_consumed:
            raise exceptions.ValidationError({"otp": ["OTP already used."]})
        if otp.is_expired:
            raise exceptions.ValidationError({"otp": ["OTP has expired."]})
        if otp.attempts >= AuthSettings.OTP_MAX_ATTEMPTS:
            raise exceptions.ValidationError({"otp": ["Maximum OTP attempts exceeded."]})

        otp.attempts += 1

        if not AuthOTPService._verify_code(code, otp.code_hash):
            otp.save(update_fields=["attempts", "updated_at"])
            raise exceptions.ValidationError({"otp": ["Invalid OTP."]})

        otp.consumed_at = timezone.now()
        otp.save(update_fields=["attempts", "consumed_at", "updated_at"])

        AuthAuditService.log(
            "otp_verified",
            user=otp.user,
            email=otp.email,
            details={"purpose": purpose},
        )
        return otp


class AuthPasswordService:
    @staticmethod
    @transaction.atomic
    def reset_password(*, user, new_password):
        user.set_password(new_password)
        user.last_password_changed_at = timezone.now()
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(
            update_fields=[
                "password",
                "last_password_changed_at",
                "failed_login_attempts",
                "locked_until",
                "updated_at",
            ]
        )

        AuthTokenService.bump_token_version(user)
        AuthTokenService.revoke_all_for_user(user, reason="password_reset")

        AuthAuditService.log(
            "password_changed",
            user=user,
            email=user.email,
            details={"source": "password_reset"},
        )

    @staticmethod
    @transaction.atomic
    def change_password(*, user, old_password, new_password):
        if not user.check_password(old_password):
            raise exceptions.ValidationError({"old_password": ["Old password is incorrect."]})

        user.set_password(new_password)
        user.last_password_changed_at = timezone.now()
        user.save(update_fields=["password", "last_password_changed_at", "updated_at"])

        AuthTokenService.bump_token_version(user)
        AuthTokenService.revoke_all_for_user(user, reason="password_changed")

        AuthAuditService.log(
            "password_changed",
            user=user,
            email=user.email,
            details={"source": "change_password"},
        )


class AuthEmailVerificationService:
    @staticmethod
    @transaction.atomic
    def verify_user_email(user):
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified", "updated_at"])

        AuthAuditService.log(
            "email_verified",
            user=user,
            email=user.email,
        )
