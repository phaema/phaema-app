title: Users and roles
section: Running PHAEMA
order: 1
summary: What administrators, surveyors and viewers can do, and how to add users.
---
# Users and roles

Everyone who uses PHAEMA has a user account and one **role**. The role decides what they can change. Anyone with
a role can see every record, run reports and download lists.

| | Administrator | Surveyor | Contributor | Viewer |
|---|---|---|---|---|
| See everything, run reports, download | Yes | Yes | Yes | Yes |
| Start cases and work on them | All | Their own, or on properties they manage | No | No |
| Add notes, documents and emails to cases | All | As above | Cases they are added to | No |
| See confidential case notes | Yes | Cases they own | No | No |
| Change properties | All | Those they manage | No | No |
| Change leases, breaks, rents, documents and events | All | On properties they manage | No | No |
| Change parties' details | Yes | Yes | No | No |
| Titles, INSPIRE boundaries, settings | Yes | No | No | No |
| Import from spreadsheets | Yes | No | No | No |
| Add users and give roles | Yes | No | No | No |
| Change ready-made reports | Yes | No | No | No |

A surveyor **manages** a property when they are its managing surveyor. They can change the agreements that include
that property and the events on those agreements.

**Contributors** are colleagues outside the estates team, such as the legal officer, who work on particular
cases. Add them to a case in its **People** section.

Someone who can sign in but has no role sees a "no access" page until an administrator gives them one.

## Adding a user

Administrators: select **Manage data**, then **Users**, then **Add user**. Set a username and a starting password,
then on the next page add their name and email address and choose one group: **Administrators**, **Surveyors**,
**Contributors** or **Viewers**. Their email address is used for [reminders](reminders.md).

![Manage data](/static/help/admin.jpg)
*Manage data, where administrators add users and change settings.*


## Supervisors

Each surveyor needs a **supervisor and approver**, who approves their recommendations on [cases](cases.md#approvals).
On the user record, under **Staff details**, choose the supervisor and add a job title. The supervisor can be a
surveyor or an administrator, but nobody can approve their own work. The users
list shows each person's supervisor, and the dashboard tells administrators about any surveyor without one.

To stop someone using PHAEMA, untick **Active** on their user record rather than deleting it, so their name stays
on the records they changed.

## Handing over work

When someone leaves, changes job or a new starter takes over part of a patch, administrators can move their work
in one step at **Hand over work** (`/people/hand-over/`, also linked from each user record).

1. Choose who the work comes **from**, who it goes **to**, and optionally **Only work on** one estate, site or
   building to hand over just that part of their patch.
2. Select **Show their work**. PHAEMA counts what they hold: properties they manage, open cases they own, case
   tasks not yet done, case approvals waiting for them, open cases they contribute to, lease events assigned to
   them, maintenance jobs they own, works orders waiting for their approval, valuation audit queries and the staff
   they supervise.
3. For each kind of work, keep the person you chose, pick someone else, or choose **Leave with** to keep it where
   it is. Properties, cases and approvals can only go to surveyors and administrators; contributors can also take
   over case contributions.
4. For a leaver, tick **Also stop them signing in**. Then select **Hand over work**.

Closed cases, completed tasks and past approvals keep the original names, so the history stays true. Every record
moved is listed in the [change log](change-log.md) under your name. To undo a hand-over, hand the same work back.
If the person is also an internal valuer, change the valuer record under **Manage data**, **Valuers**.
