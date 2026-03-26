"""
Send end-of-day integration messages to subscribers at their chosen hour.
Run via cron every hour:
    0 * * * * cd /path/to/project && python manage.py send_integration_messages
"""
import logging
from datetime import datetime

from django.core.management.base import BaseCommand

from chatbot.intencionate import send_integration_message
from chatbot.models import Intencionate

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send integration messages to subscribers whose hora_integrar matches current hour"

    def handle(self, *args, **options):
        current_hour = str(datetime.now().hour)
        subs = Intencionate.objects.filter(activo=True, hora_integrar=current_hour)
        count = 0

        for sub in subs:
            try:
                send_integration_message(sub)
                count += 1
                self.stdout.write(f"Sent to {sub.telefono}")
            except Exception:
                logger.exception("Failed to send integration message to %s", sub.telefono)

        self.stdout.write(self.style.SUCCESS(f"Sent {count} integration messages (hour={current_hour})"))
