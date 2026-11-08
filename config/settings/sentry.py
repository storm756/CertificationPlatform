"""Sentry set-up. No PII is sent; request bodies, cookies and user data are scrubbed."""

import sentry_sdk

_SCRUB_KEYS = {"cookies", "data", "headers", "query_string"}


def scrub_event(event, hint):
    request = event.get("request")
    if request:
        for key in _SCRUB_KEYS & request.keys():
            request[key] = "[scrubbed]"
    event.pop("user", None)
    return event


def init_sentry(dsn: str, environment: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        traces_sample_rate=0.0,
        before_send=scrub_event,
    )
