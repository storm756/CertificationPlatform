import logging

from allauth.account.adapter import DefaultAccountAdapter

from . import email_budget

log = logging.getLogger(__name__)

# allauth template prefix -> budget kind
_KIND_BY_TEMPLATE = {
    "account/email/email_confirmation": email_budget.REGISTRATION,
    "account/email/email_confirmation_signup": email_budget.REGISTRATION,
    "account/email/account_already_exists": email_budget.DUPLICATE,
    "account/email/password_reset_key": email_budget.RESET,
    "account/email/unknown_account": email_budget.RESET,
}


class BudgetedAccountAdapter(DefaultAccountAdapter):
    """Public sign-up is closed (D9): accounts are only made by /register, after is_accepting().
    Every allauth email passes the daily budgets and the one-per-address-per-day limit."""

    def is_open_for_signup(self, request):
        return False

    def send_mail(self, template_prefix, email, context):
        kind = _KIND_BY_TEMPLATE.get(template_prefix, email_budget.RESET)
        if not email_budget.can_send(kind, email):
            log.warning("Email not sent (budget or per-address limit): %s", kind)
            return
        super().send_mail(template_prefix, email, context)
        email_budget.record(kind, email)
