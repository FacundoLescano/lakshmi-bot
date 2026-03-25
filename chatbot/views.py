import json
import logging
import os
import re
import threading

import dateparser
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .availability import (
    PRICES,
    assign_camilla,
    get_consecutive_pairs,
    get_free_camillas,
    is_available,
    suggest_alternatives,
)
from .conversation import clear_session, get_session, set_session
from .models import Reserva
from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)

MASSAGE_TYPES = [
    {"id": "masaje_relajante", "title": "Relajante"},
    {"id": "masaje_descontracturante", "title": "Descontracturante"},
    {"id": "masaje_piedras", "title": "Piedras calientes"},
]

MASAJE_ID_TO_DB = {
    "masaje_relajante": "relajante",
    "masaje_descontracturante": "descontracturante",
    "masaje_piedras": "piedras_calientes",
}

DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
    "TIMEZONE": "America/Argentina/Buenos_Aires",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "RELATIVE_BASE": None,  # set dynamically
}


def normalize_ar_number(number):
    """Convert Argentine 549xx numbers to 54xx for the API."""
    return re.sub(r'^549(\d{10})$', r'54\1', number)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        return verify_webhook(request)
    return handle_message(request)


def verify_webhook(request):
    mode = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")

    if mode == "subscribe" and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return HttpResponse(challenge, status=200)

    return HttpResponse("Forbidden", status=403)


def handle_message(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    logger.info("Webhook POST received: %s", json.dumps(body)[:500])

    entry = body.get("entry", [])
    if not entry:
        return HttpResponse("OK", status=200)

    changes = entry[0].get("changes", [])
    if not changes:
        return HttpResponse("OK", status=200)

    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    if not messages:
        return HttpResponse("OK", status=200)

    message = messages[0]
    from_number = normalize_ar_number(message["from"])
    msg_type = message.get("type")

    logger.info("Message from %s, type: %s", from_number, msg_type)

    threading.Thread(
        target=process_message,
        args=(from_number, msg_type, message),
        daemon=True,
    ).start()

    return HttpResponse("OK", status=200)


def process_message(from_number, msg_type, message):
    try:
        from django.db import close_old_connections
        close_old_connections()

        session = get_session(from_number)

        if msg_type == "interactive":
            interactive = message.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            button_id = button_reply.get("id", "")
            handle_button(from_number, button_id, session)

        elif msg_type == "text":
            text = message.get("text", {}).get("body", "").strip()
            handle_text(from_number, text, session)

    except Exception:
        logger.exception("Error processing message from %s", from_number)
    finally:
        from django.db import close_old_connections
        close_old_connections()


# ── Text handler ──────────────────────────────────────────────

def handle_text(from_number, text, session):
    if text.lower() in ("finalizar conversación", "finalizar conversacion", "finalizar"):
        clear_session(from_number)
        send_text_message(
            to=from_number,
            text="Conversación finalizada. ¡Gracias por contactarte con Lakshmi!",
        )
        return

    if not session:
        send_welcome(from_number)
        return

    step = session.get("step")

    if step == "awaiting_nombre":
        handle_nombre(from_number, text, session)
    elif step == "awaiting_horario":
        handle_horario(from_number, text, session)
    else:
        reprompt(from_number, session)


def handle_nombre(from_number, text, session):
    if not text:
        send_text_message(
            to=from_number,
            text="Por favor enviá tu nombre y apellido. Ejemplo: Juan Pérez",
        )
        return

    session["nombre"] = text
    session["step"] = "awaiting_horario"
    set_session(from_number, session)

    send_text_message(
        to=from_number,
        text=(
            "¿Para qué día y horario querés la cita?\n\n"
            "Podés escribir, por ejemplo:\n"
            "• hoy a las 15\n"
            "• mañana a las 10\n"
            "• viernes a las 18"
        ),
    )


def parse_horario(text):
    """Parse user input like 'martes a las 9', 'mañana 15hs', etc."""
    import re as _re
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Normalize: "a las 9" → "a las 9:00", "15hs" → "15:00"
    normalized = _re.sub(r'(\d{1,2})\s*hs?\b', r'\1:00', text)
    normalized = _re.sub(r'a las (\d{1,2})\b(?!:)', r'a las \1:00', normalized)

    now_ar = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    settings = {
        **DATEPARSER_SETTINGS,
        "RELATIVE_BASE": now_ar.replace(tzinfo=None),
    }

    parsed = dateparser.parse(normalized, languages=["es"], settings=settings)

    if parsed and parsed.hour == 0 and parsed.minute == 0:
        # dateparser ignored the time, try extracting it manually
        match = _re.search(r'(\d{1,2})(?::(\d{2}))?\s*(?:hs?)?', text)
        if match:
            hour = int(match.group(1))
            if 0 < hour <= 23:
                parsed = parsed.replace(hour=hour)

    # Strip timezone so Django stores the Argentina local time directly
    if parsed and parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)

    return parsed


def handle_horario(from_number, text, session):
    parsed = parse_horario(text)

    if not parsed:
        send_text_message(
            to=from_number,
            text="No pude entender la fecha. Probá con algo como: mañana a las 15, viernes a las 10",
        )
        return

    parsed = parsed.replace(minute=0, second=0, microsecond=0)
    logger.info("Parsed datetime: %s (hour=%s, tzinfo=%s)", parsed, parsed.hour, parsed.tzinfo)

    es_pareja = session.get("pareja", False)

    if es_pareja:
        has_availability = is_available(parsed) and len(get_consecutive_pairs(parsed)) > 0
    else:
        has_availability = is_available(parsed) and len(get_free_camillas(parsed)) >= 1

    if has_availability:
        session["horario"] = parsed.isoformat()
        session["step"] = "awaiting_confirm"
        set_session(from_number, session)
        ask_confirmation(from_number, session, parsed)
    else:
        alternatives = suggest_alternatives(parsed, pareja=es_pareja)
        if alternatives:
            session["alternatives"] = [a.isoformat() for a in alternatives]
            session["step"] = "awaiting_alt"
            set_session(from_number, session)

            buttons = []
            for i, alt in enumerate(alternatives):
                label = alt.strftime("%A %H:%Mhs").capitalize()
                buttons.append({"id": f"alt_{i}", "title": label[:20]})
            buttons.append({"id": "alt_otro", "title": "Otro horario"})

            send_interactive_buttons(
                to=from_number,
                body_text=(
                    f"El horario {parsed.strftime('%A %H:%Mhs')} no está disponible. "
                    "¿Te sirve alguno de estos?"
                ),
                buttons=buttons,
            )
        else:
            send_text_message(
                to=from_number,
                text="No hay horarios disponibles cercanos a esa hora. Probá con otro día u horario.",
            )


# ── Button handler ────────────────────────────────────────────

def handle_button(from_number, button_id, session):
    logger.info("Button pressed: %s, session: %s", button_id, session)

    # Main menu
    if button_id == "btn_reserva":
        set_session(from_number, {"step": "awaiting_pareja"})
        send_interactive_buttons(
            to=from_number,
            body_text="¿La reserva es para pareja?",
            buttons=[
                {"id": "pareja_si", "title": "Sí, para pareja"},
                {"id": "pareja_no", "title": "No, individual"},
            ],
        )
        return

    if button_id == "btn_info":
        send_text_message(to=from_number, text="Más información")
        return

    if not session:
        logger.warning("Session lost for %s, restarting flow", from_number)
        send_text_message(
            to=from_number,
            text="Se perdió la sesión. Empecemos de nuevo.",
        )
        send_welcome(from_number)
        return

    step = session.get("step")

    # Pareja
    if step == "awaiting_pareja" and button_id in ("pareja_si", "pareja_no"):
        session["pareja"] = button_id == "pareja_si"
        session["step"] = "awaiting_masaje"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text="¿Qué tipo de masaje te gustaría?",
            buttons=MASSAGE_TYPES,
        )
        return

    # Masaje
    if step == "awaiting_masaje" and button_id.startswith("masaje_"):
        session["masaje_id"] = button_id
        session["masaje_name"] = next(
            (m["title"] for m in MASSAGE_TYPES if m["id"] == button_id),
            button_id,
        )
        session["step"] = "awaiting_nombre"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text="Por favor enviá tu nombre y apellido. Ejemplo: Juan Pérez",
        )
        return

    # Alternativas de horario
    if step == "awaiting_alt":
        if button_id == "alt_otro":
            session["step"] = "awaiting_horario"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Decime otro día y horario que te quede bien.",
            )
            return

        alt_index = int(button_id.replace("alt_", ""))
        alternatives = session.get("alternatives", [])
        if alt_index < len(alternatives):
            chosen = alternatives[alt_index]
            session["horario"] = chosen
            session["step"] = "awaiting_confirm"
            set_session(from_number, session)

            from datetime import datetime
            parsed = datetime.fromisoformat(chosen)
            ask_confirmation(from_number, session, parsed)
        return

    # Confirmar reserva
    if step == "awaiting_confirm":
        if button_id == "confirm_si":
            save_reserva(from_number, session)
            return
        if button_id == "confirm_no":
            session["step"] = "awaiting_horario"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Decime otro día y horario que te quede bien.",
            )
            return


# ── Helpers ───────────────────────────────────────────────────

def send_welcome(from_number):
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "Hola, gracias por contactarte con Lakshmi, "
            "hacemos todo tipo de masajes"
        ),
        buttons=[
            {"id": "btn_reserva", "title": "Reserva"},
            {"id": "btn_info", "title": "Más información"},
        ],
    )


def ask_confirmation(from_number, session, dt):
    masaje_db_key = MASAJE_ID_TO_DB.get(session["masaje_id"], "relajante")
    precio = PRICES.get(masaje_db_key, 0)
    adelanto = precio // 2
    pareja_text = "para pareja" if session.get("pareja") else "individual"

    send_interactive_buttons(
        to=from_number,
        body_text=(
            f"Resumen de tu reserva:\n\n"
            f"👤 {session['nombre']}\n"
            f"💆 {session['masaje_name']} ({pareja_text})\n"
            f"📅 {dt.strftime('%A %d/%m a las %H:%Mhs')}\n"
            f"💰 Precio: ${precio:,}\n"
            f"💳 Adelanto (50%): ${adelanto:,}\n\n"
            f"¿Confirmás la reserva?"
        ),
        buttons=[
            {"id": "confirm_si", "title": "Sí, confirmar"},
            {"id": "confirm_no", "title": "Cambiar horario"},
        ],
    )


def save_reserva(from_number, session):
    from datetime import datetime

    masaje_db_key = MASAJE_ID_TO_DB.get(session["masaje_id"], "relajante")
    horario = datetime.fromisoformat(session["horario"])
    es_pareja = session.get("pareja", False)
    precio = PRICES.get(masaje_db_key, 0)
    adelanto = precio // 2

    try:
        camillas = assign_camilla(horario, count=1, pareja=es_pareja)
    except ValueError:
        logger.warning("No camillas available at %s for %s", horario, from_number)
        send_text_message(
            to=from_number,
            text=(
                "Lo sentimos, ya no quedan camillas disponibles para ese horario. "
                "Por favor elegí otro horario."
            ),
        )
        session["step"] = "awaiting_horario"
        set_session(from_number, session)
        return

    for sucursal, camilla in camillas:
        Reserva.objects.create(
            nombre=session["nombre"],
            es_pareja=es_pareja,
            tipo_masaje=masaje_db_key,
            horario=horario,
            sucursal=sucursal,
            camilla=camilla,
        )

    send_text_message(
        to=from_number,
        text=(
            f"✅ ¡Reserva confirmada!\n\n"
            f"Para completar tu reserva, realizá una transferencia de ${adelanto:,} "
            f"al siguiente CBU:\n\n"
            f"🏦 CBU: 0000000000000000000000\n"
            f"👤 Titular: Lakshmi Masajes\n\n"
            f"Envianos el comprobante por este mismo chat. ¡Te esperamos!"
        ),
    )
    clear_session(from_number)


def reprompt(from_number, session):
    step = session.get("step")
    if step == "awaiting_pareja":
        send_interactive_buttons(
            to=from_number,
            body_text="Por favor elegí una opción:",
            buttons=[
                {"id": "pareja_si", "title": "Sí, para pareja"},
                {"id": "pareja_no", "title": "No, individual"},
            ],
        )
    elif step == "awaiting_masaje":
        send_interactive_buttons(
            to=from_number,
            body_text="Por favor elegí el tipo de masaje:",
            buttons=MASSAGE_TYPES,
        )
    elif step == "awaiting_nombre":
        send_text_message(
            to=from_number,
            text="Por favor enviá tu nombre y apellido. Ejemplo: Juan Pérez",
        )
    elif step == "awaiting_horario":
        send_text_message(
            to=from_number,
            text="Decime un día y horario. Ejemplo: mañana a las 15",
        )
    else:
        send_welcome(from_number)
