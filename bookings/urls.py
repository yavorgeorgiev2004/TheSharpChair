"""

bookings/urls.py
================
URL routing configuration for the bookings application.

HOW URL ROUTING WORKS
---------------------
Each path() call maps a URL pattern to a view function and gives it
a name. Django checks patterns in order from top to bottom and calls
the first matching view.

URL NAMES
---------
The name= argument is critical. It allows views and templates to
reference URLs by name rather than hardcoded paths:

    In views.py:       redirect('my_bookings')
    In templates:      {% url 'cancel_booking' booking.id %}

If you rename a URL path (e.g. '/my-bookings/' → '/bookings/'),
only this file needs updating. Views, templates, and redirects
all continue working because they reference the name, not the path.

URL PARAMETERS
--------------
<int:booking_id> captures an integer from the URL and passes it
to the view as the booking_id argument:

    /my-bookings/cancel/42/  →  cancel_booking(request, booking_id=42)

<str:ref> captures a string:
    /book/confirmed/SC3F7A9B/  →  booking_confirmed(request, ref='SC3F7A9B')

ADDING NEW URLS
---------------
1. Write the view function in views.py
2. Add a path() here with a unique name
3. Reference by name in templates and redirects
"""

from django.urls import path
from . import views

urlpatterns = [

    # ── PUBLIC — no login required ───────────────────────
    path('',
         views.home,
         name='home'),          # → views.home()

    path('services/',
         views.services_view,
         name='services'),      # → views.services_view()


    # ── AUTHENTICATION ───────────────────────────────────
    path('register/',
         views.register_view,
         name='register'),      # → views.register_view()

    path('login/',
         views.login_view,
         name='login'),         # → views.login_view()
                                # settings.LOGIN_URL points here

    path('logout/',
         views.logout_view,
         name='logout'),    # → views.logout_view() — POST only in production


    # ── BOOKING WIZARD — 4 steps ──────────────────────────
    # Each step stores its selection in the session and redirects to the next.
    # Steps guard against being accessed out of order by checking session keys.

    path('book/',
         views.book_step1,
         name='book_step1'),    # Step 1: choose service

    path('book/barber/',
         views.book_step2,
         name='book_step2'),    # Step 2: choose barber

    path('book/datetime/',
         views.book_step3,
         name='book_step3'),    # Step 3: choose date and time slot

    path('book/details/',
         views.book_step4,
         name='book_step4'),    # Step 4: personal details + confirm

    # <str:ref> captures the booking reference from the URL
    # e.g. /book/confirmed/SC3F7A9B2E/ →
    # booking_confirmed(request, ref='SC3F7A9B2E')
    path('book/confirmed/<str:ref>/',
         views.booking_confirmed,
         name='booking_confirmed'),


    # ── CUSTOMER ACCOUNT ────────────────────────────────────────
    path('my-bookings/',
         views.my_bookings,
         name='my_bookings'),   # settings.LOGIN_REDIRECT_URL points here

    # <int:booking_id> captures the booking primary key as an integer
    # e.g. /my-bookings/edit/42/ → edit_booking(request, booking_id=42)
    path('my-bookings/edit/<int:booking_id>/',
         views.edit_booking,
         name='edit_booking'),

    path('my-bookings/cancel/<int:booking_id>/',
         views.cancel_booking,
         name='cancel_booking'),  # accessible to customer OR assigned barber


    # ── BARBER ────────────────────────────────────────────────
    path('schedule/',
         views.barber_schedule,
         # only barbers can see this — role checked in view
         name='barber_schedule'),


    # ── AJAX — internal JSON API ────────────────────────────
    # Called by JavaScript fetch() in book_step3.html
    # when the user picks a date.
    # Returns JSON: {"slots": ["08:00", "08:30", ...]}
    # Protected by @login_required and @require_GET decorators in views.py
    path('ajax/slots/',
         views.available_slots_ajax,
         name='available_slots_ajax'),
]

