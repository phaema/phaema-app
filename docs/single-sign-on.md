# Single sign-on with the council's own accounts

PHAEMA can let people sign in with the accounts they already use at work, through OpenID Connect. This guide covers
Microsoft 365 (Microsoft Entra ID); Keycloak and other OpenID Connect services work the same way with their own
addresses. It is optional and off until both steps below are done. With it off, PHAEMA works exactly as before.

## What it does

- A **Sign in with Microsoft** button appears on the sign-in page. The council's own password, multi-factor and
  conditional access rules apply, so PHAEMA's two-step sign-in is not asked for as well.
- People are matched to their PHAEMA account by email address the first time, and by their fixed Microsoft ID
  after that, so a later change of name or address does not matter.
- Roles and access areas can follow Microsoft groups (optional).
- People outside the council (consultants, valuers, solicitors) can keep a PHAEMA password, or be invited as
  guests in Microsoft Entra and use the button like staff.
- Administrators keep a PHAEMA password and two-step sign-in as a fallback if Microsoft is unavailable. The
  superuser made at installation always signs in with a PHAEMA password and is never linked to a Microsoft account.

PHAEMA asks Microsoft only for the person's name, email address and (if you use them) groups. It does not read
mail, files or calendars, and keeps no Microsoft password or token.

## Step 1: the council's IT team registers PHAEMA in Microsoft Entra

1. In the Microsoft Entra admin centre open **App registrations**, **New registration**.
2. Name: `PHAEMA`. Supported account types: **Accounts in this organizational directory only**.
3. Redirect URI: platform **Web**, address `https://YOUR-PHAEMA-ADDRESS/login/sso/callback/`.
4. Select **Register**. Note the **Application (client) ID** and the **Directory (tenant) ID**.
5. **Certificates & secrets**, **New client secret**. Note the secret's **Value** and its expiry date (put a
   reminder in a calendar: sign-in stops when it expires).
6. **Token configuration**, **Add optional claim**, **ID** token, tick **email**, **given_name** and
   **family_name**.
7. For roles from groups (optional): **Token configuration**, **Add groups claim**, choose **Groups assigned to the
   application**, and for the ID token choose **Group ID**. Then in **Enterprise applications**, **PHAEMA**,
   **Users and groups**, add the groups that should use PHAEMA. Under **Properties** set **Assignment required** to
   **Yes** if only those groups may sign in.

No API permissions beyond the default sign-in permission are needed, and no administrator consent for mail or files.

## Step 2: the installer adds the details to the server

On the PHAEMA server, add to `/opt/phaema/.env` (replace the capitals):

```
PHAEMA_SSO_ISSUER=https://login.microsoftonline.com/TENANT-ID/v2.0
PHAEMA_SSO_CLIENT_ID=CLIENT-ID
PHAEMA_SSO_CLIENT_SECRET=SECRET-VALUE
PHAEMA_SSO_NAME=Microsoft
```

Check that `PHAEMA_BASE_URL` is the https address people use, then run `./phaema.sh update`.

## Step 3: an administrator turns it on

1. Make sure each person's PHAEMA account has their work email address (**Manage data**, **Users**).
2. **Manage data**, **Module settings**, **Single sign-on**: tick **Sign in with the council's own accounts**.
3. Choose **who can still sign in with a PHAEMA password**:
   - *Only people without a council account, and administrators as a fallback* (the default). Once someone has
     signed in with Microsoft, their PHAEMA password stops working. Outside consultants who have never used the
     button keep theirs.
   - *Anyone, as well as their council account.* Useful while you are trying it out.
4. **Create a PHAEMA account at first council sign-in** is off to start with: only people you have added can sign
   in. Turn it on to let anyone Microsoft allows through have an account; they see nothing until they have a role.

Test with one person in a private browser window before telling everyone, and keep an administrator signed in
while you do.

## Roles and access areas from groups (optional)

**Manage data**, **Sign-in group mappings**, **Add**. Paste the group's **Object ID** from Microsoft Entra, describe
it, and choose the role, the access area, or both, that its members get. Add one line for each.

- At every sign-in, a person gains the mapped roles and areas of the groups they are in, and loses mapped roles
  and areas of groups they are no longer in.
- Roles and areas that no mapping mentions stay as an administrator set them.
- With no mappings, roles are managed in PHAEMA as before.
- Changes are recorded in the change log.
- If a person is in more groups than Microsoft will list (over 200), their roles are left unchanged. Choosing
  **Groups assigned to the application** in step 1 avoids this.
- Instead of groups you can use Entra **app roles**: put the app role's value in the mapping.

## Leavers and movers

- When a council account is closed or blocked, the person can no longer sign in with Microsoft. With the default
  password setting they cannot use a PHAEMA password either.
- Someone already signed in stays signed in until their PHAEMA session ends (up to two weeks). To stop access at once, and to move
  their work, use **Hand over work**.
- Outside consultants with PHAEMA passwords are not affected by Microsoft: close their accounts in PHAEMA when
  their work ends.
- To move a person to a different Microsoft account, open them in **Manage data**, **Users**, tick **Delete** in
  the **Council sign-in** box and save. They are matched again by email address at their next sign-in.

## Other sign-in services

Set `PHAEMA_SSO_ISSUER` to the service's issuer address (the part before `/.well-known/openid-configuration`), for
example `https://sso.example.gov.uk/realms/council` for Keycloak, and `PHAEMA_SSO_NAME` to the name for the button.
The service must send an `email` claim; groups are read from the `groups` and `roles` claims.

## If something goes wrong

| What people see | Likely cause |
|---|---|
| "There is no PHAEMA account for ..." | Their PHAEMA account has a different email address, or none. |
| "The sign-in service refused the request" | The client secret is wrong or has expired, or the redirect address in Entra does not match. |
| "The sign-in service does not match the address in the single sign-on settings" | The tenant ID in `PHAEMA_SSO_ISSUER` is wrong. |
| Microsoft shows a redirect address error (AADSTS50011) | The redirect URI in Entra must be exactly `PHAEMA_BASE_URL` followed by `/login/sso/callback/`. |
| No button on the sign-in page | The three `PHAEMA_SSO_` settings are not all set, or the Module settings box is not ticked. |

Details are written to the server log (`./phaema.sh logs`).
