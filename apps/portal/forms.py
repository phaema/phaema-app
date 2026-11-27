# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ContactChange


class EmailForm(forms.Form):
    email = forms.EmailField(label=_("Email address"), max_length=254)


class CodeForm(forms.Form):
    code = forms.RegexField(label=_("Sign-in code"), regex=r"^\s*\d{6}\s*$", max_length=12,
                            error_messages={"invalid": _("Enter the 6-digit code from the email.")})


class ContactChangeForm(forms.ModelForm):
    class Meta:
        model = ContactChange
        fields = ["contact_name", "email", "phone", "address", "note"]
        widgets = {"address": forms.Textarea(attrs={"rows": 4}), "note": forms.Textarea(attrs={"rows": 3})}
