from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
import re
from rest_framework import exceptions
from rest_framework.test import APIClient, APIRequestFactory

from Authentication.models import AuthAuditLog, AuthOTP, AuthSession
from Authentication.jwt import JwtAuthentication
from Authentication.services import AuthOTPService, AuthSettings
from subscriptions.models import CustomerAccount, CustomerSubscription


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

    def test_password_change_invalidates_existing_token(self):
        token = self.user.token
        self.user.token_version += 1
        self.user.save(update_fields=["token_version", "updated_at"])
        request = self.factory.get("/api/auth/user", HTTP_AUTHORIZATION=f"Bearer {token}")
        auth = JwtAuthentication()
        with self.assertRaises(exceptions.AuthenticationFailed):
            auth.authenticate(request)

    def test_authenticate_header_advertises_bearer_scheme(self):
        request = self.factory.get("/api/auth/user")
        auth = JwtAuthentication()
        self.assertEqual(auth.authenticate_header(request), "Bearer")


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

    def test_me_endpoint_returns_single_user_payload(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], "profile_user@example.com")
        self.assertEqual(resp.data["id"], self.user.id)

    def test_me_endpoint_requires_authentication_with_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)


class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="login_user",
            email="login_user@example.com",
            password="pass@12345",
        )

    def _extract_otp_from_last_email(self) -> str:
        self.assertTrue(mail.outbox)
        body = mail.outbox[-1].body
        match = re.search(r"\b(\d{6})\b", body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_login_creates_session_and_audit_log(self):
        resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["token_type"], "Bearer")
        self.assertIn("user", resp.data)
        self.assertIn("subscription", resp.data)
        self.assertIn(settings.AUTH_COOKIE_NAME, resp.cookies)
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, resp.cookies)
        self.assertTrue(AuthSession.objects.filter(user=self.user).exists())
        self.assertTrue(AuthAuditLog.objects.filter(user=self.user, event="login_success").exists())

    def test_logout_revokes_session(self):
        login_resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        token = login_resp.cookies[settings.AUTH_COOKIE_NAME].value
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logout_resp = self.client.post("/api/auth/logout", {}, format="json")
        self.assertEqual(logout_resp.status_code, 200)
        session = AuthSession.objects.get(user=self.user)
        self.assertIsNotNone(session.revoked_at)

    def test_refresh_rotates_session(self):
        login_resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        original_refresh_token = login_resp.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
        refresh_resp = self.client.post("/api/auth/refresh", {"refresh_token": original_refresh_token}, format="json")
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, refresh_resp.cookies)
        self.assertNotEqual(original_refresh_token, refresh_resp.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value)

    def test_forgot_and_reset_password_flow(self):
        forgot_resp = self.client.post("/api/auth/forgotpassword", {"email": self.user.email}, format="json")
        self.assertEqual(forgot_resp.status_code, 200)
        otp_code = self._extract_otp_from_last_email()
        reset_resp = self.client.post(
            "/api/auth/resetpassword",
            {"email": self.user.email, "otp": otp_code, "new_password": "newpass@123"},
            format="json",
        )
        self.assertEqual(reset_resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass@123"))

    def test_email_verification_flow(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        self.client.force_authenticate(user=self.user)
        request_resp = self.client.post("/api/auth/request-email-verification", {}, format="json")
        self.assertEqual(request_resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        otp_code = self._extract_otp_from_last_email()
        self.client.force_authenticate(user=None)
        verify_resp = self.client.post(
            "/api/auth/verify-email",
            {"email": self.user.email, "otp": otp_code},
            format="json",
        )
        self.assertEqual(verify_resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_resend_email_verification_works_without_login(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        resp = self.client.post(
            "/api/auth/resend-email-verification",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email_verified"], False)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_email_verification_reports_already_verified(self):
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified", "updated_at"])
        resp = self.client.post(
            "/api/auth/resend-email-verification",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email_verified"], True)

    def test_login_requires_verified_email(self):
        original_value = AuthSettings.REQUIRE_EMAIL_VERIFIED
        AuthSettings.REQUIRE_EMAIL_VERIFIED = True
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        try:
            resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(str(resp.data["detail"]), "Email verification is required before login.")
        finally:
            AuthSettings.REQUIRE_EMAIL_VERIFIED = original_value

    def test_register_creates_customer_account_and_subscription(self):
        resp = self.client.post(
            "/api/auth/register",
            {
                "username": "new_user@example.com",
                "email": "new_user@example.com",
                "password": "pass@12345",
                "first_name": "New",
                "last_name": "User",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["intent"], "standard")
        self.assertIn("subscription", resp.data)
        user = User.objects.get(email="new_user@example.com")
        self.assertTrue(CustomerAccount.objects.filter(owner=user).exists())
        self.assertTrue(CustomerSubscription.objects.filter(customer_account__owner=user).exists())

    def test_register_accepts_trial_intent_and_returns_subscription_snapshot(self):
        resp = self.client.post(
            "/api/auth/register",
            {
                "username": "trial_user@example.com",
                "email": "trial_user@example.com",
                "password": "pass@12345",
                "first_name": "Trial",
                "last_name": "User",
                "intent": "trial",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["intent"], "trial")
        self.assertTrue(resp.data["trial_started"])
        self.assertEqual(resp.data["subscription"]["subscription"]["status"], "trialing")

    def test_forgot_password_send_is_rate_limited(self):
        original_limit = AuthSettings.OTP_SEND_RATE_LIMIT_ATTEMPTS
        original_window = AuthSettings.OTP_SEND_RATE_LIMIT_WINDOW
        AuthSettings.OTP_SEND_RATE_LIMIT_ATTEMPTS = 1
        AuthSettings.OTP_SEND_RATE_LIMIT_WINDOW = 600
        try:
            first = self.client.post("/api/auth/forgotpassword", {"email": self.user.email}, format="json")
            self.assertEqual(first.status_code, 200)

            second = self.client.post("/api/auth/forgotpassword", {"email": self.user.email}, format="json")
            self.assertEqual(second.status_code, 429)
        finally:
            AuthSettings.OTP_SEND_RATE_LIMIT_ATTEMPTS = original_limit
            AuthSettings.OTP_SEND_RATE_LIMIT_WINDOW = original_window

    def test_verify_email_invalid_attempts_are_rate_limited(self):
        original_limit = AuthSettings.OTP_VERIFY_RATE_LIMIT_ATTEMPTS
        original_window = AuthSettings.OTP_VERIFY_RATE_LIMIT_WINDOW
        AuthSettings.OTP_VERIFY_RATE_LIMIT_ATTEMPTS = 1
        AuthSettings.OTP_VERIFY_RATE_LIMIT_WINDOW = 600
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        AuthOTPService.create_otp(user=self.user, email=self.user.email, purpose="email_verification")

        try:
            first = self.client.post(
                "/api/auth/verify-email",
                {"email": self.user.email, "otp": "000000"},
                format="json",
            )
            self.assertEqual(first.status_code, 400)

            second = self.client.post(
                "/api/auth/verify-email",
                {"email": self.user.email, "otp": "000000"},
                format="json",
            )
            self.assertEqual(second.status_code, 429)
        finally:
            AuthSettings.OTP_VERIFY_RATE_LIMIT_ATTEMPTS = original_limit
            AuthSettings.OTP_VERIFY_RATE_LIMIT_WINDOW = original_window
