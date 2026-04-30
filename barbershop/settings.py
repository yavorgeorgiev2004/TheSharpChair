"""
barbershop/settings.py
======================
Central Django configuration file for The Sharp Chair project.

This file controls every major behaviour of the application:
security, database connection, installed apps, middleware, templates,
static files, and authentication redirects.

HOW SECRETS ARE MANAGED
------------------------
All sensitive values (SECRET_KEY, DATABASE_URL, DEBUG) are read from
environment variables using python-decouple. Locally these live in a
.env file that is listed in .gitignore and never committed to GitHub.
On Heroku they are set as Config Vars in the dashboard. This means
the codebase contains zero sensitive information.

ENVIRONMENT SWITCHING
---------------------
The DATABASE_URL variable controls which database Django connects to.
- Local:  DATABASE_URL=sqlite:///db.sqlite3  → uses a local file
- Heroku: DATABASE_URL=postgres://...        → uses PostgreSQL server
dj-database-url parses whichever URL is present and configures Django
automatically. No code changes required between environments.

UPDATING THIS FILE
------------------
- Adding a new Django app: add it to INSTALLED_APPS
- Changing database: update DATABASE_URL in .env or Heroku config vars
- Adding middleware: insert into MIDDLEWARE in the correct position
- Changing static file behaviour: update STATICFILES_STORAGE
"""

from pathlib import Path
from decouple import config     # reads .env locally, env vars on Heroku
import dj_database_url          # parses DATABASE_URL string into Django format

# ── BASE DIRECTORY ────────────────────────────────────────────────────────────
# Path(__file__) is the absolute path to this settings.py file.
# .resolve().parent.parent walks two levels up to reach the project root.
# All other paths in this file are built relative to BASE_DIR.
BASE_DIR = Path(__file__).resolve().parent.parent


# ── SECURITY ──────────────────────────────────────────────────────────────────
# SECRET_KEY is used by Django to cryptographically sign session cookies,
# CSRF tokens, and password reset links. Must be kept secret at all times.
# Generated with: python -c "from django.core.management.utils import
# get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')

# DEBUG=True shows detailed error pages in the browser — useful locally
# but dangerous in production as it exposes code and config to users.
# Always False on Heroku via the environment variable.
# cast=bool converts the string 'False' from the env var to Python False.
DEBUG = config('DEBUG', default=True, cast=bool)

# Heroku provides a .herokuapp.com subdomain. localhost and 127.0.0.1
# are needed for local development. The leading dot covers all subdomains.
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.herokuapp.com',
]


# ── INSTALLED APPLICATIONS ────────────────────────────────────────────────────
# Django only loads apps listed here. The first six are Django's own built-in
# apps. 'bookings' is the custom app containing all project-specific code.
# When adding a new app, always add it here or Django will ignore it.
INSTALLED_APPS = [
    'django.contrib.admin',         # built-in admin panel at /admin/
    'django.contrib.auth',          # authentication framework (User model)
    'django.contrib.contenttypes',  # tracks model types across the project
    'django.contrib.sessions',      # server-side session storage
    'django.contrib.messages',      # one-time flash messages framework
    'django.contrib.staticfiles',   # static file management (CSS, JS)
    # ── Project apps ──
    'bookings',                     # the main application for this project
]


# ── MIDDLEWARE ────────────────────────────────────────────────────────────────
# Middleware are functions that process every request and response in order.
# The order matters — each middleware wraps the ones below it.
# WhiteNoiseMiddleware MUST come second (after SecurityMiddleware) so it
# can intercept static file requests before Django processes them as views.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',        # sets security headers
    'whitenoise.middleware.WhiteNoiseMiddleware',           # serves CSS/JS files
    'django.contrib.sessions.middleware.SessionMiddleware', # enables session system
    'django.middleware.common.CommonMiddleware',            # URL normalisation
    'django.middleware.csrf.CsrfViewMiddleware',            # CSRF token validation
    'django.contrib.auth.middleware.AuthenticationMiddleware', # attaches user to request
    'django.contrib.messages.middleware.MessageMiddleware', # enables flash messages
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # prevents iframe embedding
]

# Root URL configuration — Django starts URL matching here
ROOT_URLCONF = 'barbershop.urls'


# ── TEMPLATES ─────────────────────────────────────────────────────────────────
# Configures Django's template engine.
# DIRS tells Django to also look in the top-level /templates folder for
# base.html and other shared templates. APP_DIRS=True means Django also
# looks inside each app's own templates/ subdirectory automatically.
# context_processors inject variables into every template automatically
# (e.g. request, user, messages) without needing to pass them from views.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # project-level templates folder
        'APP_DIRS': True,                  # also check bookings/templates/
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # makes request available in all templates
                'django.contrib.auth.context_processors.auth', # makes user available in all templates
                'django.contrib.messages.context_processors.messages', # makes messages available
            ],
        },
    },
]

# Entry point for WSGI servers (gunicorn on Heroku)
WSGI_APPLICATION = 'barbershop.wsgi.application'


# ── DATABASE ──────────────────────────────────────────────────────────────────
# dj_database_url.config() reads DATABASE_URL from the environment and
# converts it to the dictionary format Django expects.
#
# Example local .env:    DATABASE_URL=sqlite:///db.sqlite3
# Example Heroku:        DATABASE_URL=postgres://user:pass@host:5432/dbname
#
# The default= fallback means SQLite is used if DATABASE_URL is not set,
# so a developer can run the project with zero database setup locally.
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
    )
}


# ── PASSWORD VALIDATION ───────────────────────────────────────────────────────
# Django runs these validators when a user sets or changes their password.
# They reject passwords that are too similar to user info, too short,
# too common (e.g. "password"), or entirely numeric.
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ── AUTHENTICATION REDIRECTS ──────────────────────────────────────────────────
# LOGIN_URL: where unauthenticated users are sent when they hit a
# @login_required protected view.
# LOGIN_REDIRECT_URL: where users land after successfully logging in.
# LOGOUT_REDIRECT_URL: where users land after logging out.
LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/my-bookings/'
LOGOUT_REDIRECT_URL = '/'


# ── INTERNATIONALISATION ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-gb'       # British English for date/number formatting
TIME_ZONE     = 'Europe/London' # all datetimes stored and displayed in GMT/BST
USE_I18N      = True           # enables Django's translation framework
USE_TZ        = True           # stores all datetimes as UTC in the database


# ── STATIC FILES ──────────────────────────────────────────────────────────────
# STATIC_URL: the URL prefix for static files (e.g. /static/css/style.css)
# STATIC_ROOT: where collectstatic gathers all static files for production.
#   Run: python manage.py collectstatic before deploying.
# STATICFILES_DIRS: additional directories Django looks in for static files
#   during development (our /static/ folder at the project root).
# STATICFILES_STORAGE: whitenoise compresses files and adds content hashes
#   to filenames (e.g. style.abc123.css) so browser caches update correctly.
STATIC_URL       = '/static/'
STATIC_ROOT      = BASE_DIR / 'staticfiles'  # created by collectstatic
STATICFILES_DIRS = [BASE_DIR / 'static']     # source: our /static/ folder
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ── MISC ──────────────────────────────────────────────────────────────────────
# Django 3.2+ requires explicitly setting the default primary key type.
# BigAutoField uses 64-bit integers — supports up to 9.2 quintillion rows.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ── MESSAGES FRAMEWORK ────────────────────────────────────────────────────────
# Maps Django message levels to CSS class names used in base.html.
# This allows the template to apply the correct styling to each alert type
# without needing if/elif logic in the template itself.
# Usage in views: messages.success(request, "Booking confirmed!")
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG:   'alert-info',
    messages_constants.INFO:    'alert-info',
    messages_constants.SUCCESS: 'alert-success',
    messages_constants.WARNING: 'alert-warning',
    messages_constants.ERROR:   'alert-error',
}
