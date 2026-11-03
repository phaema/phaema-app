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
| Module settings (OS Maps key, reminder lead times, brand colour) | ✓ | – | – |
| Add users and give them roles | ✓ (not superusers) | – | – |
| Use the API | Read and write | Read; change what they can change on screen | Read only |

Notes:

- "Manage data" (the data-entry screens) appears for Administrators and Surveyors. Records a surveyor cannot change open read-only.
- Someone who signs in without a role sees a "no access yet" page until an administrator gives them one.
- The person who installs PHAEMA creates a **superuser** with `./phaema.sh admin`. Superusers can do everything, including creating other superusers. Keep superuser accounts to a minimum and use the Administrators role day to day.
- Every change, whoever makes it, is recorded in the change log.
