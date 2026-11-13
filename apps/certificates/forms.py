from django import forms
from django.utils.translation import gettext_lazy as _

from .codes import normalise_code


class VerifyCodeForm(forms.Form):
    code = forms.CharField(
        label=_("Verification code"),
        max_length=40,
        help_text=_("The 10 letters and digits printed under the QR code."),
        widget=forms.TextInput(
            attrs={"autocomplete": "off", "autocapitalize": "characters", "spellcheck": "false"}
        ),
    )

    def clean_code(self):
        code = normalise_code(self.cleaned_data["code"])
        if code is None:
            raise forms.ValidationError(
                _("That is not a verification code. It has 10 letters and digits.")
            )
        return code
