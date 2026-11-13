"""/admin/ for someone who may not use it: a 403, never an endless redirect (found in Stage 10a)."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


def test_signed_out_goes_to_the_real_sign_in_and_keeps_next(client):
    response = client.get("/admin/", follow=False)
    assert response.status_code == 302 and response["Location"].startswith("/admin/login/")
    response = client.get("/admin/login/?next=/admin/")
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=/admin/"


@pytest.mark.parametrize("role", [Role.LEARNER, Role.MENTOR])
def test_signed_in_without_admin_access_gets_403_not_a_loop(client, make_user, role):
    user = make_user(role=role)
    if role == Role.MENTOR:  # a mentor has set up 2FA, so only the admin site itself is refused
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(user)
    response = client.get("/admin/", follow=True)
    assert response.status_code == 403
    assert len(response.redirect_chain) <= 1  # one hop to /admin/login/, then the 403
    assert AuditEvent.objects.filter(action="access.denied").exists()


def test_the_login_page_itself_is_not_a_loop_either(client, make_user):
    client.force_login(make_user())
    assert client.get("/admin/login/?next=/admin/").status_code == 403
