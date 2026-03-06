from .settings import *  # noqa: F401,F403


# Isolated fast test database to avoid collisions with existing Postgres test_FA DB.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # type: ignore[name-defined]
    }
}

# Keep tests lightweight.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
