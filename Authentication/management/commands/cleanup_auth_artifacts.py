from django.core.management.base import BaseCommand
from django.utils import timezone

from Authentication.models import AuthOTP, AuthSession


class Command(BaseCommand):
    help = "Clean up expired and revoked authentication sessions and OTPs."

    def handle(self, *args, **options):
        now = timezone.now()
        revoked_deleted, _ = AuthSession.objects.filter(
            revoked_at__isnull=False,
            refresh_expires_at__lt=now,
        ).delete()
        expired_deleted, _ = AuthSession.objects.filter(
            refresh_expires_at__lt=now,
        ).delete()
        otp_deleted, _ = AuthOTP.objects.filter(expires_at__lt=now).delete()

        self.stdout.write(f"revoked_sessions_deleted: {revoked_deleted}")
        self.stdout.write(f"expired_sessions_deleted: {expired_deleted}")
        self.stdout.write(f"expired_otps_deleted: {otp_deleted}")
