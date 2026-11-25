title: Rent schedule
section: Key dates
order: 2
summary: How rent changes over the life of an agreement.
---
# Rent schedule

Each agreement has a rent schedule: a list of rents, each with the date it takes effect. The agreement's
**current rent** is always the latest entry that has taken effect. PHAEMA updates it automatically each day, so a
stepped rent changes on the right date without anyone editing the lease.

## What creates entries

| Reason | How it gets there |
|---|---|
| Initial rent | Created from the rent when the agreement is first saved or imported. |
| Rent review | Created when you [record a rent review outcome](events.md#rent-reviews). |
| Fixed step | Added by hand, for stepped rents agreed in the lease. |
| Index-linked increase | Created when you record an [index-linked review](#index-linked-reviews), or added by hand. |
| Variation or concession | Added by hand, for a rent-free period, concession or deed of variation. |
| Lease renewal | Added by hand. |

## Adding a change

On the agreement page, select **Add a rent step, concession or variation**. Enter the date it takes effect, the
new annual rent, the reason and any notes. You can add future steps in advance.

You can remove an entry that was added in error. An agreement always keeps at least one rent.

> Rent changes are made on the rent schedule, not by editing the rent on the agreement or by
> [importing](import-export.md#leases-and-licences). This keeps a full history of the rent.

## Index-linked reviews

For a lease whose rent follows RPI, CPI or CPIH, PHAEMA works out the new rent at each review. Enter the index
terms on the agreement (**Manage data**, the agreement, **Index-linked reviews**):

| Term | What to enter |
|---|---|
| Index | CPI, CPIH or RPI (administrators can add others). |
| Base index month | The month of the figure the current rent is based on: the start of the lease, or the figure used at the last review. PHAEMA moves it on at each review. |
| Index months before the review | Many leases use the figure for a month two or three months before the review date, because figures are published about a month late. 0 means the review month itself. |
| Cap and collar | The most and least the rent may rise, as a percentage a year. Leave blank if there is none. |
| Cap and collar compound | Ticked (the usual drafting): 4% a year over three years allows 12.49%. Unticked: 12%. |
| Upwards only | The rent never falls. |

The working is shown on the review: the two index figures, the change, the rent at the index, any cap or collar,
and the new rent. The new rent is filled in for you; check it against the lease before you
[record the outcome](events.md#rent-reviews). The rent schedule entry is marked **Index-linked increase**, and the
figure used becomes the base for the next review.

**Index figures.** Under **Finance**, **Index figures**, PHAEMA keeps the monthly figures. Each day it fetches new
CPI, CPIH and RPI figures from the Office for National Statistics website once they are due. If the server cannot
reach the internet, an administrator downloads the series as a CSV file from the ONS website and uploads it there.
A plain file with two columns, month and value, also works.

## Payments

The agreement page shows the next payments due, worked out from the rent frequency (usual quarter days, other
quarterly dates, monthly or annually in advance). This is a guide: part periods are not apportioned. When the
[rent ledger](rent-ledger.md) is switched on, it raises the actual demands, apportions part periods and records
receipts and arrears.
