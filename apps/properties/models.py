# SPDX-License-Identifier: AGPL-3.0-or-later
"""Property register (terrier) and title records."""
import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from apps.core.files import process_image, validate_image, validate_pdf, validate_plan
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


class PropertyUse(models.Model):
    """The council's own list of property uses (Office, Shop, Depot and so on), kept by administrators.

    Each can be matched to a term in the Government Property Data Standard's usage list, which the standard's
    export then uses.
    """

    name = models.CharField(_("use"), max_length=80, unique=True)
    standard_usage = models.CharField(
        _("Government Property Data Standard usage"), max_length=80, blank=True,
        help_text=_("The matching term in the standard's usage list, for example \"Retail\" or \"Depot\". "
                    "Used in the standard's export. Leave blank if none fits."))
    active = models.BooleanField(_("in use"), default=True,
                                 help_text=_("Untick to stop it being chosen for new properties."))
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("property use")
        verbose_name_plural = _("property uses")

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
    strategy_section = models.CharField(
        _("estate strategy section"), max_length=100, blank=True,
        help_text=_("The section of the council's estate strategy or asset management plan that covers this "
                    "property, for example \"4.2 Investment estate\"."))
    purpose_review_date = models.DateField(
        _("holding purpose review date"), null=True, blank=True,
        help_text=_("When the reason for holding the property is next due to be reviewed."))
    portfolio = models.ForeignKey(
        Portfolio, verbose_name=_("portfolio"), null=True, blank=True, on_delete=models.PROTECT,
        related_name="properties", help_text=_("The service or portfolio the property belongs to."),
    )
    tenure = models.CharField(_("tenure"), max_length=20, choices=Tenure.choices, blank=True)
    occupation = models.CharField(
        _("occupation status"), max_length=20, choices=Occupation.choices, blank=True
    )
    use_description = models.CharField(
        _("use description"), max_length=100, blank=True,
        help_text=_("In your own words, e.g. Light industrial, Kiosk café, Surface car park (180 spaces)")
    )
    use_type = models.ForeignKey(
        PropertyUse, verbose_name=_("use (from the list)"), null=True, blank=True, on_delete=models.PROTECT,
        related_name="properties",
        help_text=_("The main use, chosen from the council's list. Add anything more exact in the description."))
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

    class DisposalMethod(models.TextChoices):
        PRIVATE_TREATY = "private_treaty", _("Private treaty")
        AUCTION = "auction", _("Auction")
        FORMAL_TENDER = "formal_tender", _("Formal tender")
        INFORMAL_TENDER = "informal_tender", _("Informal tender")
        DEVELOPMENT_AGREEMENT = "development", _("Development agreement")
        BUILDING_AGREEMENT = "building", _("Building agreement")
        COMMUNITY_TRANSFER = "community", _("Community asset transfer")
        OTHER = "other", _("Other")

    disposal_method = models.CharField(_("method of disposal"), max_length=20, choices=DisposalMethod.choices,
                                       blank=True)
    disposal_reason = models.CharField(
        _("reason for disposal"), max_length=255, blank=True,
        help_text=_("e.g. Surplus to the service's needs after the depot review; Cabinet decision 14 May 2026."))
    disposal_expected_on = models.DateField(_("disposal expected on"), null=True, blank=True,
                                            help_text=_("When completion is expected. A best estimate is fine."))
    disposal_expected_value = models.DecimalField(
        _("expected disposal value (£)"), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

    # Acquisition
    acquired_on = models.DateField(
        _("acquired on"), null=True, blank=True,
        help_text=_("When the council acquired its interest. If only the year is known, enter 1 January of it."))

    # Designations: blank means not known.
    class Listed(models.TextChoices):
        NO = "no", _("Not listed")
        GRADE_1 = "1", _("Grade I")
        GRADE_2_STAR = "2star", _("Grade II*")
        GRADE_2 = "2", _("Grade II")
        LOCAL = "local", _("Locally listed")

    class Designation(models.TextChoices):
        YES = "yes", _("Yes")
        NO = "no", _("No")

    listed_building = models.CharField(_("listed building"), max_length=5, choices=Listed.choices, blank=True)
    scheduled_monument = models.CharField(_("scheduled monument"), max_length=3, choices=Designation.choices,
                                          blank=True)
    sssi = models.CharField(_("site of special scientific interest (SSSI)"), max_length=3,
                            choices=Designation.choices, blank=True)
    conservation_area = models.CharField(_("in a conservation area"), max_length=3, choices=Designation.choices,
                                         blank=True)
    designation_notes = models.CharField(
        _("designation notes"), max_length=255, blank=True,
        help_text=_("e.g. the list entry number, or which part of the property is covered."))

    # Vacancy: for a property whose occupation is Vacant.
    class VacancyStatus(models.TextChoices):
        AVAILABLE = "available", _("Available")
        UNDER_OFFER = "under_offer", _("Under offer")
        UNDERLET = "underlet", _("Underlet")
        WITHDRAWN = "withdrawn", _("Withdrawn (not on the market)")

    vacant_since = models.DateField(_("vacant since"), null=True, blank=True)
    vacancy_status = models.CharField(_("vacancy status"), max_length=12, choices=VacancyStatus.choices, blank=True)
    available_from = models.DateField(_("available from"), null=True, blank=True)
    available_until = models.DateField(
        _("available until"), null=True, blank=True,
        help_text=_("If the space is only available for a time, for example until redevelopment starts."))

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

    # Site and buildings: what the property physically is. Recorded on a site, and on each building (block) in it.
    class Construction(models.TextChoices):
        MASONRY = "masonry", _("Traditional masonry (brick or block)")
        STONE = "stone", _("Stone")
        STEEL_FRAME = "steel_frame", _("Steel frame")
        PORTAL_FRAME = "portal_frame", _("Steel portal frame")
        CONCRETE_FRAME = "concrete_frame", _("Concrete frame")
        TIMBER_FRAME = "timber_frame", _("Timber frame")
        MODULAR = "modular", _("Modular or prefabricated")
        MIXED = "mixed", _("Mixed")
        OTHER = "other", _("Other")

    class RoofType(models.TextChoices):
        PITCHED = "pitched", _("Pitched")
        HIPPED = "hipped", _("Hipped")
        MONO = "mono", _("Mono-pitch")
        FLAT = "flat", _("Flat")
        MANSARD = "mansard", _("Mansard")
        NORTH_LIGHT = "north_light", _("North light (saw-tooth)")
        CURVED = "curved", _("Curved or barrel")
        MIXED = "mixed", _("Mixed")
        OTHER = "other", _("Other")

    class RoofCovering(models.TextChoices):
        SLATE = "slate", _("Slate")
        CLAY_TILE = "clay_tile", _("Clay tile")
        CONCRETE_TILE = "concrete_tile", _("Concrete tile")
        METAL_SHEET = "metal_sheet", _("Profiled metal sheet")
        COMPOSITE = "composite", _("Insulated composite panel")
        FIBRE_CEMENT = "fibre_cement", _("Fibre cement or asbestos cement sheet")
        FELT = "felt", _("Built-up bituminous felt")
        SINGLE_PLY = "single_ply", _("Single-ply membrane")
        ASPHALT = "asphalt", _("Mastic asphalt")
        LIQUID = "liquid", _("Liquid-applied membrane")
        GRP = "grp", _("GRP (glass fibre)")
        METAL = "metal", _("Lead, zinc or copper")
        GREEN = "green", _("Green roof")
        MIXED = "mixed", _("Mixed")
        OTHER = "other", _("Other")

    class WindowType(models.TextChoices):
        TIMBER_SINGLE = "timber_single", _("Timber, single glazed")
        TIMBER_DOUBLE = "timber_double", _("Timber, double glazed")
        UPVC = "upvc", _("uPVC, double glazed")
        ALUMINIUM = "aluminium", _("Aluminium, double glazed")
        STEEL = "steel", _("Steel, single glazed")
        CURTAIN = "curtain", _("Curtain walling")
        ROOFLIGHTS = "rooflights", _("Roof lights only")
        NONE = "none", _("None")
        MIXED = "mixed", _("Mixed")
        OTHER = "other", _("Other")

    class YesNo(models.TextChoices):
        YES = "yes", _("Yes")
        NO = "no", _("No")

    class Electricity(models.TextChoices):
        THREE = "three", _("Three-phase")
        SINGLE = "single", _("Single-phase")
        YES = "yes", _("Connected, phase not known")
        NONE = "none", _("None")

    class Drainage(models.TextChoices):
        MAINS = "mains", _("Mains drainage")
        PRIVATE = "private", _("Private (septic tank or treatment plant)")
        NONE = "none", _("None")

    location_description = models.TextField(
        _("location"), blank=True,
        help_text=_("Where the property is and what surrounds it: the part of town, road links, neighbouring "
                    "uses, access."))
    building_description = models.TextField(
        _("description"), blank=True,
        help_text=_("What is there: for a site, the buildings and land; for a building, its layout, "
                    "accommodation and condition in outline."))
    built = models.CharField(_("built"), max_length=40, blank=True, help_text=_("Year or period, e.g. 1987 or 1930s."))
    built_year = models.PositiveSmallIntegerField(
        _("year built"), null=True, blank=True, validators=[MinValueValidator(1000), MaxValueValidator(2200)],
        help_text=_("A single year, for reports. Use the earliest year of the period if only that is known."))

    class Condition(models.TextChoices):
        A = "A", _("A: good, performing as intended")
        B = "B", _("B: satisfactory, minor deterioration")
        C = "C", _("C: poor, major repair or replacement soon")
        D = "D", _("D: bad, life expired or serious risk")

    condition_grade = models.CharField(
        _("overall condition"), max_length=1, choices=Condition.choices, blank=True,
        help_text=_("The building as a whole, from its last condition survey. Components are graded separately "
                    "under Maintenance."))
    condition_surveyed_on = models.DateField(_("condition surveyed on"), null=True, blank=True)
    construction_type = models.CharField(_("construction"), max_length=20, choices=Construction.choices, blank=True)
    construction_detail = models.CharField(
        _("construction detail"), max_length=255, blank=True,
        help_text=_("e.g. cavity brick walls under a steel truss roof, solid concrete floors."))
    storeys = models.PositiveSmallIntegerField(_("storeys"), null=True, blank=True,
                                               help_text=_("Above ground, including the ground floor."))
    basement_levels = models.PositiveSmallIntegerField(_("basement levels"), null=True, blank=True)
    roof_type = models.CharField(_("roof type"), max_length=20, choices=RoofType.choices, blank=True)
    roof_covering = models.CharField(_("roof covering"), max_length=20, choices=RoofCovering.choices, blank=True)
    roof_detail = models.CharField(_("roof detail"), max_length=255, blank=True,
                                   help_text=_("e.g. main roof pitched slate; rear extension flat, single-ply, 2019."))
    window_type = models.CharField(_("windows"), max_length=20, choices=WindowType.choices, blank=True)
    window_detail = models.CharField(_("window detail"), max_length=255, blank=True)
    parking = models.TextField(_("parking"), blank=True,
                               help_text=_("e.g. surface car park to the front, shared with Unit 2; 2 accessible bays."))
    parking_spaces = models.PositiveIntegerField(_("parking spaces"), null=True, blank=True)
    mains_gas = models.CharField(_("mains gas"), max_length=3, choices=YesNo.choices, blank=True)
    electricity = models.CharField(_("electricity"), max_length=10, choices=Electricity.choices, blank=True)
    mains_water = models.CharField(_("mains water"), max_length=3, choices=YesNo.choices, blank=True)
    drainage = models.CharField(_("drainage"), max_length=10, choices=Drainage.choices, blank=True)
    services_notes = models.TextField(_("services notes"), blank=True,
                                      help_text=_("e.g. heating, supply capacity, where the meters are."))
    solar_pv = models.CharField(_("solar panels"), max_length=3, choices=YesNo.choices, blank=True)
    solar_capacity_kwp = models.DecimalField(
        _("solar capacity (kWp)"), max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

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
        self.clean_physical()

    def save(self, *args, **kwargs):
        # Derive easting/northing from the boundary centre when not entered.
        if self.boundary and self.easting is None and self.northing is None:
            centre = self.boundary.point_on_surface
            self.easting, self.northing = round(centre.x), round(centre.y)
        # The year built is taken from the "built" text when it has not been entered.
        if self.built and self.built_year is None:
            from .uses import year_from

            self.built_year = year_from(self.built)
        # Vacancy details belong to a vacant property: they are cleared once it is occupied again.
        if self.occupation != self.Occupation.VACANT:
            self.vacant_since = self.available_from = self.available_until = None
            self.vacancy_status = ""
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
    def site_area_sqm(self):
        return (self.site_area_ha * 10000).quantize(Decimal("1")) if self.site_area_ha is not None else None

    def site_area_text(self):
        """The site area in both units, e.g. "0.2500 ha (2,500 m²)"."""
        if self.site_area_ha is None:
            return ""
        return f"{self.site_area_ha.normalize():f} ha ({self.site_area_sqm:,} m²)"

    def storeys_text(self):
        parts = []
        if self.storeys:
            parts.append(str(self.storeys))
        if self.basement_levels:
            parts.append(f"{self.basement_levels} basement level{'s' if self.basement_levels != 1 else ''}")
        return " plus ".join(parts)

    def services_rows(self):
        """(label, value) for each service that has been recorded."""
        rows = [(_("Mains gas"), self.get_mains_gas_display()), (_("Electricity"), self.get_electricity_display()),
                (_("Mains water"), self.get_mains_water_display()), (_("Drainage"), self.get_drainage_display())]
        solar = self.get_solar_pv_display()
        if self.solar_pv == self.YesNo.YES and self.solar_capacity_kwp is not None:
            solar = f"{solar}, {self.solar_capacity_kwp.normalize():f} kWp"
        rows.append((_("Solar panels"), solar))
        if self.services_notes:
            rows.append((_("Services notes"), self.services_notes))
        return [(str(label), str(value)) for label, value in rows if value]

    def physical_rows(self):
        """(label, value) for each recorded fact about the site and buildings, in report order."""
        def with_detail(value, detail):
            return "; ".join(x for x in (str(value), detail) if x)

        parking = self.parking
        if self.parking_spaces is not None:
            spaces = f"{self.parking_spaces} space{'s' if self.parking_spaces != 1 else ''}"
            parking = f"{spaces}. {parking}" if parking else spaces
        rows = [
            (_("Location"), self.location_description),
            (_("Site area"), self.site_area_text()),
            (_("Description"), self.building_description),
            (_("Built"), self.built or (str(self.built_year) if self.built_year else "")),
            (_("Overall condition"), self.condition_text()),
            (_("Construction"), with_detail(self.get_construction_type_display(), self.construction_detail)),
            (_("Storeys"), self.storeys_text()),
            (_("Roof"), with_detail(", ".join(x for x in (str(self.get_roof_type_display()),
                                                         str(self.get_roof_covering_display())) if x),
                                    self.roof_detail)),
            (_("Windows"), with_detail(self.get_window_type_display(), self.window_detail)),
            (_("Parking"), parking),
        ]
        return [(str(label), str(value)) for label, value in rows if value] + self.services_rows()

    def condition_text(self):
        if not self.condition_grade:
            return ""
        text = str(self.get_condition_grade_display())
        if self.condition_surveyed_on:
            text += " ({})".format(_("surveyed %(date)s") % {"date": date_format(self.condition_surveyed_on, "j F Y")})
        return text

    def designation_rows(self):
        """(label, value) for each designation recorded, whether it applies or not; nothing for 'not known'."""
        rows = [
            (_("Listed building"), self.get_listed_building_display()),
            (_("Scheduled monument"), self.get_scheduled_monument_display()),
            (_("SSSI"), self.get_sssi_display()),
            (_("Conservation area"), self.get_conservation_area_display()),
            (_("Notes"), self.designation_notes),
        ]
        return [(str(label), str(value)) for label, value in rows if value]

    @property
    def designated(self):
        """True when any designation applies, so the page can flag it."""
        return (self.listed_building not in ("", self.Listed.NO) or "yes" in (
            self.scheduled_monument, self.sssi, self.conservation_area))

    def use_text(self, with_class=True):
        """The use as one phrase: the list entry, the description where it adds something, and the use class."""
        name, detail = (self.use_type.name if self.use_type_id else ""), self.use_description.strip()
        if name and name.lower() in detail.lower():  # "Public library" already says "Library"
            name = ""
        text = ": ".join(x for x in (name, detail) if x)
        if with_class and self.use_class:
            text = f"{text} ({self.use_class})".strip()
        return text

    def vacancy_text(self):
        if self.occupation != self.Occupation.VACANT:
            return ""
        parts = [str(self.get_vacancy_status_display())]
        if self.vacant_since:
            parts.append(str(_("vacant since %(date)s") % {"date": date_format(self.vacant_since, "j F Y")}))
        if self.available_from:
            parts.append(str(_("available from %(date)s") % {"date": date_format(self.available_from, "j F Y")}))
        if self.available_until:
            parts.append(str(_("available until %(date)s") % {"date": date_format(self.available_until, "j F Y")}))
        return "; ".join(x for x in parts if x)

    def planned_disposal_rows(self):
        """(label, value) for a disposal that is planned but not yet completed."""
        if self.disposed_on:
            return []
        rows = [
            (_("Reason"), self.disposal_reason),
            (_("Method"), self.get_disposal_method_display()),
            (_("Expected"), date_format(self.disposal_expected_on, "j F Y") if self.disposal_expected_on else ""),
            (_("Expected value"), f"£{self.disposal_expected_value:,.0f}"
             if self.disposal_expected_value is not None else ""),
        ]
        return [(str(label), str(value)) for label, value in rows if value]

    def latest_cost(self):
        costs = list(self.costs.all())
        return costs[0] if costs else None

    def clean_physical(self):
        today = date.today()
        errors = {}
        if self.condition_surveyed_on and not self.condition_grade:
            errors["condition_grade"] = _("Choose the overall condition the survey found.")
        if self.condition_surveyed_on and self.condition_surveyed_on > today:
            errors["condition_surveyed_on"] = _("The survey date cannot be in the future.")
        if self.built_year and self.built_year > today.year + 5:
            errors["built_year"] = _("Enter the year the building was, or will be, completed.")
        if self.acquired_on and self.acquired_on > today:
            errors["acquired_on"] = _("The acquisition date cannot be in the future.")
        if self.vacant_since and self.vacant_since > today:
            errors["vacant_since"] = _("The date it became vacant cannot be in the future.")
        if self.available_from and self.available_until and self.available_until < self.available_from:
            errors["available_until"] = _("This must be on or after the available from date.")
        if errors:
            raise ValidationError(errors)
        if self.solar_capacity_kwp is not None and self.solar_pv != self.YesNo.YES:
            raise ValidationError({"solar_capacity_kwp": _("Set solar panels to Yes to record a capacity.")})

    @property
    def main_photo(self):
        photos = list(self.photos.all())
        return next((p for p in photos if p.is_main), photos[0] if photos else None)


class PropertyCost(TimeStampedModel):
    """What a property cost to run in one financial year, and the business rates payable on it."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="costs")
    year_starting = models.PositiveSmallIntegerField(
        _("financial year starting"), validators=[MinValueValidator(1990), MaxValueValidator(2200)],
        help_text=_("The year the financial year starts in: 2025 for 2025-26."))
    running_cost = models.DecimalField(
        _("running cost (£)"), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("The cost of occupying and running the property for the year: energy, water, cleaning, "
                    "security, repairs and maintenance, insurance and service charges. Leave out rates, rent "
                    "and capital works."))
    rates = models.DecimalField(
        _("business rates (£)"), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)], help_text=_("Business rates payable by the council for the year."))
    notes = models.CharField(_("notes"), max_length=255, blank=True,
                             help_text=_("e.g. where the figures came from, or what is estimated."))

    class Meta:
        ordering = ["-year_starting"]
        constraints = [models.UniqueConstraint(fields=["property", "year_starting"], name="one_cost_per_year")]
        verbose_name = _("running cost")
        verbose_name_plural = _("running costs and rates")

    def __str__(self):
        return f"{self.property.reference} {self.year_label()}"

    def year_label(self):
        """The financial year as it is usually written: 2025-26."""
        return f"{self.year_starting}-{str(self.year_starting + 1)[-2:]}"

    def clean(self):
        super().clean()
        if self.running_cost is None and self.rates is None:
            raise ValidationError(_("Enter the running cost, the rates, or both."))


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


def _plan_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    return f"plans/{instance.property_id}/{uuid.uuid4().hex}.{ext}"


class PropertyPlan(TimeStampedModel):
    """A floor plan or other drawing of a property: a PDF, or an AutoCAD drawing (DWG or DXF)."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="plans")
    title = models.CharField(_("title"), max_length=200, help_text=_("e.g. Ground floor plan, or Site layout."))
    file = models.FileField(_("file"), upload_to=_plan_path, validators=[validate_plan],
                            help_text=_("A PDF, or an AutoCAD drawing (.dwg or .dxf), up to 50 MB."))
    original_filename = models.CharField(_("original file name"), max_length=255, blank=True, editable=False)
    drawn_on = models.DateField(_("date of plan"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True,
                             help_text=_("e.g. scale, who drew it, or that it is as-built."))

    class Meta:
        ordering = ["title", "pk"]
        verbose_name = _("floor plan")
        verbose_name_plural = _("floor plans")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return self.property.get_absolute_url()

    def file_type(self):
        ext = self.file.name.rsplit(".", 1)[-1].lower() if self.file and "." in self.file.name else ""
        return {"pdf": "PDF", "dwg": "AutoCAD DWG", "dxf": "AutoCAD DXF"}.get(ext, ext.upper())

    def save(self, *args, **kwargs):
        if self.file and not getattr(self.file, "_committed", True):
            self.original_filename = (getattr(self.file, "name", "") or "").rsplit("/", 1)[-1][:255]
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
