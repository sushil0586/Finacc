from rest_framework.authentication import get_authorization_header, BaseAuthentication
from rest_framework import exceptions
import jwt
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

            user_id = payload.get("user_id")
            username = payload.get("username")
            email = payload.get("email")

            if user_id:
                user = User.objects.get(pk=user_id)
            elif username:
                user = User.objects.get(username=username)
            elif email:
                user = User.objects.get(email=email)
            else:
                raise exceptions.AuthenticationFailed("Token missing user identity.")

            if payload.get("ver") and payload["ver"] != user.token_version:
                raise exceptions.AuthenticationFailed("Token version is no longer valid.")

            session_key = payload.get("sid")
            if session_key:
                try:
                    session = AuthSession.objects.get(session_key=session_key, user=user)
                except AuthSession.DoesNotExist as exc:
                    raise exceptions.AuthenticationFailed("Session not found.") from exc
                AuthTokenService.assert_session_active(session, user)
                session.last_used_at = timezone.now()
                session.save(update_fields=["last_used_at", "updated_at"])

            return (user, token)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User does not exist")

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
