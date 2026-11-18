from django.core.management.base import BaseCommand
from core import services


class Command(BaseCommand):
    def handle(self, *a, **kw):
        u = services.ensure_superadmin()
        services.SiteConfig.get()
        self.stdout.write(f"Super admin tayyor: {u.phone}")
