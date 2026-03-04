from rest_framework.authentication import get_authorization_header, BaseAuthentication

from rest_framework import exceptions
import jwt
from django.conf import settings
from Authentication.models import User

class JwtAuthentication(BaseAuthentication):

    def authenticate(self, request):
        auth_header = get_authorization_header(request)
        if not auth_header:
            return None
        try:
            auth_data = auth_header.decode("utf-8").strip()
        except Exception:
            raise exceptions.AuthenticationFailed("Invalid authorization header.")

        auth_token = auth_data.split(" ")
        if len(auth_token) != 2:
            raise exceptions.AuthenticationFailed("Token not valid")

        token = auth_token[1].strip()
        if not token:
            raise exceptions.AuthenticationFailed("Token not valid")

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

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

            return (user, token)

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired")

        except jwt.DecodeError:
            raise exceptions.AuthenticationFailed("Token not valid")
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User does not exist")







