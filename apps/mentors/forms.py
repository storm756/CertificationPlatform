from django import forms
from django.utils import timezone

from apps.accounts.forms import clean_person_name
from apps.batches.models import Batch, BatchStatus
from apps.batches.scoping import batches_for


class NewBatchForm(forms.Form):
    name = forms.CharField(max_length=120)
    centre = forms.CharField(max_length=120, required=False)
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    seat_limit = forms.IntegerField(min_value=1, max_value=1000, initial=40)

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "The end date is before the start date.")
        return data


class RegistrationSettingsForm(forms.Form):
    accepting = forms.BooleanField(required=False, label="Registration is open")
    opens_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
    )
    closes_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
    )
    seat_limit = forms.IntegerField(min_value=1, max_value=1000)

    def clean(self):
        data = super().clean()
        opens, closes = data.get("opens_at"), data.get("closes_at")
        if opens and closes and closes <= opens:
            self.add_error("closes_at", "Registration must close after it opens.")
        return data

    @classmethod
    def for_batch(cls, batch, *args):
        def local(value):
            return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M") if value else ""

        initial = {
            "accepting": batch.accepting,
            "opens_at": local(batch.opens_at),
            "closes_at": local(batch.closes_at),
            "seat_limit": batch.seat_limit,
        }
        return cls(*args, initial=initial)


class MoveLearnerForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=Batch.objects.none(), empty_label=None, label="Move to")

    def __init__(self, *args, mentor, current_batch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = (
            batches_for(mentor).filter(status=BatchStatus.ACTIVE).exclude(pk=current_batch.pk)
        )


class CertificateNameForm(forms.Form):
    certificate_name = forms.CharField(max_length=120, label="Certificate name")

    def clean_certificate_name(self):
        return clean_person_name(self.cleaned_data["certificate_name"])
