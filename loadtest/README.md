# Load test: 60 learners take the final together (locust)

**Pass line (Stage 10, architecture §17): p95 under 1 second** for every request of the exam together, with no failures, while 60
simulated learners sign in, wait for each other, then take the whole final at the same moment.

Run it against **staging only, by a person** (D29). Claude only ever ran a 5-learner smoke test against a local development stack.
Never run it against production.

## What it does

`locustfile.py` simulates one learner per user: sign in, wait until all 60 have arrived, open the final, start it, then for every
question open the page, post the answer (the invented questions say which option is `RIGHT`), "read" for `LT_THINK` seconds, and
finally open the review page, submit and read the result. It uses the same pages a browser does, with the CSRF token and cookies.
Sign-in is reported but **not counted** against the pass line (60 password checks at once are set-up, not the exam).

## Set-up (on a PC, not on the server)

```bash
python -m venv .venv-load && . .venv-load/bin/activate     # Windows: .venv-load\Scripts\activate
pip install -r loadtest/requirements.txt
```

## Run on staging

1. Staging has the course loaded and the Playwright journeys have passed (`e2e/README.md`). Nobody else should be using staging.
2. Add the 60 learners and the exam set, on the server with the owner helper from `docs/runbook.md`:
   ```bash
   "${MANAGE[@]}" loadtest_seed --count 60
   ```
   (Refuses any settings but dev and staging. Learners are `lt001@load.example.com` … `lt060@load.example.com`, batch `LT-01`, all with the
   final open. The released exam set is the same `E2EJ` set as the journeys use; `e2e_seed` is not needed first.)
3. From one network (all 60 sign in from the same address; the per-network sign-in limit is 90 a minute, so 60 fit):
   ```bash
   locust -f loadtest/locustfile.py --headless --host https://staging.cyberfirstresponse.io \
          -u 60 -r 60 --run-time 20m --csv loadtest/results
   ```
   `-r 60` starts everyone at once. The run stops when the 60 learners have finished (or at `--run-time`). `LT_THINK` (default 3 s per
   question) is the pause between questions; use `LT_THINK=0` for the harshest case. Environment variables: `LT_USERS` (default 60,
   keep it equal to `-u`), `LT_THINK`, `LT_P95_MS` (the pass line, default 1000), `LT_PASSWORD`, `LT_DOMAIN`.
4. Read the last lines: `VERDICT: PASS` or `FAIL` with the p50 and p95 of the exam requests (the exit code is 0 or 1). The table above
   it gives each endpoint. A failure on `/exam/final/start/` usually means a learner was not seeded or the final is locked.
5. Look at the server while it runs: `docker stats`, and `docker compose logs web | tail` for errors. Record the numbers (users, think
   time, p50, p95, failures, server size, commit) in `docs/history/` and tick launch checklist item 7 in `docs/STATUS.md`.
6. Remove everything: `"${MANAGE[@]}" loadtest_seed --clean` (the learners, their attempts and the batch) and, to remove the
   exam set too, `"${MANAGE[@]}" e2e_clean`. The server's rate limits (answers 1200 an hour per learner, submits 60 an hour) are not
   reached by one final each.

If the run fails the line, do not change the limit: send the numbers back (the slowest endpoint, the server's CPU and memory) as a
note for a Claude session to fix in a PR.
