"""
Send daily morning motivational messages to all active subscribers.
Run via cron at 8:00 AM Argentina time:
    0 8 * * * cd /path/to/project && python manage.py send_daily_messages
"""
import logging

from django.core.management.base import BaseCommand

from chatbot.intencionate import send_daily_morning_message
from chatbot.models import Intencionate

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send daily motivational messages to active Intencionate subscribers"

    def handle(self, *args, **options):
        subs = Intencionate.objects.filter(activo=True)
        count = 0

        for sub in subs:
            try:
                send_daily_morning_message(sub)
                count += 1
                self.stdout.write(f"Sent to {sub.telefono}")
            except Exception:
                logger.exception("Failed to send daily message to %s", sub.telefono)

        self.stdout.write(self.style.SUCCESS(f"Sent {count} daily messages"))
