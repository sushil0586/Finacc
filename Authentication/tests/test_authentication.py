from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework import exceptions
from rest_framework.test import APIClient, APIRequestFactory

from Authentication.models import AuthAuditLog, AuthOTP, AuthSession
from Authentication.jwt import JwtAuthentication
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


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="login_user",
            email="login_user@example.com",
            password="pass@12345",
        )

    def test_login_creates_session_and_audit_log(self):
        resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.data)
        self.assertIn("refresh_token", resp.data)
        self.assertIn("user", resp.data)
        self.assertTrue(AuthSession.objects.filter(user=self.user).exists())
        self.assertTrue(AuthAuditLog.objects.filter(user=self.user, event="login_success").exists())

    def test_logout_revokes_session(self):
        login_resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        token = login_resp.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logout_resp = self.client.post("/api/auth/logout", {}, format="json")
        self.assertEqual(logout_resp.status_code, 200)
        session = AuthSession.objects.get(user=self.user)
        self.assertIsNotNone(session.revoked_at)

    def test_refresh_rotates_session(self):
        login_resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        refresh_resp = self.client.post("/api/auth/refresh", {"refresh_token": login_resp.data["refresh_token"]}, format="json")
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn("refresh_token", refresh_resp.data)
        self.assertNotEqual(login_resp.data["refresh_token"], refresh_resp.data["refresh_token"])

    def test_forgot_and_reset_password_flow(self):
        forgot_resp = self.client.post("/api/auth/forgotpassword", {"email": self.user.email}, format="json")
        self.assertEqual(forgot_resp.status_code, 200)
        otp = AuthOTP.objects.filter(email=self.user.email, purpose="password_reset").latest("created_at")
        reset_resp = self.client.post(
            "/api/auth/resetpassword",
            {"email": self.user.email, "otp": otp.code, "new_password": "newpass@123"},
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
        otp = AuthOTP.objects.filter(email=self.user.email, purpose="email_verification").latest("created_at")
        self.client.force_authenticate(user=None)
        verify_resp = self.client.post(
            "/api/auth/verify-email",
            {"email": self.user.email, "otp": otp.code},
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
        resp = self.client.post(
            "/api/auth/resend-email-verification",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email_verified"], True)

    def test_login_requires_verified_email(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        resp = self.client.post("/api/auth/login", {"email": self.user.email, "password": "pass@12345"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "email_not_verified")
        self.assertEqual(resp.data["next_action"], "verify_email")
        self.assertEqual(resp.data["email"], self.user.email)

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
        self.assertTrue(CustomerAccount.objects.filter(primary_user=user).exists())
        self.assertTrue(CustomerSubscription.objects.filter(customer_account__primary_user=user).exists())

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
        self.assertEqual(resp.data["subscription"]["subscription"]["status"], "trial")
