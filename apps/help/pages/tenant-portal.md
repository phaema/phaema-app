---
title: Tenant portal
section: Key dates
order: 6
summary: Giving tenants a sign-in to see their account, demands, key dates and the documents you share, and checking contact changes they ask for.
---
# Tenant portal

The tenant portal lets the council's tenants see online what they now phone or email about: what they owe, the
demands to pay, key dates and documents you choose to share. Tenants sign in at **/tenant/**. They are not PHAEMA
users: they never see staff pages, other tenants or anything internal such as notes, cases or valuations.

## Switching it on

An administrator ticks **Tenant portal** in the settings, under **Tenant portal**, and can write a **welcome** that
tenants see first, for example how to contact the estates team. Sign-in codes are emailed through **GOV.UK Notify**
(see [emailing demands](emailing-demands.md)), so the portal cannot be used by tenants until IT has added the
council's Notify key.

## Giving someone an account

Only the estates team adds accounts; tenants cannot add colleagues. In **Manage data → Tenant portal accounts**,
choose **Add**, pick the tenant, and enter the person's name and their own email address. Tick what they may see:

- **Finance**: the account, balance, overdue amounts, demands with **Pay now**, the statement, and asking to change
  contact details for demands.
- **Facilities**: [reporting repairs](repair-reports.md) and following them, and later certificates and service
  charges. On its own it also shows key dates and shared documents.

PHAEMA emails an invitation when you save. To send it again, tick the account and choose **Send the invitation
email again**. To stop someone signing in, untick **Active**: they are signed out at their next click. Accounts are
not deleted, so the change log keeps who had access.

## Signing in

The tenant enters their email address and is emailed a 6-digit code, which works once for 15 minutes. The page
looks the same whether or not the address has an account. After 5 wrong tries the code stops working. Tenants are
signed out after 30 minutes without use.

## What tenants see

For each agreement the council lets to them:

- **Your account**: balance, overdue amount, overdue by age, interest building up on late payment, and the next
  credit control step if it stays unpaid (or that a payment plan is in place). A **Pay** button for the balance.
- **Demands to pay**: each unpaid charge with its reference, due date and a **Pay now** link to the council's
  payment page. Payments come back through the receipts import as now.
- **Statement**: every charge and payment with the running balance.
- **Key dates**: rent review, break dates and notice deadlines, option dates and expiry still to come.
- **Documents**: only the ones you share.
- **Contact details for demands**, with a way to ask for a change.
- **Repairs** (facilities rights, with the maintenance module on): **Report a repair**, and each report's progress,
  target date and who pays. See [repair reports](repair-reports.md).

Agreements stay visible for 12 months after they end, so deposit and dilapidations can be settled. Agreements still
at heads of terms are never shown.

## Sharing documents

Documents are not shared unless you choose. On the agreement, under **Documents**, choose **Share with tenant**
next to a document, or **Stop sharing**. You can also tick **Shared with the tenant** in **Edit this agreement**.

## Contact changes from tenants

When a tenant asks to change their contact details for demands, nothing changes straight away. The managing
surveyor of the property (or an administrator) sees **Contact change from a tenant to check** on their dashboard. In
**Manage data → Contact changes from tenants**, tick it and choose **Accept** (the agreement's billing contact is
updated) or **Decline**. Everything a tenant does is in the change log, marked **Tenant portal** with their name.

## Trying it out

On a test site, IT can set `PHAEMA_PORTAL_SHOW_CODES` so that, while Notify is not set up, the sign-in code is shown
on screen instead of emailed. Never set this on a live site.
