"""
bookings/models.py
==================
Defines all database tables for The Sharp Chair as Django model classes.

HOW MODELS WORK
---------------
Each Python class here maps to one table in the database. Each class
attribute maps to one column. Django reads these classes and generates
SQL automatically when you run:

    python manage.py makemigrations   # generates migration file from models
    python manage.py migrate          # executes SQL against the database

You never write SQL manually. Django's ORM handles all of it.

DATABASE TABLES DEFINED HERE
-----------------------------
  UserProfile   → bookings_userprofile table
  Service       → bookings_service table
  Barber        → bookings_barber table
  Booking       → bookings_booking table (core transaction table)
  Cancellation  → bookings_cancellation table (audit trail)

RELATIONSHIPS
-------------
  auth_user ──1:1──► UserProfile   (one user has one profile)
  auth_user ──1:1──► Barber        (one user can be one barber)
  auth_user ──1:M──► Booking       (one customer has many bookings)
  Barber    ──1:M──► Booking       (one barber has many bookings)
  Service   ──1:M──► Booking       (one service used in many bookings)
  Booking   ──1:1──► Cancellation  (one booking has one cancellation record)

UPDATING MODELS
---------------
After any change to a model field, always run makemigrations then migrate.
Skipping this leaves the database out of sync with the Python code.
"""

import uuid                          # generates unique booking references
from datetime import datetime, timedelta  # datetime arithmetic for end_time calculation
from django.db import models
from django.contrib.auth.models import User  # Django's built-in user table
from django.core.exceptions import ValidationError


# ── USER PROFILE ──────────────────────────────────────────────────────────────
class UserProfile(models.Model):
    """
    Extends Django's built-in User model with a phone number.

    WHY A SEPARATE TABLE
    --------------------
    Django's auth_user table covers authentication (email, password).
    Rather than hacking the built-in User model, we extend it cleanly
    using a OneToOneField — a foreign key with a UNIQUE constraint,
    meaning one user can have exactly one profile and vice versa.

    CREATED AUTOMATICALLY
    ---------------------
    UserProfile is created in forms.py inside RegisterForm.save()
    immediately after the User record is saved. A user can never
    exist without a profile.
    """

    # OneToOneField creates a unique FK — generates:
    # user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
    # CASCADE means deleting the user also deletes their profile
    # related_name='profile' allows: user.profile.phone
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    phone = models.CharField(max_length=20)  # VARCHAR(20) — stored as-is, not validated

    # auto_now_add=True sets this to NOW() on INSERT, never updated afterwards
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # String representation shown in admin panel dropdowns and list views
        return f"{self.user.get_full_name()} — Profile"


# ── SERVICE ───────────────────────────────────────────────────────────────────
class Service(models.Model):
    """
    A service offered by the barber shop (e.g. Classic Haircut, Fade & Blend).

    LOOKUP TABLE PATTERN
    --------------------
    Service is a standalone lookup table — it references nothing else
    and is referenced by Booking via ForeignKey. If you add a new service
    here, it immediately appears in the booking wizard because views.py
    queries Service.objects.filter(is_active=True) dynamically.

    SOFT DEACTIVATION
    -----------------
    is_active=False hides a service from the booking wizard without
    deleting it. This is important because Booking uses on_delete=PROTECT
    on its service FK — you cannot delete a service that bookings reference.
    Set is_active=False instead to retire a service gracefully.

    ADDING A NEW SERVICE
    --------------------
    Go to /admin → Services → Add Service, or load a fixture with:
        python manage.py loaddata initial_data
    """

    name        = models.CharField(max_length=100)  # VARCHAR(100)
    description = models.TextField()                # TEXT — unlimited length
    duration_mins = models.IntegerField(            # INTEGER — minutes as integer
        help_text="Duration in minutes"             # shown in admin panel
    )
    price = models.DecimalField(                    # NUMERIC(6,2) — e.g. 18.00
        max_digits=6,
        decimal_places=2
    )
    # BooleanField — False hides service from booking wizard without deleting
    is_active = models.BooleanField(default=True)

    class Meta:
        # Default ordering when querying Service.objects.all()
        # Shows cheapest services first in the listing
        ordering = ['price']

    def __str__(self):
        return f"{self.name} (£{self.price}, {self.duration_mins}min)"


# ── BARBER ────────────────────────────────────────────────────────────────────
class Barber(models.Model):
    """
    Represents a barber — linked to a User account so the barber can log in.

    ROLE DETECTION
    --------------
    There is no separate roles table. Whether a user is a barber is
    determined entirely by whether a Barber record exists for them:

        hasattr(request.user, 'barber')  →  True = barber, False = customer

    This check appears in views.py and base.html to show different
    navigation and different data depending on who is logged in.

    CREATING A BARBER ACCOUNT
    -------------------------
    1. Go to /admin → Users → Add User → fill in name and password
    2. Go to /admin → Barbers → Add Barber → link to that user
    The user can now log in and see the barber schedule instead of My Bookings.

    TAKING A BARBER OFFLINE
    -----------------------
    Set is_available=False in the admin. The barber will not appear
    in the booking wizard's barber selection step until re-enabled.
    """

    # OneToOneField — one user account, one barber profile
    # related_name='barber' allows: user.barber (accessed in views and templates)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='barber'
    )

    speciality   = models.CharField(max_length=100)  # e.g. "Fades & Skin Fades"
    bio          = models.TextField(blank=True)       # optional — blank=True allows empty
    is_available = models.BooleanField(default=True)  # toggle to hide barber from bookings

    def __str__(self):
        # get_full_name() returns "First Last" from the linked User record
        return self.user.get_full_name()


# ── BOOKING ───────────────────────────────────────────────────────────────────
class Booking(models.Model):
    """
    The core transaction table — one row per appointment.

    This is the most connected table in the schema. It holds three
    ForeignKeys (customer, barber, service) making it the junction
    that ties all other tables together.

    DOUBLE-BOOKING PREVENTION — TWO LAYERS
    ----------------------------------------
    Layer 1 — Python (clean method below):
        Queries existing bookings and raises ValidationError if overlap found.
        Runs before any database write via full_clean() in views.py.

    Layer 2 — Database (UniqueConstraint in Meta):
        PostgreSQL enforces UNIQUE(barber_id, date, start_time).
        Even if a Python bug bypasses layer 1, the database will
        reject a conflicting INSERT with an IntegrityError.

    END TIME CALCULATION — BUG FIX EXPLANATION
    -------------------------------------------
    end_time cannot be set by the user — it is calculated automatically
    from start_time + service.duration_mins. The original bug was that
    Django's full_clean() ran validate_unique() before save() had a
    chance to calculate end_time, causing a "null field" error.

    Fix: _calculate_end_time() is extracted into its own method and
    called at the START of clean() so end_time exists before any
    validation runs. It is also called in save() to ensure it is
    always recalculated on every write.

    STATUS FLOW
    -----------
        pending → confirmed → completed
                           ↘ cancelled
    """

    # ── Status constants — use these instead of raw strings to avoid typos ──
    STATUS_PENDING   = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    # ── FOREIGN KEYS ──────────────────────────────────────────────────────────
    # ForeignKey generates an INTEGER column with a FOREIGN KEY constraint.
    # Django automatically names the column customer_id, barber_id, service_id.
    # related_name allows reverse access: user.bookings.all()

    # CASCADE: deleting a user deletes all their bookings
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    # CASCADE: deleting a barber deletes all their bookings
    barber = models.ForeignKey(
        'Barber',
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    # PROTECT: prevents deleting a service that bookings reference
    # Use is_active=False to retire a service instead of deleting it
    service = models.ForeignKey(
        'Service',
        on_delete=models.PROTECT,
        related_name='bookings'
    )

    # ── BOOKING FIELDS ────────────────────────────────────────────────────────
    date       = models.DateField()    # DATE column — e.g. 2025-06-10
    start_time = models.TimeField()    # TIME column — e.g. 10:30:00

    # null=True, blank=True: allows end_time to be empty initially.
    # It is always populated by _calculate_end_time() in clean() and save()
    # before any data reaches the database. Made nullable to fix the bug
    # where full_clean() ran before save() had calculated the value.
    end_time = models.TimeField(null=True, blank=True)

    # choices= restricts values to the STATUS_CHOICES list above
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CONFIRMED
    )

    notes      = models.TextField(blank=True)  # optional customer requests

    # unique=True adds UNIQUE constraint — no two bookings share the same ref
    # editable=False hides from admin/forms — only set programmatically in save()
    ref = models.CharField(max_length=12, unique=True, editable=False)

    # auto_now_add: set on INSERT only — records when booking was first created
    # auto_now: updated on every save — records last modification time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Default query order — most recent bookings first
        ordering = ['-date', '-start_time']

        constraints = [
            # Database-level double-booking prevention (Layer 2)
            # PostgreSQL will reject any INSERT where the same barber has
            # an existing booking with the same date AND start_time.
            # This is a safety net — Python validation (Layer 1) runs first.
            models.UniqueConstraint(
                fields=['barber', 'date', 'start_time'],
                name='unique_barber_slot'
            )
        ]

    # ── PRIVATE HELPER ────────────────────────────────────────────────────────
    def _calculate_end_time(self):
        """
        Calculates and sets end_time from start_time + service duration.

        Extracted into its own method (DRY principle) so both clean()
        and save() can call it without duplicating the logic.

        Uses datetime.combine() to merge the date and start_time into a
        single datetime object, then adds a timedelta of duration_mins
        minutes. The resulting datetime's .time() component is the end_time.

        Only runs if start_time and service_id are both present —
        guards against being called on a partially-filled object.
        """
        if self.start_time and self.service_id:
            start_dt = datetime.combine(
                # Use today's date as a placeholder if date not yet set —
                # only the time component of the result is used
                self.date or datetime.today().date(),
                self.start_time
            )
            # Add the service duration as a timedelta in minutes
            end_dt = start_dt + timedelta(minutes=self.service.duration_mins)
            self.end_time = end_dt.time()

    # ── SAVE ──────────────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        """
        Overrides Django's default save() to:
        1. Auto-generate a unique booking reference on first save
        2. Recalculate end_time before every database write

        super().save() calls Django's original save() to do the
        actual INSERT or UPDATE SQL. Always call it last.
        """
        # Only generate ref on creation (not on updates)
        # uuid4() generates a random UUID, .hex strips hyphens,
        # [:8] takes the first 8 characters, .upper() capitalises them
        # Result: e.g. 'SC3F7A9B2E'
        if not self.ref:
            self.ref = 'SC' + uuid.uuid4().hex[:8].upper()

        # Always recalculate end_time before saving to keep it in sync
        # with any changes to start_time or service
        self._calculate_end_time()

        # Call Django's original save() to write to the database
        super().save(*args, **kwargs)

    # ── VALIDATION ────────────────────────────────────────────────────────────
    def clean(self):
        """
        Business rule validation — runs before any database write via
        full_clean() which is called explicitly in views.py book_step4().

        Django's validation pipeline:
            clean_fields()    → validates each field individually
            clean()           → cross-field / business rule validation  ← here
            validate_unique() → checks UniqueConstraint

        Raising ValidationError at any stage prevents the save() call.
        The error message is returned to the view and shown to the user.

        NOTE: _calculate_end_time() is called first so end_time is
        populated before validate_unique() checks it — this is the
        fix for the original "end_time cannot be null" bug.
        """
        # Import here to avoid circular import with the datetime module
        from datetime import time as dt_time

        # STEP 1: Calculate end_time before any validation runs
        # This fixes the bug — end_time must exist before validate_unique()
        self._calculate_end_time()

        # STEP 2: Weekdays only (Monday=0 through Sunday=6)
        # weekday() >= 5 catches Saturday (5) and Sunday (6)
        if self.date and self.date.weekday() >= 5:
            raise ValidationError("Bookings are only available Monday to Friday.")

        # STEP 3: Opening hours check — 8am to 8pm
        # Uses Python's comparison chaining: 8:00 <= start < 20:00
        if self.start_time and not (dt_time(8, 0) <= self.start_time < dt_time(20, 0)):
            raise ValidationError("Bookings must start between 8:00am and 8:00pm.")

        # STEP 4: Overlap check — query database for conflicts
        # Only runs if all required fields are present (guards against
        # partially-filled objects during admin form validation)
        if self.barber_id and self.date and self.start_time and self.end_time:
            # Interval overlap algorithm:
            # Two ranges [A_start, A_end] and [B_start, B_end] overlap if:
            # A_start < B_end AND A_end > B_start
            # Applied here: existing booking overlaps candidate slot if:
            # existing.start_time < candidate.end_time (starts before candidate ends)
            # existing.end_time > candidate.start_time (ends after candidate starts)
            conflicts = Booking.objects.filter(
                barber=self.barber,
                date=self.date,
                status__in=[self.STATUS_CONFIRMED, self.STATUS_PENDING],
                start_time__lt=self.end_time,    # existing starts before this ends
                end_time__gt=self.start_time,    # existing ends after this starts
            ).exclude(pk=self.pk)  # exclude self when editing an existing booking

            if conflicts.exists():
                raise ValidationError(
                    "This time slot is already booked for the selected barber."
                )

    # ── COMPUTED PROPERTY ─────────────────────────────────────────────────────
    @property
    def is_past(self):
        """
        Returns True if the booking's date and time have already passed.

        @property decorator makes this callable as booking.is_past
        without needing parentheses — used in templates and views
        to determine if edit/cancel buttons should be shown.
        """
        import datetime as dt
        booking_dt = dt.datetime.combine(self.date, self.start_time)
        return booking_dt < datetime.now()

    def __str__(self):
        return (
            f"#{self.ref} — {self.customer.get_full_name()} "
            f"with {self.barber} on {self.date} at {self.start_time}"
        )


# ── CANCELLATION ──────────────────────────────────────────────────────────────
class Cancellation(models.Model):
    """
    Audit record created whenever a booking is cancelled.

    WHY A SEPARATE TABLE
    --------------------
    We use soft deletion — cancelled bookings are never removed from the
    database. Instead their status is set to 'cancelled' and this separate
    Cancellation record stores who cancelled it, when, and why.

    This preserves a complete audit trail for:
    - Dispute resolution (customer claims they didn't cancel)
    - Business analytics (which barber has most cancellations?)
    - Data integrity (historical records remain complete)

    WHO CAN CANCEL
    --------------
    Both customers and barbers can cancel (handled in views.py
    cancel_booking()). The cancelled_by FK records who did it.

    SET_NULL ON DELETE
    ------------------
    If the user who cancelled later has their account deleted,
    SET_NULL preserves the Cancellation record with cancelled_by=None
    rather than deleting the entire audit record.
    """

    # OneToOneField — one booking can only be cancelled once
    # CASCADE means deleting the booking also deletes its cancellation record
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='cancellation'
    )

    # ForeignKey — records which user initiated the cancellation
    # SET_NULL preserves the record if the user account is later deleted
    # null=True required when using SET_NULL
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cancellations'
    )

    reason       = models.TextField(blank=True)   # optional reason from the form
    cancelled_at = models.DateTimeField(auto_now_add=True)  # set automatically on creation

    def __str__(self):
        return f"Cancellation: #{self.booking.ref} by {self.cancelled_by}"
