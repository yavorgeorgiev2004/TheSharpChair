"""
bookings/forms.py
=================
All form classes for The Sharp Chair application.

HOW DJANGO FORMS WORK
---------------------
A form class does two things:
  1. Renders HTML input fields (label, input, error messages)
  2. Validates submitted data before it reaches the database

VALIDATION PIPELINE
-------------------
When form.is_valid() is called, Django runs these stages in order:
  1. field.clean()          → converts raw input to Python type
                              (e.g. '2025-06-10' → date(2025, 6, 10))
  2. clean_<fieldname>()   → custom per-field validation method
                              (auto-called if method exists)
  3. form.clean()          → cross-field validation
                              (access multiple fields at once)

If any stage raises ValidationError, the pipeline stops, the error
is attached to the form, and is_valid() returns False. The database
is never touched until ALL stages pass.

FORM TYPES USED
---------------
  forms.Form      → generic form, not tied to a model
                    Used for wizard steps and cancellation
  forms.ModelForm → tied to a specific model, can save() directly
                    Used for EditBookingForm

FORMS IN THIS FILE
------------------
  RegisterForm       → new user registration (extends UserCreationForm)
  BookingStep1Form   → service selection (radio buttons)
  BookingStep2Form   → barber selection (radio buttons)
  BookingStep3Form   → date and time selection
  BookingStep4Form   → personal details (name, email, phone, notes)
  EditBookingForm    → edit existing booking (ModelForm)
  CancellationForm   → optional reason when cancelling
"""

from datetime import date, time, datetime, timedelta

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm   # handles password hashing

from .models import Booking, UserProfile, Service, Barber


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION FORMS
# ═════════════════════════════════════════════════════════════════════════════

class RegisterForm(UserCreationForm):
    """
    Registration form for new customers.

    INHERITANCE
    -----------
    Extends Django's built-in UserCreationForm which provides:
    - username field
    - password1 field (with strength requirements)
    - password2 field (confirmation — must match password1)
    - Password hashing on save()

    We add first_name, last_name, email, and phone on top.

    SAVING
    ------
    The overridden save() method:
    1. Creates the User record (via super().save())
    2. Immediately creates a linked UserProfile with the phone number
    A user and their profile are always created together atomically.
    """

    # Extra fields not in UserCreationForm — added to the form
    first_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'James'})
    )
    last_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Anderson'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'james@example.com'})
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': '+44 7700 900000'})
    )

    class Meta:
        # model = User tells Django this form creates User instances
        model  = User
        # fields controls the order fields appear in the rendered form
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Choose a username'}),
        }

    def clean_email(self):
        """
        Custom email validation — Django calls this automatically because
        the method name follows the clean_<fieldname>() convention.

        Checks the database for an existing user with this email address.
        Raises ValidationError if found — prevents duplicate accounts.
        Must return the cleaned value even if no error is raised.
        """
        email = self.cleaned_data.get('email')

        # Database query — check for existing user with this email
        # .exists() is efficient — returns True/False without fetching rows
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")

        # Always return the cleaned value from a clean_<field> method
        return email

    def save(self, commit=True):
        """
        Overrides UserCreationForm.save() to also create UserProfile.

        commit=False pattern:
            super().save(commit=False) builds the User object in memory
            without running the INSERT SQL yet. This allows us to set
            additional fields before saving.

        Then we call user.save() and UserProfile.objects.create() in
        sequence — both records are created in the same request.
        """
        # Build User object in memory — does NOT hit the database yet
        user = super().save(commit=False)
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']

        if commit:
            user.save()  # INSERT INTO auth_user — writes to database

            # Create linked profile immediately after user exists
            # Must be after user.save() because UserProfile needs user.id
            UserProfile.objects.create(
                user=user,
                phone=self.cleaned_data['phone']
            )

        return user


# ═════════════════════════════════════════════════════════════════════════════
# BOOKING WIZARD FORMS — one per step
# ═════════════════════════════════════════════════════════════════════════════

class BookingStep1Form(forms.Form):
    """
    Step 1 — Service selection.

    ModelChoiceField renders a queryset as form options.
    widget=RadioSelect changes the default dropdown to radio buttons
    so each service can be displayed as a clickable card in the template.
    empty_label=None removes the '--------' default empty option.
    """
    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True),  # only show active services
        widget=forms.RadioSelect,
        empty_label=None,
    )


class BookingStep2Form(forms.Form):
    """
    Step 2 — Barber selection.

    select_related('user') on the queryset pre-fetches each barber's
    linked User record so displaying barber.user.get_full_name() in
    the template doesn't trigger a separate query per barber.
    """
    barber = forms.ModelChoiceField(
        queryset=Barber.objects.filter(is_available=True).select_related('user'),
        widget=forms.RadioSelect,
        empty_label=None,
    )


class BookingStep3Form(forms.Form):
    """
    Step 3 — Date and time selection.

    CONTEXT-AWARE VALIDATION
    ------------------------
    The form receives barber and service in __init__ so the clean()
    method can access them for slot validation. These are passed from
    the view when instantiating the form.

    START TIME FIELD
    ----------------
    start_time uses HiddenInput — the visible time slot buttons in the
    template are styled divs, not a real select. When clicked, they
    populate this hidden field with the selected time value.
    required=False here because validation of start_time is handled
    in clean() after checking both date and time together.
    """

    date = forms.DateField(
        # type='date' renders a native browser date picker
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    start_time = forms.TimeField(
        widget=forms.HiddenInput(),  # populated by JavaScript when a slot is clicked
        required=False,
    )

    def __init__(self, *args, barber=None, service=None, **kwargs):
        """
        Custom __init__ stores barber and service on the form instance
        so they can be used in clean() for validation context.
        **kwargs passes any remaining arguments to the parent __init__.
        """
        super().__init__(*args, **kwargs)
        self.barber  = barber
        self.service = service

    def clean_date(self):
        """
        Validates the selected date.
        - Rejects past dates
        - Rejects weekends (shop closed Saturday and Sunday)
        Returns the cleaned date object for use in clean().
        """
        chosen = self.cleaned_data.get('date')
        if not chosen:
            return chosen  # required=True handles the empty case

        # Reject past dates — cannot book an appointment that has already passed
        if chosen < date.today():
            raise forms.ValidationError("Please choose a future date.")

        # weekday() returns 0 (Monday) through 6 (Sunday)
        # >= 5 catches Saturday (5) and Sunday (6)
        if chosen.weekday() >= 5:
            raise forms.ValidationError(
                "We are closed on weekends. Please pick Monday–Friday."
            )

        return chosen

    def clean(self):
        """
        Cross-field validation — runs after all individual field validations.
        super().clean() returns the cleaned_data dictionary with all
        field values that passed their individual validation.
        Checks that a time slot was actually selected.
        """
        cleaned    = super().clean()
        chosen_date = cleaned.get('date')
        start_time  = cleaned.get('start_time')

        # Only check if date passed validation (could be None if date invalid)
        if chosen_date and not start_time:
            raise forms.ValidationError("Please select a time slot.")

        return cleaned


class BookingStep4Form(forms.Form):
    """
    Step 4 — Personal details (name, email, phone, notes).

    This is a plain Form (not ModelForm) because the data is used in
    the view to set fields on the Booking object, not saved directly
    from the form. The notes field is the only one stored on Booking.
    Name, email, and phone are for confirmation purposes.

    Fields are pre-filled with the logged-in user's existing data
    via the initial= parameter passed from the view.
    """

    first_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'James'})
    )
    last_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Anderson'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'james@example.com'})
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'placeholder': '+44 7700 900000'})
    )
    notes = forms.CharField(
        required=False,  # optional — customer may leave blank
        widget=forms.Textarea(attrs={
            'placeholder': 'Any special requests or preferences...',
            'rows': 3
        })
    )


# ═════════════════════════════════════════════════════════════════════════════
# EDIT AND CANCEL FORMS
# ═════════════════════════════════════════════════════════════════════════════

class EditBookingForm(forms.ModelForm):
    """
    Form for editing an existing booking's date, time, and notes.

    MODELFORM PATTERN
    -----------------
    ModelForm is tied directly to the Booking model. Passing instance=booking
    in the view pre-populates all fields with the existing record's values.
    Calling form.save() on a valid submission generates an UPDATE SQL
    statement automatically.

    DATE FIELD OVERRIDE
    -------------------
    The date field is overridden to use type='date' input for a native
    date picker, rather than the default text input ModelForm would provide.

    START TIME AS CHOICES
    ---------------------
    start_time is overridden to a ChoiceField populated by _time_choices()
    which generates options for every 30-minute slot in the day.
    The choices are strings (HH:MM:SS) that views.py parses back to
    time objects after the form is validated.
    """

    # Override the default date field to use a native browser date picker
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model  = Booking
        fields = ['date', 'start_time', 'notes']
        widgets = {
            'start_time': forms.Select(),    # rendered as a dropdown
            'notes':      forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        """
        Override __init__ to replace the default TimeField with a
        ChoiceField containing all valid 30-minute slots.
        Called when the form is instantiated in edit_booking() view.
        """
        super().__init__(*args, **kwargs)
        # Replace the TimeField widget with a Select dropdown of time choices
        self.fields['start_time'] = forms.ChoiceField(
            choices=self._time_choices()
        )

    def _time_choices(self):
        """
        Generates a list of (value, label) tuples for every 30-minute
        slot between 8am and 8pm.

        Value: 'HH:MM:SS' string (used when parsing in view)
        Label: 'HH:MM' string (displayed to the user)

        Returns list of tuples e.g.:
            [('08:00:00', '08:00'), ('08:30:00', '08:30'), ...]
        """
        choices = []
        current = datetime.combine(date.today(), time(8, 0))
        end     = datetime.combine(date.today(), time(20, 0))

        while current < end:
            t = current.time()
            choices.append((
                t.strftime('%H:%M:%S'),  # value — parsed back in view
                t.strftime('%H:%M')      # label — shown to user
            ))
            current += timedelta(minutes=30)

        return choices

    def clean_date(self):
        """
        Validates the new date:
        - Rejects weekends
        - Rejects past dates
        """
        chosen = self.cleaned_data.get('date')

        if chosen and chosen.weekday() >= 5:
            raise forms.ValidationError("We are closed on weekends.")

        if chosen and chosen < date.today():
            raise forms.ValidationError("Please choose a future date.")

        return chosen


class CancellationForm(forms.Form):
    """
    Simple form with an optional reason field shown on the cancellation page.

    required=False means the user can submit without providing a reason.
    The reason is stored in the Cancellation audit record in views.py.
    """

    reason = forms.CharField(
        required=False,  # cancellation reason is always optional
        widget=forms.Textarea(attrs={
            'placeholder': 'Optional: let us know why you are cancelling...',
            'rows': 3
        })
    )
