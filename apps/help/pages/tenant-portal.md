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
- **Facilities**: [reporting repairs](repair-reports.md), service charge budgets and statements, and certificates
  the tenant provides. It also shows key dates and shared documents.

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
- **Requests**: **Make a request** for a consent, such as to assign, underlet or alter the premises, with guidance
  and a list of documents to attach for each kind. It opens a case at once, and the tenant follows its stage, target
  date and decision. See [requests from tenants and departments](cases.md#requests-from-tenants-and-departments).
- **Service charges** (facilities rights, with the service charge module on): the budget and year-end statements
  you have issued, and a way to query a line. See [service charges](service-charges.md#in-the-tenant-portal).
- **Certificates you provide** (facilities rights, with the compliance module on): certificates the tenant must
  arrange, such as a gas safety record, with their status, and a way to send a new one. Tenants are reminded by email
  before they run out. See [compliance](compliance.md#certificates-tenants-provide).
- **Repairs** (facilities rights, with the maintenance module on): **Report a repair**, and each report's progress,
  target date and who pays. See [repair reports](repair-reports.md).

Agreements stay visible for 12 months after they end, so deposit and dilapidations can be settled. Agreements still
at heads of terms are never shown.

## Messages

Tenants can send the estates team a message about an agreement, or about one of their requests, from **Messages
with the estates team** on the agreement page. It goes to the managing surveyor of the property and anyone
[covering for them](users-and-roles.md) that day; if no one manages the property, to the administrators. They are
emailed that there is a message (the text stays in PHAEMA) and see **Message from a tenant** on their dashboard.

Open the agreement and choose the link to the messages, read the thread and **Send the reply**. The tenant is emailed
through GOV.UK Notify that there is a reply, and sees it in the portal. Administrators and surveyors can reply.

## Insurance, rent deposit and payment plan

- **Insurance**: tenants see who insures under their agreement. Where the tenant insures, they see the date of the
  latest certificate you hold and can **send your insurance certificate** (insurer, when the cover runs until, and
  a PDF). It is filed with the agreement's documents as an insurance certificate, marked as sent by the tenant, with
  the cover end date as its date for review, so it comes up on the dashboard before it runs out.
- **Rent deposit** (finance rights): the balance held and every movement, as on the agreement's deposit account.
- **Payment plan** (finance rights): when a plan is in place or was recently not kept, the arrears it covers, how
  much is paid off and still to pay, whether it is on track or behind, and the instalments.

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
