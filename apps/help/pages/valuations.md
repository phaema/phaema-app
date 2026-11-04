title: Asset valuation
section: Key dates
order: 8
summary: Asset classes set by finance, the yearly valuation programme run as cases, Red Book records, impairment reviews and the year-end schedule.
---
# Asset valuation

The asset valuation module manages the valuations the council needs for its accounts, following the CIPFA Code
of Practice on Local Authority Accounting and the RICS Valuation – Global Standards (the Red Book) with its UK
national supplement. It is an optional module: an administrator switches it on in **Module settings**. Find it
under **Buildings**, **Asset valuation**.

## Finance's criteria

Finance sets the rules, under **Manage data**:

| Setting | What it is |
|---|---|
| Asset classes | Each class's measurement basis, how often it is revalued, any index used in the years between, and whether buildings are depreciated |
| Year end | Normally 31 March |
| De minimis | Assets worth less than this are left out of the programme |
| Componentisation | Buildings worth more than the threshold are valued in significant components (by default, any worth 20% or more of the building value) |
| Valuer rotation | How long an external firm or lead valuer is used before rotating |

PHAEMA starts with the classes in the CIPFA Code, as defaults for finance to confirm:

| Class | Basis | Revalued |
|---|---|---|
| Other land and buildings (operational) | Existing use value; depreciated replacement cost for specialised buildings | Every 5 years |
| Investment property | Fair value | Every year |
| Surplus assets | Fair value | Every 5 years |
| Assets held for sale | Lower of carrying amount and fair value less costs to sell | Every year |
| Heritage assets | As finance decides | Not revalued by default |
| Community assets, assets under construction | Historic cost | Not revalued |

## Classifying assets

Each top-level property needs an asset class. The first time, **Classify them from their holding purpose**
classifies every property from its holding purpose in the register. Change a class on the property's valuation
page with **Reclassify**, giving the date and reason (for example a Cabinet decision to dispose). The history is
kept.

## The yearly programme

The asset valuation page lists the assets due at the year end, and why: not valued yet, due on the class's cycle,
or reclassified since the last valuation. Download the **valuer's data pack** (Excel), with each asset's address,
UPRN, class, basis, tenure, floor areas, leases and rents, and last value, to send with the instructions.

**Start the programme** (administrators) opens a programme case, and an **asset valuation case** for each asset,
owned by its managing surveyor, with an instruction recorded against it. The cases carry the task lists and the
supervisor approval described in [cases](cases.md).

## Recording a valuation

Values come back on each valuation's page, or all at once with the **Valuer's returned figures** import (see
[importing](import-export.md)). PHAEMA records what the Red Book expects a valuation to document:

- the basis, method and purpose;
- when the terms of engagement were agreed;
- the valuation date and the report date, separately;
- the inspection date and its extent: full, external only or desktop;
- special assumptions and key assumptions;
- any material valuation uncertainty, with the valuer's statement;
- the valuer, whether internal or external, their RICS number, and any conflicts of interest declared;
- the value, split between land and buildings, the remaining life of the buildings, and significant components;
- the report itself.

PHAEMA checks that land and buildings add up to the value, and shows the change since the last valuation.

## Accepting for the accounts

An administrator (normally finance) selects **Accept** once the valuation is complete. PHAEMA will not accept a
valuation without a value, valuer, report date and terms of engagement, or a building over the componentisation
threshold without its components. Accepted valuations are locked; an administrator can reopen one.

## Impairment and material change

PHAEMA prompts a review when something happens after a valuation that may affect value: a change of occupation or
holding purpose, a lease ending, an emergency repair, or a component graded D. **Open a review** starts an
impairment review case with the reasons in its notes.

## The year-end schedule

**Year-end schedule for finance** downloads every classified asset with its class, basis, valuer, valuation date,
value, land and buildings split, remaining life, material uncertainty and components, for the fixed asset
register and the working papers.
