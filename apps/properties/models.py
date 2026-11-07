# SPDX-License-Identifier: AGPL-3.0-or-later
"""Property register (terrier) and title records."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.files import process_image, validate_image, validate_pdf
from apps.core.models import TimeStampedModel

uprn_validator = RegexValidator(r"^\d{1,12}$", _("A UPRN is a number of up to 12 digits."))
usrn_validator = RegexValidator(r"^\d{1,8}$", _("A USRN is a number of up to 8 digits."))
postcode_validator = RegexValidator(
    r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$", _("Enter a valid UK postcode.")
)
title_number_validator = RegexValidator(
    r"^[A-Z]{1,3}\d{1,7}$", _("HM Land Registry title numbers are 1-3 letters followed by digits, e.g. ON123456.")
)


class Portfolio(models.Model):
    """The service or portfolio a property belongs to, such as Investment, Leisure or Adult Social Care.
    Each council keeps its own list under Manage data, Portfolios."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    description = models.CharField(_("description"), max_length=250, blank=True,
                                   help_text=_("What belongs in this portfolio, as a guide for people choosing it."))
    active = models.BooleanField(_("in use"), default=True,
                                 help_text=_("Untick to stop it being offered for new properties; properties already "
                                             "in it keep it."))
    order = models.PositiveSmallIntegerField(_("order"), default=100, help_text=_("Lower numbers come first in lists."))

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("portfolio")
        verbose_name_plural = _("portfolios")

    def __str__(self):
        return self.name


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
    portfolio = models.ForeignKey(
        Portfolio, verbose_name=_("portfolio"), null=True, blank=True, on_delete=models.PROTECT,
        related_name="properties", help_text=_("The service or portfolio the property belongs to."),
    )
    tenure = models.CharField(_("tenure"), max_length=20, choices=Tenure.choices, blank=True)
    occupation = models.CharField(
        _("occupation status"), max_length=20, choices=Occupation.choices, blank=True
    )
    use_description = models.CharField(
        _("use"), max_length=100, blank=True, help_text=_("e.g. Retail, Office, Industrial, Car park")
    )
    use_class = models.CharField(_("planning use class"), max_length=20, blank=True, help_text=_("e.g. E(a), B2, B8"))
    managing_surveyor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("managing surveyor"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="managed_properties",
        help_text=_("The officer responsible for managing this property."),
    )

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
    gea_sqm = models.DecimalField(
        _("gross external area (m²)"), max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )

    class AreaStandard(models.TextChoices):
        COMP6 = "comp6", _("RICS Code of Measuring Practice, 6th edition")
        IPMS = "ipms", _("IPMS: All Buildings")
        OTHER = "other", _("Other")

    class AreaSource(models.TextChoices):
        SURVEY = "survey", _("Measured survey")
        DRAWINGS = "drawings", _("Taken from drawings")
        PLAN = "plan", _("Lease or title plan")
        ESTIMATE = "estimate", _("Estimate")

    area_standard = models.CharField(
        _("measured to"), max_length=10, choices=AreaStandard.choices, blank=True,
        help_text=_("The measurement standard the floor areas follow. RICS asks for the basis to be recorded."))
    area_source = models.CharField(_("source of areas"), max_length=10, choices=AreaSource.choices, blank=True)
    areas_measured_on = models.DateField(_("areas measured on"), null=True, blank=True)

    # Disposal: once sold or let on a long lease, the property leaves the active register and open data.
    disposed_on = models.DateField(_("disposed of on"), null=True, blank=True,
                                   help_text=_("Completion date of the sale or long lease."))
    disposal_price = models.DecimalField(_("disposal price (£)"), max_digits=14, decimal_places=2, null=True,
                                         blank=True)

    # Location (British National Grid)
    easting = models.PositiveIntegerField(_("easting"), null=True, blank=True)
    northing = models.PositiveIntegerField(_("northing"), null=True, blank=True)
    boundary = models.MultiPolygonField(_("boundary"), srid=27700, null=True, blank=True)
    boundary_source = models.CharField(
        _("boundary source"), max_length=255, blank=True,
        help_text=_("Where the boundary came from, e.g. HM Land Registry INSPIRE parcel 12345678, or drawn by hand."),
    )

    # Publication
    exclude_from_publication = models.BooleanField(
        _("exclude from open data"), default=False,
        help_text=_("Tick for sensitive assets (e.g. refuges) that must not appear in the Transparency Code register."),
    )
    site_hazards = models.TextField(
        _("hazards and safety notes for visits"), blank=True,
        help_text=_("For anyone visiting: access, lone working, dogs, unsafe areas, confined spaces. Shown on jobs, "
                    "cases and valuations for this property and its parts."))
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

    def descendants(self):
        """All parts below this property as (property, depth) pairs, in tree order."""
        everything = list(Property.objects.filter(pk__in=self._descendant_ids()).order_by("reference"))
        by_parent = {}
        for p in everything:
            by_parent.setdefault(p.parent_id, []).append(p)
        result = []

        def walk(node_id, depth):
            for child in by_parent.get(node_id, []):
                result.append((child, depth))
                walk(child.pk, depth + 1)

        walk(self.pk, 1)
        return result

    def _descendant_ids(self):
        ids, frontier = set(), [self.pk]
        while frontier:
            frontier = list(Property.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            ids.update(frontier)
        return ids

    def area_breakdown(self):
        """How this property's floor area is made up from its parts.

        Lettable parts are the lowest-level records (those with no parts of their own).
        Returns None when the property has no parts.
        """
        parts = self.descendants()
        if not parts:
            return None
        child_ids = {p.parent_id for p, _depth in parts}
        # Lettable parts: the lowest-level records, excluding things like estate roads
        # whose occupation is "not applicable".
        leaves = [p for p, _depth in parts
                  if p.pk not in child_ids and p.occupation != self.Occupation.NOT_APPLICABLE]
        zero = Decimal("0")
        leaf_nia = sum((p.nia_sqm or zero for p in leaves), zero)
        leaf_gia = sum((p.gia_sqm or zero for p in leaves), zero)
        if self.gia_sqm:
            gia, gia_source = self.gia_sqm, "recorded"
        else:
            buildings = [p for p, _d in parts if p.property_type == self.PropertyType.BUILDING and p.gia_sqm]
            gia = sum((b.gia_sqm for b in buildings), zero) or None
            gia_source = "buildings" if gia else None
        vacant = [p for p in leaves if p.occupation == self.Occupation.VACANT]
        return {
            "parts": parts,
            "leaf_ids": {p.pk for p in leaves},
            "leaf_count": len(leaves),
            "leaf_nia": leaf_nia,
            "leaf_gia": leaf_gia,
            "gia": gia,
            "gia_source": gia_source,
            "non_lettable": (gia - leaf_nia) if gia and leaf_nia else None,
            "net_to_gross": (leaf_nia / gia * 100).quantize(Decimal("0.1")) if gia and leaf_nia else None,
            "vacant_count": len(vacant),
            "vacant_nia": sum((p.nia_sqm or zero for p in vacant), zero),
        }

    @property
    def main_photo(self):
        photos = list(self.photos.all())
        return next((p for p in photos if p.is_main), photos[0] if photos else None)


def _photo_path(instance, filename):
    return f"photos/{instance.property_id}/{uuid.uuid4().hex}.jpg"


class PropertyPhoto(TimeStampedModel):
    """A photograph of a property. Uploads are resized and stripped of location (EXIF) data."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(_("photo"), upload_to=_photo_path, validators=[validate_image],
                              help_text=_("JPEG or PNG image up to 20 MB."))
    caption = models.CharField(_("caption"), max_length=200, blank=True)
    taken_on = models.DateField(_("date taken"), null=True, blank=True)
    is_main = models.BooleanField(_("main photo"), default=False,
                                  help_text=_("Shown first on the property page."))
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["-is_main", "order", "pk"]
        verbose_name = _("photo")
        verbose_name_plural = _("photos")

    def __str__(self):
        return self.caption or f"Photo of {self.property.name}"

    def get_absolute_url(self):
        return self.property.get_absolute_url()

    def save(self, *args, **kwargs):
        if self.image and not getattr(self.image, "_committed", True):
            self.image = process_image(self.image)
        if self.is_main:
            PropertyPhoto.objects.filter(property_id=self.property_id, is_main=True).exclude(pk=self.pk).update(is_main=False)
        super().save(*args, **kwargs)


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

    def get_absolute_url(self):
        return reverse("properties:title", args=[self.pk])

    def clean_fields(self, exclude=None):
        if self.title_number:
            self.title_number = self.title_number.upper().replace(" ", "")
        else:
            self.title_number = None  # keeps uniqueness working for unregistered titles
        super().clean_fields(exclude=exclude)


def _document_path(instance, filename):
    return f"titles/{instance.title_id}/{uuid.uuid4().hex}.pdf"


class TitleDocument(TimeStampedModel):
    """A PDF held against a title: official copies, plans, deeds and leases."""

    class DocumentType(models.TextChoices):
        REGISTER = "register", _("Official copy of the register")
        PLAN = "plan", _("Title plan")
        CONVEYANCE = "conveyance", _("Conveyance or transfer")
        LEASE = "lease", _("Lease")
        DEED = "deed", _("Other deed or agreement")
        OTHER = "other", _("Other document")

    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(_("document type"), max_length=20, choices=DocumentType.choices)
    file = models.FileField(_("PDF file"), upload_to=_document_path, validators=[validate_pdf],
                            help_text=_("PDF up to 25 MB."))
    original_filename = models.CharField(_("original file name"), max_length=255, blank=True, editable=False)
    description = models.CharField(_("description"), max_length=200, blank=True)
    document_date = models.DateField(_("document date"), null=True, blank=True,
                                     help_text=_("For official copies, the date and time of the copy."))

    class Meta:
        ordering = ["document_type", "-document_date"]
        verbose_name = _("title document")
        verbose_name_plural = _("title documents")

    def __str__(self):
        return self.description or self.get_document_type_display()

    def get_absolute_url(self):
        return self.title.get_absolute_url()

    def save(self, *args, **kwargs):
        if self.file and not getattr(self.file, "_committed", True):
            self.original_filename = self.file.name.rsplit("/", 1)[-1][:255]
        super().save(*args, **kwargs)


class InspireParcel(models.Model):
    """HM Land Registry INSPIRE Index Polygon: the indicative extent of a registered freehold title.

    Open data under the Open Government Licence. Display must carry the attribution in
    inspire_attribution(). Title numbers are not included in the open data.
    """

    inspire_id = models.CharField(_("INSPIRE ID"), max_length=50, unique=True)
    geometry = models.MultiPolygonField(srid=27700)
    valid_from = models.DateField(null=True, blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("INSPIRE parcel")
        verbose_name_plural = _("INSPIRE parcels")

    def __str__(self):
        return self.inspire_id


def inspire_attribution():
    """Attribution HM Land Registry requires wherever INSPIRE polygons are shown."""
    from datetime import date

    year = date.today().year
    return (
        f"This information is subject to Crown copyright and database rights {year} and is reproduced with "
        "the permission of HM Land Registry. The polygons (including the associated geometry, namely x, y "
        f"co-ordinates) are subject to Crown copyright and database rights {year} Ordnance Survey AC0000851063."
    )
