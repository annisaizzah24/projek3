import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "sociovault-super-secret-key-2026-production")
    
    # Gunakan SQLite untuk pengembangan lokal; database lain dapat diatur lewat DATABASE_URL.
    DEFAULT_SQLITE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'sociovault.db')}"

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or DEFAULT_SQLITE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    # Batas maksimal ukuran berkas unggahan (16 MB)
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
