# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rent ledger: charges raised by demand runs, credit notes, receipts and finance exports.

Balances are not stored. A lease's account is worked out from its charges and receipts each
time, setting payments against the oldest debt first, so the ledger can never drift out of step.
"""
from decimal import Decimal

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
        CREDIT = "credit", _("Credit note")
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
    export = models.ForeignKey(ExportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="charges")

    class Meta:
        ordering = ["due_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["invoice_number"], condition=~models.Q(invoice_number=""),
                                    name="ledger_unique_invoice_number"),
            models.UniqueConstraint(fields=["lease", "period_start"], condition=models.Q(kind="rent"),
                                    name="ledger_one_rent_charge_per_period"),
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
