# SPDX-License-Identifier: AGPL-3.0-or-later
"""Projects: larger pieces of work above cases. A project can cover several properties (a development), none yet
(an acquisition, with a proposed site drawn on the map), or many (a programme). It passes four gateways through five
phases, has a team, milestones, tasks, notes and documents, and groups the cases, jobs and valuations that serve it."""
import uuid
from datetime import date

from django.conf import settings
from django.contrib.gis.db import models
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.models import validate_case_file
from apps.core.models import TimeStampedModel


class Phase(models.TextChoices):
    IDEA = "idea", _("Idea")
    BUSINESS_CASE = "business_case", _("Business case")
    DELIVERY = "delivery", _("Delivery")
    COMPLETION = "completion", _("Completion")
    CLOSE = "close", _("Close")


PHASE_ORDER = [p for p, _l in Phase.choices]

# Gateway number -> (phase it ends, phase it opens, what it decides, usual decision-maker)
GATEWAYS = {
    1: (Phase.IDEA, Phase.BUSINESS_CASE, _("Go ahead with a business case"), "officer"),
    2: (Phase.BUSINESS_CASE, Phase.DELIVERY, _("Approval to proceed"), "cabinet"),
    3: (Phase.DELIVERY, Phase.COMPLETION, _("Completion confirmed"), "officer"),
    4: (Phase.COMPLETION, Phase.CLOSE, _("Close-out review"), "officer"),
}


class ProjectType(models.Model):
    class Kind(models.TextChoices):
        DEVELOPMENT = "development", _("Development")
        ACQUISITION = "acquisition", _("Acquisition")
        DISPOSAL = "disposal", _("Disposal")
        PROGRAMME = "programme", _("Programme")
        REVIEW = "review", _("Strategic review")

    code = models.SlugField(_("code"), max_length=40, unique=True)
    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=12, choices=Kind.choices)
    description = models.TextField(_("description"), blank=True)
    confidential_by_default = models.BooleanField(
        _("confidential by default"), default=False,
        help_text=_("New projects of this type start confidential: only the team and administrators can see them."))
    phase_names = models.JSONField(
        _("phase names"), default=dict, blank=True,
        help_text=_('Optional new names for the phases, for example {"business_case": "Outline business case"}.'))
    active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("project type")
        verbose_name_plural = _("project types")

    def __str__(self):
        return self.name

    def phase_label(self, phase):
        return (self.phase_names or {}).get(phase) or str(dict(Phase.choices)[phase])


class Project(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        PAUSED = "paused", _("Paused")
        STOPPED = "stopped", _("Stopped")
        CLOSED = "closed", _("Closed")

    year = models.PositiveSmallIntegerField(editable=False)
    number = models.PositiveIntegerField(editable=False)
    name = models.CharField(_("name"), max_length=200)
    project_type = models.ForeignKey(ProjectType, on_delete=models.PROTECT, related_name="projects",
                                     verbose_name=_("type"))
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.ACTIVE)
    status_reason = models.CharField(_("reason for pausing or stopping"), max_length=300, blank=True)
    phase = models.CharField(_("phase"), max_length=14, choices=Phase.choices, default=Phase.IDEA)
    lead = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="led_projects", verbose_name=_("project lead"))
    sponsor = models.CharField(_("sponsor"), max_length=150, blank=True,
                               help_text=_("The senior officer or councillor who owns the project."))
    start_date = models.DateField(_("start"), default=date.today)
    target_date = models.DateField(_("target completion"), null=True, blank=True)
    confidential = models.BooleanField(
        _("confidential"), default=False,
        help_text=_("Only the project team and administrators can see a confidential project or its site."))
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="phases",
                               verbose_name=_("part of"), help_text=_("For a later phase of a larger project."))
    # A proposed site: for land the council does not own yet (acquisitions), or a site not yet in the register.
    site_address = models.TextField(_("proposed site address"), blank=True)
    site_boundary = models.MultiPolygonField(_("proposed site boundary"), srid=27700, null=True, blank=True)
    site_title_number = models.CharField(_("title number"), max_length=20, blank=True)
    vendor = models.ForeignKey("leases.Party", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="projects_selling", verbose_name=_("vendor or other party"))

    class Meta:
        ordering = ["-year", "-number"]
        constraints = [models.UniqueConstraint(fields=["year", "number"], name="project_unique_number")]

    def __str__(self):
        return f"{self.display_reference} {self.name}"

    @property
    def display_reference(self):
        return f"PRJ-{self.year}-{self.number:03d}" if self.number else "PRJ-new"

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.number:
            self.year = self.year or (self.start_date or date.today()).year
            with transaction.atomic():
                last = Project.objects.select_for_update().filter(year=self.year).aggregate(n=Max("number"))["n"]
                self.number = (last or 0) + 1
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in (self.Status.ACTIVE, self.Status.PAUSED)

    @property
    def phase_index(self):
        return PHASE_ORDER.index(self.phase)

    def phase_label(self, phase=None):
        return self.project_type.phase_label(phase or self.phase)

    def next_gateway(self):
        """The gateway that ends the current phase, or None after the last one."""
        return next((n for n, g in GATEWAYS.items() if g[0] == self.phase), None)

    def rag(self, today=None):
        """Red, amber or green, with a reason: red for a missed milestone, amber for a slipping forecast, an overdue
        task or a pause."""
        today = today or date.today()
        if not self.is_open:
            return "grey", self.get_status_display()
        missed = [m for m in self.milestones.all() if not m.actual_date and m.target_date and m.target_date < today]
        if missed:
            return "red", _("Milestone missed")
        if self.status == self.Status.PAUSED:
            return "yellow", _("Paused")
        slipping = [m for m in self.milestones.all() if not m.actual_date and m.forecast_date and m.target_date
                    and m.forecast_date > m.target_date]
        if slipping:
            return "yellow", _("Forecast later than target")
        if self.tasks.filter(done_on__isnull=True, due_date__lt=today).exists():
            return "yellow", _("Overdue tasks")
        return "green", _("On track")


class ProjectProperty(models.Model):
    class Part(models.TextChoices):
        IN_SCOPE = "in_scope", _("In scope")
        DEVELOP = "develop", _("To develop")
        DISPOSE = "dispose", _("To dispose of")
        IMPROVE = "improve", _("To improve")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="property_links")
    property = models.ForeignKey("properties.Property", on_delete=models.CASCADE, related_name="project_links")
    part = models.CharField(_("part in the project"), max_length=10, choices=Part.choices, default=Part.IN_SCOPE)
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "property"], name="project_property_once")]
        ordering = ["property__reference"]
        verbose_name = _("project property")
        verbose_name_plural = _("project properties")

    def __str__(self):
        return f"{self.project.display_reference}: {self.property.reference}"


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        SURVEYOR = "surveyor", _("Surveyor")
        FINANCE = "finance", _("Finance")
        LEGAL = "legal", _("Legal")
        VALUER = "valuer", _("Valuer")
        MEMBER = "member", _("Team member")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_places")
    role = models.CharField(_("role on the project"), max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="project_member_once")]
        verbose_name = _("project team member")
        verbose_name_plural = _("project team")

    def __str__(self):
        return f"{self.project.display_reference}: {self.user}"


class ProjectParty(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="party_links")
    party = models.ForeignKey("leases.Party", on_delete=models.CASCADE, related_name="project_links")
    role = models.CharField(_("role"), max_length=60, help_text=_("For example: agent, architect, the other side."))

    class Meta:
        verbose_name = _("outside party")
        verbose_name_plural = _("outside parties")

    def __str__(self):
        return f"{self.project.display_reference}: {self.party} ({self.role})"


def _project_file_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.project_id}/{uuid.uuid4().hex}.{ext}"


class GatewayDecision(TimeStampedModel):
    class Maker(models.TextChoices):
        OFFICER = "officer", _("Officer (delegated decision)")
        CABINET = "cabinet", _("Cabinet or committee")
        BOARD = "board", _("Capital or programme board")
        OTHER = "other", _("Other")

    class Outcome(models.TextChoices):
        APPROVED = "approved", _("Approved: move to the next phase")
        DEFERRED = "deferred", _("Deferred: more work needed")
        REJECTED = "rejected", _("Rejected: stop the project")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="gateway_decisions")
    number = models.PositiveSmallIntegerField(_("gateway"), choices=[(n, f"Gateway {n}") for n in GATEWAYS])
    decision_maker = models.CharField(_("decided by"), max_length=8, choices=Maker.choices)
    decided_on = models.DateField(_("decided on"))
    outcome = models.CharField(_("outcome"), max_length=8, choices=Outcome.choices)
    reference = models.CharField(_("decision reference"), max_length=100, blank=True,
                                 help_text=_("For example the Cabinet minute or delegated decision number."))
    report = models.FileField(_("report"), upload_to=_project_file_path, blank=True, validators=[validate_case_file])
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["number", "decided_on", "pk"]
        verbose_name = _("gateway decision")
        verbose_name_plural = _("gateway decisions")

    def __str__(self):
        return f"{self.project.display_reference} gateway {self.number}: {self.get_outcome_display()}"


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(_("milestone"), max_length=150)
    target_date = models.DateField(_("target"), null=True, blank=True)
    forecast_date = models.DateField(_("forecast"), null=True, blank=True)
    actual_date = models.DateField(_("achieved"), null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "target_date", "pk"]

    def __str__(self):
        return self.name


class ProjectTask(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    description = models.CharField(_("task"), max_length=200)
    phase = models.CharField(_("phase"), max_length=14, choices=Phase.choices, default=Phase.IDEA)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="project_tasks", verbose_name=_("owner"))
    due_date = models.DateField(_("due"), null=True, blank=True)
    done_on = models.DateField(_("done"), null=True, blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+")

    class Meta:
        ordering = ["done_on", "due_date", "pk"]

    def __str__(self):
        return self.description


class ProjectNote(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="notes")
    text = models.TextField(_("note"))

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:60]


class ProjectDocument(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(_("file"), upload_to=_project_file_path, validators=[validate_case_file])

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
