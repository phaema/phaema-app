# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rent ledger: charges raised by demand runs, credit notes, receipts and finance exports.

Balances are not stored. A lease's account is worked out from its charges and receipts each
time, setting payments against the oldest debt first, so the ledger can never drift out of step.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.leases.models import Lease

PENNY = Decimal("0.01")


class DemandRun(TimeStampedModel):
    """One batch of charges, for payments falling due between two dates."""
    due_from = models.DateField(_("payments due from"))
    due_to = models.DateField(_("payments due to"))
    issue_date = models.DateField(_("issue date"))
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("demand run")

    def __str__(self):
        return f"Demand run {self.due_from:%d/%m/%Y}–{self.due_to:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("ledger:run", args=[self.pk])


class ExportBatch(TimeStampedModel):
    """Charges sent to the finance system together."""

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("finance export")
        verbose_name_plural = _("finance exports")

    def __str__(self):
        return f"Finance export {self.pk} ({self.created_at:%d/%m/%Y})"


class Charge(TimeStampedModel):
    class Kind(models.TextChoices):
        RENT = "rent", _("Rent")
        SERVICE = "service", _("Service charge")
        CREDIT = "credit", _("Credit note")
        INTEREST = "interest", _("Interest on late payment")
        OTHER = "other", _("Other charge")

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="charges")
    run = models.ForeignKey(DemandRun, on_delete=models.PROTECT, null=True, blank=True, related_name="charges")
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices, default=Kind.RENT)
    description = models.CharField(_("description"), max_length=200)
    period_start = models.DateField(_("period from"), null=True, blank=True)
    period_end = models.DateField(_("period to"), null=True, blank=True)
    issue_date = models.DateField(_("issued"))
    due_date = models.DateField(_("due"))
    net = models.DecimalField(_("net"), max_digits=12, decimal_places=2)
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=0)
    vat = models.DecimalField(_("VAT"), max_digits=12, decimal_places=2, default=0)
    gross = models.DecimalField(_("total"), max_digits=12, decimal_places=2)
    invoice_number = models.CharField(_("invoice number"), max_length=30, blank=True)
    credit_for = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="credits",
                                   verbose_name=_("credit for"))
    service_year = models.ForeignKey("servicecharges.ScheduleYear", on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="charges", verbose_name=_("service charge year"))
    export = models.ForeignKey(ExportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="charges")

    class Meta:
        ordering = ["due_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["invoice_number"], condition=~models.Q(invoice_number=""),
                                    name="ledger_unique_invoice_number"),
            models.UniqueConstraint(fields=["lease", "period_start"], condition=models.Q(kind="rent"),
                                    name="ledger_one_rent_charge_per_period"),
            models.UniqueConstraint(fields=["lease", "period_start", "service_year"],
                                    condition=models.Q(kind="service"), name="ledger_one_service_charge_per_period"),
        ]

    def __str__(self):
        return f"{self.reference} {self.lease.reference} £{self.gross}"

    @property
    def reference(self):
        """The invoice number if PHAEMA numbered it, otherwise PHAEMA's own reference for finance to quote."""
        return self.invoice_number or f"PHC{self.pk:06d}"

    def get_absolute_url(self):
        return reverse("ledger:account", args=[self.lease_id]) + f"#charge-{self.pk}"

    @staticmethod
    def amounts(net, vat_rate):
        net = Decimal(net).quantize(PENNY)
        vat = (net * Decimal(vat_rate) / 100).quantize(PENNY)
        return net, vat, net + vat


class Receipt(TimeStampedModel):
    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="receipts")
    received_on = models.DateField(_("received"))
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    payment_reference = models.CharField(_("payment reference"), max_length=60, unique=True,
                                         help_text=_("The finance system's unique reference for this payment."))
    quoted_reference = models.CharField(_("reference quoted"), max_length=60, blank=True,
                                        help_text=_("The invoice or other reference the payer quoted."))
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        ordering = ["received_on", "pk"]

    def __str__(self):
        return f"Receipt {self.payment_reference} £{self.amount}"

    def get_absolute_url(self):
        return reverse("ledger:account", args=[self.lease_id]) + f"#receipt-{self.pk}"


class BaseRate(models.Model):
    """The Bank of England base rate from a date, for interest on late rent."""

    effective_from = models.DateField(_("from"), unique=True)
    rate = models.DecimalField(_("base rate (%)"), max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["-effective_from"]
        verbose_name = _("Bank of England base rate")
        verbose_name_plural = _("Bank of England base rates")

    def __str__(self):
        return f"{self.rate}% from {self.effective_from:%d %b %Y}"


class ChaseStage(models.Model):
    """One step in chasing overdue rent, taken once the oldest unpaid charge is this many days overdue."""

    class Action(models.TextChoices):
        LETTER = "letter", _("Send a letter")
        CASE = "case", _("Open a rent arrears recovery case")
        REVIEW = "review", _("Review the account (for example refer to legal or debt collectors)")

    order = models.PositiveSmallIntegerField(_("order"), default=1)
    name = models.CharField(_("name"), max_length=100)
    days_overdue = models.PositiveSmallIntegerField(_("days overdue"))
    action = models.CharField(_("action"), max_length=8, choices=Action.choices, default=Action.LETTER)
    template_code = models.SlugField(
        _("letter template"), max_length=60, blank=True,
        help_text=_("The code of the letter in the document library, for example arrears_reminder."))
    minimum_overdue = models.DecimalField(
        _("only if at least (£) is overdue"), max_digits=10, decimal_places=2, default=0,
        help_text=_("Small debts below this are left for the next stage or the next demand."))

    class Meta:
        ordering = ["days_overdue", "order"]
        verbose_name = _("credit control stage")
        verbose_name_plural = _("credit control stages")

    def __str__(self):
        return f"{self.name} ({self.days_overdue} days)"

    @property
    def template(self):
        if not self.template_code:
            return None
        from apps.documents.models import DocumentTemplate

        return DocumentTemplate.objects.filter(code=self.template_code).first()


class ChaseAction(TimeStampedModel):
    """A chasing step taken on an account: a letter sent, a case opened or the account reviewed."""

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="chase_actions")
    stage = models.ForeignKey(ChaseStage, on_delete=models.PROTECT, related_name="actions")
    taken_on = models.DateField(_("date"))
    overdue = models.DecimalField(_("overdue then"), max_digits=12, decimal_places=2)
    taken_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    case = models.ForeignKey("cases.Case", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["-taken_on", "-pk"]

    def __str__(self):
        return f"{self.stage.name} on {self.taken_on:%d %b %Y}"


class PaymentPlan(TimeStampedModel):
    """An agreement with a tenant to clear arrears by instalments. Chasing pauses while the plan is kept."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        COMPLETED = "completed", _("Completed")
        BROKEN = "broken", _("Broken")
        CANCELLED = "cancelled", _("Cancelled")

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="payment_plans")
    agreed_on = models.DateField(_("agreed"))
    amount = models.DecimalField(_("arrears covered (£)"), max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    grace_days = models.PositiveSmallIntegerField(
        _("days allowed after each instalment"), default=7,
        help_text=_("An instalment counts as missed this many days after its date."))
    also_current_rent = models.BooleanField(
        _("tenant also pays the current rent"), default=True,
        help_text=_("Usual: instalments are on top of the rent as it falls due."))
    case = models.ForeignKey("cases.Case", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("arrears case"))
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["-agreed_on", "-pk"]
        verbose_name = _("payment plan")

    def __str__(self):
        return f"Payment plan £{self.amount} agreed {self.agreed_on:%d %b %Y}"

    def get_absolute_url(self):
        return reverse("ledger:account", args=[self.lease_id]) + "#plan"


class Instalment(models.Model):
    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE, related_name="instalments")
    due_date = models.DateField(_("due"))
    amount = models.DecimalField(_("amount (£)"), max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["plan", "due_date"]

    def __str__(self):
        return f"£{self.amount} by {self.due_date:%d %b %Y}"
