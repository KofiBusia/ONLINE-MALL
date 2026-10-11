"""Configuration from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///edwom.db"  # created in the instance/ folder
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    IS_PRODUCTION = bool(os.environ.get("RENDER")) or _flag("PRODUCTION")
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-not-secret"
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 30
    WTF_CSRF_TIME_LIMIT = None
    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"

    MAX_PHOTOS_PER_PRODUCT = int(os.environ.get("MAX_PHOTOS_PER_PRODUCT", "8"))
    MAX_PHOTO_MB = int(os.environ.get("MAX_PHOTO_MB", "10"))
    MAX_CONTENT_LENGTH = (MAX_PHOTOS_PER_PRODUCT * MAX_PHOTO_MB + 2) * 1024 * 1024

    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
    COMMISSION_RATE = float(os.environ.get("COMMISSION_RATE", "0.08"))
    SHOP_FEE_PESEWAS = int(os.environ.get("SHOP_FEE_PESEWAS", "15000"))  # GH₵150 one-time listing fee
    DELIVERY_SAME_REGION = int(os.environ.get("DELIVERY_SAME_REGION_PESEWAS", "2500"))
    DELIVERY_OTHER_REGION = int(os.environ.get("DELIVERY_OTHER_REGION_PESEWAS", "4500"))
    AUTO_RELEASE_HOURS = int(os.environ.get("AUTO_RELEASE_HOURS", "72"))

    SEED_DEMO = _flag("SEED_DEMO", "1")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = True
    RATELIMIT_HEADERS_ENABLED = True
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    PER_PAGE = 24
