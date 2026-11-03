title: Rent ledger
section: Key dates
order: 4
summary: Raising rent, credit notes, receipts, arrears, statements and the finance export.
---
# Rent ledger

The rent ledger charges rent on agreements the council lets out, records payments from the finance system,
and shows what each tenant owes. It is an optional module: an administrator switches it on in
[settings](settings.md#rent-ledger-settings). When it is on, **Rents** appears in the menu.

## Who raises the invoices

Councils work in one of two ways, chosen in settings:

| Setting | What happens |
|---|---|
| PHAEMA numbers the invoices | Each charge gets an invoice number from PHAEMA (for example PH000123). The finance system records the invoices and collects the money. |
| The finance system raises the invoices | PHAEMA works out what is due and sends it to finance with its own reference (for example PHC000123). Finance raises and numbers the invoices. |

Either way, the [finance export](#the-finance-export) is how charges reach the finance system, and
[receipts](#receipts) come back the same way.

## Raising rent

Administrators: select **Rents**, then **Raise rent**.

1. Choose the range of **payment dates** to charge, for example the next quarter, and the **issue date**.
2. Select **Preview the charges**. PHAEMA lists every charge due between the dates on current and holding-over
   agreements let out by the council.
3. Check the list and select **Raise these charges**.

How PHAEMA works out each charge:

- Rent is due in advance on each payment date, from the agreement's rent frequency (quarter days, other quarterly
  dates, monthly or annually).
- The amount is the annual rent in force on the first day of the period, from the [rent schedule](rent-schedule.md),
  divided by the number of payments a year.
- **Part periods** are apportioned by day (annual rent × days ÷ 365). This happens when an agreement starts
  between quarter days, which is charged from the start date to the day before the first quarter day, or when it
  ends part way through a period.
- **VAT** is added at the standard rate where the agreement is marked VAT chargeable (the council has opted to tax).
- Agreements at a peppercorn or no rent, and agreements where the council is the tenant, are not charged.
- **Rent for a period is only ever charged once**, so runs can overlap without charging twice.

Charges cannot be deleted. Correct a mistake with a [credit note](#credit-notes).

## Rent accounts and statements

Each agreement has a rent account, which you can open from the agreement's page, the arrears list or the receipts
list. It shows every charge and payment in date order with a running balance, and marks what is still owed on each
charge, and whether it is overdue.

Payments are set against the **oldest debt first**. The account can be downloaded to Excel or CSV, or opened as a
**printable statement** to send to the tenant.

A party's page shows the balance of each of their agreements.

## Credit notes

Administrators can credit a charge, in full or in part, from the rent account: open **Credit this charge**, enter
the amount (or leave it blank for the whole charge) and a reason. VAT is credited in proportion. A credit note
gets an invoice number in the same series and goes to finance in the next export.

## Receipts

Payments are recorded in the finance system and imported into PHAEMA. Administrators: select **Rents**, then
**Import receipts**, and follow the usual [import steps](import-export.md#how-every-import-works).

Each payment is matched to an agreement by, in order:

1. the **lease reference**, if given;
2. the **invoice reference** the payer quoted, which can be a PHAEMA invoice number or PHC reference;
3. the **customer reference**, but only if that customer has a single agreement.

Payments already in PHAEMA (same payment reference) are left alone, so importing the same file twice is safe.
A negative amount records a refund or a returned payment.

## Arrears

**Rents**, then **Arrears**, lists every agreement with overdue rent, aged by how long it has been overdue:
1–30 days, 31–60 days, 61–90 days and over 90 days. Download it to Excel for arrears meetings. The
[dashboard](dashboard.md) shows the total arrears and the collection rate.

The **collection rate** is the rent received in the last 12 months as a percentage of the rent that fell due in the
same period.

## The finance export

**Rents**, then **Finance exports**, collects every charge and credit note not yet sent to finance into a numbered
export. Download it as Excel or CSV and load it into the finance system. Each charge is only ever in one export,
and earlier exports can be downloaded again.

The columns are fixed, so the finance team can map them once:

| Column | Contents |
|---|---|
| Record type | Invoice or Credit note. |
| PHAEMA reference | PHAEMA's unique reference for the charge (PHC…). |
| Invoice number | PHAEMA's invoice number, if PHAEMA numbers invoices. |
| Credit for | For a credit note, the invoice it credits. |
| Customer reference, name, address | From the [party](parties.md). The customer reference is the party's finance customer reference. |
| Lease reference, Premises, UPRN | The agreement and its properties. |
| Description, Period from, Period to | What the charge is for. |
| Issue date, Due date | |
| Net, VAT code, VAT rate, VAT, Gross | Amounts in pounds; credit notes are negative. The VAT codes are set in settings. |
| Income code | The rent income ledger code set in settings. |

## Other reports

The [report builder](reports.md) has **Rent charges** and **Rent receipts** datasets, for example to list the rent
charged on one estate, or the charges still waiting to go to finance.
