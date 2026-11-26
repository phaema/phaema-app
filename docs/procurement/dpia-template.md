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
automated decisions about people, profile them, or share data with the PHAEMA project or other third parties.

**Personal data held**

| Who | What | Where it comes from |
| --- | --- | --- |
| Council staff and outside users (consultants, legal staff) | Name, work email, job title, role and access areas, supervisor, sign-in records, two-step sign-in set-up, what they changed and when | The council |
| Tenants, licensees and other parties to agreements | For individuals and sole traders: name, correspondence address, email, phone, contact name; rent account, arrears, payment plans, deposits; case notes and correspondence | The party, their agents and solicitors, the council's finance system |
| Guarantors and former tenants still liable (AGAs) | Name, address, the agreement they are liable for | Lease documents |
| Occupiers of council buildings | Organisation or team names; headcounts (numbers, not names) | The council |
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
