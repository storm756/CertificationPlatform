"""60 learners take the final exam together (architecture §17, Stage 10).

Each simulated learner signs in with a seeded account (`manage.py loadtest_seed`), waits until
every learner has arrived, then starts the final and answers all of its questions the way a browser
does: open the question page, post the answer, move on, open the review page, submit and read the
result. The questions are the invented ones from the seed; the right option says RIGHT in its text.

    locust -f loadtest/locustfile.py --headless --host https://staging.example.org \
        -u 60 -r 60 --run-time 15m

Pass mark: the 95th percentile of all exam requests together is under 1 second, none fails.
The sign-in requests are reported but not counted (60 password checks at once are setup).
The run ends with a verdict and the exit code reflects it (0 pass, 1 fail). See loadtest/README.md.

Settings (environment variables):
    LT_USERS   learners to simulate (default 60; use -u as well, they must agree)
    LT_THINK   seconds a learner "reads" each question, 0 for none (default 3)
    LT_P95_MS  the pass line in milliseconds (default 1000)
"""

import os
import random
import re

import gevent
from locust import HttpUser, between, events, task
from locust.exception import StopUser
from locust.stats import StatsEntry

PASSWORD = os.environ.get("LT_PASSWORD", "e2e-Invented-Pass-42")
DOMAIN = os.environ.get("LT_DOMAIN", "load.example.com")
USERS = int(os.environ.get("LT_USERS", "60"))
THINK = float(os.environ.get("LT_THINK", "3"))
P95_MS = float(os.environ.get("LT_P95_MS", "1000"))

LABEL = re.compile(r'<label class="opt">(.*?)</label>', re.S)
VALUE = re.compile(r'name="choice" value="([^"]+)"')
POSITION = re.compile(r'class="muted">\s*(\d+)\s*/\s*(\d+)\s*<')
ATTEMPT = re.compile(r"/attempt/(\d+)/")

_numbers = iter(range(1, 10_000))
_arrived = gevent.event.Event()
_waiting = {"n": 0}


class FinalTaker(HttpUser):
    """One learner: sign in, wait for the others, take the whole final, submit."""

    wait_time = between(0, 0)

    def on_start(self):
        self.number = next(_numbers)
        self.email = f"lt{self.number:03d}@{DOMAIN}"
        self.sign_in()
        # Everyone starts the final at the same moment, the worst case for the server.
        _waiting["n"] += 1
        if _waiting["n"] >= USERS:
            _arrived.set()
        _arrived.wait(timeout=300)

    def csrf(self):
        return self.client.cookies.get("csrftoken", "")

    def sign_in(self):
        self.client.get("/accounts/login/", name="/accounts/login/ (page)")
        with self.client.post(
            "/accounts/login/",
            data={"login": self.email, "password": PASSWORD},
            headers={"X-CSRFToken": self.csrf(), "Referer": self.host + "/accounts/login/"},
            name="/accounts/login/ (sign in)",
            catch_response=True,
        ) as response:
            if "/accounts/login/" in response.url:
                response.failure(f"sign-in failed for {self.email}")
                raise StopUser()

    def think(self):
        if THINK > 0:
            gevent.sleep(random.uniform(THINK * 0.5, THINK * 1.5))  # noqa: S311 - not security

    @task
    def take_the_final(self):
        self.client.get("/exam/final/", name="/exam/final/")
        with self.client.post(
            "/exam/final/start/",
            headers={"X-CSRFToken": self.csrf(), "Referer": self.host + "/exam/final/"},
            name="/exam/final/start/",
            catch_response=True,
        ) as response:
            match = ATTEMPT.search(response.url)
            if not match:
                response.failure("the final did not start (locked, limited or not seeded)")
                raise StopUser()
        attempt = match.group(1)

        total = 1
        position = 1
        while position <= total:
            page = self.client.get(
                f"/attempt/{attempt}/q/{position}/", name="/attempt/[id]/q/[n]/"
            ).text
            found = POSITION.search(page)
            if found:
                total = int(found.group(2))
            token = self.right_token(page)
            if token:
                self.client.post(
                    f"/attempt/{attempt}/answer/",
                    data={"position": position, "choice": token, "flag_present": "1"},
                    headers={"X-CSRFToken": self.csrf(), "Referer": self.host + "/"},
                    name="/attempt/[id]/answer/",
                )
            self.think()
            position += 1

        self.client.get(f"/attempt/{attempt}/review/", name="/attempt/[id]/review/")
        self.client.post(
            f"/attempt/{attempt}/submit/",
            headers={"X-CSRFToken": self.csrf(), "Referer": self.host + "/"},
            name="/attempt/[id]/submit/",
        )
        self.client.get(f"/attempt/{attempt}/result/", name="/attempt/[id]/result/")
        raise StopUser()  # one final each

    @staticmethod
    def right_token(page):
        for block in LABEL.findall(page):
            if "RIGHT answer" in block:
                value = VALUE.search(block)
                return value.group(1) if value else None
        return None


@events.quitting.add_listener
def verdict(environment, **_):
    """The pass line covers the exam itself (everything after sign-in); sign-in is reported apart,
    because 60 password checks at once are setup, not the exam."""
    stats = environment.stats
    exam = StatsEntry(stats, "exam", "")
    for (name, _method), entry in stats.entries.items():
        if not name.startswith("/accounts/login/"):
            exam.extend(entry)
    p95 = exam.get_response_time_percentile(0.95) or 0
    failures = stats.total.num_failures
    ok = p95 < P95_MS and failures == 0 and exam.num_requests > 0
    print(
        f"\nVERDICT: {'PASS' if ok else 'FAIL'}: exam requests {exam.num_requests}, "
        f"failures {failures}, p50 {exam.median_response_time} ms, p95 {p95:.0f} ms "
        f"(line: p95 under {P95_MS:.0f} ms and no failures; sign-in not counted)"
    )
    environment.process_exit_code = 0 if ok else 1
