title: Maintenance
section: Key dates
order: 6
summary: Repairs and works orders, planned and statutory maintenance, components, contractors and who pays.
---
# Maintenance

Maintenance is an optional module. An administrator switches it on under **Manage data**, **Module settings**,
by ticking **Maintenance**. It then appears under **Buildings** in the menu, with an **Overview** of emergencies, jobs past target,
overdue statutory tasks, contracts to re-tender and contractors whose insurance is running out.

What sets PHAEMA apart is that maintenance is linked to the lease: who pays for a repair is worked out from the
lease repairing terms, and the cost can go straight to the tenant's rent account or the service charge.

## Reporting a repair

Select **Report a repair**, or **Report a repair** on a property's maintenance page. Choose the property, say
what needs doing, pick a category (roof, heating, electrical and so on) and a priority:

![The maintenance overview](/static/help/maintenance.jpg)
*The overview: emergencies, jobs past target and what is due.*


| Priority | Target |
|---|---|
| Emergency | Make safe the same day |
| Urgent | Within 5 working days |
| Routine | Within 20 working days |
| Planned | The planned task's due date |

Weekends and England and Wales bank holidays are not counted. Each job gets a number such as **JOB-2026-0042**,
which is also the works order number.

## Who pays

PHAEMA suggests who pays from the current lease of the property:

![A repair job with who pays and the Before you visit panel](/static/help/job.jpg)
*A job shows who pays, and the hazards before anyone visits.*


| Lease | Repairs to the inside | Structure, roof and exterior |
|---|---|---|
| Full repairing | Tenant | Tenant |
| Internal repairing, or limited by a schedule of condition | Tenant | Council, through the service charge if the lease has one |
| Landlord repairs | Council (service charge if there is one) | Council (service charge if there is one) |
| Not let | Council | Council |

Common parts of a building with let units go to the service charge when the leases have one. A property's
maintenance page shows the whole table for that property. The suggestion is a starting point: change it on the
job, with a reason, for example **Council, recharged to the tenant** for damage they caused. Always check the lease itself
for anything unusual.

## Works orders and approval

On the job, choose the contractor, enter the estimate and any purchase order number from the finance system, then
**Issue the works order**. PHAEMA can email the order to the contractor, and **Print the works order** gives a
printable copy. PHAEMA warns if the contractor's insurance has expired or is not recorded.

Orders estimated above the approval limit (£5,000 unless an administrator changes it in **Module settings**)
need approval first. Select **Ask *your supervisor* to approve the order**: your supervisor is emailed and sees it
on their dashboard. Nobody approves their own order; administrators can approve any. If the estimate changes
after approval, it needs approving again. Supervisors are set on each user record (see
[Users and roles](users-and-roles.md#supervisors)).

## Completing and paying

Record the completion date, the work done, the final cost and the contractor's invoice number. Add photos and
certificates as documents. Then, depending on who pays:

- **Recharged to the tenant:** select **Recharge the cost** to add a charge to the tenant's
  [rent account](rent-ledger.md), with VAT if the lease is opted.
- **Service charge:** choose the service charge year and heading to add the cost to that year's
  [spending](service-charges.md).

Close the job when everything is settled.

## Planned maintenance

On a property's maintenance page, **Add tasks from the library** lists common planned and statutory tasks, such
as gas safety checks, fixed electrical inspections (EICR), fire alarm servicing, emergency lighting tests,
legionella risk assessments, asbestos re-inspections and lift thorough examinations, each with its usual
frequency and the law or standard behind it. Tick the ones that apply, set the first due date and the
contractor. Change any task's frequency or dates under **Manage data**. The library is PHAEMA's own; check
frequencies against your risk assessments, written schemes and the manufacturers' instructions.

![The planned maintenance list](/static/help/planned.jpg)
*Planned and statutory tasks, overdue first.*


PHAEMA raises a job for each task 28 days before it is due (change this per task, or leave it blank to raise jobs
by hand). Completing the job records the task as done and sets the next due date. You can also select **Done**
on the task itself. Overdue statutory tasks show red on the dashboard and the overview.

## Components and the lifecycle forecast

The component register records the parts of each building that wear out: roofs, boilers, lifts, windows, fire
alarms. Add them under **Add a component** on a property's maintenance page. For each, record the category,
Uniclass 2015 code and NRM3 element if you use them, the year installed and expected life, the condition grade
(A good, B satisfactory, C poor, D bad) and the replacement cost.

![The component register](/static/help/components.jpg)
*Components with condition and replacement cost.*


**Lifecycle forecast** shows when components fall due for replacement over 5 to 30 years, and the cost each year,
split between capital and revenue. Download it to Excel for the capital programme.

## Condition surveys and backlog maintenance

A condition survey records the state of a building or site on a date, and the work it found, element by element.

**Adding a survey.** On a property's maintenance page, under **Condition surveys**, select **Add a condition
survey**. Enter the kind of survey (full, visual inspection, desktop review or specialist), the date, the surveyor
and firm, the overall condition grade and, if you have it, the report as a PDF. The next survey is due five years
later unless you give another date.

**The work found.** Add each item: the element (roof, structure, external walls, heating and so on), where it is,
the work needed, its condition grade (A to D), its priority, the estimated cost and whether it is capital. If the
item is about a component in the register, choose it. Priorities follow the usual public sector scale:

| Priority | Meaning | Falls due |
|---|---|---|
| 1 Urgent | Health and safety, or needed to keep the building open | Within a year |
| 2 Essential | To stop serious deterioration | Within two years |
| 3 Desirable | To stop further deterioration | Within five years |
| 4 Long term | Can wait | Beyond five years |

The year due is set from the priority unless you enter one.

**Finishing.** When every item is in, select **Finish the survey**. The property takes the survey's overall
condition and date (unless a later survey has already been finished), and, if you leave the box ticked, each
component named on an item takes the worst grade found for it. A finished survey can be reopened to correct it.

**Acting on items.** Select **Raise a job** on an item to open a repair job for it, with the element, cost,
component and survey details filled in. Priority 1 items become urgent jobs, priority 2 routine and the rest
planned. The item shows as done when its job is completed. You can also mark an item **Done** (for example work
done by a tenant) or **Not needed** (for example a building being closed), with a note.

**Condition surveys** (in the maintenance menu) is the survey programme: every building and top-level site, when
it was last surveyed, its grade, and when the next survey is due, with filters for never surveyed, overdue and due
within a year.

**Backlog** totals the work still to do across the estate: by priority, by element and by year due, with overdue
work counted in this year. Backlog maintenance is the work of priorities 1 to 3; priority 4 is shown beside it.
Filter by priority, building or surveyor, and download the list to Excel for the asset management plan.

**Importing a survey.** Survey firms usually supply their findings as a spreadsheet. Under **Import**, **Condition
surveys**, upload one row per item. Rows with the same property and survey date become one survey, which is added
as being entered so you can check it and finish it.

## Contractors

Administrators add contractors under **Manage data**, with contact details, out of hours number, insurer, public
liability cover, insurance expiry date and accreditations. A contractor's page shows their jobs, contracts and
spend in the last 12 months.

## Contractor portal

With the contractor portal switched on (**Manage data**, **Module settings**, **Contractor portal**), people at
your contractors can sign in at `/contractor/` to deal with the works orders sent to their firm. They sign in with
a code emailed to them each time, through GOV.UK Notify, and never see any other firm's jobs, or a job before its
order is issued.

**Giving access.** On a contractor's page, under **Contractor portal**, select **Add a person** and enter their
name and email address. PHAEMA emails them an invitation. Each person needs their own address. **Stop access**
stops them signing in at once; **Send the invitation again** if it went astray. Works order emails tell the firm
they can answer in the portal once it has an account.

**What contractors do.** For each order they see the property and its address, the priority and target date, the
order value, the details, the officer to contact and the **Before you visit** hazards. They can:

- **Accept** the order, with the date they expect to attend, or **decline** it with a reason. A decline emails the
  job's owner, who chooses another contractor and issues the order again.
- Add **progress notes**, each with a photo if they like.
- Report the **work done**: the date, what was done, the cost before VAT, their invoice reference and up to ten
  certificates or other files. The job is marked completed with those details, the files are added to its
  documents, and the job's owner is emailed. Check the work and the cost as for any completed job before closing
  it or raising a recharge.

Everything a contractor sends appears on the job under **From the contractor**, and the change log names the person
and the portal.

## Contracts

The contracts register records service contracts, such as fire alarm servicing or water hygiene, with their
term, annual value and the properties they cover. The RICS professional standard on service charges in
commercial property expects contracts to be re-tendered or benchmarked at least every three years, so PHAEMA
shows when each is due and lists those due within six months on the overview. Record the date a contract was
last tendered or benchmarked to move the date on.

## Filtering by building or surveyor

The repair jobs, planned maintenance, components, lifecycle forecast and contracts pages can be filtered by
**building or estate** (including every unit and part within it) and by **managing surveyor** (or "Mine"). The
same filters are on the cases, lease events, leases, compliance and asset valuation pages. Downloads to Excel
follow the filters.

## Reports

The **Maintenance** ready-made reports include repairs past target, statutory maintenance overdue, planned
maintenance due in 90 days, repair spending in the last 12 months, components in poor or bad condition,
contracts due for re-tender and contractor insurance expiring.

## Worked example

At **DM-N04 Northfield Leisure Centre** a ceiling tile has fallen near the learner pool. The job is reported as an
**emergency**, so its target is the same day, and the works order goes to the building contractor straight away.
**Who pays** shows PHAEMA's suggestion from the leisure trust's
lease (DL-0520), which keeps structural repairs with the council: check the lease and change it with a reason if
needed. The job page's **Before you visit** panel warns about the pool plant room.

At **DM-N09 Northfield Market Hall**, replacing cracked panes in the roof lantern is estimated at £14,800, above the
£5,000 approval limit, so the order waits for Sam Hughes to approve it. At Unit 6 of the business park, graffiti on
the shutter was removed for £180 and marked
**Council, recharged to the tenant**: select **Recharge the cost** to add it to the tenant's rent account.
