import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Carga valores comunes desde .env o entorno
    SECRET_KEY = os.getenv('SECRET_KEY') or os.urandom(32).hex()
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(basedir, 'mi_app.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Parámetros de la aplicación
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5001))
    DEFAULT_USER_PASSWORD = os.getenv('DEFAULT_USER_PASSWORD')
    DECLARATION_UPLOAD_FOLDER = os.getenv('DECLARATION_UPLOAD_FOLDER', os.path.join(basedir, 'uploads', 'declarations'))
    ORDER_EXPORT_FOLDER = os.getenv('ORDER_EXPORT_FOLDER', os.path.join(basedir, 'exports'))
    BACKUP_FOLDER = os.getenv('BACKUP_FOLDER', os.path.join(basedir, 'backups'))
    ALLOWED_DECLARATION_EXTENSIONS = {'pdf'}
    LOGIN_RATE_LIMIT = os.getenv('LOGIN_RATE_LIMIT', '30 per minute')
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    PHASE_ONE_ORDER_LIMIT = float(os.getenv('PHASE_ONE_ORDER_LIMIT', 235))
    MIN_TOTAL_ORDER_AMOUNT = float(os.getenv('MIN_TOTAL_ORDER_AMOUNT', 4800))
    MAX_REFERENCES_PER_USER = int(os.getenv('MAX_REFERENCES_PER_USER', 10))
    PHASE_TWO_REFERENCE_LIMIT = int(os.getenv('PHASE_TWO_REFERENCE_LIMIT', 20))
    FINAL_SELECTION_LIMIT = int(os.getenv('FINAL_SELECTION_LIMIT', 85))
    SITE_ACCESS_PASSWORD = os.getenv('SITE_ACCESS_PASSWORD')
    # Published, edition-specific AGPL corresponding-source location.
    SOURCE_CODE_URL = (os.getenv('SOURCE_CODE_URL') or '').strip()
    # Online restoration is disabled; an offline atomic procedure is supplied.
    ALLOW_ONLINE_RESTORE = False

    APP_ENV = os.getenv('APP_ENV', 'production')
    DEFAULT_LANGUAGE = os.getenv('DEFAULT_LANGUAGE', 'es')
    SUPPORTED_LANGUAGES = tuple(
        lang.strip() for lang in os.getenv('SUPPORTED_LANGUAGES', 'es,en').split(',') if lang.strip()
    ) or ('es',)

    # CSRF y session
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    # Do not trust client-controlled X-Forwarded headers without a trusted proxy.
    # Set to 1 ONLY if exactly one reverse proxy sanitises these headers.
    TRUSTED_PROXY_COUNT = int(os.getenv('TRUSTED_PROXY_COUNT', '0'))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Rate limiting
    RATELIMIT_DEFAULT = "5000 per day"
    # Usa memoria en local si no hay Redis disponible
    RATELIMIT_STORAGE_URI = os.getenv('REDIS_URL') or 'memory://'

class DevelopmentConfig(Config):
    DEBUG = True
    # En desarrollo, quizá quieras cookies menos restrictivas
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    # Fail fast when required deployment secrets have not been configured.
    if not os.getenv('SECRET_KEY') or os.getenv('SECRET_KEY', '').startswith('REPLACE_'):
        raise RuntimeError('Set a strong SECRET_KEY in your private .env file')
    if not os.getenv('SITE_ACCESS_PASSWORD') or os.getenv('SITE_ACCESS_PASSWORD', '').startswith('REPLACE_'):
        raise RuntimeError('Set SITE_ACCESS_PASSWORD in your private .env file')
    if (not (os.getenv('SOURCE_CODE_URL') or '').startswith('https://')
            or 'REPLACE_' in os.getenv('SOURCE_CODE_URL', '')):
        raise RuntimeError('Configure SOURCE_CODE_URL with the public HTTPS source repository for this edition')
    DEBUG = False
    # En producción, más seguro
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"

# Si en el futuro necesitas testing:
class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
