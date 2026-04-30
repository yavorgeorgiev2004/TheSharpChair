"""
barbershop/urls.py
==================
Root URL configuration for The Sharp Chair Django project.

Django starts here when matching any incoming URL. This file has two
entries — the admin panel and the bookings app. All application URLs
are defined in bookings/urls.py and included here with include().

HOW URL ROUTING WORKS
---------------------
1. A request arrives at e.g. /my-bookings/
2. Django checks this file first
3. The '' prefix matches everything, so Django passes the full URL
   to bookings/urls.py for further matching
4. bookings/urls.py finds the correct view function and calls it

ADDING NEW APPS
---------------
If a new Django app is created (e.g. 'payments'), add a new path:
    path('payments/', include('payments.urls')),
and create a urls.py inside that app with its own URL patterns.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Django's built-in admin panel — automatically generated from admin.py
    # Only accessible to users with is_staff=True on their User account
    # Provides full CRUD on all registered models
    path('admin/', admin.site.urls),

    # Delegates all other URLs to the bookings app's url configuration.
    # The empty string '' means no prefix — bookings/urls.py handles
    # everything from the root domain onwards (/, /book/, /login/, etc.)
    path('', include('bookings.urls')),
]
