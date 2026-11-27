# Data protection impact assessment: [council name] PHAEMA

A template based on the steps in the ICO's
[DPIA guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/).
The description of what PHAEMA does with personal data is filled in; the council's data protection officer completes
the rest, decides the lawful bases and risks, and signs it off. Parts in **[square brackets]** are for the council.

A DPIA may not be strictly required for an estates system, which mostly holds information about property and
businesses. Many councils complete one anyway because PHAEMA holds personal data about sole traders, guarantors,
staff and occasionally vulnerable occupiers, and because it replaces or joins up existing systems.

## 1. Why the council is doing this

[Council name] uses PHAEMA to manage the land and buildings it owns, lets and occupies: the property register, leases
and licences, rent and service charges, casework, valuations, maintenance, compliance and projects. [Say what it
replaces, for example spreadsheets or an older system, and the benefits expected.]

## 2. The processing

**Nature.** Staff enter and import records; PHAEMA stores them in a PostgreSQL database and file store on
[the council's servers / the hosting supplier's servers in the UK]. It sends email reminders to staff, produces
letters and demands for tenants, exports charges to the finance system and imports receipts. It does not make
automated decisions about people, profile them, or share data with the PHAEMA project. If the council switches on
**emailing demands** or the **tenant portal**, emails to tenants go through GOV.UK Notify (see the
[tenant portal annex](#annex-a-tenant-portal-and-emails-to-tenants)); otherwise no third party receives personal
data.

**Personal data held**

| Who | What | Where it comes from |
| --- | --- | --- |
| Council staff and outside users (consultants, legal staff) | Name, work email, job title, role and access areas, supervisor, sign-in records, two-step sign-in set-up, what they changed and when | The council |
| Tenants, licensees and other parties to agreements | For individuals and sole traders: name, correspondence address, email, phone, contact name; rent account, arrears, payment plans, deposits; case notes and correspondence | The party, their agents and solicitors, the council's finance system |
| Guarantors and former tenants still liable (AGAs) | Name, address, the agreement they are liable for | Lease documents |
| Occupiers of council buildings | Organisation or team names; headcounts (numbers, not names); for named property liaisons and heads of service, their PHAEMA account, the repair reports and requests they make | The council |
| Contractors | Company and contact names, email, phone, insurance and accreditation details | The contractor |
| People named in documents | Anything in uploaded leases, deeds, emails, photos and site visit records | Staff uploads |

**Special category and criminal offence data.** Not needed for estates work. It may appear in case notes or
correspondence (for example a tenant's health given as a reason for arrears). [Say how staff are told to handle
this: for example, record only what is needed, and mark notes confidential, which only the case owner and administrators can see.]

**Scope.** About [number] properties, [number] agreements, [number] parties and [number] staff users. Data is kept
for the periods in the [retention schedule](retention-schedule.md).

**Context.** Most data is about businesses. Some tenants are individuals, small traders, community groups or
charities, and some may be in financial difficulty. People would expect the council to hold this to manage their
agreement.

**Purposes.** Managing the council's property and agreements; collecting rent and charges; meeting legal duties
such as building safety, the Landlord and Tenant Acts and the accounts; and reporting on the estate.

## 3. Consultation

[Who was consulted: estates, finance, IT security, records management, legal, Information Governance group; any
tenant representatives.]

## 4. Necessity and proportionality

| Question | Answer |
| --- | --- |
| Lawful basis (UK GDPR Article 6) | [Usually 6(1)(e) public task for estate management and legal duties, and 6(1)(b) contract for managing agreements with individual tenants. The DPO decides.] |
| Data minimisation | PHAEMA asks for contact details of a party, not personal profiles. Optional fields can be left blank. Headcounts in space records are numbers only |
| Accuracy | Records show who changed them and when; staff correct them on screen |
| Retention | See the [retention schedule](retention-schedule.md). PHAEMA does not yet delete records automatically; [say who reviews and deletes, and how often] |
| Individuals' rights | Access requests: search by party name finds their agreements, accounts, cases and documents; reports export to Excel. Rectification on screen. Erasure where retention allows, by an administrator |
| Processors | [None if the council hosts it; otherwise the hosting or support supplier, under a contract with Article 28 terms] |
| International transfers | None: PHAEMA runs where the council installs it. Map tiles are fetched by the user's browser from OpenStreetMap or Ordnance Survey; no personal data is sent |

## 5. Risks

| Risk | Likelihood | Severity | Overall |
| --- | --- | --- | --- |
| Unauthorised access to tenants' financial information | [Remote / possible / probable] | [Minimal / significant / severe] | [Low / medium / high] |
| Staff seeing more than they need (for example finance details outside their patch) | [ ] | [ ] | [ ] |
| Special category data recorded in case notes without need | [ ] | [ ] | [ ] |
| Data kept longer than needed | [ ] | [ ] | [ ] |
| Loss of data through server failure | [ ] | [ ] | [ ] |
| A leaver keeping access | [ ] | [ ] | [ ] |

## 6. Measures to reduce the risks

| Risk | Measures PHAEMA provides | Council measures | Residual risk |
| --- | --- | --- | --- |
| Unauthorised access | Two-step sign-in or single sign-on; limits on password guessing; sessions end after 10 hours or 2 hours idle; HTTPS only; security headers; files served only to signed-in users | [Network controls, hosting certification, penetration test] | [ ] |
| Seeing too much | Roles and access areas; surveyors see finance only for their own patch; confidential case notes (case owner and administrators only); outside users with an access end date | [Who approves roles; periodic access review] | [ ] |
| Special category data in notes | Confidential notes, seen only by the case owner and administrators | [Guidance and training] | [ ] |
| Over-retention | Change log shows what is held; reports find ended agreements and closed cases | [Annual review against the retention schedule] | [ ] |
| Data loss | Nightly backups kept 14 days by the installer; standard PostgreSQL | [Off-server copies, restore tests] | [ ] |
| Leaver keeping access | Hand over work blocks sign-in and moves their work in one step; single sign-on stops access when the council account is disabled | [Leavers process] | [ ] |

## 7. Sign-off

| Item | Name and date | Notes |
| --- | --- | --- |
| Measures approved by | [ ] | |
| Residual risks approved by | [ ] | If any high risk remains, consult the ICO before going ahead |
| DPO advice | [ ] | |
| DPO advice accepted or overruled by | [ ] | |
| Review date | [ ] | Review when PHAEMA's use changes, such as switching on a new module |

## Annex A: tenant portal and emails to tenants

Complete this annex only if the council switches on **email demands** or the **tenant portal** (both are off until an
administrator turns them on). The portal is the one part of PHAEMA used by people outside the council, so it changes
the processing more than any other module. The ICO lists processing that gives the public online access to their
data, and new technology, among the things that point towards doing a DPIA.

### A1. What changes

**Emailing demands.** After a demand run, staff can email each tenant their charges, total, any overdue amount and a
**Pay now** link to the council's own payment page. The email lists the charges.

**The tenant portal** at `/tenant/`. People at a tenant whom the estates team invites can sign in to see, for their
own agreements only:

- their rent account: balance, overdue amounts by age, interest building up, the next credit control step, any
  payment plan and its progress, unpaid demands with **Pay now** links, and the statement
- key dates, documents the council has chosen to share, who insures, their rent deposit
- service charge budgets and year-end statements the council has issued
- certificates they must provide (such as a gas safety record), with a way to send them
- their repair reports and requests (such as consent to assign), with progress and decisions
- messages with the estates team

They can also ask to change their contact details for demands (estates accept or decline), report repairs with
photos, make requests that open a case, send certificates and insurance documents, query a line of a service charge
statement, and send messages.

**People who work in council departments** (property liaisons) can report repairs and make space requests on their
building pages. They are council staff with PHAEMA accounts, so this is covered by the main assessment.

### A2. Personal data added

| Who | What | Where it comes from |
| --- | --- | --- |
| People at a tenant with a portal account | Name, work or personal email address, which tenant they act for, whether they see finance or facilities information, when invited and last signed in; sign-in codes (kept only as a keyed hash, valid for 15 minutes and deleted the next day) | The estates team, from the tenant |
| The same people | What they send: contact changes, repair reports and photos, requests and their documents, certificates, insurance documents, messages, service charge questions | The tenant |
| Tenants receiving emails | Email address, name, and the email: for demands, the charges and amounts; for the portal, invitations, sign-in codes, "there is a reply" and certificate reminders | PHAEMA |
| Everyone using the portal | Session cookie and the change log entry for anything they change, marked "Tenant portal" with their name and email | PHAEMA |

PHAEMA keeps a copy of every email it sends to a tenant (sign-in codes are masked), so staff can see what was sent.
Photos are reduced in size and their location data removed when uploaded.

### A3. Necessity and proportionality

| Question | Answer |
| --- | --- |
| Lawful basis | [Usually the same as for the agreement: 6(1)(b) contract and 6(1)(e) public task. The portal is a way of giving tenants information the council already holds about them; it is not based on consent. The DPO decides.] |
| Is it needed? | It lets tenants see and do online what they now phone or email about. Using it is optional for tenants: the council keeps its usual letters and phone line |
| Data minimisation | Only the tenant's own agreements. Nothing internal is shown: case notes, tasks, approvals, valuations, other tenants. Documents are shown only when staff choose to share them. Emails say only that there is a message or reply, not what it says. Each person is given finance rights, facilities rights or both, so a facilities manager does not see the rent account |
| Accuracy | Tenants see the same figures staff see and can ask for contact details to be corrected; staff accept or decline |
| Retention | See the [retention schedule](retention-schedule.md). Access ends automatically 12 months after the agreement ends. GOV.UK Notify keeps a copy of each email for [7 days by default](https://notifications.service.gov.uk/using-notify/data-retention-period); the council can change this once its Notify service is live. Used and expired sign-in codes are deleted by the daily tasks the next day |
| Individuals' rights | Portal users can see much of what is held about their agreement themselves. Access requests and rectification as for the main system; an administrator can make an account inactive at once |
| Processors | GOV.UK Notify, run by the Government Digital Service, is a processor for emails to tenants under the [Notify data processing agreement](https://www.notifications.service.gov.uk/agreement/non-crown.pdf) the council accepts before its Notify service goes live. [Add the hosting or support supplier, if any] |
| International transfers | GOV.UK Notify stores and processes data in AWS data centres in the UK and Ireland, and its sub-processors in the UK and EEA, according to its [security information](https://www.notifications.service.gov.uk/features/security). [The DPO decides whether this needs recording as a restricted transfer; the EEA is covered by UK adequacy regulations.] Nothing else leaves PHAEMA's hosting |

### A4. Risks

| Risk | Likelihood | Severity | Overall |
| --- | --- | --- | --- |
| Someone outside the tenant signs in (for example with access to a tenant's email inbox) | [ ] | [ ] | [ ] |
| A tenant sees another tenant's information through a fault | [ ] | [ ] | [ ] |
| Staff share a document with internal comments, or reply in a message with more than they should | [ ] | [ ] | [ ] |
| A person who has left the tenant company keeps access | [ ] | [ ] | [ ] |
| The portal is attacked from the internet (it is the only part a member of the public can reach without a council account) | [ ] | [ ] | [ ] |
| Emails sent to the wrong address | [ ] | [ ] | [ ] |
| Tenants upload special category data (for example in a message about arrears) | [ ] | [ ] | [ ] |
| The portal is not accessible to a tenant who needs it | [ ] | [ ] | [ ] |

### A5. Measures

| Risk | Measures PHAEMA provides | Council measures | Residual risk |
| --- | --- | --- | --- |
| Someone else signs in | Accounts only by estates invitation; sign-in by a 6-digit code emailed each time, valid once for 15 minutes, 5 tries, stored only as a keyed hash; limits on requests per address and per connection; the same page whether or not an address has an account; signed out after 30 minutes idle | [Check the email address with the tenant before inviting; ask tenants to tell you when someone leaves] | [ ] |
| Another tenant's information | Every portal page takes its agreements from one shared rule (the tenant's own let agreements), and other records give "page not found"; tests check each page; the portal has no access to staff pages, the admin or the API | [CREST penetration test of `/tenant/` before live use] | [ ] |
| Sharing too much | Documents are not shared unless staff choose; internal notes, tasks and approvals never reach the portal; emails carry no message text | [Guidance for staff on what to share and how to write replies] | [ ] |
| Leavers at the tenant | Accounts can be made inactive at once, which signs the person out; access ends 12 months after the agreement ends; last sign-in date shown to staff | [Yearly check of portal accounts with each tenant] | [ ] |
| Attack from the internet | Its own content security policy; pages not cached; HTTPS only; CSRF protection; uploads checked by content and size; rate limits | [Penetration test; monitoring; prompt patching] | [ ] |
| Wrong email address | Demand emails go to the billing email on the agreement or the tenant's email; staff see a list and an example before sending; every email is recorded | [Check addresses when setting up; act on bounces reported in Notify] | [ ] |
| Special category data sent by tenants | The text goes to the managing surveyor only; it is not shown to other tenant users of another company | [Guidance; record only what is needed] | [ ] |
| Accessibility | GOV.UK Design System; works on a phone | [Independent accessibility audit before live use; publish the portal's accessibility statement] | [ ] |

### A6. Sign-off for the annex

| Item | Name and date | Notes |
| --- | --- | --- |
| Pilot with a few tenants agreed by | [ ] | Recommended before opening the portal to all tenants |
| Penetration test completed | [ ] | |
| Accessibility audit completed | [ ] | |
| Privacy notice for tenants updated | [ ] | Tell tenants about the portal, Notify and what they can see |
| Annex approved by | [ ] | |
