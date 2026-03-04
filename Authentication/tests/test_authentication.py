from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import exceptions
from rest_framework.test import APIClient, APIRequestFactory

from Authentication.jwt import JwtAuthentication


User = get_user_model()


class JwtAuthenticationTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="auth_user",
            email="auth_user@example.com",
            password="pass@12345",
        )

    def test_missing_authorization_header_returns_none(self):
        request = self.factory.get("/api/auth/user")
        auth = JwtAuthentication()
        self.assertIsNone(auth.authenticate(request))

    def test_invalid_authorization_header_raises(self):
        request = self.factory.get("/api/auth/user", HTTP_AUTHORIZATION="Bearer")
        auth = JwtAuthentication()
        with self.assertRaises(exceptions.AuthenticationFailed):
            auth.authenticate(request)

    def test_valid_token_authenticates_user(self):
        request = self.factory.get("/api/auth/user", HTTP_AUTHORIZATION=f"Bearer {self.user.token}")
        auth = JwtAuthentication()
        result = auth.authenticate(request)
        self.assertIsNotNone(result)
        user, _ = result
        self.assertEqual(user.pk, self.user.pk)


class AuthUserEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="profile_user",
            email="profile_user@example.com",
            password="pass@12345",
            first_name="Profile",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)

    def test_user_endpoint_returns_authenticated_user(self):
        resp = self.client.get("/api/auth/user")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["email"], "profile_user@example.com")
