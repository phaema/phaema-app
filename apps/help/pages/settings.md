title: Settings and themes
section: Running PHAEMA
order: 2
summary: Council-wide settings, reminder timings, maps, branding, themes and accessibility.
---
# Settings and themes

## Council settings

Administrators: select **Manage data**, then **Module settings**. There is one set of settings for the whole council.

| Setting | What it does |
|---|---|
| Organisation name | Shown in the header of every page. |
| Modules | Turn on modules as they become available: rent ledger, service charges, maintenance, compliance and the Golden Thread. |
| Letters and notices | The department, postal address (also the address for service of notices), phone and email printed on letters from the [document library](documents.md). |
| Publish open data | Publishes the Transparency Code land and assets list and the list of available property at /open-data/, without signing in. See [open data](compliance.md#open-data). |
| Works orders needing approval | Works orders estimated above this need the supervisor's approval. See [maintenance](maintenance.md#works-orders-and-approval). |
| OS Maps API key and style | Turns on Ordnance Survey base maps. See [maps](maps.md#base-maps). |
| Brand colour | The colour of the header, as a hex code such as #003078. Choose a dark colour so the white text stays readable. Leave blank for the PHAEMA blue. |
| Two-step sign-in | Who must use an authenticator app code after their password: administrators (the default), everyone, or nobody. See [two-step sign-in](users-and-roles.md#two-step-sign-in). |
| Single sign-on | Lets people sign in with their council account (Microsoft 365 and others), and sets who can still use a PHAEMA password. See [signing in with your council account](users-and-roles.md#signing-in-with-your-council-account). |
| Reminder timings | See [reminders](#reminders). |

### Rent ledger settings

| Setting | What it does |
|---|---|
| Rent ledger | Switches the [rent ledger](rent-ledger.md) on. |
| Who raises rent invoices | PHAEMA numbers the invoices, or the finance system raises them. See [who raises the invoices](rent-ledger.md#who-raises-the-invoices). |
| Invoice number prefix and next invoice number | How PHAEMA numbers invoices and credit notes, for example PH000123. Set the next number when you start, so it does not clash with existing invoices. |
| Standard VAT rate | Added to rent on agreements marked VAT chargeable. |
| Rent income code | The finance ledger code for rent income, included in the finance export. |
| Service charge ledger | Switches on [service charges](service-charges.md). Needs the rent ledger. |
| Service charge income code | The finance ledger code for service charge income. If blank, the rent income code is used. |
| VAT codes | The finance system's codes for standard-rated and exempt lines. |

### Reminders

For each kind of event, list how many days before the date to send reminders, separated by commas: for example
`180,90,30`. Tick or untick **Weekly overdue reminders** to turn
Monday reminders about overdue events on or off. See [reminders and calendar](reminders.md).

## Themes and accessibility

Each person can choose how PHAEMA looks, using the links under the menu. Your choice is remembered on that computer.

| Theme | Best for |
|---|---|
| Standard | Most people. GOV.UK colours. |
| Dark | Low light, or if you find white backgrounds tiring. |
| High contrast | Low vision. Yellow and white text on black. |
| Match my device | Follows your computer's or phone's light or dark mode. |

**Style** changes the layout and lettering. It works with any theme.

| Style | What it looks like |
|---|---|
| Classic | The GOV.UK look. |
| Clear | Each section sits in its own box with a coloured edge showing what it is about: purple for cases, blue for leases, green for buildings, brown for money and navy for the estate. The section heading always says the same, so the colour is only a help. Uses Atkinson Hyperlegible, a typeface the Braille Institute designed so that easily confused letters and numbers (such as I, l and 1, or O and 0) look different. |
| Compact | Smaller headings and tighter tables, so more fits on a large screen. |

**Hide and show sections.** Dashboard sections have a **Hide** link in their heading. PHAEMA remembers which you
have hidden on that computer. **Hide all** and **Show all** do every section at once. Hidden sections still print.

**Text size** makes all text smaller or larger. Your browser's zoom (Ctrl and + on Windows, Cmd and + on a Mac) also works
on every page.

PHAEMA is built with the GOV.UK Design System and aims to meet the Web Content Accessibility Guidelines (WCAG) 2.2
at level AA. Every page works with a keyboard alone and with screen readers. Report any problem to your PHAEMA
administrator.
