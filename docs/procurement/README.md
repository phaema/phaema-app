# Procurement and information governance pack

Documents a council needs when it assesses, buys support for, or goes live with PHAEMA. Each is written for a council
hosting PHAEMA itself or through a supplier; the parts in **[square brackets]** are for the council to complete.

| Document | Who uses it | What it is |
| --- | --- | --- |
| [Service definition](service-definition.md) | Procurement, IT | One page of facts in the order G-Cloud listings use: what PHAEMA does, hosting, security, accessibility, data export and exit, licence and support |
| [Accessibility statement](accessibility-statement.md) | Digital or web team | A statement in the GOV.UK model format, to publish once the council has checked PHAEMA on its own installation, and a second one for the tenant portal, which the public use |
| [Data protection impact assessment](dpia-template.md) | Data protection officer | A DPIA with the processing PHAEMA does already described, for the council to complete and sign, with an annex for the tenant portal and emails to tenants |
| [Record of processing](record-of-processing.md) | Data protection officer | Article 30 entries for the processing PHAEMA supports |
| [Retention schedule](retention-schedule.md) | Records manager | Suggested retention periods for PHAEMA's records, to align with the council's own schedule |
| [Security answers](security-answers.md) | IT security | Short answers to the questions council security questionnaires usually ask |

**If the council switches on the tenant portal or emailing demands**, complete Annex A of the DPIA, the tenant portal
rows of the record of processing and retention schedule, and the second accessibility statement. Emails to tenants
then go through GOV.UK Notify as a processor, under the agreement the council accepts with Notify. Before opening the
portal to all tenants, the council should run a pilot with a few tenants and commission a penetration test of
`/tenant/` and an independent accessibility audit.

These are templates, not legal advice. Each council's data protection officer decides the lawful bases, retention
periods and risks for its own use. The [SECURITY.md](../../SECURITY.md) policy and the
[technical manual](https://phaema.co.uk/docs/technical-manual.html) hold the technical detail behind the answers.
