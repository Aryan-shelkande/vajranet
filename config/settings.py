"""VajraNet Django settings — SQLite locally, PostgreSQL-ready for Render."""

from __future__ import annotations

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    WEATHER_CACHE_SECONDS=(int, 600),
    FORECAST_CACHE_SECONDS=(int, 1800),
    ALERT_CACHE_SECONDS=(int, 300),
    EARTHQUAKE_CACHE_SECONDS=(int, 600),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-change-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "weather",
    "disasters",
    "safety",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.platform_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "vajranet",
        }
    }

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
    },
    "EXCEPTION_HANDLER": "weather.api_exceptions.custom_exception_handler",
}

# External API configuration
DEFAULT_WEATHER_PROVIDER = env("DEFAULT_WEATHER_PROVIDER", default="open_meteo")
OPENWEATHER_API_KEY = env("OPENWEATHER_API_KEY", default="")
NASA_FIRMS_MAP_KEY = env("NASA_FIRMS_MAP_KEY", default="")
IMD_API_KEY = env("IMD_API_KEY", default="")
BLITZORTUNG_USERNAME = env("BLITZORTUNG_USERNAME", default="")
BLITZORTUNG_PASSWORD = env("BLITZORTUNG_PASSWORD", default="")

# Map basemap — OpenFreeMap Liberty (vector style via MapLibre; no API key).
# Do NOT point MAP_TILE_STYLE_URL at tile.openstreetmap.org volunteer raster servers.
MAP_TILE_STYLE_URL = env(
    "MAP_TILE_STYLE_URL",
    default="https://tiles.openfreemap.org/styles/liberty",
)
MAP_TILE_ATTRIBUTION = env(
    "MAP_TILE_ATTRIBUTION",
    default=(
        'OpenFreeMap © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">'
        "OpenMapTiles</a> Data from "
        '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">'
        "OpenStreetMap</a>"
    ),
)
MAP_TILE_MAX_ZOOM = env.int("MAP_TILE_MAX_ZOOM", default=18)
# Backward-compatible alias (prefer MAP_TILE_STYLE_URL)
MAP_TILE_URL = env("MAP_TILE_URL", default="") or MAP_TILE_STYLE_URL

# Vajra AI — platform assistant by default; optional OpenAI / Ollama
AI_PROVIDER = env("AI_PROVIDER", default="platform")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o-mini")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://127.0.0.1:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="llama3.2")
AI_BRIEFING_CACHE_SECONDS = env.int("AI_BRIEFING_CACHE_SECONDS", default=600)

# SMS alerts — demo mode is the default so local use does not spend credits.
SMS_ENABLED = env.bool("SMS_ENABLED", default=True)
SMS_DEMO_MODE = env.bool("SMS_DEMO_MODE", default=True)
SMS_PROVIDER = env("SMS_PROVIDER", default="demo")
SMS_API_URL = env("SMS_API_URL", default="")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="VAJRANET")
SMS_TIMEOUT_SECONDS = env.float("SMS_TIMEOUT_SECONDS", default=8.0)

WEATHER_CACHE_SECONDS = env("WEATHER_CACHE_SECONDS")
FORECAST_CACHE_SECONDS = env("FORECAST_CACHE_SECONDS")
ALERT_CACHE_SECONDS = env("ALERT_CACHE_SECONDS")
EARTHQUAKE_CACHE_SECONDS = env("EARTHQUAKE_CACHE_SECONDS")

HTTP_TIMEOUT_SECONDS = 15.0
HTTP_MAX_RETRIES = 2

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_DIR = BASE_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "vajranet.log",
            "maxBytes": 5_000_000,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "weather": {"level": LOG_LEVEL, "propagate": True},
        "disasters": {"level": LOG_LEVEL, "propagate": True},
        "django.request": {"level": "WARNING", "propagate": True},
    },
}

PLATFORM_NAME = "VajraNet"
PLATFORM_SUBTITLE = "India Atmospheric & Disaster Intelligence"
DISCLAIMER = (
    "Information shown on this platform is intended for situational awareness "
    "and should not replace official warnings or instructions issued by "
    "competent authorities such as IMD, NDMA, or state disaster management agencies."
)
