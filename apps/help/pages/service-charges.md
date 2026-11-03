title: Service charges
section: Key dates
order: 5
summary: Schedules, shares, budgets, on-account demands, spending and the year-end reconciliation.
---
# Service charges

Service charges recover the cost of shared services, such as estate roads, landscaping, security and cleaning of
common parts, from the tenants who benefit. It is an optional module: an administrator switches it on in
[settings](settings.md#rent-ledger-settings), and it needs the [rent ledger](rent-ledger.md), because service
charges are demanded and collected through it. When it is on, **Service charges** appears in the menu.

The module follows the usual approach set out in the RICS professional statement on service charges in
commercial property: a budget, payments on account, and a year-end reconciliation against actual costs.

## Schedules

A schedule is one pool of shared costs. Administrators set it up in **Manage data**, then **Service charge
schedules**:

- the **properties covered**, such as an estate or a building;
- **how costs are shared**: by floor area (NIA), by fixed percentages set for each lease, or equally per unit;
- when the **service charge year** starts, usually 1 April;
- the **contributing leases**, each with an optional **annual cap** if the lease limits the service charge.

Use separate schedules where different tenants pay for different things, for example one for the estate roads
and another for a building's lift.

## Shares

Shares are worked out over all the lettable units in the schedule, **including empty ones**. The council pays
the share of any unit that is not let (the void share), as a landlord normally must. The schedule page shows
each lease's floor area, share and on-account payment, and the council's share.

## Budgets and payments on account

For each year, add the **budget** by cost heading (cleaning, security, repairs and so on) in **Manage data**,
then **Service charge years**. When it is agreed, open the year and select **Approve the budget**.

From then on, every [demand run](rent-ledger.md#raising-rent) also charges each lease its share of the budget,
on its rent payment dates, as **service charge on account**. You can choose to charge rent only, service charges
only, or both. Where a payment period runs over the end of the service charge year, it is split, and each part is
charged at its own year's budget. VAT is added where the lease is VAT chargeable.

## Spending

Record what the council actually spends on each heading during the year:

- in **Manage data**, on the year, or
- by importing it from the finance system: **Import**, then **Service charge spending**. Each row gives the
  schedule, date, heading, supplier, description, invoice reference and amount. The date decides which year the
  cost falls in. A row with an invoice reference already recorded for that year is not added twice.

The year page compares **budget and actual** by heading, and can be downloaded to Excel.

## Year-end reconciliation

After the year ends and all the spending is in, open the year and select **Reconcile the year**. For each lease,
PHAEMA works out:

1. its share of the **actual** spending;
2. scaled by the **days it was in force** in the year, for leases that started or ended during it;
3. limited by any **cap**;
4. less what it was **charged on account**.

The result is a **balancing charge** (the tenant owes more) or a **balancing credit** (the tenant paid too much).
The preview also shows how much the council bears for empty units, part years and caps. Confirm it and PHAEMA
raises the balancing charges and credits on the tenants' rent accounts, numbered and ready for the next
[finance export](rent-ledger.md#the-finance-export), and closes the year.

The RICS professional statement recommends that tenants receive their year-end statement within four months of
the year end.

## Tenant statements

Each lease has a printable **service charge statement** for the year, linked from the year page. It shows the
schedule's budget and actual costs by heading, the tenant's share, the days and any cap applied, what was paid on
account, and the balance. Before the year is reconciled it is marked as a draft.
