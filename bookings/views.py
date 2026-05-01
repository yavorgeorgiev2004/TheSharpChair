"""
bookings/views.py
=================
All view functions for The Sharp Chair application.

HOW VIEWS WORK
--------------
A view is a Python function that:
  1. Receives an HttpRequest object
  2. Runs application logic (queries database, validates forms, etc.)
  3. Returns an HttpResponse (rendered HTML or JSON)

Django routes requests to the correct view via urls.py. Every URL
in the application maps to exactly one view function.

VIEW GROUPS IN THIS FILE
------------------------
  PUBLIC          → home(), services_view()
  AUTHENTICATION  → register_view(), login_view(), logout_view()
  BOOKING WIZARD  → book_step1() through book_step4(), booking_confirmed()
  CUSTOMER        → my_bookings(), edit_booking(), cancel_booking()
  BARBER          → barber_schedule()
  AJAX / API      → available_slots_ajax()

SECURITY PATTERN
----------------
Every view that handles user data is decorated with @login_required.
This redirects unauthenticated users to /login/ before any code runs.
Object-level security uses get_object_or_404(Booking, customer=request.user)
so users can only access their own records — a 404 is returned for others.

SESSION MANAGEMENT
------------------
The booking wizard stores selections across four HTTP requests using
Django's session framework. Data is stored server-side in the
django_session database table. The browser only holds a session key
cookie — no booking data is ever sent to the browser.
"""

from datetime import date, time, datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required  # security decorator
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages  # flash message framework
from django.http import JsonResponse            # returns JSON instead of HTML
# restricts to GET requests only
from django.views.decorators.http import require_GET

from .models import Service, Barber, Booking, Cancellation
from .forms import (
    RegisterForm,
    BookingStep1Form, BookingStep2Form,
    BookingStep3Form, BookingStep4Form,
    EditBookingForm, CancellationForm
)


# ═════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def get_available_slots(barber, chosen_date, service):
    """
    Returns a list of available start times for a given barber, date,
    and service. Called by book_step3() for the rendered page and by
    available_slots_ajax() for the AJAX date picker.

    ALGORITHM
    ---------
    1. Fetch all existing confirmed/pending bookings for this barber on
       this date in ONE query (before the loop — avoids N+1 problem).
    2. Iterate through every 30-minute window from 8am to 8pm using a
       while loop with timedelta arithmetic.
    3. For each window, apply the interval overlap check:
         conflict exists if:  existing.start < candidate.end
                         AND  existing.end   > candidate.start
    4. Only add the window to the results list if no conflict found.

    INTERVAL OVERLAP LOGIC
    ----------------------
    Two time ranges [A_start, A_end] and [B_start, B_end] overlap if:
        A_start < B_end  AND  A_end > B_start
    This correctly handles partial overlaps — a 60-minute booking at
    10:00 blocks both the 10:00 and 10:30 slots.

    PERFORMANCE NOTE
    ----------------
    The database query runs once before the while loop. The ORM filter
    inside the loop re-uses the cached queryset without additional
    database calls, so performance is constant regardless of loop count.

    Args:
        barber      : Barber model instance
        chosen_date : Python date object
        service     : Service model instance (provides duration_mins)

    Returns:
        List of datetime.time objects representing free start times
    """
    # Opening and closing times as Python time objects
    OPEN = time(8, 0)   # 08:00
    CLOSE = time(20, 0)  # 20:00

    # Step between slots — 30 minutes as a timedelta
    interval = timedelta(minutes=30)

    # ONE database query — fetch all active bookings for this barber/date.
    # We reuse this queryset inside the loop rather than querying per slot.
    # status__in is equivalent to SQL: WHERE status IN ('confirmed', 'pending')
    taken = Booking.objects.filter(
        barber=barber,
        date=chosen_date,
        status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_PENDING],
    )

    slots = []

    # datetime.combine() merges a date and a time into a datetime object
    # so we can do arithmetic with timedelta
    # (can't add timedelta to time alone)
    current = datetime.combine(chosen_date, OPEN)
    end_day = datetime.combine(chosen_date, CLOSE)

    # Step through every possible 30-minute start time
    # Stop when the slot + service duration would run past closing time
    while current + timedelta(minutes=service.duration_mins) <= end_day:

        # Calculate where this slot would end
        slot_end = current + timedelta(minutes=service.duration_mins)

        # Interval overlap check against all existing bookings
        # start_time__lt → field lookup: existing.start_time < slot_end
        # end_time__gt   → field lookup: existing.end_time   > current
        conflict = taken.filter(
            start_time__lt=slot_end.time(),
            end_time__gt=current.time(),
        ).exists()  # .exists() is more efficient than .count() > 0

        # Only add slot to results if no conflict found
        if not conflict:
            slots.append(current.time())

        # Move forward by 30 minutes for the next iteration
        current += interval

    return slots


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC VIEWS — no authentication required
# ═════════════════════════════════════════════════════════════════════════════

def home(request):
    """
    Renders the home page (/).

    Passes active services and available barbers to the template so
    the stats section (barber count) updates automatically when
    barbers are added or removed via the admin panel.
    """
    services = Service.objects.filter(is_active=True)
    barbers = Barber.objects.filter(is_available=True).select_related('user')
    return render(request, 'bookings/home.html', {
        'services': services,
        'barbers':  barbers,
    })


def services_view(request):
    """
    Renders the full services listing page (/services/).

    Only shows services where is_active=True — retired services are
    hidden automatically without any code changes needed.
    """
    services = Service.objects.filter(is_active=True)
    return render(request, 'bookings/services.html', {'services': services})


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION VIEWS
# ═════════════════════════════════════════════════════════════════════════════

def register_view(request):
    """
    Handles new user registration (/register/).

    GET:  Display the empty RegisterForm
    POST: Validate the form, create User + UserProfile, log in, redirect

    Uses RegisterForm from forms.py which extends Django's UserCreationForm.
    On success, login() creates a session and sets the session cookie.
    Redirect to home if user is already authenticated.
    """
    # Redirect already-authenticated users away from the register page
    if request.user.is_authenticated:
        return redirect('home')

    # Pass request.POST when the form was submitted, None on GET request
    # This is the standard Django form pattern — one view handles both
    form = RegisterForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        # form.save() creates the User record and linked UserProfile
        user = form.save()
        # login() creates a new session in django_session table
        login(request, user)
        messages.success(
            request,
            f"Welcome, {user.first_name}! Your account has been created."
        )
        return redirect('my_bookings')

    return render(request, 'bookings/register.html', {'form': form})


def login_view(request):
    """
    Handles user login (/login/).

    GET:  Display the AuthenticationForm
    POST: Validate credentials, create session, redirect

    AuthenticationForm is Django's built-in form — it handles username/
    password validation and password hash verification automatically.

    ?next= parameter: if Django redirected the user here from a
    @login_required view, the original URL is in request.GET['next'].
    We redirect there after login so the user reaches their destination.
    """
    if request.user.is_authenticated:
        return redirect('home')

    # AuthenticationForm requires 'request' as first argument for security
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f"Welcome back, {user.first_name}!")
        # Respect ?next= parameter, default to my_bookings if not present
        return redirect(request.GET.get('next', 'my_bookings'))

    return render(request, 'bookings/login.html', {'form': form})


@login_required
def logout_view(request):
    """
    Logs the user out (/logout/).

    logout() deletes the session from the database and clears the
    session cookie. @login_required ensures only authenticated users
    can call this (prevents CSRF-based logout attacks on logged-out users).
    """
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect('home')


# ═════════════════════════════════════════════════════════════════════════════
# BOOKING WIZARD — 4 steps, session-based state
# ═════════════════════════════════════════════════════════════════════════════

@login_required
def book_step1(request):
    """
    Step 1 — Choose a service (/book/).

    Clears any previous incomplete booking from the session first,
    so starting a new booking always begins fresh.

    POST: stores the selected service ID in request.session and
    redirects to step 2. Session data persists across requests because
    Django stores it server-side in the django_session database table.
    """
    # Clear any leftover session data from a previous incomplete booking
    for key in [
        'booking_service', 'booking_barber',
        'booking_date', 'booking_time'
    ]:
        # pop with None default prevents KeyError
        request.session.pop(key, None)

    form = BookingStep1Form(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        # Store selected service ID in session — persists to step 2, 3, 4
        request.session['booking_service'] = form.cleaned_data['service'].id
        return redirect('book_step2')

    return render(request, 'bookings/book_step1.html', {
        'form':     form,
        'services': Service.objects.filter(is_active=True),
        'step':     1,  # passed to step_progress.html partial
    })


@login_required
def book_step2(request):
    """
    Step 2 — Choose a barber (/book/barber/).

    Guards against URL-jumping — if session has no service chosen,
    redirect back to step 1. This prevents broken bookings where
    steps are skipped.
    """
    # Guard: redirect to step 1 if session doesn't have service selection
    if 'booking_service' not in request.session:
        return redirect('book_step1')

    form = BookingStep2Form(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        request.session['booking_barber'] = form.cleaned_data['barber'].id
        return redirect('book_step3')

    return render(request, 'bookings/book_step2.html', {
        'form':    form,
        'barbers': Barber.objects.filter(
            is_available=True
        ).select_related('user'),
        'step':    2,
    })


@login_required
def book_step3(request):
    """
    Step 3 — Choose date and time (/book/datetime/).

    Generates available slots by calling get_available_slots() with
    the barber and service from the session. Slots are pre-rendered
    on page load so they are visible without JavaScript. The AJAX
    endpoint available_slots_ajax() refreshes them dynamically when
    the user changes the date.

    Time is stored as a string in the session (HH:MM:SS format)
    because session data must be JSON-serialisable — time objects are not.
    """
    if 'booking_service' not in request.session:
        return redirect('book_step1')
    if 'booking_barber' not in request.session:
        return redirect('book_step2')

    # Retrieve the objects chosen in previous steps from the database
    service = get_object_or_404(Service, pk=request.session['booking_service'])
    barber = get_object_or_404(Barber,  pk=request.session['booking_barber'])

    # Pass barber and service to the form for context-aware validation
    form = BookingStep3Form(
        request.POST or None,
        barber=barber,
        service=service
    )
    slots = []

    # Generate slots for display — either from
    # POST data or existing session value
    chosen_date_str = (
        request.POST.get('date') or
        request.session.get('booking_date')
    )
    if chosen_date_str:
        try:
            chosen_date = date.fromisoformat(chosen_date_str)
            if chosen_date.weekday() < 5:  # only generate for weekdays
                slots = get_available_slots(barber, chosen_date, service)
        except ValueError:
            pass  # invalid date string — slots remain empty

    if request.method == 'POST' and form.is_valid():
        # Store date as ISO string and time
        # as HH:MM:SS string (JSON-serialisable)
        request.session['booking_date'] = form.cleaned_data['date'].isoformat()
        request.session['booking_time'] = (
            form.cleaned_data['start_time'].strftime('%H:%M:%S')
        )
        return redirect('book_step4')

    return render(request, 'bookings/book_step3.html', {
        'form':    form,
        'slots':   slots,    # pre-rendered slots for initial page load
        'service': service,
        'barber':  barber,
        'step':    3,
    })


@login_required
def book_step4(request):
    """
    Step 4 — Personal details and confirmation (/book/details/).

    Pre-fills form fields with the logged-in user's existing data
    so they don't have to type it on every booking.

    On valid POST:
    1. Build a Booking object (commit=False style — not saved yet)
    2. Run full_clean() — triggers clean() then validate_unique()
    3. If clean passes, save() to write to the database
    4. Clear session data for the completed booking
    5. Redirect to confirmation page

    full_clean() is called explicitly because Django does not call
    it automatically on model.save() — we need it for our custom
    clean() validation to run.
    """
    # Guard: all four session keys must exist
    required = [
        'booking_service', 'booking_barber',
        'booking_date', 'booking_time'
    ]
    if not all(k in request.session for k in required):
        return redirect('book_step1')

    # Rebuild objects from session data
    service = get_object_or_404(Service, pk=request.session['booking_service'])
    barber = get_object_or_404(Barber,  pk=request.session['booking_barber'])
    chosen_date = date.fromisoformat(request.session['booking_date'])
    start_time = datetime.strptime(
        request.session['booking_time'], '%H:%M:%S'
    ).time()

    # Pre-fill form with existing user data using initial=
    initial = {
        'first_name': request.user.first_name,
        'last_name':  request.user.last_name,
        'email':      request.user.email,
        'phone': getattr(getattr(request.user, 'profile', None), 'phone', ''),
    }

    form = BookingStep4Form(request.POST or None, initial=initial)

    if request.method == 'POST' and form.is_valid():
        try:
            # Create Booking object in memory without saving to database yet
            booking = Booking(
                customer=request.user,
                barber=barber,
                service=service,
                date=chosen_date,
                start_time=start_time,
                notes=form.cleaned_data['notes'],
                status=Booking.STATUS_CONFIRMED,
            )

            # full_clean() runs:
            #   clean_fields()    → validates each field type
            #   clean()           →
            # our business rules (weekday, hours, overlap)
            #   validate_unique() → checks UniqueConstraint
            # Raises ValidationError if anything fails
            booking.full_clean()

            # All validation passed — write to the database
            # save() also generates the ref and calculates end_time
            booking.save()

            # Clear wizard session data now that booking is complete
            for key in required:
                request.session.pop(key, None)

            messages.success(
                request,
                f"Booking confirmed! Your reference is #{booking.ref}"
            )
            # Redirect to confirmation page with booking ref in URL
            return redirect('booking_confirmed', ref=booking.ref)

        except Exception as e:
            # Catch ValidationError or IntegrityError and show to user
            messages.error(request, f"Could not complete booking: {e}")

    return render(request, 'bookings/book_step4.html', {
        'form':        form,
        'service':     service,
        'barber':      barber,
        'chosen_date': chosen_date,
        'start_time':  start_time,
        'step':        4,
    })


@login_required
def booking_confirmed(request, ref):
    """
    Confirmation page shown after a successful booking
    (/book/confirmed/<ref>/).

    The <ref> URL parameter is captured from the URL and passed as
    an argument. get_object_or_404 with customer=request.user ensures
    only the customer who made this booking can view the confirmation —
    anyone else gets a 404.
    """
    booking = get_object_or_404(Booking, ref=ref, customer=request.user)
    return render(
        request,
        'bookings/booking_confirmed.html',
        {'booking': booking}
    )


# ═════════════════════════════════════════════════════════════════════════════
# CUSTOMER ACCOUNT VIEWS
# ═════════════════════════════════════════════════════════════════════════════

@login_required
def my_bookings(request):
    """
    Customer dashboard — lists all bookings for
    the logged-in user (/my-bookings/).

    QUERY OPTIMISATION
    ------------------
    .select_related('barber__user', 'service') fetches related objects
    using a SQL JOIN in a single database query. Without it, accessing
    booking.barber.user.first_name inside the template loop would
    trigger a separate query per booking (N+1 problem).

    The double underscore traverses FK relationships:
        barber__user = follow barber FK, then follow user FK on barber
    """
    bookings = Booking.objects.filter(
        customer=request.user           # READ — SELECT WHERE customer_id = ?
    ).select_related(
        'barber__user', 'service'       # JOIN to avoid N+1 queries
    ).order_by('-date', '-start_time')  # most recent first

    return render(request, 'bookings/my_bookings.html', {
        'bookings': bookings,
        # used in template for past/future detection
        'today':    date.today(),
    })


@login_required
def edit_booking(request, booking_id):
    """
    Allows a customer to edit date, time, or notes on their booking
    (/my-bookings/edit/<booking_id>/).

    SECURITY: get_object_or_404 with customer=request.user means
    a customer cannot edit another customer's booking — they get a 404.

    commit=False pattern:
        form.save(commit=False) builds the updated Booking object in
        memory without writing to the database. This allows us to run
        full_clean() before the UPDATE SQL executes.
    """
    # Security: 404 if booking doesn't exist or doesn't belong to this user
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)

    # Block editing cancelled bookings — redirect with warning
    if booking.status == Booking.STATUS_CANCELLED:
        messages.error(request, "You cannot edit a cancelled booking.")
        return redirect('my_bookings')

    form = EditBookingForm(request.POST or None, instance=booking)

    if request.method == 'POST' and form.is_valid():
        # commit=False: build updated object without writing yet
        updated = form.save(commit=False)

        # Parse time string from form select field back to time object
        time_str = form.cleaned_data['start_time']
        if isinstance(time_str, str):
            updated.start_time = datetime.strptime(time_str, '%H:%M:%S').time()

        try:
            updated.full_clean()  # run validation before saving UPDATE
            updated.save()        # UPDATE bookings_booking SET ...
            messages.success(request, "Your booking has been updated.")
            return redirect('my_bookings')
        except Exception as e:
            messages.error(request, f"Could not update booking: {e}")

    # Pre-generate slots for the current barber and date for the form
    slots = []
    if booking.date:
        slots = get_available_slots(
            booking.barber, booking.date, booking.service
        )

    return render(request, 'bookings/edit_booking.html', {
        'form':    form,
        'booking': booking,
        'slots':   slots,
    })


@login_required
def cancel_booking(request, booking_id):
    """
    Cancels a booking — accessible to the customer OR the assigned barber
    (/my-bookings/cancel/<booking_id>/).

    SOFT DELETE PATTERN
    -------------------
    The booking is NOT removed from the database. Instead:
    1. booking.status is changed to 'cancelled'
    2. A Cancellation record is created with who/when/why

    This preserves the full audit trail and prevents orphaned
    Cancellation records that would lose their context.

    PERMISSION CHECK
    ----------------
    Three valid reasons to cancel:
    - You are the customer who made the booking
    - You are the barber assigned to the booking
    - You are a staff admin

    Anyone else gets an error and redirect.

    POST REDIRECT
    -------------
    Barbers are redirected to their schedule, customers to their
    bookings list — determined by the permission check.
    """
    booking = get_object_or_404(Booking, id=booking_id)

    # ── Permission check ──
    is_customer = (booking.customer == request.user)
    is_barber = (
        hasattr(request.user, 'barber') and
        booking.barber == request.user.barber
    )

    # Block if none of the valid roles match
    if not (is_customer or is_barber or request.user.is_staff):
        messages.error(
            request,
            "You do not have permission to cancel this booking."
        )
        return redirect('my_bookings')

    # Block double-cancellation
    if booking.status == Booking.STATUS_CANCELLED:
        messages.warning(request, "This booking is already cancelled.")
        return redirect('my_bookings')

    form = CancellationForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        # SOFT DELETE — change status rather than deleting the row
        booking.status = Booking.STATUS_CANCELLED
        booking.save()  # UPDATE bookings_booking SET status = 'cancelled'

        # Create audit record — records who cancelled, when, and why
        Cancellation.objects.create(
            booking=booking,
            cancelled_by=request.user,
            reason=form.cleaned_data.get('reason', ''),
        )

        messages.success(
            request,
            f"Booking #{booking.ref} has been cancelled."
        )

        # Redirect to appropriate page based on who cancelled
        if is_barber and not is_customer:
            return redirect('barber_schedule')
        return redirect('my_bookings')

    return render(request, 'bookings/cancel_booking.html', {
        'form':    form,
        'booking': booking,
    })


# ═════════════════════════════════════════════════════════════════════════════
# BARBER VIEWS
# ═════════════════════════════════════════════════════════════════════════════

@login_required
def barber_schedule(request):
    """
    Barber's dashboard — shows only the logged-in barber's upcoming
    appointments (/schedule/).

    ROLE CHECK
    ----------
    hasattr(request.user, 'barber') checks whether a Barber record
    exists for this user. Regular customers don't have one, so they
    are redirected away. This is the role detection mechanism — no
    separate roles table is needed.

    DATA SHOWN TO BARBER
    --------------------
    Unlike my_bookings (which shows barber name), this view shows
    the customer's name and email — the information a barber needs
    to identify and contact their clients.
    """
    # Role check — regular customers don't have a .barber attribute
    if not hasattr(request.user, 'barber'):
        messages.error(request, "You do not have a barber profile.")
        return redirect('home')

    # Only show upcoming confirmed/pending — not cancelled or completed
    # Ordered chronologically so barber sees their day in time order
    bookings = Booking.objects.filter(
        barber=request.user.barber,
        status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_PENDING],
    ).select_related(
        # JOIN to avoid N+1 for customer name and service
        'customer', 'service'
    ).order_by('date', 'start_time')  # ascending — earliest first

    return render(
        request,
        'bookings/barber_schedule.html',
        {'bookings': bookings}
    )


# ═════════════════════════════════════════════════════════════════════════════
# AJAX ENDPOINT — internal API for the time slot picker
# ═════════════════════════════════════════════════════════════════════════════

@login_required
@require_GET  # return 405 Method Not Allowed if called with POST/PUT/DELETE
def available_slots_ajax(request):
    """
    Returns available time slots as JSON for the booking wizard date picker
    (/ajax/slots/?barber_id=1&service_id=2&date=2025-06-10).

    HOW THIS INTERNAL API WORKS
    ---------------------------
    This is not an external API — it is a Django view that returns JSON
    instead of HTML. When the user picks a date on book_step3.html,
    JavaScript calls this URL, receives the JSON response, and renders
    the time slot buttons dynamically without reloading the page.

    QUERY PARAMETERS (from the URL ?key=value syntax)
    -------------------------------------------------
    barber_id  : ID of the selected Barber record
    service_id : ID of the selected Service record (provides duration)
    date       : ISO format date string e.g. '2025-06-10'

    RESPONSE FORMAT
    ---------------
    Success: {"slots": ["08:00", "08:30", "09:30", ...]}
    Error:   {"error": "description"} with HTTP 400 status

    ERROR HANDLING
    --------------
    The try/except catches invalid IDs, malformed dates, and closed
    weekend dates, returning a JSON error response rather than crashing.
    """
    try:
        # Read query parameters from the URL (?barber_id=1&...)
        barber_id = request.GET.get('barber_id')
        date_str = request.GET.get('date')
        service_id = request.GET.get('service_id')

        # Fetch the objects — raises Barber/Service.DoesNotExist if invalid IDs
        barber = Barber.objects.get(pk=barber_id)
        service = Service.objects.get(pk=service_id)

        # Convert ISO date string to Python date object
        chosen_date = date.fromisoformat(date_str)

        # Reject weekend requests with a descriptive error
        if chosen_date.weekday() >= 5:
            return JsonResponse({'error': 'Closed on weekends'}, status=400)

        # Generate available slots using the shared helper function
        slots = get_available_slots(barber, chosen_date, service)

        # List comprehension: convert each time object to 'HH:MM' string
        # strftime('%H:%M') formats time(9, 30, 0) → '09:30'
        # JSON cannot serialise Python time objects directly
        return JsonResponse({'slots': [s.strftime('%H:%M') for s in slots]})

    except Exception as e:
        # Catch-all for invalid IDs, bad date strings, etc.
        return JsonResponse({'error': str(e)}, status=400)

