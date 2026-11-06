#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds the PHAEMA project website: what is being built, what it does, why open source, the roadmap,
links to the test site, training, manuals and code, and how to take part.

    python3 website/build.py            # writes website/index.html (a complete page to host anywhere)
    python3 website/build.py --artifact # writes the body-only variant for a claude.ai artifact preview

Edit the LINKS, ROADMAP and other lists below, then rebuild.
"""
import html
import sys
from pathlib import Path

AS_OF = "November 2026"

# Where things live. An empty string shows "coming soon" instead of a link.
LINKS = {
    "test_site": "https://demo.phaema.co.uk",
    "contact": "stuart@phaema.co.uk",  # an email address for enquiries; leave empty to point people to GitHub
    "repo": "https://github.com/phaema/phaema-app",
    "issues": "https://github.com/phaema/phaema-app/issues",
    "new_issue": "https://github.com/phaema/phaema-app/issues/new",
    "roadmap": "https://github.com/phaema/phaema-app/blob/main/docs/roadmap.md",
    "contributing": "https://github.com/phaema/phaema-app/blob/main/CONTRIBUTING.md",
    "licence": "https://github.com/phaema/phaema-app/blob/main/LICENSE",
    "licensing": "https://github.com/phaema/phaema-app/blob/main/LICENSING.md",
    "help_pages": "https://github.com/phaema/phaema-app/tree/main/apps/help/pages",
    "mac_setup": "https://github.com/phaema/phaema-app/blob/main/docs/setup-mac.md",
    "training": "https://claude.ai/artifact/7wkjDTdrtqLZwuf3zo79VE",
    "user_manual": "https://claude.ai/artifact/CTsfQjqNtVH4qBZjg5QjRo",
    "technical_manual": "https://claude.ai/artifact/8sTYq44xi5Ps3NuVFDrEm2",
    "test_programme": "https://claude.ai/artifact/7jMMkZAmCZMEgvEfYhhiK1",
    "integrations": "https://claude.ai/artifact/8nri1SACnG6YVXkp1HSJgU",
    "tour": "tour.html",
    "security": "https://github.com/phaema/phaema-app/blob/main/SECURITY.md",
}

PILOT_SUBJECT = "PHAEMA pilot council"

# What PHAEMA brings together (title, description)
BRINGS_TOGETHER = [
    ("Property terrier", "The register of land and buildings, mapped from Land Registry boundaries, with UPRNs, floor "
     "areas and titles."),
    ("Lease and key-date records", "Leases, licences and wayleaves, with rent reviews, breaks, expiries and notice "
     "deadlines that remind the right people."),
    ("Compliance and the Golden Thread", "Certificates, remedial actions and building information for every "
     "building."),
    ("Asset valuation", "The rolling programme, Red Book records and the year-end schedule for finance."),
    ("Projects, acquisitions and disposals", "Gateways, budgets, risks and the register changes completion needs."),
    ("Rents and service charges, if wanted", "Optional ledgers that feed the council's finance system, or leave this "
     "to the systems it already has."),
]

WHO_FOR = [
    ("District and borough councils", "With a small estates team and an ageing terrier or spreadsheets."),
    ("Smaller unitary authorities", "That want one system without enterprise licence costs."),
    ("Councils merging under local government reorganisation", "Which must combine two or more estates systems. "
     "PHAEMA gives the new council one system it owns, with spreadsheet imports to bring each council's records "
     "across."),
    ("Combined authorities and development bodies", "Running acquisitions, disposals and regeneration programmes."),
]

WAYS = [
    ("Run it yourselves", "The council's IT team installs PHAEMA with one command on its own servers or on UK or EU "
     "cloud hosting."),
    ("Have a supplier host it", "Any IT supplier can host and support PHAEMA under the open licence, so the council "
     "can change supplier without changing system."),
    ("Become a pilot council", "Pilot councils run the test programme with their own staff and their own data, and "
     "decide which connectors come first. The project helps with setting up, bringing data across and training."),
]

SECURE_NOW = [
    ("Two-step sign-in", "A code from an authenticator app after the password, required for administrators by "
     "default and for everyone if the council chooses. Single-use recovery codes, and administrators can reset a "
     "lost phone."),
    ("Access by role and area", "Roles decide what people can change and access areas decide what they can open, "
     "checked on the server for every page, download, report and API call."),
    ("A log of every change", "Who changed what and when, across properties, leases, cases, finance, access and "
     "sign-in."),
    ("Your data, your hosting", "PHAEMA runs on the council's own servers or UK or EU hosting, and sends nothing to "
     "the project."),
    ("Secure servers by default", "The installer sets up HTTPS, a firewall, automatic security updates and nightly "
     "backups."),
    ("Open to inspection", "Every line of code, every automated test and the security policy are public."),
]

BEFORE_LIVE = [
    "An independent penetration test by a CREST or CHECK accredited tester, with a summary of the results published",
    "Single sign-on with the council's own accounts, such as Microsoft Entra ID, so the council's own sign-in rules "
    "apply",
    "An independent accessibility audit against WCAG 2.2 AA",
    "Templates for a data protection impact assessment and record of processing, and answers to common security "
    "questionnaires",
    "Numbered releases, with release notes and a security support period for each",
]

CAPABILITIES = [
    ("Property register", "Estates, sites, buildings and units in a tree, with UPRN and USRN, floor areas to the RICS "
     "measurement codes, titles, photos, disposals and a map drawn from Land Registry INSPIRE parcels."),
    ("Leases and key dates", "Leases, licences and wayleaves, let out or held. Rent reviews, breaks, expiries and "
     "notice deadlines become events with email reminders and a calendar feed."),
    ("Cases and approvals", "Consents, renewals, dilapidations and enquiries with stages, tasks and statutory target "
     "dates. Supervisors approve decisions, with conflicts of interest declared first."),
    ("Projects", "Developments, acquisitions, disposals and programmes taken through four gateways, with milestones, a "
     "budget by financial year, risks and a checklist of the register changes completion needs."),
    ("Document library", "Thirty letter and notice templates, from consent letters to section 25 notice particulars, "
     "filled in from the case and downloaded to Word. Councils can adapt them and add their own."),
    ("Rents and arrears", "Demand runs, VAT, credit notes, receipts imported from finance, aged arrears and an export "
     "file for the finance system."),
    ("Service charges", "Budgets, apportionment by floor area with caps, actual costs and year-end reconciliation on "
     "the RICS service charge timetable."),
    ("Maintenance", "Repairs with target dates, who pays under the lease, works orders and their approval, recharges, "
     "planned maintenance and component lifecycles."),
    ("Compliance", "Fire, gas, electrical, water, asbestos, lift and EPC certificates with remedial actions, Golden "
     "Thread information and site hazards shown before every visit."),
    ("Asset valuation", "The rolling valuation programme, internal or external valuers, Red Book records, impairment "
     "prompts and the year-end schedule for finance."),
    ("People and access", "Four roles, access areas that decide who sees each module, supervision chains, cover for "
     "absence and a hand-over of a leaver's work in one step."),
    ("Reports and open data", "Ready-made and custom reports to Excel and CSV, the Transparency Code land and assets "
     "list, an open API and a change log of every edit."),
]

OPEN_SOURCE = [
    ("No licence fees", "Any council can download and run PHAEMA. Money goes on hosting, support and improvements "
     "that every council then shares."),
    ("No lock-in", "Data sits in an open PostgreSQL database with exports to CSV, Excel and GeoJSON. Any supplier, or "
     "the council's own IT team, can host and support it, so changing supplier does not mean changing system."),
    ("Open to inspection", "Every line of code can be read, tested and security-reviewed by the council or anyone it "
     "trusts. Nothing is hidden behind a vendor's contract."),
    ("Build once, share everywhere", "When one council pays for a feature, every council gets it. Improvements come "
     "back to the shared code under the AGPL licence, so nobody can take it private."),
    ("Follows government guidance", "The Technology Code of Practice asks the public sector to be open, use open "
     "standards and make code reusable. PHAEMA is built on the GOV.UK Design System and aims for WCAG 2.2 AA."),
    ("Your data, your hosting", "Councils choose where PHAEMA runs: their own servers or UK or EU hosting. Planned "
     "connectors use open standards, so they work with Microsoft 365 or with open-source alternatives."),
]

# (status, title, items)
ROADMAP = [
    ("done", "Built", [
        "Property register, map and Land Registry boundaries",
        "Leases, key dates, reminders and calendar feed",
        "Cases, approvals and the document library",
        "Rent ledger and service charges",
        "Maintenance, compliance and the Golden Thread",
        "Asset valuation",
        "Projects with gateways, budgets, risks and completion",
        "Access areas, cover and hand-over of work",
        "Reports, imports, open data and API",
        "Help, user and technical manuals, and e-learning for five roles",
        "One-step server installation with HTTPS and nightly backups",
        "A public test site, reset every 48 hours",
        "Two-step sign-in (multi-factor authentication) and a published security policy",
    ]),
    ("now", "Now: testing", [
        "A major test programme run by council staff",
        "Feedback from testers on the public test site",
        "Fixing what testing finds, and preparing for an independent penetration test and accessibility audit",
    ]),
    ("next", "Next: connectors", [
        "Single sign-on with the council's own accounts",
        "Ordnance Survey address, UPRN and EPC lookups",
        "Map layers for QGIS, ArcGIS and other GIS",
        "Texts and letters to tenants through GOV.UK Notify",
        "Notifications in Teams, Matrix or Nextcloud Talk",
        "Documents kept in SharePoint or Nextcloud",
    ]),
    ("later", "Later", [
        "Tenant and contractor portals",
        "Condition surveys and lifecycle planning",
        "Full Golden Thread information management",
        "Live finance, legal and CRM connectors",
        "Welsh translation",
    ]),
]

# (title, description, link key, link text)
RESOURCES = [
    ("Security policy", "What protects PHAEMA today, the known gaps, and how to report a security problem.",
     "security", "Read the security policy"),
    ("Tour", "A self-running, clickable tour of every part of PHAEMA, for a first look or a screen at an event.",
     "tour", "Watch the tour"),
    ("Test site", "Try PHAEMA with fictional data: a council estate, leases, cases and projects to explore. "
     "Request a sign-in on the site; the data is reset every 48 hours.",
     "test_site", "Open the test site"),
    ("Training", "Interactive courses for surveyors, finance, maintenance, administrators and viewers, using the "
     "real screens.", "training", "Start the training"),
    ("User manual", "How to do each task in PHAEMA, with worked examples from the demonstration data.",
     "user_manual", "Read the user manual"),
    ("Help pages", "The same help that appears inside PHAEMA, readable on GitHub.", "help_pages",
     "Browse the help"),
    ("Technical manual", "Architecture, frameworks, data model, security, hosting and how to extend PHAEMA.",
     "technical_manual", "Read the technical manual"),
    ("Test programme", "The tests council staff run before go-live, with expected results to record.",
     "test_programme", "See the test programme"),
    ("Source code", "The full application under the AGPL, with its automated tests and installation scripts.",
     "repo", "Go to GitHub"),
    ("Roadmap", "What is built, what is being tested and what comes next.", "roadmap", "Read the roadmap"),
    ("Integrations review", "The market review behind the connectors plan, including open-source GIS and Microsoft "
     "365 alternatives.", "integrations", "Read the review"),
]

# (who, what they can do)
INVOLVE = [
    ("Councils", "Try the test site, run parts of the test programme with your own staff, and tell us what your "
     "estates team needs. Pilot councils run PHAEMA with their own data, get help setting it up, and shape what is "
     "built next."),
    ("Surveyors and estates staff", "Check that the processes match how you work: rent reviews, the 1954 Act, "
     "service charges, valuations and casework. Practical corrections from practitioners are the most valuable "
     "contribution of all."),
    ("Developers", "Pick up an issue, fix a bug or build a connector. PHAEMA is Django and PostGIS with an automated "
     "test suite; contributions are signed off under the Developer Certificate of Origin."),
    ("GIS and data teams", "Help shape the map layers, OS and EPC lookups and open data output so PHAEMA fits "
     "the systems you already run."),
    ("Suppliers", "Host and support PHAEMA for councils. The code is free for you to use; the AGPL asks only that "
     "your improvements are shared."),
]


def esc(s):
    return html.escape(s, quote=True)


def link(key, text, cls=""):
    url = LINKS.get(key, "")
    if not url:
        return f'<span class="soon">Coming soon</span>'
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{esc(url)}">{esc(text)}</a>'


def capability_list():
    return "\n".join(f'      <article><h3>{esc(t)}</h3><p>{esc(d)}</p></article>' for t, d in CAPABILITIES)


def open_source_list():
    return "\n".join(f'      <div><h3>{esc(t)}</h3><p>{esc(d)}</p></div>' for t, d in OPEN_SOURCE)


def roadmap_columns():
    out = []
    for status, title, items in ROADMAP:
        lis = "".join(f"<li>{esc(i)}</li>" for i in items)
        out.append(f'      <section class="stage stage--{status}" aria-label="{esc(title)}">'
                   f'<h3><span class="stage__mark" aria-hidden="true"></span>{esc(title)}</h3><ul>{lis}</ul></section>')
    return "\n".join(out)


def resource_list():
    rows = []
    for title, desc, key, text in RESOURCES:
        rows.append(f'      <li><h3>{esc(title)}</h3><p>{esc(desc)}</p><p class="go">{link(key, text)}</p></li>')
    return "\n".join(rows)


def titled_list(items, tag="div"):
    return "\n".join(f'      <{tag}><h3>{esc(t)}</h3><p>{esc(d)}</p></{tag}>' for t, d in items)


def plain_list(items):
    return "".join(f"<li>{esc(i)}</li>" for i in items)


def pilot_href():
    from urllib.parse import quote

    if LINKS["contact"]:
        return esc(f"mailto:{LINKS['contact']}?subject={quote(PILOT_SUBJECT)}")
    return esc(LINKS["new_issue"])


def involve_list():
    return "\n".join(f'      <div><h3>{esc(w)}</h3><p>{esc(d)}</p></div>' for w, d in INVOLVE)


def test_site_cta():
    if LINKS["test_site"]:
        return f'<a class="button" href="{esc(LINKS["test_site"])}">Try the test site</a>'
    return '<a class="button" href="#resources">Training and manuals</a>'


def contact_line():
    if LINKS["contact"]:
        e = esc(LINKS["contact"])
        return (f'<p>Email <a class="copy" href="mailto:{e}">{e}</a> with questions, ideas or offers of help, '
                f'or raise an issue on GitHub. Councils interested in becoming a pilot council, and suppliers interested in hosting PHAEMA, are '
                f'especially welcome.</p>')
    return '<p>The quickest way to reach the project is to raise an issue on GitHub: questions, ideas and offers of help are all welcome there.</p>'


BODY = r'''<div class="top"><div class="wrap top__inner">
  <a class="brand" href="#about" aria-label="PHAEMA home"><span class="brand__mark" aria-hidden="true"></span>PHAEMA</a>
  <nav aria-label="Sections"><ul class="nav">
    <li><a href="#about">About</a></li>
    <li><a href="#councils">For councils</a></li>
    <li><a href="#capabilities">What it does</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#open-source">Why Open Source</a></li>
    <li><a href="tour.html">Tour</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#resources">Resources</a></li>
    <li><a href="#take-part">Take part</a></li>
  </ul></nav>
</div></div>

<main id="main">
<section class="view" id="about" aria-labelledby="h-about">
  <div class="wrap hero">
    <div class="hero__text">
      <p class="kicker">Open-source Property Holding and Estate Management Application for councils in England and Wales</p>
      <h1 id="h-about">One open system for council estates.</h1>
      <p class="lede">Many councils run their estate across a terrier, a lease database, compliance spreadsheets, a valuation workbook and separate project trackers. PHAEMA (Property Holding and Estate Management Application) brings the property register, leases, casework, projects, rents, service charges, repairs, compliance and asset valuations into one system, built around the property and the lease. There is no licence fee, the code is open, and councils are invited to pilot it.</p>
      <div class="cta">
        <a class="button" href="__PILOT__">Become a pilot council</a>
        __TEST_CTA__
        <a class="button button--quiet" href="tour.html">Watch the tour</a>
      </div>
      <p class="status-line"><span class="pill">Alpha</span> In testing, __ASOF__. Not yet ready for live estate management.</p>
    </div>
    <figure class="plan">
      <div class="plan__sheet"><img src="img/my-work.jpg" width="1920" height="1230" alt="PHAEMA's My work dashboard for a surveyor: items that need attention, upcoming events, open cases and the properties they manage."></div>
      <figcaption><span class="plan__key" aria-hidden="true"></span>My work: one surveyor's overdue items, next 90 days, cases and properties.</figcaption>
    </figure>
  </div>

  <div class="wrap band">
    <h2>Where the project is</h2>
    <p class="band__lead">All twelve modules are built and documented, with about 240 automated tests, a user manual, a technical manual and e-learning for five roles. A public test site is running. Next come testing by pilot councils, independent security and accessibility checks, and connectors to the systems councils already use.</p>
    <p><a href="#roadmap">See the roadmap</a></p>
  </div>

  <div class="wrap four">
    <div><h3>Free to use</h3><p>No licence fee, ever. Councils pay only for hosting and any support they choose, and can run it themselves or have any supplier host it.</p></div>
    <div><h3>Built by surveyors</h3><p>Covers the day-to-day work of public sector estate and asset management, to the professional standards: heads of terms to the RICS leasing code, 1954 Act notice dates, service charges to the RICS 2nd edition, Red Book valuation records and Golden Thread building information.</p></div>
    <div><h3>Accessible by design</h3><p>Built on the GOV.UK Design System and aiming for WCAG 2.2 AA, with dark, high-contrast and large-text settings.</p></div>
    <div><h3>Secure by design</h3><p>Two-step sign-in, access by role and area, a log of every change, and hosting in the UK or EU. <a href="#security">What is done, and what comes before live use</a>.</p></div>
  </div>
</section>

<section class="view" id="councils" aria-labelledby="h-councils">
  <div class="wrap">
    <h2 id="h-councils">PHAEMA for councils</h2>
    <p class="lede">Estates teams often work across several systems and a lot of spreadsheets, each bought, supported and kept up to date separately. PHAEMA puts the estate in one place, with no licence fee, so the money goes on hosting, support and improvements that every council shares.</p>
    <h3 class="sub">What it brings together</h3>
    <div class="benefits">
__BRINGS__
    </div>
    <h3 class="sub">Who it is for</h3>
    <div class="involve two">
__WHO_FOR__
    </div>
    <h3 class="sub">Ways to use PHAEMA</h3>
    <div class="involve">
__WAYS__
    </div>
    <div class="band">
      <h3>What it costs</h3>
      <p>No licence fee, now or later. The costs are a modest server, the staff time to bring records across and train people, and any support the council chooses to buy.</p>
      <div class="cta">
        <a class="button" href="__PILOT__">Become a pilot council</a>
        <a class="button button--quiet" href="#security">Read about security</a>
      </div>
    </div>
  </div>
</section>

<section class="view" id="capabilities" aria-labelledby="h-capabilities">
  <div class="wrap">
    <h2 id="h-capabilities">What PHAEMA does</h2>
    <p class="lede">The optional modules (rents, service charges, maintenance, compliance and valuation) can each be switched on when a council is ready, or left to the systems it already has.</p>
    <div class="modules">
__CAPABILITIES__
    </div>
    <div class="shots">
      <figure><img src="img/project.jpg" width="1920" height="1230" loading="lazy" alt="A development project at its business case phase, showing the five phases, project details and a map."><figcaption>A development project at its business case gateway.</figcaption></figure>
      <figure><img src="img/case.jpg" width="1920" height="1230" loading="lazy" alt="A licence for alterations case at the assessing stage, with key dates, target date and linked agreement."><figcaption>A consent case with its statutory target date.</figcaption></figure>
      <figure><img src="img/compliance.jpg" width="1920" height="1230" loading="lazy" alt="The compliance overview listing certificates by status, with expired and missing certificates first."><figcaption>Compliance across every building.</figcaption></figure>
      <figure><img src="img/estate.jpg" width="1920" height="1230" loading="lazy" alt="The whole estate dashboard with vacancy, rent roll and lease event figures."><figcaption>The whole estate at a glance.</figcaption></figure>
    </div>
    <p class="fine">Screenshots show fictional demonstration data.</p>
  </div>
</section>

<section class="view" id="security" aria-labelledby="h-security">
  <div class="wrap">
    <h2 id="h-security">Security and assurance</h2>
    <p class="lede">What protects PHAEMA today, what will be done before councils use it for live work, and how a council can check it for itself.</p>
    <h3 class="sub">In place now</h3>
    <div class="benefits">
__SECURE_NOW__
    </div>
    <div class="band split">
      <div>
        <h3>Before live use</h3>
        <ul class="ticks">__BEFORE_LIVE__</ul>
      </div>
      <div>
        <h3>Check it yourself</h3>
        <p>Councils and their suppliers are welcome to review the code or test their own installation. Please report security problems privately to __EMAIL_LINK__.</p>
        <p>__SECURITY_LINK__ · __TECH_LINK__</p>
      </div>
    </div>
  </div>
</section>

<section class="view" id="open-source" aria-labelledby="h-open-source">
  <div class="wrap">
    <h2 id="h-open-source">Why open source</h2>
    <p class="lede">Councils already pay, separately, for estates systems that do much the same job. Open source lets them pay once, together, and own the result.</p>
    <div class="benefits">
__OPEN_SOURCE__
    </div>
    <div class="band licence">
      <h3>The licence</h3>
      <p>PHAEMA is licensed under the GNU Affero General Public License v3.0. Anyone may use, study, change and share it. Anyone who runs a changed version as an online service must publish their changes under the same licence, which keeps every improvement available to all councils.</p>
      <p>__LICENCE_LINK__ · __LICENSING_LINK__</p>
    </div>
  </div>
</section>

<section class="view" id="roadmap" aria-labelledby="h-roadmap">
  <div class="wrap">
    <h2 id="h-roadmap">Roadmap</h2>
    <p class="lede">What is built, what is being tested now, and what comes next. Councils taking part help decide the order.</p>
    <div class="stages">
__ROADMAP__
    </div>
    <p>Connectors will be one optional module, off by default and built on open standards, so the same connector works with Microsoft 365 or with open-source alternatives such as Nextcloud, Matrix and Keycloak.</p>
    <p>__ROADMAP_LINK__ · __INTEGRATIONS_LINK__</p>
  </div>
</section>

<section class="view" id="resources" aria-labelledby="h-resources">
  <div class="wrap">
    <h2 id="h-resources">Resources</h2>
    <p class="lede">Everything you need to try PHAEMA, learn it, test it or run it.</p>
    <ul class="resources">
__RESOURCES__
    </ul>
    <div class="band run">
      <h3>Run it on your own computer</h3>
      <p>You need Docker (or Colima on a Mac) and Git. Mac users can follow the __MAC_LINK__.</p>
      <pre class="scroll" tabindex="0"><code>git clone https://github.com/phaema/phaema-app.git
cd phaema-app
./phaema.sh start
./phaema.sh admin        # create your sign-in</code></pre>
    </div>
  </div>
</section>

<section class="view" id="take-part" aria-labelledby="h-take-part">
  <div class="wrap">
    <h2 id="h-take-part">Take part</h2>
    <p class="lede">PHAEMA is built by a chartered surveyor with a very small team. Every tester, reviewer and contributor makes it better for every council.</p>
    <div class="involve">
__INVOLVE__
    </div>
    <div class="band">
      <h3>Get in touch</h3>
      __CONTACT__
      <div class="cta">
        <a class="button" href="__NEW_ISSUE__">Raise an issue</a>
        <a class="button button--quiet" href="__CONTRIBUTING__">How to contribute</a>
      </div>
    </div>
  </div>
</section>
</main>

<footer class="foot"><div class="wrap">
  <p>PHAEMA is free software under the GNU Affero General Public License v3.0. It is in alpha and not yet ready for live estate management. Screenshots show fictional demonstration data. Updated __ASOF__. Contact: __EMAIL__.</p>
</div></footer>

<script>
(function () {
  var views = Array.prototype.slice.call(document.querySelectorAll('.view'));
  var links = Array.prototype.slice.call(document.querySelectorAll('.nav a'));
  function show() {
    var id = (location.hash || '#about').slice(1);
    var el = document.getElementById(id);
    if (!el || !el.classList.contains('view')) id = 'about';
    views.forEach(function (v) { v.hidden = v.id !== id; });
    links.forEach(function (a) { if (a.getAttribute('href') === '#' + id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  }
  window.addEventListener('hashchange', function () { show(); window.scrollTo(0, 0); });
  show();
  window.scrollTo(0, 0);
})();
</script>
'''

STYLE = r'''<title>PHAEMA</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap">
<style>
/* Layout: a single-column estates "terrier" page; the one bold device is the red edging of a title plan. */
:root {
  --paper: #f6f8f7; --sheet: #ffffff; --ink: #13233a; --muted: #4a5864; --line: #cfd6d8;
  --edge: #c1272d; --survey: #2c6a3e; --link: #1b5c89; --tint: #e8efec; --focus: #ffdd00; --on-survey: #ffffff;
  --amber: #8a5a00;
  --display: "Bricolage Grotesque", "Arial Narrow", Arial, sans-serif;
  --body: "Atkinson Hyperlegible", Verdana, Arial, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #0e151d; --sheet: #15202b; --ink: #e6ecef; --muted: #a9b5be; --line: #2d3b48;
  --edge: #ff6f69; --survey: #7fc78f; --link: #86bfe9; --tint: #1a2732; --on-survey: #0e151d; --amber: #f2c46d; color-scheme: dark; } }
:root[data-theme="dark"] {
  --paper: #0e151d; --sheet: #15202b; --ink: #e6ecef; --muted: #a9b5be; --line: #2d3b48;
  --edge: #ff6f69; --survey: #7fc78f; --link: #86bfe9; --tint: #1a2732; --on-survey: #0e151d; --amber: #f2c46d; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 1.0625rem/1.6 var(--body); }
.wrap { max-width: 1140px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
a { color: var(--link); text-underline-offset: .15em; }
a:hover { text-decoration-thickness: 3px; }
a:focus-visible, button:focus-visible, .scroll:focus-visible {
  outline: 3px solid var(--focus); outline-offset: 0; background-color: var(--focus); color: #0b0c0c; box-shadow: 0 4px 0 #0b0c0c; }
.scroll:focus-visible { background: none; box-shadow: none; }
h1, h2, h3 { font-family: var(--display); line-height: 1.1; text-wrap: balance; margin: 0 0 .5em; font-weight: 800; }
h1 { font-size: clamp(2.3rem, 5.2vw, 4rem); letter-spacing: -.02em; }
h2 { font-size: clamp(1.75rem, 3.4vw, 2.5rem); letter-spacing: -.01em; }
h3 { font-size: 1.3rem; font-weight: 600; }
p { margin: 0 0 1em; max-width: 68ch; }
.skip { position: absolute; left: -9999px; top: 0; z-index: 20; }
.skip:focus { left: 16px; top: 8px; background: var(--focus); color: #0b0c0c; padding: 8px 12px; }

.top { background: var(--ink); color: var(--paper); position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--ink); }
.top__inner { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 28px; padding-block: 12px; }
.brand { color: var(--paper); text-decoration: none; font-family: var(--display); font-weight: 800; font-size: 1.35rem; letter-spacing: .14em; display: inline-flex; align-items: center; gap: 10px; }
.brand__mark { width: 18px; height: 14px; border: 2.5px solid var(--edge); display: inline-block; }
.nav { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 20px; margin: 0; padding: 0; }
.nav a { color: var(--paper); font-weight: 700; font-size: 1rem; }
.nav a[aria-current="page"] { text-decoration: none; border-bottom: 3px solid var(--edge); }

.view { padding-block: 48px 64px; scroll-margin-top: 120px; }
.hero { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 48px; align-items: center; }
.hero__text { min-width: 0; }
.kicker { color: var(--muted); font-size: 1rem; margin-bottom: .75em; }
.lede { font-size: 1.2rem; }
.fine { font-size: .92rem; color: var(--muted); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; margin: 1.5em 0; }
.button { display: inline-block; background: var(--survey); color: var(--on-survey); font-weight: 700; text-decoration: none; padding: 12px 20px; border-radius: 3px; box-shadow: 0 3px 0 rgba(0,0,0,.35); }
.button--quiet { background: transparent; color: var(--link); box-shadow: inset 0 0 0 2px var(--link); }
.status-line { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; color: var(--muted); font-size: .98rem; }
.pill { font-weight: 700; font-size: .85rem; padding: 2px 10px; border: 2px solid var(--amber); color: var(--amber); letter-spacing: .06em; text-transform: uppercase; }

/* The title plan: a screenshot "edged red", as on a Land Registry plan */
.plan { margin: 0; min-width: 0; }
.plan__sheet { background: var(--sheet); border: 1px solid var(--line); padding: 14px; position: relative; }
.plan__sheet::after { content: ""; position: absolute; inset: 7px; border: 3px solid var(--edge); pointer-events: none; }
.plan__sheet img { display: block; width: 100%; height: auto; }
.plan figcaption { display: flex; gap: 10px; align-items: center; font-size: .95rem; color: var(--muted); margin-top: 10px; }
.plan__key { width: 26px; height: 14px; border: 3px solid var(--edge); flex: none; }

.band { margin-top: 48px; padding-block: 28px; border-top: 3px solid var(--ink); border-bottom: 1px solid var(--line); }
.band__lead { font-size: 1.25rem; }
.four { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 28px; margin-top: 32px; }
.four p { font-size: 1rem; }
.involve.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
h3.sub { margin-top: 40px; font-size: 1.45rem; font-weight: 800; }
.split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 40px; }
.ticks { margin: 0; padding-left: 1.1em; }
.ticks li { margin-bottom: .5em; }
.three, .benefits, .involve { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 32px; margin-top: 32px; }
.three p, .benefits p, .involve p { font-size: 1rem; }
.benefits > div, .involve > div { border-top: 1px solid var(--line); padding-top: 16px; min-width: 0; }

.modules { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 40px; margin-top: 24px; }
.modules article { border-top: 1px solid var(--line); padding-block: 18px 6px; min-width: 0; }
.modules p { font-size: 1rem; }
.shots { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; margin-top: 40px; }
.shots figure { margin: 0; min-width: 0; }
.shots img { display: block; width: 100%; height: auto; border: 1px solid var(--line); }
.shots figcaption { font-size: .95rem; color: var(--muted); margin-top: 8px; }

/* Roadmap: four stages, the way a title plan marks land edged, hatched and outlined */
.stages { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; margin-block: 24px 28px; align-items: start; }
.stage { background: var(--sheet); border: 1px solid var(--line); padding: 18px 20px; min-width: 0; }
.stage h3 { display: flex; align-items: center; gap: 10px; font-size: 1.15rem; }
.stage__mark { width: 22px; height: 12px; flex: none; border: 3px solid var(--muted); }
.stage--done .stage__mark { border-color: var(--survey); background: var(--survey); }
.stage--now { border: 3px solid var(--edge); }
.stage--now .stage__mark { border-color: var(--edge); }
.stage--next .stage__mark { border-style: dashed; border-color: var(--link); }
.stage--later .stage__mark { border-style: dotted; }
.stage ul { margin: 0; padding-left: 1.1em; font-size: .97rem; }
.stage li { margin-bottom: .45em; }

.resources { list-style: none; margin: 24px 0 0; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 32px; }
.resources li { border-top: 1px solid var(--line); padding-block: 18px 8px; min-width: 0; display: flex; flex-direction: column; }
.resources p { font-size: 1rem; }
.resources .go { margin-top: auto; font-weight: 700; }
.soon { display: inline-block; font-size: .9rem; font-weight: 700; color: var(--muted); border: 2px dotted var(--muted); padding: 1px 8px; }
pre { font: .95rem/1.5 var(--mono); background: var(--sheet); border: 1px solid var(--line); padding: 14px 16px; margin: 0; }
.scroll { overflow-x: auto; max-width: 100%; }
.copy { user-select: all; }

.foot { border-top: 1px solid var(--line); padding-block: 24px 40px; color: var(--muted); font-size: .92rem; }

@media (max-width: 960px) {
  .hero { grid-template-columns: minmax(0, 1fr); }
  .stages { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .resources, .benefits, .involve { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .three { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .four { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .modules, .shots, .stages, .resources, .benefits, .involve, .involve.two, .four, .split { grid-template-columns: minmax(0, 1fr); }
  .view { padding-block: 28px 40px; }
}
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
</style>
'''


def build(artifact=False):
    body = (BODY.replace("__CAPABILITIES__", capability_list())
            .replace("__OPEN_SOURCE__", open_source_list())
            .replace("__ROADMAP__", roadmap_columns())
            .replace("__RESOURCES__", resource_list())
            .replace("__INVOLVE__", involve_list())
            .replace("__BRINGS__", titled_list(BRINGS_TOGETHER))
            .replace("__WHO_FOR__", titled_list(WHO_FOR))
            .replace("__WAYS__", titled_list(WAYS))
            .replace("__SECURE_NOW__", titled_list(SECURE_NOW))
            .replace("__BEFORE_LIVE__", plain_list(BEFORE_LIVE))
            .replace("__PILOT__", pilot_href())
            .replace("__SECURITY_LINK__", link("security", "Security policy"))
            .replace("__TECH_LINK__", link("technical_manual", "Technical manual"))
            .replace("__EMAIL_LINK__", f'<a href="mailto:{esc(LINKS["contact"])}">{esc(LINKS["contact"])}</a>'
                     if LINKS["contact"] else link("new_issue", "the project"))
            .replace("__TEST_CTA__", test_site_cta())
            .replace("__CONTACT__", contact_line())
            .replace("__LICENCE_LINK__", link("licence", "Read the licence"))
            .replace("__LICENSING_LINK__", link("licensing", "How PHAEMA is licensed"))
            .replace("__ROADMAP_LINK__", link("roadmap", "The full roadmap on GitHub"))
            .replace("__INTEGRATIONS_LINK__", link("integrations", "The integrations review"))
            .replace("__MAC_LINK__", link("mac_setup", "Mac setup guide"))
            .replace("__NEW_ISSUE__", esc(LINKS["new_issue"]))
            .replace("__CONTRIBUTING__", esc(LINKS["contributing"]))
            .replace("__EMAIL__", esc(LINKS["contact"]) or "via GitHub")
            .replace("__ASOF__", AS_OF))
    if artifact:
        return STYLE + body
    return ('<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="description" content="PHAEMA: one open system for council estates in England and Wales, '
            'covering the property register, leases, compliance, valuation and projects, with no licence fee. Try it, '
            'check its security and become a pilot council.">\n'
            + STYLE + '</head>\n<body>\n<a class="skip" href="#main">Skip to content</a>\n'
            + body + '\n</body>\n</html>\n')


if __name__ == "__main__":
    here = Path(__file__).parent
    artifact = "--artifact" in sys.argv
    out = here / ("artifact.html" if artifact else "index.html")
    out.write_text(build(artifact), encoding="utf-8")
    print(f"Wrote {out}")
