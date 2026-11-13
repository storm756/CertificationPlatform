"""Per-client rate limits must not share one bucket behind Caddy (REMOTE_ADDR is Caddy's own address)."""

import pytest
from django.urls import reverse

LIMIT = 120  # the rate on /learn/check and the block endpoint, per hour


def _exhaust(client, url):
    for _ in range(LIMIT):
        assert client.post(url).status_code != 429
    return client.post(url)


@pytest.mark.parametrize(
    "url",
    [reverse("learn_check"), reverse("learn_block", args=[1, "no-such-unit", 0])],
    ids=["check", "block_action"],
)
def test_learn_limits_are_per_user_not_shared(url, client, make_user, make_batch):
    batch = make_batch()
    first, second = make_user(batch=batch), make_user(batch=batch)
    client.force_login(first)
    assert _exhaust(client, url).status_code == 429  # the first learner hit the limit

    other_browser = client.__class__()
    other_browser.force_login(second)
    assert (
        other_browser.post(url).status_code != 429
    )  # a second learner, same address, is not blocked


def test_the_mentor_reset_limit_is_per_client_ip_not_shared(client, db):
    url = reverse("mentor_reset", args=["not-a-real-token"])
    for _ in range(30):
        assert client.post(url, HTTP_X_FORWARDED_FOR="198.51.100.7").status_code == 404
    assert client.post(url, HTTP_X_FORWARDED_FOR="198.51.100.7").status_code == 429
    # another phone behind the same proxy (same REMOTE_ADDR) still gets through
    assert client.post(url, HTTP_X_FORWARDED_FOR="203.0.113.77").status_code == 404
