"""
manage.py
=========
Django's command-line utility for administrative tasks.

This file is the entry point for all management commands during
development. It is not used in production — Heroku uses wsgi.py
instead via the Procfile.

COMMON COMMANDS
---------------
python manage.py runserver
    Starts the local development server at http://127.0.0.1:8000
    Auto-reloads when Python files change. Never use in production.

python manage.py makemigrations
    Reads models.py and generates a migration file describing schema
    changes. Run this every time you change a model field.

python manage.py migrate
    Applies pending migrations to the database. Creates or alters
    tables to match the current state of models.py.

python manage.py createsuperuser
    Creates an admin account for the /admin/ panel interactively.
    On Heroku: heroku run python manage.py createsuperuser

python manage.py loaddata initial_data
    Loads the services fixture into the database:
        bookings/fixtures/initial_data.json
    Run once after the first migrate to populate service data.

python manage.py collectstatic
    Copies all static files (CSS, JS) into STATIC_ROOT (staticfiles/).
    Heroku runs this automatically on deploy via whitenoise.

python manage.py shell
    Opens an interactive Python shell with Django pre-configured.
    Useful for testing ORM queries during development.
"""

import os
import sys


def main():
    """
    Sets the Django settings module and delegates to Django's
    command-line management utility.

    os.environ.setdefault() sets DJANGO_SETTINGS_MODULE only if it
    is not already set — allows the settings module to be overridden
    externally (e.g. for testing with different settings).
    """
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barbershop.settings')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Pass command-line arguments (e.g. 'runserver', 'migrate') to Django
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
