# SPDX-License-Identifier: AGPL-3.0-or-later
"""Space and costing: who occupies the council's buildings, how much space, and how well it is used.

An optional module (Module settings, "space and costing"). Design: claude/design-occupation-records.md; decisions
of 18 November 2026.

- Occupier: a council directorate, department or team, or an outside body sharing a building (One Public Estate).
- Space: a floor of a building, a room on a floor, or a shared space (reception, meeting rooms, circulation, plant).
- Occupation: an occupier in a space (or a whole building) from one date to another, for all of it or a share.
- Headcount: people based in a building, by occupier, from a date ("flexibility but accountability": every figure
  keeps who entered it and its source, and changes are in the change log).
- Use measures and figures: public use of a building (visits, bookings, hours used ...), per period.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.properties.models import Property

ZERO = Decimal("0")
BUILDING_TYPES = (Property.PropertyType.BUILDING, Property.PropertyType.UNIT, Property.PropertyType.SITE)


class Occupier(TimeStampedModel):
    class Level(models.TextChoices):
        DIRECTORATE = "directorate", _("Directorate")
        DEPARTMENT = "department", _("Department or service")
        TEAM = "team", _("Team")
        EXTERNAL = "external", _("Outside organisation")

    class Kind(models.TextChoices):
        NHS = "nhs", _("NHS")
        POLICE = "police", _("Police")
        FIRE = "fire", _("Fire and rescue")
        PUBLIC = "public", _("Other public body")
        CHARITY = "charity", _("Charity or voluntary group")
        OTHER = "other", _("Other")

    name = models.CharField(_("name"), max_length=200)
    level = models.CharField(_("level"), max_length=20, choices=Level.choices, default=Level.DEPARTMENT)
    parent = models.ForeignKey("self", verbose_name=_("part of"), null=True, blank=True, on_delete=models.PROTECT,
                               related_name="children",
                               help_text=_("The directorate a department belongs to, or the department a team "
                                           "belongs to."))
    external_kind = models.CharField(_("kind of outside organisation"), max_length=20, choices=Kind.choices,
                                     blank=True)
    cost_centre = models.CharField(_("cost centre"), max_length=40, blank=True)
    head_of_service = models.CharField(_("head of service"), max_length=200, blank=True)
    liaison = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("property liaison"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="liaison_for",
        help_text=_("The person in this department who deals with the estates team about its buildings."))
    liaison_name = models.CharField(
        _("property liaison (if not a PHAEMA user)"), max_length=200, blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("occupier")
        verbose_name_plural = _("occupiers (departments and outside organisations)")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("space:occupier", args=[self.pk])

    @property
    def is_external(self):
        return self.level == self.Level.EXTERNAL

    def clean(self):
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": _("An occupier cannot be part of itself.")})
        if self.is_external and self.parent_id:
            raise ValidationError({"parent": _("An outside organisation is not part of the council's structure.")})
        if not self.is_external and self.external_kind:
            raise ValidationError({"external_kind": _("Only for outside organisations.")})

    def family(self):
        """This occupier and every occupier below it."""
        found, frontier = [self], [self]
        while frontier:
            frontier = list(Occupier.objects.filter(parent__in=frontier))
            found.extend(frontier)
        return found


class Space(TimeStampedModel):
    class Kind(models.TextChoices):
        FLOOR = "floor", _("Floor")
        ROOM = "room", _("Room or area")
        SHARED = "shared", _("Shared space")

    class Use(models.TextChoices):
        OFFICE = "office", _("Office")
        MEETING = "meeting", _("Meeting rooms")
        PUBLIC = "public", _("Public area or counter")
        LIBRARY = "library", _("Library")
        CLINIC = "clinic", _("Clinic or treatment")
        STORE = "store", _("Storage")
        KITCHEN = "kitchen", _("Kitchen, welfare and toilets")
        RECEPTION = "reception", _("Reception")
        CIRCULATION = "circulation", _("Circulation (corridors, stairs, lifts)")
        PLANT = "plant", _("Plant and services")
        OTHER = "other", _("Other")

    building = models.ForeignKey(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                 related_name="spaces")
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.FLOOR)
    name = models.CharField(_("name"), max_length=120, help_text=_("For example: Ground floor, Room 2.14."))
    floor = models.ForeignKey("self", verbose_name=_("on floor"), null=True, blank=True, on_delete=models.CASCADE,
                              related_name="parts", limit_choices_to={"kind": "floor"},
                              help_text=_("For a room or shared space, the floor it is on."))
    level = models.SmallIntegerField(_("floor number"), default=0,
                                     help_text=_("0 for the ground floor, -1 for a basement. Sets the order."))
    use = models.CharField(_("use"), max_length=20, choices=Use.choices, default=Use.OFFICE)
    area_sqm = models.DecimalField(_("area (m²)"), max_digits=10, decimal_places=2, null=True, blank=True,
                                   validators=[MinValueValidator(0)],
                                   help_text=_("Net internal area, ideally. For a floor, the whole floor."))
    capacity = models.PositiveIntegerField(_("capacity"), null=True, blank=True,
                                           help_text=_("Desks, workstations or places for people."))
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["building", "-level", "kind", "name"]
        verbose_name = _("space")
        verbose_name_plural = _("spaces (floors, rooms and shared space)")

    def __str__(self):
        if self.floor_id:
            try:
                return f"{self.name}, {self.floor.name}"
            except Space.DoesNotExist:  # the floor is being deleted with its rooms
                pass
        return self.name

    def get_absolute_url(self):
        return reverse("space:building", args=[self.building_id])

    @property
    def is_shared(self):
        return self.kind == self.Kind.SHARED

    def clean(self):
        if self.kind == self.Kind.FLOOR and self.floor_id:
            raise ValidationError({"floor": _("A floor is not on another floor.")})
        if self.floor_id:
            if self.floor.building_id != self.building_id:
                raise ValidationError({"floor": _("Choose a floor of the same building.")})
            self.level = self.floor.level
        if self.building_id and self.building.property_type not in BUILDING_TYPES:
            raise ValidationError({"building": _("Spaces belong to a building, a lettable unit or a site.")})


class Occupation(TimeStampedModel):
    class Basis(models.TextChoices):
        SOLE = "sole", _("Sole use")
        SHARED = "shared", _("Shared with others")
        TIME_SHARE = "time_share", _("At set times (time-share)")

    building = models.ForeignKey(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                 related_name="occupations")
    space = models.ForeignKey(Space, verbose_name=_("space"), null=True, blank=True, on_delete=models.CASCADE,
                              related_name="occupations",
                              help_text=_("Leave blank if the occupier has the whole building."))
    occupier = models.ForeignKey(Occupier, verbose_name=_("occupier"), on_delete=models.PROTECT,
                                 related_name="occupations")
    starts = models.DateField(_("from"), default=date.today)
    ends = models.DateField(_("until"), null=True, blank=True, help_text=_("Leave blank while they are there."))
    share_percent = models.DecimalField(
        _("share (%)"), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(100)],
        help_text=_("Give a percentage or an area, or neither if they have all of the space."))
    share_sqm = models.DecimalField(_("or area (m²)"), max_digits=10, decimal_places=2, null=True, blank=True,
                                    validators=[MinValueValidator(Decimal("0.01"))])
    basis = models.CharField(_("basis"), max_length=20, choices=Basis.choices, default=Basis.SOLE)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["building", "-starts"]
        verbose_name = _("occupation")
        verbose_name_plural = _("occupations")

    def __str__(self):
        where = self.space or self.building
        return f"{self.occupier} in {where}"

    def get_absolute_url(self):
        return reverse("space:building", args=[self.building_id])

    def clean(self):
        errors = {}
        if self.space_id and self.building_id and self.space.building_id != self.building_id:
            errors["space"] = _("Choose a space in this building.")
        if self.share_percent and self.share_sqm:
            errors["share_sqm"] = _("Give a percentage or an area, not both.")
        if self.ends and self.starts and self.ends < self.starts:
            errors["ends"] = _("The end date must be after the start.")
        whole = self.whole_area()
        if self.share_sqm and whole is not None and self.share_sqm > whole:
            errors["share_sqm"] = _("This is more than the whole space (%(area)s m²).") % {"area": whole}
        if errors:
            raise ValidationError(errors)

    def current(self, on=None):
        on = on or date.today()
        return self.starts <= on and (self.ends is None or self.ends >= on)

    def whole_area(self):
        if self.space_id:
            return self.space.area_sqm
        return self.building.floor_area("net")[0] or self.building.floor_area("gross")[0]

    def area(self):
        """Square metres this occupation covers, or None if the space has no area."""
        if self.share_sqm:
            return self.share_sqm
        whole = self.whole_area()
        if whole is None:
            return None
        if self.share_percent:
            return (whole * self.share_percent / 100).quantize(Decimal("0.01"))
        return whole

    def percent(self):
        if self.share_percent:
            return self.share_percent
        whole = self.whole_area()
        if self.share_sqm and whole:
            return (self.share_sqm / whole * 100).quantize(Decimal("0.1"))
        return Decimal("100")


class Headcount(TimeStampedModel):
    building = models.ForeignKey(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                 related_name="headcounts")
    occupier = models.ForeignKey(Occupier, verbose_name=_("occupier"), on_delete=models.CASCADE,
                                 related_name="headcounts")
    counted_on = models.DateField(_("as at"), default=date.today)
    people = models.PositiveIntegerField(_("people based here"))
    fte = models.DecimalField(_("full-time equivalent"), max_digits=8, decimal_places=1, null=True, blank=True)
    source = models.CharField(_("source"), max_length=200, blank=True,
                              help_text=_("Where the figure comes from, for example \"HR establishment list\"."))

    class Meta:
        ordering = ["building", "occupier", "-counted_on"]
        constraints = [models.UniqueConstraint(fields=["building", "occupier", "counted_on"],
                                               name="one_headcount_per_date")]
        verbose_name = _("headcount")
        verbose_name_plural = _("headcounts")

    def __str__(self):
        return f"{self.occupier}: {self.people} at {self.building} ({self.counted_on:%d %b %Y})"


class UseMeasure(models.Model):
    """A measure of public use, from a list the council keeps: visits, bookings, hours used ..."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    unit = models.CharField(_("unit"), max_length=40, help_text=_("For example: visits, bookings, hours."))
    help = models.CharField(_("how to count it"), max_length=255, blank=True)
    active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("public use measure")
        verbose_name_plural = _("public use measures")

    def __str__(self):
        return self.name


class UseFigure(TimeStampedModel):
    building = models.ForeignKey(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                 related_name="use_figures")
    measure = models.ForeignKey(UseMeasure, verbose_name=_("measure"), on_delete=models.PROTECT,
                                related_name="figures")
    period_start = models.DateField(_("from"))
    period_end = models.DateField(_("to"))
    value = models.DecimalField(_("figure"), max_digits=12, decimal_places=1, validators=[MinValueValidator(0)])
    available = models.DecimalField(
        _("out of"), max_digits=12, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text=_("Optional: the most there could have been, for example hours open, so a percentage is shown."))
    source = models.CharField(_("source"), max_length=200, blank=True)

    class Meta:
        ordering = ["building", "measure", "-period_start"]
        constraints = [models.UniqueConstraint(fields=["building", "measure", "period_start"],
                                               name="one_use_figure_per_period")]
        verbose_name = _("public use figure")
        verbose_name_plural = _("public use figures")

    def __str__(self):
        return f"{self.measure}: {self.value} ({self.period_start:%b %Y} to {self.period_end:%b %Y})"

    def clean(self):
        if self.period_end and self.period_start and self.period_end < self.period_start:
            raise ValidationError({"period_end": _("The period must end after it starts.")})

    def percent(self):
        if self.available:
            return (Decimal(str(self.value)) / Decimal(str(self.available)) * 100).quantize(Decimal("0.1"))
        return None


# ---------------------------------------------------------------- costs (module level 2)

def financial_year_label(year):
    return f"{year}-{(year + 1) % 100:02d}"


class CostLine(models.Model):
    """A kind of building cost, from a list the council keeps: rates, energy, cleaning ... and notional rent."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    notional = models.BooleanField(
        _("notional (not cash)"), default=False,
        help_text=_("For notional rent on freehold buildings: shown separately, and totals are given with and "
                    "without it."))
    from_jobs = models.BooleanField(
        _("can be worked out from maintenance jobs"), default=False,
        help_text=_("If no figure is entered for a year, use the council's cost of maintenance jobs completed in "
                    "that year (when the maintenance module is on)."))
    help = models.CharField(_("what to include"), max_length=255, blank=True)
    active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("cost line")
        verbose_name_plural = _("cost lines")

    def __str__(self):
        return self.name


class BuildingCost(TimeStampedModel):
    building = models.ForeignKey(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                 related_name="building_costs")
    year_starting = models.PositiveSmallIntegerField(
        _("financial year starting"), validators=[MinValueValidator(1990), MaxValueValidator(2200)],
        help_text=_("2025 for 2025-26."))
    line = models.ForeignKey(CostLine, verbose_name=_("cost"), on_delete=models.PROTECT, related_name="amounts")
    amount = models.DecimalField(_("amount (£)"), max_digits=14, decimal_places=2,
                                 validators=[MinValueValidator(0)])
    source = models.CharField(_("source"), max_length=200, blank=True,
                              help_text=_("Where the figure comes from, for example \"Finance ledger, cost centre "
                                          "PL210\" or \"Valuer's estimate of rental value\"."))

    class Meta:
        ordering = ["building", "-year_starting", "line"]
        constraints = [models.UniqueConstraint(fields=["building", "year_starting", "line"],
                                               name="one_cost_line_per_year")]
        verbose_name = _("building cost")
        verbose_name_plural = _("building costs")

    def __str__(self):
        return f"{self.line} {financial_year_label(self.year_starting)}: £{self.amount:,.0f} ({self.building})"

    def get_absolute_url(self):
        return reverse("space:building", args=[self.building_id])


class CostSharing(TimeStampedModel):
    """How one building's costs are shared between its occupiers."""

    class Method(models.TextChoices):
        AREA = "area", _("By floor area held (shared space spread in proportion)")
        HEADCOUNT = "headcount", _("By headcount")
        FIXED = "fixed", _("Fixed percentages agreed with finance")

    building = models.OneToOneField(Property, verbose_name=_("building"), on_delete=models.CASCADE,
                                    related_name="cost_sharing")
    method = models.CharField(_("share costs"), max_length=10, choices=Method.choices, default=Method.AREA)
    notes = models.CharField(_("notes"), max_length=255, blank=True,
                             help_text=_("For example who agreed fixed percentages, and when."))

    class Meta:
        verbose_name = _("cost sharing")
        verbose_name_plural = _("cost sharing")

    def __str__(self):
        return f"{self.building}: {self.get_method_display()}"


class FixedShare(models.Model):
    sharing = models.ForeignKey(CostSharing, on_delete=models.CASCADE, related_name="shares")
    occupier = models.ForeignKey(Occupier, verbose_name=_("occupier"), on_delete=models.PROTECT,
                                 related_name="fixed_shares")
    percent = models.DecimalField(_("share (%)"), max_digits=5, decimal_places=2,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sharing", "occupier"], name="one_fixed_share_each")]
        verbose_name = _("fixed share")
        verbose_name_plural = _("fixed shares")

    def __str__(self):
        return f"{self.occupier}: {self.percent}%"
