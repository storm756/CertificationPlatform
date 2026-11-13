"""What a person sees when a rate limit stops them (Stage 10).

Every limit is keyed per signed-in user, per batch (sign-up) or per real client IP
(`apps.audit.services.client_ip`), never django-ratelimit's `key="ip"`, which behind Caddy is
Caddy's own address and would make one bucket for the whole site.

The page always says how long to wait, so nobody is left guessing.
"""

from django.shortcuts import render

ALLAUTH_WAIT_MINUTES = 1  # allauth's limits on sign-in and password reset are per minute
HOURLY_WAIT_MINUTES = 60  # our own per-user / per-IP limits on endpoints are per hour


def window_minutes(rate: str) -> int:
    """'90/10m' -> 10, '30/h' -> 60, '5/m' -> 1: the longest anyone waits under that rate."""
    period = rate.split("/", 1)[1]
    digits = "".join(ch for ch in period if ch.isdigit())
    unit = period[len(digits) :] or "s"
    seconds = int(digits or 1) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit[0]]
    return max(1, -(-seconds // 60))


def too_many(request, minutes: int, template: str = "429.html", context=None):
    response = render(request, template, {"wait_minutes": minutes, **(context or {})}, status=429)
    response["Retry-After"] = str(minutes * 60)
    response["Cache-Control"] = "no-store"
    return response


def allauth_429(request, exception=None):
    """handler429: allauth's own sign-in and reset limits."""
    return too_many(request, ALLAUTH_WAIT_MINUTES)


def ratelimited_view(request, exception=None):
    """RATELIMIT_VIEW: a django-ratelimit decorator with block=True (all of ours are per hour)."""
    return too_many(request, HOURLY_WAIT_MINUTES)
