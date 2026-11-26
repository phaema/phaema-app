# Making a PHAEMA release

Councils update from numbered releases, not from whatever is on `main`. Each release has a tag, a GitHub release
with notes, and an entry in [CHANGELOG.md](../CHANGELOG.md).

## Numbering

`MAJOR.MINOR.PATCH`, as in [semantic versioning](https://semver.org/):

- **Patch** (0.10.1): fixes only, no migrations that change data, nothing to do but update.
- **Minor** (0.11.0): new features. Below 1.0 a minor release may also need action when updating; say so under
  **Before updating**.
- **1.0.0**: the first version a council runs live, after the independent security test. Betas are
  `1.0.0-beta.1` and so on.

## Steps

1. Make sure `main` is green: tests, coverage minimum, Ruff, CodeQL and the dependency check.
2. Move the **Unreleased** entries in `CHANGELOG.md` under a new heading with the number and date. Keep
   **Before updating** at the top of the entry if anything needs action.
3. Set `PHAEMA_VERSION` in `phaema/settings.py` to the same number.
4. Merge those two changes in one pull request titled `Release 0.10.0`.
5. Tag the merge commit and push the tag: `git tag -a v0.10.0 -m "PHAEMA 0.10.0"` then `git push origin v0.10.0`.
6. On GitHub, create a release from the tag. Paste the changelog entry as the notes.
7. Update the test site, then tell early adopters (mailing list or user group) with a link to the notes.

## Security fixes

A fix for a reported vulnerability goes out as a patch release as soon as it is ready, with a short note in the
release and in SECURITY.md once councils have had time to update. The reporter is credited if they agree.
