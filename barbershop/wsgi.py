"""
barbershop/wsgi.py
==================
WSGI (Web Server Gateway Interface) entry point for The Sharp Chair.

WSGI is the standard Python interface between a web server and a
Django application. When Heroku starts the application using the
Procfile command:

    web: gunicorn barbershop.wsgi --log-file -

Gunicorn imports this file and calls the 'application' object to
handle incoming HTTP requests.

This file should not need to be modified for normal development.
If the project settings file is moved or renamed, update the
DJANGO_SETTINGS_MODULE string below to match.
"""

import os
from django.core.wsgi import get_wsgi_application

# Tell Django which settings module to use before loading the app.
# This must be set before get_wsgi_application() is called.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barbershop.settings')

# get_wsgi_application() initialises Django and returns a callable
# that gunicorn uses to handle each incoming HTTP request.
application = get_wsgi_application()
