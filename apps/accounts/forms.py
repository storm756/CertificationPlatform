import re
from datetime import date

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from apps.batches.models import Batch, BatchStatus
from apps.batches.rules import accepting_batches

from .models import Language, normalise_email
from .rules import AGE_GUARDIAN, AGE_REFUSE, MIN_AGE, age_band

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f<>]")


def clean_person_name(value: str) -> str:
    value = " ".join(value.split())
    if len(value) < 2 or _CONTROL_CHARS.search(value):
        raise forms.ValidationError("Please enter a valid name.")
    return value


class RegistrationForm(forms.Form):
    certificate_name = forms.CharField(
        max_length=120,
        label="Full name for your certificate",
        help_text="This exact name will be printed on your certificate. Check the spelling now.",
    )
    email = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    preferred_language = forms.ChoiceField(choices=Language.choices, label="Language")
    date_of_birth = forms.DateField(
        label="Date of birth", widget=forms.DateInput(attrs={"type": "date"})
    )
    # Validated against every active batch so that "closed meanwhile" reaches the server-side
    # re-check (which gives the proper message). The dropdown only lists open batches.
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(status=BatchStatus.ACTIVE), label="Batch", empty_label=None
    )
    guardian_name = forms.CharField(max_length=120, required=False, label="Guardian's full name")
    guardian_email = forms.EmailField(required=False, label="Guardian's email")
    accept_privacy = forms.BooleanField(
        required=True, label="I have read and accept the privacy notice."
    )

    def __init__(self, *args, now=None, **kwargs):
        super().__init__(*args, **kwargs)
        now = now or timezone.now()
        self.fields["batch"].choices = [(b.pk, str(b)) for b in accepting_batches(now)]

    def keep_posted_batch_choice(self):
        """After a refusal, keep the chosen (now closed) batch visible so the input is kept."""
        batch = self.cleaned_data.get("batch")
        if batch and str(batch.pk) not in {str(pk) for pk, _ in self.fields["batch"].choices}:
            self.fields["batch"].choices = [
                *self.fields["batch"].choices,
                (batch.pk, f"{batch} (closed)"),
            ]

    def clean_certificate_name(self):
        return clean_person_name(self.cleaned_data["certificate_name"])

    def clean_guardian_name(self):
        value = self.cleaned_data["guardian_name"]
        return clean_person_name(value) if value.strip() else ""

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        today = timezone.localdate()
        if dob > today or dob < date(today.year - 100, 1, 1):
            raise forms.ValidationError("Please check the date of birth.")
        if age_band(dob, today) == AGE_REFUSE:
            raise forms.ValidationError(f"You must be {MIN_AGE} or older to join.")
        return dob

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        data = super().clean()
        dob = data.get("date_of_birth")
        if dob and age_band(dob, timezone.localdate()) == AGE_GUARDIAN:
            for field in ("guardian_name", "guardian_email"):
                if not data.get(field):
                    self.add_error(field, "A guardian is needed if you are 16 or 17.")
            email, guardian = data.get("email"), data.get("guardian_email")
            if email and guardian and normalise_email(email) == normalise_email(guardian):
                self.add_error("guardian_email", "Your guardian needs their own email address.")
        return data


class GuardianConfirmForm(forms.Form):
    guardian_name = forms.CharField(max_length=120, label="Your full name")
    declaration = forms.BooleanField(
        label="I declare that I am the parent or legal guardian of this learner and I consent "
        "to the collection and use of their data as described above."
    )

    def clean_guardian_name(self):
        return clean_person_name(self.cleaned_data["guardian_name"])
