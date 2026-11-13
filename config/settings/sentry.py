"""Sentry set-up (architecture §16, §17). Off when SENTRY_DSN is empty.

No PII is sent: request bodies, cookies, headers, query strings and the user are dropped;
stack frames carry no local variables; email addresses are masked in messages, exception text
and breadcrumbs (a database error can quote one). A person creates the Sentry project and puts
its DSN in /srv/csfr/<env>/app.env (docs/runbook.md).
"""

import re

import sentry_sdk

_SCRUB_KEYS = {"cookies", "data", "headers", "query_string", "env"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
MASK = "[email]"


def _mask(value):
    return _EMAIL.sub(MASK, value) if isinstance(value, str) else value


def _mask_breadcrumb(crumb):
    crumb["message"] = _mask(crumb.get("message"))
    data = crumb.get("data")
    if isinstance(data, dict):
        crumb["data"] = {key: _mask(value) for key, value in data.items()}
    return crumb


def scrub_event(event, hint):
    request = event.get("request")
    if request:
        for key in _SCRUB_KEYS & request.keys():
            request[key] = "[scrubbed]"
    event.pop("user", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        exc["value"] = _mask(exc.get("value"))
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        logentry["message"] = _mask(logentry.get("message"))
        logentry.pop("params", None)
    event["message"] = _mask(event.get("message")) if "message" in event else None
    if event["message"] is None:
        event.pop("message")
    crumbs = event.get("breadcrumbs")
    values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
    for crumb in values or []:
        _mask_breadcrumb(crumb)
    return event


def scrub_breadcrumb(crumb, hint):
    return _mask_breadcrumb(crumb)


def init_sentry(dsn: str, environment: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        include_local_variables=False,
        traces_sample_rate=0.0,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
    )
