# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estates strategy, step 2: the council's estate strategy, its objectives and the action plan.

Organised around the RICS guidance on strategic public sector property asset management: each objective can record
the corporate aim it serves, its financial effect, risks and opportunities, expected outcomes, how success is
measured, and an action plan of projects, cases and other actions.
"""
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class EstateStrategy(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ADOPTED = "adopted", _("Adopted")
        REPLACED = "replaced", _("Replaced")

    title = models.CharField(_("title"), max_length=200,
                             help_text=_("For example Asset Management Strategy 2026 to 2031."))
    starts_on = models.DateField(_("period from"))
    ends_on = models.DateField(_("period to"))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT,
                              help_text=_("Only one strategy is adopted at a time; adopting one marks the "
                                          "previous one replaced."))
    approved_by = models.CharField(_("approved by"), max_length=120, blank=True,
                                   help_text=_("For example Cabinet or Full Council."))
    approved_on = models.DateField(_("approved on"), null=True, blank=True)
    minute_reference = models.CharField(_("minute or decision reference"), max_length=60, blank=True)
    document_url = models.URLField(_("published document"), blank=True,
                                   help_text=_("Link to the strategy on the council's website."))
    principles = models.TextField(_("policy principles"), blank=True,
                                  help_text=_("The rules the strategy sets, one per paragraph, for example: keep "
                                              "property only where a service needs it and it is fit for purpose."))

    class Meta:
        ordering = ["-starts_on"]
        verbose_name = _("estate strategy")
        verbose_name_plural = _("estate strategies")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("strategy:home") + f"?strategy={self.pk}"

    def clean(self):
        if self.starts_on and self.ends_on and self.ends_on <= self.starts_on:
            raise ValidationError({"ends_on": _("The period must end after it starts.")})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == self.Status.ADOPTED:
            EstateStrategy.objects.filter(status=self.Status.ADOPTED).exclude(pk=self.pk).update(
                status=self.Status.REPLACED)

    @classmethod
    def current(cls):
        return cls.objects.filter(status=cls.Status.ADOPTED).first()


class Objective(TimeStampedModel):
    class Rag(models.TextChoices):
        GREEN = "green", _("On track")
        AMBER = "amber", _("At risk")
        RED = "red", _("Off track")
        DONE = "done", _("Achieved")

    strategy = models.ForeignKey(EstateStrategy, on_delete=models.CASCADE, related_name="objectives",
                                 verbose_name=_("strategy"))
    number = models.CharField(_("number"), max_length=10, blank=True, help_text=_("As in the strategy, e.g. 3.2."))
    title = models.CharField(_("objective"), max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="strategy_objectives", verbose_name=_("owner"))
    target_date = models.DateField(_("target date"), null=True, blank=True)
    corporate_aim = models.TextField(_("corporate aim it serves"), blank=True)
    financial_effect = models.TextField(_("financial effect"), blank=True,
                                        help_text=_("Savings, income or capital receipts expected, and costs."))
    risks = models.TextField(_("risks and opportunities"), blank=True)
    outcomes = models.TextField(_("expected outcomes"), blank=True)
    measures = models.TextField(_("how success is measured"), blank=True)
    reported_status = models.CharField(_("reported status"), max_length=6, choices=Rag.choices, blank=True)
    progress_note = models.TextField(_("progress"), blank=True)
    status_on = models.DateField(_("status updated"), null=True, blank=True)
    status_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+", verbose_name=_("status updated by"))
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["strategy", "order", "number", "pk"]
        verbose_name = _("objective")
        verbose_name_plural = _("objectives")

    def __str__(self):
        return f"{self.number} {self.title}".strip()

    def get_absolute_url(self):
        return reverse("strategy:objective", args=[self.pk])


class Action(TimeStampedModel):
    """One line of an objective's action plan: a project, a case, or a stand-alone action."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        DONE = "done", _("Done")
        DROPPED = "dropped", _("Dropped")

    objective = models.ForeignKey(Objective, on_delete=models.CASCADE, related_name="actions",
                                  verbose_name=_("objective"))
    title = models.CharField(_("action"), max_length=200, blank=True,
                             help_text=_("Leave blank for a project or case: its name is used."))
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, null=True, blank=True,
                                related_name="strategy_actions", verbose_name=_("project"))
    case = models.ForeignKey("cases.Case", on_delete=models.CASCADE, null=True, blank=True,
                             related_name="strategy_actions", verbose_name=_("case"))
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="strategy_actions", verbose_name=_("owner"))
    target_date = models.DateField(_("target date"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.NOT_STARTED)
    done_on = models.DateField(_("done on"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["target_date", "pk"]
        verbose_name = _("action")
        verbose_name_plural = _("actions")

    def __str__(self):
        return self.label

    @property
    def label(self):
        if self.title:
            return self.title
        if self.project_id:
            return f"{self.project.display_reference} {self.project.name}"
        if self.case_id:
            return f"{self.case.display_reference} {self.case.title}"
        return ""

    def clean(self):
        if self.project_id and self.case_id:
            raise ValidationError(_("Link a project or a case, not both."))
        if not (self.title or self.project_id or self.case_id):
            raise ValidationError({"title": _("Describe the action, or link a project or a case.")})

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and not self.done_on:
            self.done_on = date.today()
        if self.status != self.Status.DONE:
            self.done_on = None
        super().save(*args, **kwargs)


# ---------------------------------------------------------------- the annual asset management health check

class HealthQuestion(models.Model):
    """One question in the annual health check. PHAEMA's own wording, grouped under the headings used by the RICS
    guidance on strategic public sector property asset management. Administrators can change the list."""

    class Heading(models.TextChoices):
        STRATEGY = "strategy", _("Strategy")
        PLANNING = "planning", _("Planning")
        FINANCE = "finance", _("Financial planning")
        DEMAND = "demand", _("Demand and change")
        OPERATIONS = "operations", _("Operations")
        GOVERNANCE = "governance", _("Governance")
        CLIENT = "client", _("Intelligent client")
        POLICIES = "policies", _("Policies")
        DATA = "data", _("Data")
        REVIEW = "review", _("Review")

    heading = models.CharField(_("heading"), max_length=12, choices=Heading.choices)
    text = models.CharField(_("question"), max_length=300)
    guidance = models.CharField(_("what a good answer looks like"), max_length=400, blank=True)
    active = models.BooleanField(_("in use"), default=True,
                                 help_text=_("Untick to leave the question out of future checks. Past answers are "
                                             "kept."))
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("health check question")
        verbose_name_plural = _("health check questions")

    def __str__(self):
        return self.text


class HealthCheck(TimeStampedModel):
    """The year's asset management health check: one per financial year."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("In progress")
        FINISHED = "finished", _("Finished")

    year = models.PositiveSmallIntegerField(_("financial year starting"), unique=True,
                                            help_text=_("2026 means 2026/27."))
    lead = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                             related_name="health_checks", verbose_name=_("lead"),
                             help_text=_("The person who answers the questions, usually the head of estates."))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    finished_on = models.DateField(_("finished on"), null=True, blank=True)
    summary = models.TextField(_("summary"), blank=True,
                               help_text=_("The lead's overall view: strengths, gaps and priorities for the year."))

    class Meta:
        ordering = ["-year"]
        verbose_name = _("asset management health check")
        verbose_name_plural = _("asset management health checks")

    def __str__(self):
        from apps.projects.models import financial_year_label

        return f"Asset management health check {financial_year_label(self.year)}"

    def get_absolute_url(self):
        return reverse("strategy:health", args=[self.pk])

    def previous(self):
        return HealthCheck.objects.filter(year__lt=self.year).order_by("-year").first()


class HealthAnswer(models.Model):
    """The answer to one question in one year's check. The question's wording is copied in, so changing the list
    later does not rewrite past checks."""

    class Answer(models.TextChoices):
        YES = "yes", _("Yes")
        PARTLY = "partly", _("Partly")
        NO = "no", _("No")
        NA = "na", _("Not applicable")

    health_check = models.ForeignKey(HealthCheck, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(HealthQuestion, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="answers")
    heading = models.CharField(_("heading"), max_length=12, choices=HealthQuestion.Heading.choices)
    wording = models.CharField(_("question"), max_length=300)
    guidance = models.CharField(_("what a good answer looks like"), max_length=400, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    answer = models.CharField(_("answer"), max_length=8, choices=Answer.choices, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    evidence = models.TextField(_("evidence"), blank=True,
                                help_text=_("Where the evidence is: a link, a document or a committee report, one "
                                            "per line."))
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name=_("answered by"))
    answered_on = models.DateField(_("answered on"), null=True, blank=True)
    action = models.ForeignKey(Action, on_delete=models.SET_NULL, null=True, blank=True, related_name="health_answers",
                               verbose_name=_("improvement action"))

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("health check answer")
        verbose_name_plural = _("health check answers")

    def __str__(self):
        return self.wording

    @property
    def is_gap(self):
        return self.answer in (self.Answer.NO, self.Answer.PARTLY)

    def evidence_lines(self):
        return [line.strip() for line in self.evidence.splitlines() if line.strip()]


class HealthNote(TimeStampedModel):
    """A colleague's note on the check, or on one answer in it."""

    health_check = models.ForeignKey(HealthCheck, on_delete=models.CASCADE, related_name="notes")
    answer = models.ForeignKey(HealthAnswer, on_delete=models.CASCADE, null=True, blank=True, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    text = models.TextField(_("note"))

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("health check note")
        verbose_name_plural = _("health check notes")

    def __str__(self):
        return self.text[:60]
