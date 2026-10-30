import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'valedgari.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SEND_FILE_MAX_AGE_DEFAULT = 31536000
    APP_VERSION = os.getenv("APP_VERSION", "stage-15")
    AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "1") == "1"
    ADMIN_PAGE_SIZE = int(os.getenv("ADMIN_PAGE_SIZE", "50"))
    EXPORT_ROW_LIMIT = int(os.getenv("EXPORT_ROW_LIMIT", "5000"))
    PRIVACY_POLICY_VERSION = os.getenv("PRIVACY_POLICY_VERSION", "1405-08-07-v1")
    ANONYMOUS_REPORT_MIN_GROUP = int(os.getenv("ANONYMOUS_REPORT_MIN_GROUP", "5"))
    REQUIRE_SCIENTIFIC_APPROVAL = os.getenv("REQUIRE_SCIENTIFIC_APPROVAL", "0") == "1"
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "manual")
    PAYMENT_MERCHANT_ID = os.getenv("PAYMENT_MERCHANT_ID", "")
    PAYMENT_MODE = os.getenv("PAYMENT_MODE", "disabled")
    PAYMENT_FAKE_GATEWAY = False
    SMS_FAKE_PROVIDER = False
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    REQUIRE_SCIENTIFIC_APPROVAL = os.getenv("REQUIRE_SCIENTIFIC_APPROVAL", "1") == "1"
    AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "0") == "1"


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    PAYMENT_FAKE_GATEWAY = True
    SMS_FAKE_PROVIDER = True
    AUTO_CREATE_SCHEMA = True

