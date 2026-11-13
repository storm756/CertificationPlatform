"""The learner's certificate page and download, and the public verify page (architecture §12).

The verify page is public (D34) and rate-limited per client IP. It looks a certificate up by its
random verify code only: a certificate number never matches, so nobody can walk the numbers and
collect names.
"""

import hashlib
import io
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from apps.accounts.models import Role
from apps.accounts.rules import certificate_name_ok
from apps.audit.services import client_ip
from apps.core.ratelimits import too_many, window_minutes
from apps.results.policy import compute_results

from . import services
from .codes import normalise_code
from .forms import VerifyCodeForm
from .models import Certificate, CertificateStatus

logger = logging.getLogger(__name__)


def learner_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != Role.LEARNER:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


@learner_required
def my_certificate(request):
    user = request.user
    result = compute_results([user.pk])[user.pk]
    cert = services.current_certificate(user)
    state = services.certificate_state(cert, result)
    return render(
        request,
        "certificates/mine.html",
        {
            "cert": cert,
            "result": result,
            "state": state,
            "name_ok": certificate_name_ok(user.profile.certificate_name),
        },
    )


@learner_required
def download(request):
    """The owner's own PDF, never anyone else's: it is looked up from the signed-in user only."""
    cert = Certificate.objects.filter(user=request.user, status=CertificateStatus.ISSUED).first()
    path = services.pdf_file(cert) if cert and not cert.holder_erased else None
    if path is None:
        raise Http404
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != cert.pdf_sha256:
        logger.error("certificate %s: the stored PDF does not match its sha256", cert.pk)
        raise Http404
    response = FileResponse(
        io.BytesIO(data),
        as_attachment=True,
        filename=f"{cert.certificate_no}.pdf",
        content_type="application/pdf",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _verify_key(group, request):
    return client_ip(request) or "unknown"


def _verify_rate(group, request):
    return settings.CERTIFICATE_VERIFY_RATE  # read per request, so it can change without a restart


def _public(response):
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "no-store"
    return response


def verify_state(cert) -> str:
    if cert is None:
        return "none"
    if cert.status == CertificateStatus.REVOKED:
        return "revoked"
    return "erased" if cert.holder_erased else "valid"


@ratelimit(key=_verify_key, rate=_verify_rate, method=ratelimit.ALL, block=False)
def verify(request, code=None):
    if getattr(request, "limited", False):
        minutes = window_minutes(_verify_rate(None, request))
        return _public(too_many(request, minutes, "certificates/verify_limited.html"))
    if code is None:  # the page without a code: a box to type the code printed on paper
        form = VerifyCodeForm(request.GET if "code" in request.GET else None)
        if form.is_valid():
            return redirect("verify_code", code=form.cleaned_data["code"])
        return _public(render(request, "certificates/verify.html", {"state": "form", "form": form}))
    normalised = normalise_code(code)
    if normalised and normalised != code:
        return redirect("verify_code", code=normalised)
    cert = Certificate.objects.filter(verify_code=normalised).first() if normalised else None
    state = verify_state(cert)
    return _public(
        render(
            request,
            "certificates/verify.html",
            {"state": state, "cert": cert, "form": VerifyCodeForm()},
            status=404 if cert is None else 200,
        )
    )
