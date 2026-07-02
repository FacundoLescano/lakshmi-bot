"""
Send AI-generated post-session message to users who sent "Llegué" 2.5 hours ago.
Run via cron every 5 minutes:
    */5 * * * * cd /path/to/project && python manage.py send_llegada_messages
"""
import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from chatbot.llm_chat import generate_post_session_message
from chatbot.models import LlegadaRegistrada, Memoria
from chatbot.whatsapp import send_text_message

logger = logging.getLogger(__name__)

# Prefijos internos que no son respuestas emocionales del cliente
_PREFIJOS_INTERNOS = ("[lugar]", "[fecha_nac]", "[aceites]")


def _get_recent_memories(telefono: str, limit: int = 20) -> list[str]:
    """Return the last `limit` emotional memories for this user, excluding internal prefixes."""
    memorias = (
        Memoria.objects
        .filter(id_user=telefono)
        .exclude(context__startswith="[lugar]")
        .exclude(context__startswith="[fecha_nac]")
        .exclude(context__startswith="[aceites]")
        .order_by("-created_at")[:limit]
    )
    # Return in chronological order so the LLM reads them naturally
    return [m.context for m in reversed(list(memorias))]


class Command(BaseCommand):
    help = "Send AI post-session message to users who arrived 2.5 hours ago"

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
                memories = _get_recent_memories(llegada.telefono)
                message = generate_post_session_message(memories)

                send_text_message(to=llegada.telefono, text=message)

                llegada.mensaje_enviado = True
                llegada.save(update_fields=["mensaje_enviado"])
                count += 1
                self.stdout.write(f"Sent post-session message to {llegada.telefono}")
            except Exception:
                logger.exception("Failed to send post-session message to %s", llegada.telefono)

        self.stdout.write(self.style.SUCCESS(f"Sent {count} post-session messages"))
