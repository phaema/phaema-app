# Contributing to PHAEMA

Thank you for helping. Councils, suppliers and individuals are all welcome to contribute.

## How to contribute

1. Raise an issue describing the problem or improvement, so it can be discussed first.
2. Make your change on a branch and open a pull request.
3. Make sure the tests pass (`python -m pytest`) and add tests for new behaviour.
4. Sign off every commit (see below).

## Developer Certificate of Origin (DCO)

PHAEMA does not ask you to assign your copyright. Instead, each commit must be signed off to confirm you have the right to contribute it under the project's licence. Add a line like this to each commit message (Git does this for you with `git commit -s`):

```
Signed-off-by: Your Name <your.email@example.org>
```

By signing off you agree to the Developer Certificate of Origin 1.1:

> By making a contribution to this project, I certify that:
>
> (a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or
>
> (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications, whether created in whole or in part by me, under the same open source license (unless I am permitted to submit under a different license), as indicated in the file; or
>
> (c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not modified it.
>
> (d) I understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

## Councils commissioning work

If your council pays a supplier to develop PHAEMA features, please make it a condition of the contract that the work is released under the project licence and contributed back.

## Code style

- Python: follow PEP 8; keep functions small and readable.
- Every source file starts with `# SPDX-License-Identifier: AGPL-3.0-or-later`.
- User-facing text is wrapped for translation (`gettext` / `{% translate %}`) so PHAEMA can be offered in Welsh.
- Use plain English in screens and messages, following the GOV.UK style guide.

## Security issues

Please do not report security vulnerabilities in public issues. Email the maintainers privately (contact to be published in `SECURITY.md`).
