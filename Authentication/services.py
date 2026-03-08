import hashlib
import secrets
from datetime import timedelta

import jwt
from django.conf import settings
from django.core.cache import cache
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
    REQUIRE_EMAIL_VERIFIED = getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFIED", False)
    OTP_LENGTH = getattr(settings, "AUTH_OTP_LENGTH", 6)
    OTP_EXPIRY_MINUTES = getattr(settings, "AUTH_OTP_EXPIRY_MINUTES", 15)


class AuthAuditService:
    @staticmethod
    def log(event, *, user=None, email="", ip_address=None, user_agent="", details=None):
        AuthAuditLog.objects.create(
            user=user,
            email=email or getattr(user, "email", "") or "",
            event=event,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255],
            details=details or {},
        )


class LoginRateLimitService:
    @staticmethod
    def _key(email, ip_address, user_agent="", entity_hint=""):
        agent_key = hashlib.sha256((user_agent or "unknown").encode("utf-8")).hexdigest()[:16]
        return f"auth:login:{(email or '').lower()}:{ip_address or 'unknown'}:{agent_key}:{entity_hint or 'global'}"

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


class AuthTokenService:
    @staticmethod
    def _expiry():
        return timezone.now() + timedelta(hours=AuthSettings.ACCESS_TOKEN_HOURS)

    @classmethod
    def _refresh_expiry(cls):
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
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        return token

    @classmethod
    def issue_token_pair(cls, user, *, user_agent="", ip_address=None):
        session, refresh_token = cls.create_session(user, user_agent=user_agent, ip_address=ip_address)
        access_token = jwt.encode(cls.build_payload(user, session), settings.SECRET_KEY, algorithm="HS256")
        if isinstance(access_token, bytes):
            access_token = access_token.decode("utf-8")
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
            raise exceptions.AuthenticationFailed("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise exceptions.AuthenticationFailed("Token not valid") from exc

    @staticmethod
    def assert_session_active(session, user):
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
        return session

    @classmethod
    def rotate_refresh_token(cls, refresh_token, *, user_agent="", ip_address=None):
        session = cls.get_session_from_refresh_token(refresh_token)
        user = session.user
        session.revoke(reason="refresh_rotated")
        return cls.issue_token_pair(user, user_agent=user_agent or session.user_agent, ip_address=ip_address or session.ip_address)

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


class AuthOTPService:
    @staticmethod
    def _generate_code():
        return f"{secrets.randbelow(10 ** AuthSettings.OTP_LENGTH):0{AuthSettings.OTP_LENGTH}d}"

    @classmethod
    def create_otp(cls, *, user=None, email, purpose):
        AuthOTP.objects.filter(
            email__iexact=email,
            purpose=purpose,
            consumed_at__isnull=True,
        ).update(consumed_at=timezone.now(), updated_at=timezone.now())
        return AuthOTP.objects.create(
            user=user,
            email=email.lower(),
            purpose=purpose,
            code=cls._generate_code(),
            expires_at=timezone.now() + timedelta(minutes=AuthSettings.OTP_EXPIRY_MINUTES),
        )

    @staticmethod
    def verify_otp(*, email, purpose, code):
        otp = (
            AuthOTP.objects.select_related("user")
            .filter(email__iexact=email, purpose=purpose)
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            raise exceptions.ValidationError({"otp": ["OTP not found."]})
        if otp.is_consumed:
            raise exceptions.ValidationError({"otp": ["OTP already used."]})
        if otp.is_expired:
            raise exceptions.ValidationError({"otp": ["OTP has expired."]})
        otp.attempts += 1
        if otp.code != code:
            otp.save(update_fields=["attempts", "updated_at"])
            raise exceptions.ValidationError({"otp": ["Invalid OTP."]})
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["attempts", "consumed_at", "updated_at"])
        return otp
