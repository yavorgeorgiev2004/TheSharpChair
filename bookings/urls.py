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

