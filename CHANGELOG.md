# Changelog

What changed in each PHAEMA release, for the people who run and use it. Numbers follow
[semantic versioning](https://semver.org/): while PHAEMA is below 1.0, a new minor number (0.10.0) can include
changes that need action when updating, and these are listed under **Before updating**. How releases are made is in
[docs/releasing.md](docs/releasing.md).

Run `python manage.py migrate` after every update; the installer's update script does this for you.

## Unreleased

Everything since 0.9.0 (10 to 27 November 2026).

### Before updating
- If your proxy or a customisation loads scripts, fonts or map tiles from another address, list it in
  `PHAEMA_CSP_IMG_SOURCES` or `PHAEMA_CSP_CONNECT_SOURCES`, or set `PHAEMA_CSP_REPORT_ONLY=True` first and check the
  browser console.
- New Python package `notifications-python-client` (GOV.UK Notify): the installer's update script installs it. To
  send emails to tenants, set `PHAEMA_NOTIFY_API_KEY` and `PHAEMA_NOTIFY_TEMPLATE_ID`; without them, emails are
  recorded in PHAEMA but not sent. Never set `PHAEMA_PORTAL_SHOW_CODES` on a live site.
- The new database trigger means a retention purge of the change log needs `SET LOCAL phaema.audit_purge = 'on'`
  in the same transaction (technical manual, Audit trail).
- Letter templates may now use only `{% if %}`, `{% for %}`, `{% comment %}` and the formatting filters listed in
  Help, Documents. Run `python manage.py check_document_templates` to list any template your council changed that
  uses something else; until it is corrected, its letters show a message instead of the text.
- Signing in to the API with a username and password is now off. Give each script or system an API token
  (Manage data, API tokens), or set `PHAEMA_API_PASSWORD_SIGN_IN=True` while you move them over.

### Added
- Map layers for desktop GIS: PHAEMA's property boundaries as an OGC API - Features service at `/api/ogc/`, for
  QGIS, ArcGIS and other GIS, signed in with an API token. Two layers (every property, and top-level holdings
  only), in WGS 84 or British National Grid, with paging, bounding box and simple filters. Help, Maps.
- Tenant portal (optional, off by default) at `/tenant/`: tenants the estates team invites sign in with a code
  emailed each time and see, for their own agreements, the rent account with arrears by age, interest and the next
  credit control step, demands with Pay now links, the statement, key dates, documents the council shares, service
  charge budgets and statements, certificates they must provide, their rent deposit and payment plan; they can ask
  to change contact details, report repairs, make requests, send certificates and insurance documents, query a
  service charge line and message the estates team (#112, #117, #119).
- Emailing demands through GOV.UK Notify: each tenant gets their charges, the total, anything overdue and a Pay now
  link to the council's payment page; every email is kept as a record (#110).
- Repair reports from tenants and departments, with photos, into a triage queue under Maintenance where estates
  raise a job, link to an open job, mark it the tenant's to repair or close it, with a reply the reporter sees (#113).
- Requests that open a case, from tenants (consents such as assign, underlet, alterations and change of use) and
  departments (space requests); each case type says who can ask, with guidance and documents to attach (#115).
- Messages between tenants and the estates team, answered by the managing surveyor or whoever is covering for them;
  certificate reminders to tenants by email; certificates and insurance documents sent by tenants for estates to
  check (#117, #119).
- Departments can see their own buildings: a department's property liaison, and read-only people such as the head of
  service, sign in without a role and see the buildings their department uses, the stacking plan and their own
  space, people and capacity. The liaison records headcount, which the building's managing surveyor checks from
  their dashboard (#109).
- API tokens for other systems: read only or read and change, limited to parts of the API, an end date of at most
  two years, cancelled on their own, stored only as a hash and named in the change log (#103).
- Welsh (Cymraeg) interface, as a draft awaiting review by a qualified translator. An administrator offers it in
  Module settings, under Language; each person then chooses English or Cymraeg at the top of the page.
- IFRS 16 data pack for leases the council holds, with an IFRS 16 treatment, lease end and notes on each lease (#92).
- Index-linked rent reviews worked out from CPI, CPIH or RPI figures fetched from the ONS (#86).
- Dealings register: assignments, underleases, sharing, charges, AGAs and lease chains (#87).
- Interest on late rent, credit control stages, payment plans and a rent deposit account (#88).
- Void marketing case type with agent instructions and particulars (#89).
- ITZA on shops, an ITZA calculator and rent per m² Zone A (#90).
- Text recognised in scanned PDFs (OCR) so they can be searched (#75).
- Finance menu with rents payable; several cases in one project (#76).
- Floor areas to IPMS: All Buildings, level 1 (#73).
- Site visits on the phone with photos, differences from the record and check-measures (#70, #71).
- Estates strategy: holding purposes, asset strategies, Asset Challenge, suitability, objectives, action plan and
  board report (#65, #67); property events pipeline (#68); annual asset management health check (#69).
- Outside users with an access end date; more lease terms; space and occupiers with costs and notional rent
  (#62, #63, #64).
- Property details mapped to the Government Property Data Standard, with its export (#61).
- PDF viewer inside PHAEMA (#59); drag and drop filing of documents and emails (#57).
- Site visit sheet for every case with configurable checklists (#56); site and building details, floor plans and an
  initial valuation report (#54).
- Single sign-on with the council's own accounts (#53); forgotten password reset by email (#50); sign in with an
  email address (#48).
- Property portfolios (#46); lease management additions: dashboard flags, ERV, documents for review, demands on
  hold (#47).

### Changed
- Minimum versions raised to those PHAEMA is tested with: Django REST framework 3.18.3, drf-spectacular
  0.30.0, python-docx 1.2.0 and pytest-django 4.14.0 (#107). Django stays on 5.2, the long-term support release.
- The demonstration data is twice the size: two more fictional districts, Westbrook (DM-W, DL-06) and Kingsmere
  (DM-K, DL-07), follow Northfield's layout with their own names, rents and dates. There are now 147 properties,
  95 agreements, about 120 cases and 49 maintenance jobs. Exampleton and Northfield are unchanged, so the manual,
  e-learning and tour still match. Run `./phaema.sh demo-data --reset` on a test site to load it.

### Fixed
- Year-end service charge statements showed a zero balance once the year was reconciled, because the balancing
  charges were counted as paid on account (#117).
- The API description at `/api/schema/` builds without warnings: both sign-in methods are described, shared choice
  lists have one name, and break notice dates are typed; a test keeps it that way (#104).
- Credit notes allocated to the right charges, and service charge credits (#78).

### Security
- Uploaded files now open only for people who can open the record they belong to: files held by valuations,
  compliance or maintenance need that module, and files that belong to no record are not served. Before, anyone
  signed in could open a file whose address they knew (#108).
- Records saved through the API now go through the model's own checks, so a property can no longer be made part of
  itself, directly or round a loop; walking the property tree also stops if such a loop ever exists (#108).
- Changes made in bulk (several records at once) are now written to the change log too: unlinking from a project,
  finance export batches, cancelled payment plans, replaced estate strategies, acknowledged tasks, main photos,
  strategy review dates, event assignments and ONS index corrections (#108).
- Letter templates run in a reduced template language: tags such as `{% debug %}`, `{% load %}` and `{% include %}`
  and the `pprint` filter are not available, and merge data is plain text, so a template cannot print other data
  or read files (#104).
- Changes made through the API are now named in the change log under the account that made them, with how they
  arrived (an API token or a password); before, they showed as made by the system (#103).
- Content-Security-Policy and Permissions-Policy headers on every page; report-only mode and extra map tile
  addresses can be set (`PHAEMA_CSP_*`).
- The database refuses to change or delete change log entries (a trigger); deleting a user still clears their name
  from their entries.
- HSTS is sent by PHAEMA itself as well as the Caddy proxy, for councils using their own proxy.
- Every pull request now runs Ruff (including its security rules) and a test coverage minimum; CI actions are pinned
  to commit hashes and Dependabot proposes updates.
- Limits on repeated wrong passwords on the sign-in page, admin site and API; shorter sessions; PHAEMA refuses to
  start without a long secret key; tighter single sign-on linking; dependency and code scanning in CI (#78).

### Documentation
- Manuals, test programme, e-learning, tour and website brought up to date with each feature (#55, #60, #66, #72,
  #74, #77, #91, #93, #102, #111, #114, #116, #118, #120).
- Procurement pack: data protection impact assessment annex, record of processing, retention periods, security
  answers and a second accessibility statement for the tenant portal and emails to tenants (#121).
- Test programme: new tests for browser protections (U11), the locked change log (U12) and Welsh (CY1 to CY5).

## 0.9.0 (10 November 2026)

The first numbered alpha release. It brought together the work of the first eight weeks:

- Property register with maps, INSPIRE boundaries and spreadsheet import (#1, #2).
- Leases and licences with events, reminders, a calendar feed and rent schedules (#2, #3).
- Rent ledger (#7), service charges (#9, #10), asset valuation (#15).
- Case management with supervisor approvals, RICS Code for leasing heads of terms and 1954 Act notices (#11, #12).
- Maintenance (#13); compliance, building information and Golden Thread tiers; open data (#14).
- Document templates with Word export (#16); report builder and ready-made reports (#4, #8, #17).
- Access areas (#28, #29); hand over work (#24); projects (#30 to #32).
- Two-step sign-in and the security policy (#42); server installer with HTTPS, firewall, updates and backups (#36).
- Built-in manual and help, themes and text sizes, e-learning and the website (#4 to #6, #19, #21, #22, #44).
