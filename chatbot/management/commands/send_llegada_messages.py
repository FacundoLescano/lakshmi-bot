"""
Send Intencionate promo message to users who sent "Llegué" 2.5 hours ago.
Run via cron every 5 minutes:
    */5 * * * * cd /path/to/project && python manage.py send_llegada_messages
"""
import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from chatbot.models import LlegadaRegistrada
from chatbot.whatsapp import send_interactive_buttons

logger = logging.getLogger(__name__)

PROMO_TEXT = (
    "¿Cómo te sentiste después de la sesión? 🌿\n\n"
    "En Lakshmi también tenemos *Intencionate*, un servicio de acompañamiento emocional diario "
    "donde recibís mensajes personalizados basados en tu energía y tu historia.\n\n"
    "Es una forma de continuar el trabajo que empezaste hoy, desde casa y a tu ritmo."
)


class Command(BaseCommand):
    help = "Send Intencionate promo to users who arrived 2.5 hours ago"

    def handle(self, *args, **options):
        now = datetime.now()
        window_start = now - timedelta(hours=2, minutes=35)
        window_end = now - timedelta(hours=2, minutes=25)

        pending = LlegadaRegistrada.objects.filter(
            mensaje_enviado=False,
            llegada_at__gte=window_start,
            llegada_at__lte=window_end,
        )
        count = 0

        for llegada in pending:
            try:
                send_interactive_buttons(
                    to=llegada.telefono,
                    body_text=PROMO_TEXT,
                    buttons=[
                        {"id": "route_intencionate", "title": "Quiero saber más"},
                        {"id": "intencionate_no_gracias", "title": "No, gracias"},
                    ],
                )
                llegada.mensaje_enviado = True
                llegada.save(update_fields=["mensaje_enviado"])
                count += 1
                self.stdout.write(f"Sent to {llegada.telefono}")
            except Exception:
                logger.exception("Failed to send llegada promo to %s", llegada.telefono)

        self.stdout.write(self.style.SUCCESS(f"Sent {count} llegada promo messages"))
