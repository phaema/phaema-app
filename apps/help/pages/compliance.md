title: Compliance and building information
section: Key dates
order: 7
summary: Statutory certificates and their expiry, remedial actions, Golden Thread screening, building documents and open data.
---
# Compliance and building information

The compliance module keeps the certificates each building needs, warns before they expire, tracks the actions
they call for, and holds the building's information (the "Golden Thread") for the life of the building. It is on
unless an administrator switches it off in **Module settings**. Find it under **Buildings**, **Compliance** in the
menu, and on each property page.

## Setting up a property

On a property's compliance page, select **Choose the certificates this property needs** and tick those that
apply, for example:

| Certificate | Usually valid for |
|---|---|
| Fire risk assessment | 12 months (review) |
| Fire alarm inspection and service | 6 months |
| Emergency lighting test | 12 months |
| Gas safety record | 12 months |
| Electrical installation condition report (EICR) | 5 years |
| Legionella risk assessment | 2 years |
| Asbestos register and management plan review | 12 months |
| Lift thorough examination | 6 months |
| Energy Performance Certificate (EPC) | 10 years |
| Display Energy Certificate (DEC) | 12 months |

Administrators can change the periods, or add their own certificate types, under **Manage data**, **Compliance
types**. Check them against the council's own policies and risk assessments.

PHAEMA suggests who holds each certificate. A tenant on full repairing terms of the whole property holds its own
certificates and the council keeps a copy; otherwise the council holds them. Change it for any certificate.

The register can be filtered by certificate, who holds it, **building or estate** (including its units and parts)
and **managing surveyor**; the figures at the top follow the filters.

## Recording a certificate

Select **Record a certificate**, choose which, and enter the date, the result and the PDF. PHAEMA works out the
expiry from the usual period, or enter the date on the certificate. For an EPC or DEC, enter the rating.

| Status | Means |
|---|---|
| Valid | In date, nothing outstanding |
| Actions open | In date, with remedial actions still to do |
| Expires soon | Expires within 60 days: book the next inspection |
| Expired, Missing or Unsatisfactory | Shown red on the dashboard and the compliance page |

### Remedial actions

Type any actions from the certificate or assessment, one per line, with a priority: high (7 days), medium (30
days) or low (90 days). Each is tracked until marked **Done**. With [maintenance](maintenance.md) switched on,
**Raise a repair job** turns an action into a job for a contractor.

## Golden Thread tiers

PHAEMA keeps building information to three tiers:

| Tier | For |
|---|---|
| A, statutory | Higher-risk buildings in England (at least 18 metres or at least 7 storeys, with at least two residential units) and buildings in scope in Wales |
| B, best practice | Other buildings under the Fire Safety Order: kept to the same principles |
| C, minimal | Land and simple assets: title, plans and inspection history |

Use **Screen this building** to record the country, height, storeys and number of homes, and the responsible
person under the Fire Safety Order. PHAEMA suggests the tier; an officer confirms it, and PHAEMA records who and
when. For tier A buildings, record the accountable person. The Welsh regime is still being brought in, so PHAEMA
flags Welsh buildings with homes for an officer to check rather than deciding.

## Building information

**Add a document or a new version** keeps plans, fire safety information, health and safety files, operation
and maintenance manuals, surveys and other documents by category. A new version supersedes the old one, which
is kept in the history: building information is never deleted.

## Open data

When an administrator ticks **Publish open data** in **Module settings**, PHAEMA publishes, without signing in, at
`/open-data/`:

- **Land and assets**: every property, as the Local Government Transparency Code requires;
- **Property available**: vacant lettable property.

Each is available as CSV, JSON and GeoJSON (for maps), under the Open Government Licence. Properties marked
**Exclude from open data**, and anything that is part of them, never appear. Link to the page from the council's
website.

## Reports

The **Compliance** ready-made reports cover certificates expired, certificates expiring in 60 days, remedial
actions overdue, and EPCs rated F or G, which are below the minimum standard for letting.
