# SPDX-License-Identifier: AGPL-3.0-or-later
"""The document template library: letters and notices filled in from PHAEMA's records, exported to Word."""
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

FORBIDDEN_TAGS = re.compile(r"{%\s*(load|include|extends|debug|ssi|csrf_token|url|static)\b")


class DocumentTemplate(TimeStampedModel):
    class Category(models.TextChoices):
        CONSENTS = "consents", _("Consents and licences")
        NOTICES_1954 = "notices_1954", _("Landlord and Tenant Act 1954 notices")
        LEGAL = "legal", _("Other notices and legal")
        LETTINGS = "lettings", _("Lettings and renewals")
        RENT = "rent", _("Rent and rent reviews")
        ARREARS = "arrears", _("Arrears and income")
        MANAGEMENT = "management", _("Lease management")
        VALUATION = "valuation", _("Asset valuation")
        GENERAL = "general", _("General")

    class Source(models.TextChoices):
        CASE = "case", _("A case")
        LEASE = "lease", _("An agreement")
        PROPERTY = "property", _("A property")
        VALUATION = "valuation", _("A valuation")

    code = models.SlugField(_("code"), max_length=60, unique=True)
    name = models.CharField(_("name"), max_length=150)
    category = models.CharField(_("category"), max_length=14, choices=Category.choices, default=Category.GENERAL)
    description = models.TextField(_("when to use it"), blank=True)
    source = models.CharField(_("created from"), max_length=10, choices=Source.choices, default=Source.CASE)
    case_types = models.JSONField(
        _("offered on these case types"), default=list, blank=True,
        help_text=_("Case type codes, for example [\"assignment\", \"underletting\"]. Leave empty to offer it on "
                    "every case."))
    extra_fields = models.JSONField(
        _("questions to ask"), default=list, blank=True,
        help_text=_("Extra details to ask for when the document is created, as a list of "
                    "{\"key\": \"conditions\", \"label\": \"Conditions\", \"long\": true}."))
    body = models.TextField(
        _("text"), help_text=_("Use {{ merge_field }} for details PHAEMA fills in. # Heading, ## Subheading, "
                               "**bold**, - bullet, 1. numbered, | table | row |, --- for a new page, "
                               "[[signature]] for the signature block. Text in [square brackets] is highlighted "
                               "in Word for completing."))
    prescribed_form = models.CharField(
        _("prescribed form"), max_length=200, blank=True,
        help_text=_("If the law prescribes a form, name it: PHAEMA then warns that the particulars must go on the "
                    "current prescribed form."))
    letterhead = models.BooleanField(_("council letterhead"), default=True)
    shipped = models.BooleanField(_("supplied with PHAEMA"), default=False, editable=False)
    active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["category", "order", "name"]
        verbose_name = _("document template")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("documents:template", args=[self.code])

    def clean(self):
        if FORBIDDEN_TAGS.search(self.body or ""):
            raise ValidationError({"body": _("Templates may use {{ fields }}, {% if %} and {% for %} only.")})
        from django.template import Engine, TemplateSyntaxError

        try:
            Engine(string_if_invalid="").from_string(self.body or "")
        except TemplateSyntaxError as exc:
            raise ValidationError({"body": _("The text has a mistake in its merge fields: %(e)s") % {"e": exc}})
        if not isinstance(self.extra_fields, list) or any(
                not isinstance(f, dict) or not f.get("key") for f in self.extra_fields):
            raise ValidationError({"extra_fields": _("Use a list of {\"key\": ..., \"label\": ...}.")})

    def offered_for(self, case):
        return not self.case_types or case.case_type.code in self.case_types
