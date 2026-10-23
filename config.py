import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "sociovault-super-secret-key-2026-production")
    
    # Database configuration
    # Default ke MySQL jika ada environment variable, atau fallback ke local SQLite database
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_NAME = os.environ.get("DB_NAME", "sociovault_db")

    # If DATABASE_URL is set, use it directly; otherwise try MySQL with fallback to SQLite
    DEFAULT_MYSQL_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    db_backend = os.path.join(BASE_DIR, "backend", "sociovault.db")
    db_local = os.path.join(BASE_DIR, "sociovault.db")
    db_resolved = db_backend if (os.path.exists(db_backend) and os.path.basename(BASE_DIR) != "backend") else db_local
    DEFAULT_SQLITE_URI = f"sqlite:///{db_resolved}"

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", DEFAULT_MYSQL_URI)
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
