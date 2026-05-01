"""
bookings/admin.py
=================
Configures Django's automatically generated admin panel for all models.

HOW THE ADMIN PANEL WORKS
--------------------------
Django generates a full management interface from your model definitions
automatically. Registering a model here with @admin.register makes it
appear in the panel at /admin/.

Each ModelAdmin class customises how that model is displayed:
  list_display   → which columns appear in the list view
  list_filter    → sidebar filter options
  search_fields  → which fields the search box queries
  list_editable  → fields editable inline in the list
  (no need to open each record)
  readonly_fields → shown but not editable (for auto-generated values)
  date_hierarchy → clickable date navigation bar at the top

DOUBLE UNDERSCORE IN SEARCH FIELDS
-----------------------------------
search_fields = ['customer__email'] uses Django's ORM notation to
traverse foreign key relationships. This searches the email column
on the related auth_user table without writing any SQL manually:
    customer__email = search through customer FK → then email column
    customer__first_name = search through customer FK → then first_name

HOW BARBER ACCOUNTS ARE CREATED
--------------------------------
1. /admin → Users → Add User → fill in username, password, first/last name
2. /admin → Barbers → Add Barber → select that user,
add speciality, tick is_available
The user can now log in at /login/ and see the barber schedule.

ACCESSING THE ADMIN PANEL
--------------------------
URL:      /admin/
Login:    The superuser account created with: python manage.py createsuperuser
On Heroku: heroku run python manage.py createsuperuser --app your-app-name
"""

from django.contrib import admin
from .models import UserProfile, Service, Barber, Booking, Cancellation


# ── USER PROFILE ADMIN ───────────────────────
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin configuration for UserProfile model.
    Profiles are created automatically when a user registers —
    they should not normally need to be created manually here.
    """

    # Columns shown in the list view (/admin/bookings/userprofile/)
    list_display = ['user', 'phone', 'created_at']

    # Search box queries first_name, last_name, and email on the related User
    # The __ notation traverses the OneToOneField to auth_user
    search_fields = ['user__first_name', 'user__last_name', 'user__email']


# ── SERVICE ADMIN ─────────────────
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """
    Admin configuration for Service model.

    COMMON TASKS:
    - Add new service: Add Service button,
    fill in name/description/price/duration
    - Retire a service: set is_active=False — hides from booking wizard
      without deleting (cannot delete services that bookings reference)
    - Update price: edit directly in the list via list_editable
    """

    # Columns shown in the changelist
    list_display = ['name', 'price', 'duration_mins', 'is_active']

    # list_editable allows editing price and is_active directly
    # in the list view
    # without opening each individual service record
    list_editable = ['is_active', 'price']

    # Filter sidebar — click 'Yes' or 'No' to filter by active/inactive
    list_filter = ['is_active']


# ── BARBER ADMIN ───────────────────
@admin.register(Barber)
class BarberAdmin(admin.ModelAdmin):
    """
    Admin configuration for Barber model.

    CREATING A BARBER ACCOUNT
    -------------------------
    Step 1: /admin → Users → Add User
            Fill in: username, password, first name, last name, email
    Step 2: /admin → Barbers → Add Barber
            Select the user, fill in speciality, tick is_available

    The user can now log in and will see 'My Schedule' in the nav
    instead of 'My Bookings'.

    TAKING A BARBER OFFLINE
    -----------------------
    Set is_available=False here — they disappear from the booking wizard
    immediately. Existing bookings are not affected.
    """

    list_display = ['__str__', 'speciality', 'is_available']

    # Edit is_available directly in the list — quick toggle for absent barbers
    list_editable = ['is_available']

    list_filter = ['is_available']


# ── BOOKING ADMIN ────────────────────
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """
    Admin configuration for Booking — the most important model to manage.

    COMMON TASKS:
    - View all bookings: /admin → Bookings
    - Find a booking:   use search box (ref or customer email)
    - Filter by status: use sidebar (pending/confirmed/cancelled/completed)
    - Change status:    edit status column directly in the list
    - Mark completed:   change status to 'Completed' after appointment

    DATE HIERARCHY
    --------------
    date_hierarchy adds a clickable breadcrumb at the top:
        2025 → June → 10
    Lets you quickly navigate to a specific day's bookings.

    READONLY FIELDS
    ---------------
    ref, created_at, updated_at are auto-generated — making them
    readonly prevents accidental overwriting of the booking reference
    or timestamps.
    """

    # Columns in the changelist — most useful info at a glance
    list_display = [
        'ref', 'customer', 'barber', 'service', 'date', 'start_time', 'status'
        ]

    # Sidebar filters — click to narrow the list
    list_filter = ['status', 'date', 'barber']

    # Search box — queries across these fields
    # customer__first_name traverses FK: booking.customer → user.first_name
    # customer__email traverses FK: booking.customer → user.email
    search_fields = [
        'ref', 'customer__first_name', 'customer__last_name', 'customer__email'
        ]

    # Editable in list view — change booking status without opening each record
    list_editable = ['status']

    # Auto-generated fields — shown in detail view but not editable
    readonly_fields = ['ref', 'created_at', 'updated_at']

    # Clickable date navigation: 2025 → June → 10
    date_hierarchy = 'date'


# ── CANCELLATION ADMIN ────────────────────
@admin.register(Cancellation)
class CancellationAdmin(admin.ModelAdmin):
    """
    Admin configuration for Cancellation — the audit table.

    Cancellation records are created automatically by cancel_booking()
    in views.py — they should never be created manually here.
    This admin config is primarily for viewing the audit trail.

    cancelled_at is readonly because it is set by auto_now_add=True
    and cannot be changed after creation.
    """

    # Show who cancelled what and when
    list_display = ['booking', 'cancelled_by', 'cancelled_at']

    # Timestamp is auto-set and should never be edited
    readonly_fields = ['cancelled_at']
