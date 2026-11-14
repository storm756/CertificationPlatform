import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.utils.translation import gettext_lazy as _

from . import email_budget

RESET_LIMITED_KEY = "reset_limited_today"

log = logging.getLogger(__name__)

# allauth template prefix -> budget kind
_KIND_BY_TEMPLATE = {
    "account/email/email_confirmation": email_budget.REGISTRATION,
    "account/email/email_confirmation_signup": email_budget.REGISTRATION,
    "account/email/account_already_exists": email_budget.DUPLICATE,
    "account/email/password_reset_key": email_budget.RESET,
    # allauth's security notices (ACCOUNT_EMAIL_NOTIFICATIONS, M3)
    "account/email/email_changed": email_budget.NOTICE,
    "account/email/email_deleted": email_budget.NOTICE,
    "account/email/email_confirm": email_budget.NOTICE,
    "account/email/password_changed": email_budget.NOTICE,
    "account/email/password_set": email_budget.NOTICE,
    "account/email/password_reset": email_budget.NOTICE,
}
UNKNOWN_ACCOUNT = "account/email/unknown_account"


class BudgetedAccountAdapter(DefaultAccountAdapter):
    """Public sign-up is closed (D9): accounts are only made by /register, after is_accepting().
    Every allauth email passes the daily budgets and the one-per-address-per-day limit."""

    # Say when they can try again (Stage 10). Five wrong passwords for one email in 5 minutes, or
    # 30 from one network in a minute, stop sign-in for that long.
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "too_many_login_attempts": _(
            "Too many wrong passwords. Please wait 5 minutes and try again, or reset your password."
        ),
    }

    def is_open_for_signup(self, request):
        return False

    def _unknown_account_reset(self, email):
        """A reset for an address with no account: send nothing, use no budget (security audit
        2026-11, M1), but answer exactly as for a real address, including "already sent today"
        on a second request (pilot fixes)."""
        if email_budget.sent_recently(email_budget.RESET, email):
            self._remember_reset_limited()
            return
        email_budget.record(email_budget.RESET_UNKNOWN, email)
        if hasattr(getattr(self, "request", None), "session"):
            self.request.session.pop(RESET_LIMITED_KEY, None)

    def _remember_reset_limited(self):
        if getattr(self, "request", None) is not None and hasattr(self.request, "session"):
            self.request.session[RESET_LIMITED_KEY] = True

    def send_mail(self, template_prefix, email, context):
        if template_prefix == UNKNOWN_ACCOUNT:
            self._unknown_account_reset(email)
            return
        kind = _KIND_BY_TEMPLATE.get(template_prefix, email_budget.RESET)
        if not email_budget.can_send(kind, email):
            log.warning("Email not sent (budget or per-address limit): %s", kind)
            if kind == email_budget.RESET and email_budget.sent_recently(kind, email):
                # The same for a known and an unknown address: both get one email a day (the
                # unknown-account email counts as a reset), so this never reveals an account.
                self._remember_reset_limited()
            return
        super().send_mail(template_prefix, email, context)
        email_budget.record(kind, email)
        if kind == email_budget.RESET and hasattr(getattr(self, "request", None), "session"):
            self.request.session.pop(RESET_LIMITED_KEY, None)
