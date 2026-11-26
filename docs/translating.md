# Translating PHAEMA

PHAEMA's interface text is in English in the code, marked for translation with Django's standard tools. Each
language has a message file: Welsh is [`locale/cy/LC_MESSAGES/django.po`](../locale/cy/LC_MESSAGES/django.po).

## The Welsh draft

The Welsh translation (about 4,200 phrases, 22,000 words) is a **first draft**, written with machine assistance in
November 2026. It has not yet been checked by a qualified Welsh translator. Every entry carries the comment
`Draft translation awaiting review by a qualified Welsh translator.` A council should have it reviewed before relying
on it, for example by its own translation service or a member of
[Cymdeithas Cyfieithwyr Cymru](https://www.cyfieithwyr.cymru/), the association of Welsh translators.

Terms used throughout the draft, for the reviewer to confirm or change consistently:

| English | Welsh used |
| --- | --- |
| lease / licence | les / trwydded |
| landlord / tenant | landlord / tenant |
| property | eiddo |
| case | achos |
| rent review | adolygiad rhent |
| break option | opsiwn toriad |
| service charge | tâl gwasanaeth |
| arrears | ôl-ddyledion |
| heads of terms | penawdau telerau |
| holding over | dal drosodd |
| contracted out (of the 1954 Act) | wedi'i eithrio o'r Ddeddf |
| surveyor / managing surveyor | syrfëwr / syrfëwr rheoli |
| valuation / valuer | prisiad / prisiwr |
| asset strategy / Asset Challenge | strategaeth asedau / Her Asedau |
| Golden Thread | Edefyn Aur |
| works order | archeb waith |
| demand run | rhediad galwadau |
| access area | maes mynediad |
| two-step sign-in | mewngofnodi dau gam |

Names of standards and bodies (RICS, IPMS, ITZA, EPC, IFRS 16, ONS, HM Land Registry's INSPIRE) are kept as they
are, or given their usual Welsh form (Cofrestrfa Tir EF).

## Reviewing and correcting

1. Open `django.po` in a translation editor such as [Poedit](https://poedit.net/) (free) or in a text editor. Each
   entry has the English `msgid` and the Welsh `msgstr`.
2. Correct the Welsh. Keep placeholders exactly as they are: `%(name)s`, `%(n)s`, `%%`, and any `<strong>` or
   `<a ...>` tags. Plural entries have four forms for Welsh, in this order: for 1, for 2, for every other number
   (including 0), and for 8 and 11.
3. Delete the "Draft translation awaiting review" comment from each entry you have checked, so progress shows.
4. Compile and test: `python manage.py compilemessages -l cy` then `python -m pytest apps/core/test_language.py`.
5. Commit both `django.po` and `django.mo`, and open a pull request.

## When the English changes

After changing or adding interface text, refresh the message file and translate the new entries:

```
python manage.py makemessages -l cy --ignore "venv/*" --ignore "staticfiles/*" --ignore "website/*" \
    --ignore "training/*" --ignore "*/migrations/*"
python manage.py compilemessages -l cy
```

New or changed entries appear untranslated or marked `fuzzy`; fuzzy entries are not shown until the mark is removed.
Words used by the page scripts (for example "Hide" and "Show") are listed in `SCRIPT_TEXT` in
`apps/core/context_processors.py` and translated the same way.

## What is not translated

Records people type, the lists councils keep in Manage data (case types, holding purposes and so on), the built-in
manual, letter templates and emails. These are the next candidates for Welsh versions.
