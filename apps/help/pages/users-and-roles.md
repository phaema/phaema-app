title: Users and roles
section: Running PHAEMA
order: 1
summary: What administrators, surveyors and viewers can do, and how to add users.
---
# Users and roles

Everyone who uses PHAEMA has a user account and one **role**. The role decides what they can change. Anyone with
a role can see every record, run reports and download lists.

| | Administrator | Surveyor | Viewer |
|---|---|---|---|
| See everything, run reports, download | Yes | Yes | Yes |
| Change properties | All | Those they manage | No |
| Change leases, breaks, rents, documents and events | All | On properties they manage | No |
| Change parties' details | Yes | Yes | No |
| Titles, INSPIRE boundaries, settings | Yes | No | No |
| Import from spreadsheets | Yes | No | No |
| Add users and give roles | Yes | No | No |
| Change ready-made reports | Yes | No | No |

A surveyor **manages** a property when they are its managing surveyor. They can change the agreements that include
that property and the events on those agreements.

Someone who can sign in but has no role sees a "no access" page until an administrator gives them one.

## Adding a user

Administrators: select **Manage data**, then **Users**, then **Add user**. Set a username and a starting password,
then on the next page add their name and email address and choose one group: **Administrators**, **Surveyors** or
**Viewers**. Their email address is used for [reminders](reminders.md).

To stop someone using PHAEMA, untick **Active** on their user record rather than deleting it, so their name stays
on the records they changed.
