import asyncio
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Telegram botni ishga tushirish"

    def handle(self, *a, **kw):
        from bot.main import main
        asyncio.run(main())
