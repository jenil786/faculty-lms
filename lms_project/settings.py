import os
import dj_database_url

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = True
"""DEBUG = os.getenv("DEBUG") == "False"""
# --- ALLOWED_HOSTS FIX ---
# We combine all possible hosts into ONE list
ALLOWED_HOSTS = [
    '127.0.0.1', 
    'localhost', 
    'faculty-lms.onrender.com', 
    '.onrender.com'
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'lms',
    'reports',
    'faculty.apps.FacultyConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # ADD THIS
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
]

ROOT_URLCONF = 'lms_project.urls'

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Add this so Django looks into your manual static folders
STATICFILES_DIRS = [
    BASE_DIR / "staticfiles", # This tells Django to look where your logo is
]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "production_static" # Keep the collectstatic output separate
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lms_project.wsgi.application'

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'  
LOGOUT_REDIRECT_URL = '/login/'
# Force these to False for local development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


# =========================
# Email Configuration
# =========================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# 1. Put your real Gmail address here
EMAIL_HOST_USER = 'powerover994@gmail.com' 

# 2. Put your REAL 16-character App Password here (No spaces)
EMAIL_HOST_PASSWORD = 'hdefrvtiawziynvr' 

# 3. Match this to your EMAIL_HOST_USER
DEFAULT_FROM_EMAIL = 'SSIT LMS Admin <powerover994@gmail.com>'

EMAIL_TIMEOUT = 10