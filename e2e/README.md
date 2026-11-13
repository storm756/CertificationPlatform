# Browser journeys (Playwright)

Journeys 1 to 16 of `docs/architecture.md` §18, driven through the real pages in a real browser. (17, the restore drill, is
`docs/runbook.md` §3.1.) They run against **development, CI or staging only**, never production, using **invented data** that
`manage.py e2e_seed` adds and `manage.py e2e_clean` removes. Nothing here uses a real person, question or answer.

| File | Journeys |
| --- | --- |
| `tests/01-registration.spec.ts` | 1 no batch open · 2 adult registers and verifies · 3 17-year-old and guardian · 4 batch closes mid-form |
| `tests/02-attempts.spec.ts` | 5 resume on another phone · 6 double tap on Submit · 7 final locked with the reason · 8 gate choice · 9 result page · 10 no keys in the browser · 11 final shows overall % and bands · plus the `/admin/` 403 check |
| `tests/03-certificates-and-staff.spec.ts` | 12 certificate issued and verified · 13 two tabs, one certificate · 14 mentor scoping (403, logged) · 15 new counted part (preview, confirm) · 16 Marathi learner switches language mid-final |

The journeys run **one at a time, in order** (they change data). Each run needs fresh seed data: clean, seed, run.

## One-time set-up (on the PC that runs the browser)

```bash
cd e2e
npm ci
npx playwright install chromium        # or set E2E_CHANNEL=msedge / chrome to use an installed browser
```

## Run against your own development stack

```bash
# from the repository root, with the dev stack up (docker compose -f deploy/compose.dev.yml up)
DC="docker compose -f deploy/compose.dev.yml exec -T web python manage.py"
$DC e2e_clean; $DC e2e_seed > e2e/manifest.json
cd e2e
BASE_URL=http://localhost:8000 MAILPIT_URL=http://127.0.0.1:8025 npx playwright test
cd .. && $DC e2e_clean                 # remove the invented data afterwards
```

`E2E_MOBILE=1` runs the same journeys at 390px wide. `npx playwright show-report report` opens the last report; a failed journey
keeps a screenshot and a trace under `test-results/`.

## Run against staging (a person does this; Claude never touches the servers, D29)

Do it after the course is loaded (`docs/runbook.md` §7) and, ideally, while no real learner is using staging: journey 15 changes the
module 1 mark split for a few seconds and puts it back.

1. On the server, add the invented data with the owner helper from `docs/runbook.md` (top of the file, `MANAGE=…`):
   ```bash
   "${MANAGE[@]}" e2e_clean; "${MANAGE[@]}" e2e_seed 2>/dev/null > /tmp/e2e-manifest.json
   ```
   The command refuses any settings but dev and staging, so it cannot run on production. Copy `/tmp/e2e-manifest.json` to
   `e2e/manifest.json` on your PC (`scp`; it holds only ids and the invented accounts' addresses, no secrets).
2. On your PC:
   ```bash
   cd e2e && BASE_URL=https://staging.cyberfirstresponse.io npx playwright test
   ```
   Staging sends real e-mail, so there is no Mailpit: journeys **2 and 3** (they read the verification and guardian e-mails) are
   skipped unless you set `MAILPIT_URL`. Check those two by hand once (register, verify, guardian link), or point `MAILPIT_URL` at a
   Mailpit that staging's SMTP is temporarily switched to.
3. Remove the data: `"${MANAGE[@]}" e2e_clean`. It removes the accounts the journeys registered too (every address ending
   `@e2e.example.com`). Sign-up e-mails sent to those addresses are the only mail the run causes.
4. Record the result (pass / fail, date, commit) in `docs/history/`.

## What the seed makes (all marked)

* Batches `E2E-B01` … `E2E-B04`, a mentor for B01/B03/B04, a mentor for B02 and an admin (staff accounts have TOTP; the journeys
  compute the code from the invented secret in `manifest.json`, see `support/totp.ts`).
* Learners with the final locked, open, or already done; a released exam set `E2EJ` that follows the final's blueprint.
* A sandbox module `91` (not counted) with an invented multiple-choice part and an invented interactive part with a gate option, and
  one uncounted extra part in module 1 for journey 15. If a counted module has no published counted part (an empty database, as in
  CI), one invented part of 100 marks stands in so the course is complete. A real course is never edited.
* Invented questions say which option is right in their own words (`RIGHT`), because the browser never receives a key.

`e2e_clean` needs the database owner to remove the released exam set and question versions (they are protected by database triggers,
D31). On staging, `"${MANAGE[@]}"` is the owner. If the app's own role runs it, the set and questions stay, harmlessly, and the
command says so.

## Notes

* Staff accounts sign in once in `global-setup.ts`; an authenticator code works only once, so signing the same account in twice within
  30 seconds would be refused. The sign-in step waits for the next code and retries.
* CSS selectors are language-neutral where a journey runs in Marathi (journey 16).
