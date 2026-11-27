# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Base for PHAEMA records: creation and update times plus who made them."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


def days_list_validator(value):
    from django.core.exceptions import ValidationError

    parts = [p for p in value.replace(" ", "").split(",") if p]
    if not all(p.isdigit() and int(p) <= 1000 for p in parts):
        raise ValidationError(_("Enter whole numbers of days separated by commas, e.g. 180,90,30."))


class ModuleSettings(models.Model):
    """Single-row table holding which optional modules this council has switched on."""

    organisation_name = models.CharField(_("organisation name"), max_length=200, blank=True)
    department = models.CharField(_("department, for letters"), max_length=200, blank=True,
                                  help_text=_("For example: Estates and Property Services."))
    postal_address = models.TextField(_("postal address, for letters"), blank=True,
                                      help_text=_("Also the address for service of notices on the council."))
    letter_phone = models.CharField(_("phone, for letters"), max_length=40, blank=True)
    letter_email = models.EmailField(_("email, for letters"), blank=True)
    email_demands = models.BooleanField(
        _("email demands"), default=False,
        help_text=_("Offer to email each demand run to tenants through GOV.UK Notify. Emails are only sent once "
                    "IT has added the council's Notify key; until then they are recorded but not sent."))
    payment_link = models.CharField(
        _("payment link"), max_length=500, blank=True,
        help_text=_("The address of the council's online payment page, used for \"Pay now\" in demand emails. "
                    "You can include {reference}, {amount} and {account}, which are filled in for each tenant, "
                    "for example https://pay.example.gov.uk/rent?ref={reference}&amount={amount}"))
    website = models.CharField(_("website"), max_length=200, blank=True)
    rent_ledger_enabled = models.BooleanField(
        _("rent ledger"), default=False,
        help_text=_("Raise rent charges, keep tenant accounts and arrears, and export to the finance system."),
    )

    class Invoicing(models.TextChoices):
        PHAEMA = "phaema", _("PHAEMA numbers the invoices; finance records them")
        FINANCE = "finance", _("PHAEMA sends charges; the finance system raises the invoices")

    invoicing = models.CharField(_("who raises rent invoices"), max_length=10, choices=Invoicing.choices,
                                 default=Invoicing.PHAEMA)
    invoice_prefix = models.CharField(_("invoice number prefix"), max_length=10, default="PH",
                                      help_text=_("Put before invoice numbers, e.g. PH000123."))
    next_invoice_number = models.PositiveIntegerField(_("next invoice number"), default=1)
    vat_rate = models.DecimalField(_("standard VAT rate (%)"), max_digits=5, decimal_places=2, default=20,
                                   help_text=_("Added to rent on leases where the council has opted to tax."))
    rent_income_code = models.CharField(_("rent income code"), max_length=40, blank=True,
                                        help_text=_("Ledger code (cost centre and account) for rent income, "
                                                    "included in the finance export."))
    service_charge_income_code = models.CharField(
        _("service charge income code"), max_length=40, blank=True,
        help_text=_("Ledger code for service charge income, included in the finance export. "
                    "Leave blank to use the rent income code."))
    vat_code_standard = models.CharField(_("VAT code: standard rated"), max_length=10, default="S")
    vat_code_exempt = models.CharField(_("VAT code: exempt"), max_length=10, default="E")
    service_charges_enabled = models.BooleanField(_("service charge ledger"), default=False)
    maintenance_enabled = models.BooleanField(_("maintenance"), default=False)
    order_approval_limit = models.DecimalField(
        _("works orders needing approval (£, over)"), max_digits=10, decimal_places=2, default=5000,
        help_text=_("Works orders estimated above this need the job owner's supervisor to approve them."))
    compliance_enabled = models.BooleanField(_("compliance"), default=True)
    golden_thread_enabled = models.BooleanField(_("Golden Thread"), default=True)
    valuation_enabled = models.BooleanField(_("asset valuation"), default=False)
    space_enabled = models.BooleanField(
        _("space and costing"), default=False,
        help_text=_("Record which departments and outside organisations occupy each building, floor and room, "
                    "headcount and public use. Supports One Public Estate sharing."))
    space_costing_enabled = models.BooleanField(
        _("space and costing: show costs"), default=False,
        help_text=_("Also share each building's costs between its occupiers. Needs space and costing on."))
    open_data_enabled = models.BooleanField(
        _("publish open data"), default=False,
        help_text=_("Publish the Transparency Code land and assets list and the available property list at "
                    "/open-data/ under the Open Government Licence, without signing in."))

    class OsMapStyle(models.TextChoices):
        ROAD = "Road_3857", _("Road")
        OUTDOOR = "Outdoor_3857", _("Outdoor")
        LIGHT = "Light_3857", _("Light")

    os_maps_api_key = models.CharField(
        _("OS Maps API key"), max_length=100, blank=True,
        help_text=_("Your council's Ordnance Survey Data Hub key (free under the Public Sector Geospatial "
                    "Agreement). Leave blank to use OpenStreetMap only. The key is sent to users' browsers, "
                    "so restrict it to your PHAEMA web address in the OS Data Hub."),
    )
    os_map_style = models.CharField(_("OS map style"), max_length=20, choices=OsMapStyle.choices,
                                    default=OsMapStyle.ROAD)

    class TwoStep(models.TextChoices):
        OPTIONAL = "optional", _("Optional for everyone")
        ADMINISTRATORS = "administrators", _("Required for administrators")
        EVERYONE = "everyone", _("Required for everyone")

    two_step_required = models.CharField(
        _("two-step sign-in"), max_length=20, choices=TwoStep.choices, default=TwoStep.ADMINISTRATORS,
        help_text=_("Two-step sign-in (multi-factor authentication) asks for a code from an authenticator app "
                    "after the password. People it is required for must set it up the next time they sign in. "
                    "It is never required on a public test site."))

    sso_enabled = models.BooleanField(
        _("sign in with the council's own accounts"), default=False,
        help_text=_("Single sign-on with Microsoft 365 (Entra ID) or another OpenID Connect service. The installer "
                    "must first put the service's details in the server settings file; until then this does "
                    "nothing. People are matched to their PHAEMA account by email address."))

    class SsoPasswords(models.TextChoices):
        UNLINKED = "unlinked", _("Only people without a council account (such as outside consultants), "
                                 "and administrators as a fallback")
        EVERYONE = "everyone", _("Anyone, as well as their council account")

    sso_passwords = models.CharField(
        _("who can still sign in with a PHAEMA password"), max_length=20, choices=SsoPasswords.choices,
        default=SsoPasswords.UNLINKED,
        help_text=_("Applies once single sign-on is on. A person counts as having a council account from the "
                    "first time they sign in with it."))
    class AreaBasis(models.TextChoices):
        COMP = "comp", _("RICS Code of Measuring Practice (GIA, NIA, GEA)")
        IPMS = "ipms", _("IPMS: All Buildings (IPMS 1, 2 and 3)")

    area_basis = models.CharField(
        _("floor areas: show first"), max_length=4, choices=AreaBasis.choices, default=AreaBasis.COMP,
        help_text=_("Which set of floor areas PHAEMA uses first on property pages, reports, space costs and the "
                    "data standard export. Where a property has only the other set, that is used, always labelled "
                    "with its basis."))
    ocr_enabled = models.BooleanField(
        _("recognise text in scanned PDFs"), default=True,
        help_text=_("When a scanned PDF is added, PHAEMA reads the text in its pages in the background, on this "
                    "server, so Find in the document viewer works on it. The original scan is kept as it was. "
                    "Needs Tesseract on the server (it is in the standard installation)."))
    welsh_enabled = models.BooleanField(
        _("offer Welsh (Cymraeg)"), default=False,
        help_text=_("Shows an English | Cymraeg choice at the top of every page, so each person can use PHAEMA in "
                    "Welsh. The Welsh text is a draft awaiting review by a qualified translator: check it with "
                    "your council's translation service before relying on it."))
    strategy_review_years = models.PositiveSmallIntegerField(
        _("asset strategies are reviewed every (years)"), default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text=_("When an asset strategy is recorded without a review date, it is due for review this many "
                    "years later. The managing surveyor is prompted as it falls due."))
    outside_access_months = models.PositiveSmallIntegerField(
        _("outside users' access lasts (months)"), default=6,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text=_("When someone is marked as an outside user (for example a consultant or a tenant's agent) "
                    "and no end date is given, their access ends this many months later. An administrator can "
                    "change the date for each person."))
    sso_create_accounts = models.BooleanField(
        _("create a PHAEMA account at first council sign-in"), default=False,
        help_text=_("Off: only people an administrator has already added can sign in. On: anyone the sign-in "
                    "service lets through gets an account, with the roles and access areas from the sign-in "
                    "group mappings. Without a mapped group they see nothing until an administrator gives them "
                    "a role."))

    brand_colour = models.CharField(
        _("header colour"), max_length=7, blank=True,
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", _("Enter a colour like #1d3557."))],
        help_text=_("Your council's colour for the PHAEMA header, as a hex code such as #1d3557. "
                    "Choose a dark colour so the white header text stays readable. Leave blank for the default."),
    )

    reminder_days_review = models.CharField(
        _("rent review reminders (days before)"), max_length=60, default="180,90,30",
        validators=[days_list_validator])
    reminder_days_notice = models.CharField(
        _("break notice reminders (days before)"), max_length=60, default="180,90,30,7",
        validators=[days_list_validator])
    reminder_days_break = models.CharField(
        _("break date reminders (days before)"), max_length=60, default="30",
        validators=[days_list_validator])
    reminder_days_expiry = models.CharField(
        _("lease expiry reminders (days before)"), max_length=60, default="365,180,90",
        validators=[days_list_validator])
    reminder_days_option = models.CharField(
        _("option deadline reminders (days before)"), max_length=60, default="180,90,30,7",
        validators=[days_list_validator],
        help_text=_("For options to renew, extend or purchase. Rent-free periods ending use the other events' days."))
    reminder_days_other = models.CharField(
        _("other event reminders (days before)"), max_length=60, default="30,7",
        validators=[days_list_validator])
    overdue_reminders = models.BooleanField(
        _("weekly overdue reminders"), default=True,
        help_text=_("Every Monday, remind people of their overdue events."))

    def reminder_days(self, event_type):
        raw = getattr(self, f"reminder_days_{event_type}", None)
        if raw is None:
            raw = self.reminder_days_other
        raw = raw or ""
        return sorted({int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}, reverse=True)

    class Meta:
        verbose_name = _("module settings")
        verbose_name_plural = _("module settings")

    def __str__(self):
        return "Module settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # The settings row cannot be deleted.

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class AuditEntry(models.Model):
    """Immutable record of every create, change and delete on audited records."""

    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Changed")
        DELETE = "delete", _("Deleted")

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=Action.choices)
    changes = models.JSONField(default=dict, blank=True)
    via = models.CharField(_("made through"), max_length=120, blank=True, default="",
                           help_text=_("How the change arrived when not through the screens, such as an API token."))

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = _("audit entry")
        verbose_name_plural = _("audit entries")

    def __str__(self):
        return f"{self.get_action_display()} {self.object_repr} at {self.timestamp:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Audit entries cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit entries cannot be deleted.")


class StaffProfile(models.Model):
    """Extra details for a PHAEMA user: who supervises them and approves their work."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    job_title = models.CharField(_("job title"), max_length=100, blank=True)
    is_external = models.BooleanField(
        _("outside user"), default=False,
        help_text=_("Tick for anyone who is not council staff, such as a consultant, contractor or tenant's "
                    "agent. Their access ends automatically on the date below."))
    organisation = models.CharField(_("organisation"), max_length=200, blank=True,
                                    help_text=_("For an outside user, the firm or body they work for."))
    access_ends = models.DateField(
        _("access ends"), null=True, blank=True,
        help_text=_("The last day this person can sign in. For outside users, left blank it is filled in from "
                    "Module settings. For council staff it can be left blank."))
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="supervisees",
        verbose_name=_("supervisor and approver"),
        help_text=_("Approves this person's work at the approval points in cases, such as decisions on consents."))

    class Meta:
        verbose_name = _("staff details")
        verbose_name_plural = _("staff details")

    def __str__(self):
        return f"{self.user}"

    def save(self, *args, **kwargs):
        if self.is_external and not self.access_ends:
            from .outside import default_end

            self.access_ends = default_end()
        super().save(*args, **kwargs)


def supervisor_of(user):
    profile = StaffProfile.objects.filter(user=user).select_related("supervisor").first()
    return profile.supervisor if profile and profile.supervisor and profile.supervisor.is_active else None


class AccessArea(models.Model):
    """A named group of people and the optional modules they can open (for example Finance).

    Core PHAEMA (properties, leases, events, cases, documents) is open to everyone with a role. The role still
    decides what a person can change; an area decides which modules they can see."""

    MODULES = [("ledger", _("Rent ledger")), ("servicecharges", _("Service charges")),
               ("maintenance", _("Maintenance")), ("compliance", _("Compliance")),
               ("valuations", _("Asset valuation")), ("space", _("Space and costing")),
               ("spacecosts", _("Space costs: costs by occupier"))]

    code = models.SlugField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=60)
    description = models.CharField(_("description"), max_length=255, blank=True)
    modules = models.JSONField(_("modules"), default=list, blank=True,
                               help_text=_("The modules everyone in this area can open in full."))
    own_patch_finance = models.BooleanField(
        _("rent and service charges for their own patch"), default=False,
        help_text=_("Members see rent, arrears and service charges for the properties they manage, those of everyone "
                    "they supervise (the whole chain) and anyone they are covering for."))
    finance_actions = models.BooleanField(
        _("can raise rent, credit notes and finance exports"), default=False,
        help_text=_("For members whose role lets them change records (Surveyors). Administrators can always."))
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="access_areas",
                                     verbose_name=_("members"))
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("access area")
        verbose_name_plural = _("access areas")

    def __str__(self):
        return self.name

    def module_names(self):
        labels = dict(self.MODULES)
        return [str(labels[m]) for m in self.modules if m in labels]


class Cover(models.Model):
    """One person covering another's work for a while: they see the other person's patch as their own."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="covering",
                             verbose_name=_("covering"))
    covered = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="covered_by",
                                verbose_name=_("covering for"))
    starts_on = models.DateField(_("from"))
    ends_on = models.DateField(_("until"), help_text=_("Cover ends automatically after this day."))
    reason = models.CharField(_("reason"), max_length=200, blank=True, help_text=_("For example: annual leave."))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ends_on", "pk"]
        verbose_name = _("cover")
        verbose_name_plural = _("cover")

    def __str__(self):
        return f"{self.user} covering for {self.covered} until {self.ends_on:%d/%m/%Y}"


class AccountRequest(models.Model):
    """Someone asking for a sign-in to a public test site. Emailed to the site's contact and kept here."""

    name = models.CharField(_("name"), max_length=120)
    email = models.EmailField(_("email address"))
    organisation = models.CharField(_("organisation"), max_length=150, blank=True)
    reason = models.TextField(_("what they would like to try"), blank=True)
    requested_at = models.DateTimeField(_("requested"), auto_now_add=True)
    done = models.BooleanField(_("account set up"), default=False)

    class Meta:
        ordering = ["done", "-requested_at"]
        verbose_name = _("test account request")
        verbose_name_plural = _("test account requests")

    def __str__(self):
        return f"{self.name} <{self.email}>"


class TwoStepDevice(models.Model):
    """A person's authenticator app for two-step sign-in (TOTP, RFC 6238). Not in the change log, which would copy
    the secret; turning two-step sign-in on and off is logged against the user instead."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_step")
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(auto_now_add=True)
    last_step = models.BigIntegerField(default=0, help_text="The last time step used, so a code works only once.")

    class Meta:
        verbose_name = _("two-step sign-in")
        verbose_name_plural = _("two-step sign-in")

    def __str__(self):
        return f"Two-step sign-in for {self.user}"


class RecoveryCode(models.Model):
    """One-time codes for signing in without the authenticator app. Only a hash is kept."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Recovery code for {self.user}"


class TextCopy(models.Model):
    """A searchable copy of a scanned PDF: the same pages with the recognised text laid invisibly under each page
    image (OCR by Tesseract through OCRmyPDF). The original stays the document of record; the viewer shows this
    copy so that Find works. Keyed by the stored name of the original, so it serves any document model."""

    class Status(models.TextChoices):
        WAITING = "waiting", _("Waiting")
        DONE = "done", _("Text recognised")
        HAS_TEXT = "has_text", _("Already has text")
        TOO_BIG = "too_big", _("Too many pages")
        FAILED = "failed", _("Could not be read")

    source = models.CharField(_("original file"), max_length=255, unique=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.WAITING,
                              db_index=True)
    copy = models.CharField(_("searchable copy"), max_length=255, blank=True)
    pages = models.PositiveIntegerField(_("pages"), null=True, blank=True)
    pages_scanned = models.PositiveIntegerField(_("pages without text"), null=True, blank=True)
    characters = models.PositiveIntegerField(_("characters recognised"), null=True, blank=True)
    poor = models.BooleanField(_("hard to read"), default=False,
                               help_text=_("Little text was found on the scanned pages: Find may miss words."))
    error = models.TextField(_("what went wrong"), blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    queued_at = models.DateTimeField(_("queued"), auto_now_add=True)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)

    class Meta:
        verbose_name = _("scanned document")
        verbose_name_plural = _("scanned documents")
        ordering = ["-queued_at"]

    def __str__(self):
        return self.source.rsplit("/", 1)[-1]


class ApiToken(models.Model):
    """A key for another system to use the API: limited to what it may do and which records it may reach, with an
    end date, and cancellable on its own. It acts as its account, so it never has more than that account's role.
    Only a hash of the key is kept; the key itself is shown once, when it is made."""

    class Access(models.TextChoices):
        READ = "read", _("Read only")
        CHANGE = "change", _("Read and change")

    RESOURCES = [  # the API router's names for each part
        ("property", _("Properties")),
        ("title", _("Titles")),
        ("lease", _("Leases and licences")),
        ("party", _("Parties")),
    ]
    MAX_DAYS = 731  # two years

    name = models.CharField(_("name"), max_length=80,
                            help_text=_("What it is for, such as \"GIS layers for QGIS\" or \"Nightly export to finance\"."))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens",
                             verbose_name=_("acts as"),
                             help_text=_("The account the token acts for. It can never do more than this account's "
                                         "role allows. A separate account with the Viewer role is best for "
                                         "read-only systems."))
    access = models.CharField(_("access"), max_length=10, choices=Access.choices, default=Access.READ)
    resources = models.JSONField(_("parts of the API"), default=list, blank=True,
                                 help_text=_("Leave all unticked for every part."))
    expires_on = models.DateField(_("ends on"), help_text=_("The last day it works. At most two years ahead."))
    prefix = models.CharField(_("key starts"), max_length=16, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(_("made"), auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
                                   on_delete=models.SET_NULL, related_name="+", verbose_name=_("made by"))
    last_used_at = models.DateTimeField(_("last used"), null=True, blank=True, editable=False)
    last_used_from = models.CharField(_("last used from"), max_length=45, blank=True, editable=False)
    revoked_at = models.DateTimeField(_("cancelled"), null=True, blank=True, editable=False)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
                                   on_delete=models.SET_NULL, related_name="+", verbose_name=_("cancelled by"))

    class Meta:
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def hash(key):
        import hashlib

        return hashlib.sha256(key.encode()).hexdigest()

    def issue(self):
        """Make a new key, keep its hash and return the key. Call before the first save."""
        import secrets

        key = "phaema_" + secrets.token_urlsafe(32)
        self.prefix = key[:12]
        self.key_hash = self.hash(key)
        return key

    def is_live(self, today=None):
        from datetime import date

        return self.revoked_at is None and self.expires_on >= (today or date.today())

    def allows(self, resource):
        return not self.resources or resource in self.resources


class OutgoingEmail(models.Model):
    """An email PHAEMA has sent, or recorded for sending, through GOV.UK Notify: kept so the estates team can see
    what each tenant was sent, when, and whether it went."""

    class Status(models.TextChoices):
        RECORDED = "recorded", _("Recorded, not sent (no Notify key)")
        SENT = "sent", _("Sent to GOV.UK Notify")
        FAILED = "failed", _("Not sent: Notify refused it")

    kind = models.CharField(_("kind"), max_length=30)
    to = models.EmailField(_("to"))
    subject = models.CharField(_("subject"), max_length=250)
    body = models.TextField(_("body"))
    lease = models.ForeignKey("leases.Lease", verbose_name=_("agreement"), null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="emails")
    demand_run = models.ForeignKey("ledger.DemandRun", verbose_name=_("demand run"), null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="emails")
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.RECORDED)
    notify_id = models.CharField(_("Notify reference"), max_length=60, blank=True)
    error = models.TextField(_("error"), blank=True)
    created_at = models.DateTimeField(_("made"), auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("by"), null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    sent_at = models.DateTimeField(_("sent"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("email to a tenant")
        verbose_name_plural = _("emails to tenants")

    def __str__(self):
        return f"{self.subject} to {self.to}"
