title: Leases and licences
section: Records
order: 3
summary: Recording agreements, their terms, breaks and documents.
---
# Leases and licences

PHAEMA records every agreement over council property: leases, licences, tenancies at will, agreements for lease,
farm business tenancies, wayleaves, easements and concessions. It covers both directions:

- **let out by the council**: the council is landlord and receives rent;
- **held by the council**: the council is tenant and pays rent.

## Adding an agreement

Select **Add a lease or licence** on the lease list, or use **Manage data**. You need:

- a unique **reference**;
- the **tenant or landlord** (a [party](parties.md)), and a guarantor if there is one;
- the **premises**: one or more properties from the register;
- the **term start**, and the **term end** unless the agreement is periodic.

To add many agreements at once, see [importing leases](import-export.md#leases-and-licences).

## Terms

| Field | Notes |
|---|---|
| Status | Proposed (heads of terms), Current, Holding over or Ended. |
| Security of tenure | Whether the lease is inside the Landlord and Tenant Act 1954, Part II, or contracted out. |
| Rent and frequency | The current rent comes from the [rent schedule](rent-schedule.md). |
| Review basis and interval | How and how often the rent is reviewed. The next review date creates a [rent review event](events.md#rent-reviews). |
| Repairing and insurance | Who repairs and insures. |
| Service charge payable | Whether a service charge is due. |
| Rent excludes business rates | Ticked unless the rent includes rates. |
| Incentives | Any rent-free period or other incentive. |
| Rent deposit, where held, interest | The amount, where it is held (for example the deposit account and the deed's date) and who the interest goes to and when. |
| Alterations and reinstatement | What the tenant may alter, and whether they must reinstate at the end. |
| Special rights | Parking, rights of way, telecoms access and so on. |

![The agreement page for DL-0502](/static/help/lease.jpg)
*An agreement with its events, premises and tenant.*


These match the items the RICS Code for leasing business premises asks heads of terms to cover, so a renewal case
can start from what the current agreement says.

The agreement page shows the **term** in years and months, the **next payments due** (a guide only: part periods
are not apportioned), and all key dates.

## Break options

Add break options in **Edit this agreement**. For each, record the break date, who can exercise it (tenant,
landlord or either) and the notice period in months. PHAEMA works out the **last date to serve notice** and creates
[events](events.md#breaks) for the notice deadline and the break date.

## Documents

Store PDFs of the lease, licence, deeds of variation and other documents in **Edit this agreement**, under
Documents. Only signed-in users can open them.

## Ending an agreement

Record the outcome of the [expiry event](events.md#expiries), or set the status to Ended and fill in the
**actual end** date. Open events for an ended agreement lapse automatically.

## Worked example

**DL-0502** is Northfield Packaging Ltd's lease of Unit 2, Northfield Business Park: ten years, inside the 1954
Act, £39,000 a year plus VAT, reviewed upwards only every five years, on full repairing terms with a service charge.
It records a £9,750 rent deposit held in the council's deposit account, with interest to the tenant. The tenant can
break at year five on six months' notice, so PHAEMA has created a **break notice deadline** event six months before
the **break date** event, as well as the rent review and expiry.

**DL-0530** is the other way round: the council holds the Northfield Innovation Hub on a ten-year lease at £38,000
a year. It counts as rent the council pays, and the council's own break is recorded the same way.
