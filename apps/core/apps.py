from django.apps import AppConfig, apps
from django.db.models.signals import post_migrate


def sync_site(sender, **kwargs):
    """Make the Django Site (used in email subjects and links) match this environment."""
    from django.conf import settings
    from django.contrib.sites.models import Site

    Site.objects.update_or_create(
        pk=settings.SITE_ID,
        defaults={"domain": settings.SITE_DOMAIN, "name": settings.SITE_NAME},
    )


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self):
        # post_migrate only fires for apps with models, so hook the sites app itself.
        post_migrate.connect(sync_site, sender=apps.get_app_config("sites"))
