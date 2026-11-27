---
title: Emailing demands
section: Key dates
order: 5
summary: Sending each tenant an email with their charges and a "Pay now" link after a demand run, through GOV.UK Notify.
---
# Emailing demands

After you raise rent in a [demand run](rent-ledger.md), PHAEMA can email each tenant their charges, the total,
anything already overdue on their account and a **Pay now** link to the council's online payment page.

## Before you start

An administrator switches this on in the settings, under **Letters and notices**:

- **Email demands**: tick to show the option on each demand run.
- **Payment link**: the address of the council's payment page. You can include `{reference}`, `{amount}` and
  `{account}`, which PHAEMA fills in for each tenant, for example
  `https://pay.example.gov.uk/rent?ref={reference}&amount={amount}`. Without a link, emails are sent without
  "Pay now".

Emails are sent through **GOV.UK Notify**, the free government service councils use for emails and text messages.
Until IT has added the council's Notify key, PHAEMA **records** each email so you can see exactly what would have
gone, but sends nothing. This lets you try it out safely.

## Who gets the email

Each agreement in the run gets one email, listing its charges. It goes to the **billing email** on the agreement if
there is one, otherwise to the tenant's email. Agreements with no email address are listed so you can add one.

The tenant is asked to quote the charge's number when paying, or the agreement's reference if there is more than one
charge.

## Sending

1. Open the demand run and choose **Email these demands to tenants**.
2. Check the list and open **See an example email**.
3. Choose **Send the emails** (or **Record the emails** if Notify is not set up yet).

Each agreement is emailed once per run: choosing send again only emails agreements added since, such as ones you have
just given an email address. If Notify refuses an email, it is marked **Not sent** and you can try it again.

Only administrators and surveyors with finance actions can send demands.

## A record of every email

Every email is kept, with who sent it and when, in **Settings → Emails to tenants**. These records cannot be changed
or deleted.

Emails do **not** replace any notice that the agreement says must be served by post or by hand. Check the
agreement's notice clause before relying on email alone.

## For IT

Set `PHAEMA_NOTIFY_API_KEY` to the council's Notify API key and `PHAEMA_NOTIFY_TEMPLATE_ID` to the ID of an email
template in Notify whose subject is `((subject))` and whose message is `((body))`. A Notify "test" key lets you check
the connection without anything being delivered.
