# Users and roles

PHAEMA has three roles. Give each person one role in **Manage data > Users** (tick the group under *Role*).

| What they can do | Administrators | Surveyors | Viewers |
|---|:-:|:-:|:-:|
| View the register, maps, leases, titles, photos, documents and change log | ✓ | ✓ | ✓ |
| Change properties | All | Only those they manage | – |
| Add properties | ✓ | ✓ (they become the managing surveyor; parts only under their own properties) | – |
| Add and remove photos | All properties | Their own properties | – |
| Set boundaries from Land Registry INSPIRE parcels | All properties | Their own properties | – |
| Add and change leases, licences and break options | All | Leases on properties they manage | – |
| Record outcomes of lease events, assign them and add events | All | Events on leases of properties they manage | – |
| Change rent schedules (steps, concessions, indexation) | All | Leases of properties they manage | – |
| Add and change tenants and other parties | ✓ | ✓ | – |
| Delete properties and leases | ✓ | – | – |
| Titles and title documents | Change | View | View |
| Assign managing surveyors | ✓ | – | – |
| Spreadsheet import (properties, parties, leases and breaks) and INSPIRE import | ✓ | – | – |
| Download lists to Excel or CSV, run reports | ✓ | ✓ | ✓ |
| Save their own reports and share them | ✓ | ✓ | ✓ |
| Change or delete another person's report | ✓ | – | – |
| Change the ready-made reports | ✓ | – | – |
| See rent accounts, statements, arrears and receipts | ✓ | ✓ | ✓ |
| Start and work on cases | All | Own cases, or on properties they manage | – |
| See confidential case notes | ✓ | Cases they own | – |
| Approve a case stage | Any waiting request (not their own); redirect requests | Requests from the people they supervise | – |
| Raise rent, issue credit notes, import receipts, create finance exports | ✓ | – | – |
| See service charge schedules, years and tenant statements | ✓ | ✓ | ✓ |
| Set up schedules, budgets and spending; approve budgets; reconcile years | ✓ | – | – |
| See maintenance jobs, planned tasks, components, contractors and contracts | ✓ | ✓ | ✓ |
| Report repairs | ✓ | ✓ | – |
| Work on jobs (order, complete, recharge); add components and planned tasks | All | Properties they manage, and jobs they own | – |
| Approve works orders over the limit | Any (not their own) | Orders from the people they supervise | – |
| Add contractors and contracts | ✓ | – | – |
| Record certificates, screen buildings, add building documents | All | Properties they manage | – |
| Module settings (OS Maps key, reminder lead times, brand colour, rent ledger) | ✓ | – | – |
| Add users and give them roles | ✓ (not superusers) | – | – |
| Use the API | Read and write | Read; change what they can change on screen | Read only |

Notes:

- "Manage data" (the data-entry screens) appears for Administrators and Surveyors. Records a surveyor cannot change open read-only.
- Someone who signs in without a role sees a "no access yet" page until an administrator gives them one.
- The person who installs PHAEMA creates a **superuser** with `./phaema.sh admin`. Superusers can do everything, including creating other superusers. Keep superuser accounts to a minimum and use the Administrators role day to day.
- Every change, whoever makes it, is recorded in the change log.

A fourth role, **Contributors**, can see everything and add notes, documents and correspondence to the cases they are added to (for example the legal team). They cannot change anything else.
