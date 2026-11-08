from django.conf import settings

from apps.accounts import email_budget


def dashboard_callback(request, context):
    """Adds the 'emails sent today' counter to the admin dashboard (architecture 7.2)."""
    context["email_today"] = email_budget.sent_today()
    context["email_budget"] = settings.EMAIL_DAILY_BUDGET
    context["email_alert_at"] = settings.EMAIL_ALERT_AT
    return context
