from rest_framework.authentication import get_authorization_header, BaseAuthentication
from rest_framework import exceptions
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from Authentication.models import AuthSession, User
from Authentication.services import AuthSettings, AuthTokenService


class JwtAuthentication(BaseAuthentication):

    def authenticate(self, request):
        token = self._token_from_header(request) or self._token_from_cookie(request)
        if not token:
            return None

        try:
            payload = AuthTokenService.decode_access_token(token)
            user, session = self._resolve_principal(payload)

            if session:
                self._maybe_touch_session(session)

            return user, token
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User does not exist")

    def _resolve_principal(self, payload):
        session_key = payload.get("sid")
        user_id = payload.get("user_id")

        # Access tokens issued by our login flow always include both session id and user id.
        # Resolving the user through the session keeps the hot path to a single DB query.
        if session_key and user_id:
            try:
                session = (
                    AuthSession.objects.select_related("user")
                    .only(
                        "id",
                        "session_key",
                        "user_id",
                        "last_used_at",
                        "revoked_at",
                        "expires_at",
                        "updated_at",
                        "user__id",
                        "user__email",
                        "user__username",
                        "user__is_active",
                        "user__token_version",
                    )
                    .get(session_key=session_key, user_id=user_id)
                )
            except AuthSession.DoesNotExist as exc:
                raise exceptions.AuthenticationFailed("Session not found.") from exc

            user = session.user
            AuthTokenService.assert_session_active(session, user, payload=payload)
            return user, session

        user = self._load_user_from_payload(payload)
        if payload.get("ver") and payload["ver"] != user.token_version:
            raise exceptions.AuthenticationFailed("Token version is no longer valid.")

        if session_key:
            try:
                session = (
                    AuthSession.objects.only(
                        "id",
                        "session_key",
                        "user_id",
                        "last_used_at",
                        "revoked_at",
                        "expires_at",
                        "updated_at",
                    )
                    .get(session_key=session_key, user=user)
                )
            except AuthSession.DoesNotExist as exc:
                raise exceptions.AuthenticationFailed("Session not found.") from exc
            AuthTokenService.assert_session_active(session, user, payload=payload)
            return user, session

        return user, None

    def _load_user_from_payload(self, payload):
        user_id = payload.get("user_id")
        username = payload.get("username")
        email = payload.get("email")

        user_qs = User.objects.only("id", "email", "username", "is_active", "token_version")
        if user_id:
            return user_qs.get(pk=user_id)
        if username:
            return user_qs.get(username=username)
        if email:
            return user_qs.get(email=email)
        raise exceptions.AuthenticationFailed("Token missing user identity.")

    def _maybe_touch_session(self, session):
        now = timezone.now()
        touch_interval = max(int(AuthSettings.SESSION_TOUCH_INTERVAL_SECONDS or 0), 0)
        should_touch = (
            touch_interval == 0
            or session.last_used_at is None
            or (now - session.last_used_at) >= timedelta(seconds=touch_interval)
        )
        if should_touch:
            session.last_used_at = now
            session.save(update_fields=["last_used_at", "updated_at"])

    def _token_from_header(self, request) -> str | None:
        auth_header = get_authorization_header(request)
        if not auth_header:
            return None
        try:
            auth_data = auth_header.decode("utf-8").strip()
        except Exception:
            raise exceptions.AuthenticationFailed("Invalid authorization header.")

        parts = auth_data.split(" ")
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Token not valid")

        token = parts[1].strip()
        return token or None

    def _token_from_cookie(self, request) -> str | None:
        cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "fa_access")
        return request.COOKIES.get(cookie_name) or None

    def authenticate_header(self, request):
        return "Bearer"
