# SPDX-License-Identifier: AGPL-3.0-or-later
"""Property register (terrier) and title records."""
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

uprn_validator = RegexValidator(r"^\d{1,12}$", _("A UPRN is a number of up to 12 digits."))
usrn_validator = RegexValidator(r"^\d{1,8}$", _("A USRN is a number of up to 8 digits."))
postcode_validator = RegexValidator(
    r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$", _("Enter a valid UK postcode.")
)
title_number_validator = RegexValidator(
    r"^[A-Z]{1,3}\d{1,7}$", _("HM Land Registry title numbers are 1-3 letters followed by digits, e.g. ON123456.")
)


class Property(TimeStampedModel):
    """Any holding in the register: an estate, site, building, lettable unit or land parcel.

    Records form a hierarchy through ``parent``: estate > site > building > unit.
    Geometry is stored in British National Grid (EPSG:27700).
    """

    class PropertyType(models.TextChoices):
        ESTATE = "estate", _("Estate")
        SITE = "site", _("Site")
        BUILDING = "building", _("Building")
        UNIT = "unit", _("Lettable unit")
        LAND = "land", _("Land parcel")

    class HoldingPurpose(models.TextChoices):
        OPERATIONAL = "operational", _("Operational")
        INVESTMENT = "investment", _("Investment")
        COMMUNITY = "community", _("Community")
        SURPLUS = "surplus", _("Surplus")
        HELD_FOR_SALE = "held_for_sale", _("Held for disposal")

    class Tenure(models.TextChoices):
        FREEHOLD = "freehold", _("Freehold")
        LEASEHOLD = "leasehold", _("Leasehold")
        OTHER = "other", _("Other")
        NONE = "none", _("None (managed, not owned)")

    class Occupation(models.TextChoices):
        COUNCIL = "council", _("Occupied by the council")
        LET = "let", _("Let to a third party")
        PART_LET = "part_let", _("Partly let")
        VACANT = "vacant", _("Vacant")
        NOT_APPLICABLE = "na", _("Not applicable")

    reference = models.CharField(
        _("asset reference"), max_length=30, unique=True,
        help_text=_("The council's own unique asset ID."),
    )
    name = models.CharField(_("name"), max_length=200)
    property_type = models.CharField(_("type"), max_length=20, choices=PropertyType.choices)
    parent = models.ForeignKey(
        "self", verbose_name=_("part of"), null=True, blank=True,
        on_delete=models.PROTECT, related_name="children",
    )

    # Identifiers
    uprn = models.CharField(_("UPRN"), max_length=12, blank=True, validators=[uprn_validator], db_index=True)
    usrn = models.CharField(_("USRN"), max_length=8, blank=True, validators=[usrn_validator])

    # Address
    address_line_1 = models.CharField(_("address line 1"), max_length=200, blank=True)
    address_line_2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    town = models.CharField(_("town or city"), max_length=100, blank=True)
    postcode = models.CharField(_("postcode"), max_length=10, blank=True, validators=[postcode_validator])

    # Classification
    holding_purpose = models.CharField(
        _("holding purpose"), max_length=20, choices=HoldingPurpose.choices, blank=True
    )
    tenure = models.CharField(_("tenure"), max_length=20, choices=Tenure.choices, blank=True)
    occupation = models.CharField(
        _("occupation status"), max_length=20, choices=Occupation.choices, blank=True
    )
    use_description = models.CharField(
        _("use"), max_length=100, blank=True, help_text=_("e.g. Retail, Office, Industrial, Car park")
    )
    use_class = models.CharField(_("planning use class"), max_length=20, blank=True, help_text=_("e.g. E(a), B2, B8"))

    # Areas (RICS measurement)
    gia_sqm = models.DecimalField(
        _("gross internal area (m²)"), max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    nia_sqm = models.DecimalField(
        _("net internal area (m²)"), max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    site_area_ha = models.DecimalField(
        _("site area (hectares)"), max_digits=12, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )

    # Location (British National Grid)
    easting = models.PositiveIntegerField(_("easting"), null=True, blank=True)
    northing = models.PositiveIntegerField(_("northing"), null=True, blank=True)
    boundary = models.MultiPolygonField(_("boundary"), srid=27700, null=True, blank=True)

    # Publication
    exclude_from_publication = models.BooleanField(
        _("exclude from open data"), default=False,
        help_text=_("Tick for sensitive assets (e.g. refuges) that must not appear in the Transparency Code register."),
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["reference"]
        verbose_name = _("property")
        verbose_name_plural = _("properties")

    def __str__(self):
        return f"{self.reference} {self.name}"

    def get_absolute_url(self):
        return reverse("properties:detail", args=[self.pk])

    @property
    def address(self):
        parts = [self.address_line_1, self.address_line_2, self.town, self.postcode]
        return ", ".join(p for p in parts if p)

    def clean_fields(self, exclude=None):
        # Normalise before validation so "ox49 5aa " is accepted as "OX49 5AA".
        if self.postcode:
            self.postcode = " ".join(self.postcode.upper().split())
        self.uprn = (self.uprn or "").strip()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.parent_id:
            # Prevent a property being its own ancestor.
            node, seen = self.parent, set()
            while node is not None:
                if node.pk == self.pk or node.pk in seen:
                    raise ValidationError({"parent": _("A property cannot be part of itself.")})
                seen.add(node.pk)
                node = node.parent
        if (self.easting is None) != (self.northing is None):
            raise ValidationError(_("Enter both easting and northing, or neither."))

    def save(self, *args, **kwargs):
        # Derive easting/northing from the boundary centre when not entered.
        if self.boundary and self.easting is None and self.northing is None:
            centre = self.boundary.point_on_surface
            self.easting, self.northing = round(centre.x), round(centre.y)
        super().save(*args, **kwargs)

    def ancestors(self):
        chain, node = [], self.parent
        while node is not None:
            chain.insert(0, node)
            node = node.parent
        return chain


class Title(TimeStampedModel):
    """A registered (or unregistered) title held by the council."""

    class Tenure(models.TextChoices):
        FREEHOLD = "freehold", _("Freehold")
        LEASEHOLD = "leasehold", _("Leasehold")

    class TitleClass(models.TextChoices):
        ABSOLUTE = "absolute", _("Absolute")
        GOOD_LEASEHOLD = "good_leasehold", _("Good leasehold")
        POSSESSORY = "possessory", _("Possessory")
        QUALIFIED = "qualified", _("Qualified")
        UNREGISTERED = "unregistered", _("Unregistered")

    title_number = models.CharField(
        _("title number"), max_length=12, unique=True, null=True, blank=True,
        validators=[title_number_validator],
        help_text=_("Leave blank for unregistered land."),
    )
    tenure = models.CharField(_("tenure"), max_length=20, choices=Tenure.choices)
    title_class = models.CharField(_("class of title"), max_length=20, choices=TitleClass.choices, blank=True)
    properties = models.ManyToManyField(Property, related_name="titles", blank=True, verbose_name=_("properties"))
    deeds_location = models.CharField(
        _("deeds location"), max_length=200, blank=True,
        help_text=_("Where the original deeds are kept, e.g. Legal strongroom, packet 123."),
    )
    restrictions_and_covenants = models.TextField(_("restrictions, covenants and rights"), blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["title_number"]
        verbose_name = _("title")
        verbose_name_plural = _("titles")

    def __str__(self):
        return self.title_number or f"Unregistered title {self.pk}"

    def clean_fields(self, exclude=None):
        if self.title_number:
            self.title_number = self.title_number.upper().replace(" ", "")
        else:
            self.title_number = None  # keeps uniqueness working for unregistered titles
        super().clean_fields(exclude=exclude)
