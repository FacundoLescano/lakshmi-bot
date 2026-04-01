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
    assign_camilla,
    get_consecutive_pairs,
    get_free_camillas,
    get_prices,
    is_available,
    suggest_alternatives,
)
from .conversation import clear_session, get_session, set_session
from .models import Intencionate, Memoria, Precio, Reserva, generate_voucher_code
from . import intencionate as intencionate_bot
from .llm_router import route_message
from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)

ADMIN_CODE = "Usuario admin intencionate 27326"

DURACION_BUTTONS = [
    {"id": "dur_60", "title": "60 minutos"},
    {"id": "dur_90", "title": "90 minutos"},
    {"id": "dur_120", "title": "120 minutos"},
]

DURACION_MAP = {
    "dur_60": 60,
    "dur_90": 90,
    "dur_120": 120,
}

DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
    "TIMEZONE": "America/Argentina/Buenos_Aires",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "RELATIVE_BASE": None,
}

# Cuestionario de intención para masaje (mismo que intencionate, sin nombre ni hora_integrar)
MASAJE_QUESTIONS = [
    "¿Cuál es tu lugar de nacimiento?",
    "¿Cuál es tu fecha de nacimiento? (ej: 15/03/1990)",
    "¿Qué estás atravesando hoy?",
    "¿Qué es lo que más te mueve o te preocupa de esto?",
    "¿Cómo te estás sintiendo frente a esto?",
    "¿Dónde lo sentís en el cuerpo?",
    "¿Cómo está tu energía hoy?",
    "Si esto se ordenara, ¿qué te gustaría que pase?",
]

MASAJE_QUESTION_KEYS = [
    "q_lugar",
    "q_fecha_nac",
    "q_atravesando",
    "q_preocupa",
    "q_sintiendo",
    "q_cuerpo",
    "q_energia",
    "q_deseo",
]


def normalize_ar_number(number):
    return re.sub(r'^549(\d{10})$', r'54\1', number)


# ── Webhook entry point ──────────────────────────────────────

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

        # Si ya tiene sesión activa, derivar al bot correcto
        if session:
            bot = session.get("bot")
            if bot == "intencionate":
                intencionate_bot.process(from_number, msg_type, message, session)
                return
            # Bot lakshmi (default)
            _dispatch_lakshmi(from_number, msg_type, message, session)
            return

        # Sin sesión: manejar botones de routing primero
        if msg_type == "interactive":
            interactive = message.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            button_id = button_reply.get("id", "")

            if button_id == "route_lakshmi":
                send_welcome(from_number)
                return
            if button_id == "route_intencionate":
                intencionate_bot.process(from_number, "text", {"text": {"body": "intencionate"}}, None)
                return

            # Botón de intencionate sin sesión (ej: suscribirse)
            if button_id.startswith("int_") or button_id.startswith("sat_"):
                intencionate_bot.handle_button(from_number, button_id, None)
                return

            # Cualquier otro botón sin sesión → bienvenida
            send_text_message(to=from_number, text="Se perdió la sesión. Empecemos de nuevo.")
            send_interactive_buttons(
                to=from_number,
                body_text="¿En qué te podemos ayudar?",
                buttons=[
                    {"id": "route_lakshmi", "title": "Masajes Lakshmi"},
                    {"id": "route_intencionate", "title": "Intencionate"},
                ],
            )
            return

        # Sin sesión: si es texto, usar LLM router para decidir
        if msg_type == "text":
            text = message.get("text", {}).get("body", "").strip()

            if text.lower() in ("finalizar conversación", "finalizar conversacion", "finalizar"):
                clear_session(from_number)
                send_text_message(to=from_number, text="¡Gracias por contactarnos!")
                return

            # Admin access
            if text == ADMIN_CODE:
                start_admin(from_number)
                return

            route = route_message(text)
            logger.info("Router decision for %s: '%s' -> %s", from_number, text[:50], route)

            if route == "lakshmi":
                send_welcome(from_number)
            elif route == "intencionate":
                intencionate_bot.process(from_number, msg_type, message, None)
            else:
                # Saludo genérico — no se pudo determinar intención
                send_interactive_buttons(
                    to=from_number,
                    body_text="¡Hola! ¿En qué te podemos ayudar?",
                    buttons=[
                        {"id": "route_lakshmi", "title": "Masajes Lakshmi"},
                        {"id": "route_intencionate", "title": "Intencionate"},
                    ],
                )
            return

        # Sin sesión y no es texto ni botón (ej: imagen suelta)
        send_text_message(to=from_number, text="¡Hola! Envianos un mensaje para comenzar.")

    except Exception:
        logger.exception("Error processing message from %s", from_number)
    finally:
        from django.db import close_old_connections
        close_old_connections()


def _dispatch_lakshmi(from_number, msg_type, message, session):
    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        button_id = button_reply.get("id", "")
        handle_button(from_number, button_id, session)
    elif msg_type == "text":
        text = message.get("text", {}).get("body", "").strip()
        handle_text(from_number, text, session)
    elif msg_type in ("image", "document"):
        handle_file(from_number, session)


# ── Text handler ─────────────────────────────────────────────

def handle_text(from_number, text, session):
    if text.lower() in ("finalizar conversación", "finalizar conversacion", "finalizar"):
        clear_session(from_number)
        send_text_message(
            to=from_number,
            text="Conversación finalizada. ¡Gracias por contactarte con Lakshmi!",
        )
        return

    if text == ADMIN_CODE:
        start_admin(from_number)
        return

    if not session:
        send_welcome(from_number)
        return

    step = session.get("step")

    # Admin steps
    if step == "admin_awaiting_telefono":
        admin_search_reservas(from_number, text, session)
        return
    if step == "admin_awaiting_nuevo_precio":
        admin_set_precio(from_number, text, session)
        return

    if step == "awaiting_nombre":
        handle_nombre(from_number, text, session)
    elif step == "awaiting_horario":
        handle_horario(from_number, text, session)
    elif step == "awaiting_nuevo_horario":
        handle_nuevo_horario(from_number, text, session)
    elif step == "awaiting_voucher_code":
        handle_voucher_code(from_number, text, session)
    elif step and step.startswith("awaiting_mq"):
        handle_masaje_question(from_number, text, session)
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

    if session.get("es_regalo"):
        # Gift flow: after name, show payment info
        session["step"] = "awaiting_comprobante"
        set_session(from_number, session)
        send_payment_info(from_number, session)
    elif session.get("horario"):
        # Normal flow: horario already set, go to confirmation
        from datetime import datetime
        parsed = datetime.fromisoformat(session["horario"])
        session["step"] = "awaiting_confirm"
        set_session(from_number, session)
        ask_confirmation(from_number, session, parsed)
    else:
        # Shouldn't happen, but fallback to ask horario
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


# ── File handler (comprobante) ───────────────────────────────

def handle_file(from_number, session):
    if not session:
        send_welcome(from_number)
        return

    step = session.get("step")

    if step == "awaiting_comprobante":
        handle_comprobante_received(from_number, session)
    else:
        reprompt(from_number, session)


def handle_comprobante_received(from_number, session):
    es_pareja = session.get("pareja", False)
    duracion = session.get("duracion", 60)
    voucher_code = generate_voucher_code()

    count = 2 if es_pareja else 1
    for _ in range(count):
        Reserva.objects.create(
            nombre=session["nombre"],
            es_pareja=es_pareja,
            duracion=duracion,
            horario=None,
            sucursal="",
            camilla=None,
            voucher=generate_voucher_code() if _ > 0 else voucher_code,
            es_regalo=True,
            telefono=from_number,
        )

    send_text_message(
        to=from_number,
        text=(
            f"🎁 *Voucher de regalo*\n\n"
            f"¡Comprobante recibido! Tu voucher está listo.\n\n"
            f"🎫 Código: *{voucher_code}*\n"
            f"💆 Duración: {duracion} minutos\n"
            f"👥 {'Pareja' if es_pareja else 'Individual'}\n\n"
            f"La persona que reciba el regalo puede canjearlo "
            f"escribiéndonos y seleccionando 'Tengo un voucher'.\n\n"
            f"¡Gracias por elegir Lakshmi!"
        ),
    )
    clear_session(from_number)


# ── Horario parsing & handling ───────────────────────────────

def parse_horario(text):
    import re as _re
    from datetime import datetime
    from zoneinfo import ZoneInfo

    normalized = _re.sub(r'(\d{1,2})\s*hs?\b', r'\1:00', text)
    normalized = _re.sub(r'a las (\d{1,2})\b(?!:)', r'a las \1:00', normalized)

    now_ar = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    settings = {
        **DATEPARSER_SETTINGS,
        "RELATIVE_BASE": now_ar.replace(tzinfo=None),
    }

    parsed = dateparser.parse(normalized, languages=["es"], settings=settings)

    if parsed and parsed.hour == 0 and parsed.minute == 0:
        match = _re.search(r'(\d{1,2})(?::(\d{2}))?\s*(?:hs?)?', text)
        if match:
            hour = int(match.group(1))
            if 0 < hour <= 23:
                parsed = parsed.replace(hour=hour)

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
        # Voucher flow goes straight to confirm (name already provided)
        if session.get("flow") == "voucher":
            session["step"] = "awaiting_confirm"
            set_session(from_number, session)
            ask_confirmation(from_number, session, parsed)
        else:
            # Normal reservation: ask name next
            session["step"] = "awaiting_nombre"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Por favor enviá tu nombre y apellido. Ejemplo: Juan Pérez",
            )
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


# ── Voucher redemption ───────────────────────────────────────

def handle_voucher_code(from_number, text, session):
    code = text.strip().upper()
    try:
        reserva = Reserva.objects.get(voucher=code, horario__isnull=True)
    except Reserva.DoesNotExist:
        send_text_message(
            to=from_number,
            text="No encontramos ese código de voucher o ya fue utilizado. Verificá e intentá de nuevo.",
        )
        return

    session["flow"] = "voucher"
    session["voucher_code"] = code
    session["reserva_id"] = reserva.id
    session["pareja"] = reserva.es_pareja
    session["duracion"] = reserva.duracion
    session["nombre"] = reserva.nombre
    session["step"] = "awaiting_horario"
    set_session(from_number, session)

    send_text_message(
        to=from_number,
        text=(
            f"✅ Voucher válido: {reserva.duracion} minutos, "
            f"{'pareja' if reserva.es_pareja else 'individual'}.\n\n"
            f"¿Para qué día y horario querés la cita?\n\n"
            f"Podés escribir, por ejemplo:\n"
            f"• hoy a las 15\n"
            f"• mañana a las 10\n"
            f"• viernes a las 18"
        ),
    )


# ── Cuestionario de intención para masaje ────────────────────

def start_masaje_questionnaire(from_number, session):
    """Inicia el cuestionario. Salta lugar/fecha si el usuario ya los completó antes."""
    # Chequear si ya tenemos datos de lugar/fecha (de un cuestionario previo o suscripción)
    has_prior_data = Memoria.objects.filter(
        id_user=from_number, context__startswith="[lugar]"
    ).exists() or Intencionate.objects.filter(
        telefono=from_number, lugar_nacimiento__gt=""
    ).exists()

    if has_prior_data:
        # Saltear lugar (idx 0) y fecha (idx 1), empezar en pregunta 2
        session["mq_index"] = 2
        session["step"] = "awaiting_mq2"
    else:
        session["mq_index"] = 0
        session["step"] = "awaiting_mq0"

    set_session(from_number, session)
    idx = session["mq_index"]
    send_text_message(to=from_number, text=MASAJE_QUESTIONS[idx])


def handle_masaje_question(from_number, text, session):
    """Procesa cada respuesta del cuestionario de intención del masaje."""
    idx = session.get("mq_index", 0)
    key = MASAJE_QUESTION_KEYS[idx]

    # Guardar respuesta en sesión
    session[key] = text

    # Guardar en Memoria vinculado a la reserva
    reserva_ids = session.get("reserva_ids", [])
    reserva = Reserva.objects.filter(id=reserva_ids[0]).first() if reserva_ids else None

    # Prefijo para lugar/fecha para poder identificarlos después
    if key == "q_lugar":
        context = f"[lugar] {text[:190]}"
    elif key == "q_fecha_nac":
        context = f"[fecha_nac] {text[:185]}"
    else:
        context = text[:200]

    Memoria.objects.create(
        id_user=from_number,
        context=context,
        reserva=reserva,
    )

    # Siguiente pregunta
    next_idx = idx + 1
    if next_idx < len(MASAJE_QUESTIONS):
        session["mq_index"] = next_idx
        session["step"] = f"awaiting_mq{next_idx}"
        set_session(from_number, session)
        send_text_message(to=from_number, text=MASAJE_QUESTIONS[next_idx])
    else:
        # Cuestionario terminado
        send_text_message(
            to=from_number,
            text=(
                "🧘 ¡Gracias por compartir! Vamos a personalizar tu experiencia "
                "con aceites especiales para vos.\n\n"
                "¡Te esperamos en Lakshmi!"
            ),
        )
        clear_session(from_number)


# ── Button handler ───────────────────────────────────────────

def handle_button(from_number, button_id, session):
    logger.info("Button pressed: %s, session: %s", button_id, session)

    # ── Admin buttons ──
    if button_id == "admin_cancelar":
        session = {"bot": "lakshmi", "step": "admin_awaiting_telefono", "admin": True, "admin_action": "cancelar"}
        set_session(from_number, session)
        send_text_message(to=from_number, text="Enviá el teléfono del cliente (sin +, ej: 541166506924)")
        return

    if button_id == "admin_precios":
        admin_show_precios(from_number)
        return

    if button_id.startswith("admin_cancel_"):
        admin_confirm_cancel(from_number, button_id, session)
        return

    if button_id == "admin_cancel_confirm":
        admin_execute_cancel(from_number, session)
        return

    if button_id == "admin_cancel_abort":
        send_text_message(to=from_number, text="Cancelación abortada.")
        start_admin(from_number)
        return

    if button_id.startswith("admin_precio_"):
        admin_select_duracion(from_number, button_id, session)
        return

    if button_id == "admin_volver":
        start_admin(from_number)
        return

    # ── Router buttons (sin sesión previa) ──
    if button_id == "route_lakshmi":
        send_welcome(from_number)
        return

    if button_id == "route_intencionate":
        intencionate_bot.process(from_number, "text", {"text": {"body": "intencionate"}}, None)
        return

    # ── Intencionate buttons (derivar al otro bot) ──
    if button_id.startswith("int_") or button_id.startswith("sat_"):
        intencionate_bot.handle_button(from_number, button_id, session)
        return

    # ── Main menu buttons (no session needed) ──
    if button_id == "btn_reserva":
        set_session(from_number, {"bot": "lakshmi", "step": "awaiting_pareja", "flow": "reserva"})
        send_interactive_buttons(
            to=from_number,
            body_text="¿La reserva es para pareja?",
            buttons=[
                {"id": "pareja_si", "title": "Sí, para pareja"},
                {"id": "pareja_no", "title": "No, individual"},
            ],
        )
        return

    if button_id == "btn_cambiar":
        start_cambiar_horario(from_number)
        return

    if button_id == "btn_voucher":
        set_session(from_number, {"bot": "lakshmi", "step": "awaiting_voucher_code", "flow": "voucher"})
        send_text_message(
            to=from_number,
            text="Por favor enviá el código de tu voucher.",
        )
        return

    if button_id == "btn_intencionate":
        send_text_message(
            to=from_number,
            text="Para adquirir INTENCIONATE, contactanos directamente.",
        )
        return

    # ── Session-dependent buttons ──
    if not session:
        logger.warning("Session lost for %s, restarting flow", from_number)
        send_text_message(to=from_number, text="Se perdió la sesión. Empecemos de nuevo.")
        send_welcome(from_number)
        return

    step = session.get("step")

    # Pareja
    if step == "awaiting_pareja" and button_id in ("pareja_si", "pareja_no"):
        session["pareja"] = button_id == "pareja_si"
        session["step"] = "awaiting_duracion"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text="¿Qué duración de masaje preferís?",
            buttons=DURACION_BUTTONS,
        )
        return

    # Duracion
    if step == "awaiting_duracion" and button_id in DURACION_MAP:
        duracion = DURACION_MAP[button_id]
        session["duracion"] = duracion
        session["step"] = "awaiting_regalo"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text="¿Es para regalar?",
            buttons=[
                {"id": "regalo_si", "title": "Sí, para regalar"},
                {"id": "regalo_no", "title": "No, es para mí"},
            ],
        )
        return

    # Regalo
    if step == "awaiting_regalo" and button_id in ("regalo_si", "regalo_no"):
        es_regalo = button_id == "regalo_si"
        session["es_regalo"] = es_regalo

        if es_regalo:
            # Gift: ask name, then payment, then voucher
            session["step"] = "awaiting_nombre"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Por favor enviá el nombre y apellido de quien recibe el regalo. Ejemplo: Juan Pérez",
            )
        else:
            # Normal: ask horario first, then name
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
            from datetime import datetime
            chosen = alternatives[alt_index]
            session["horario"] = chosen
            parsed = datetime.fromisoformat(chosen)

            if session.get("flow") == "voucher":
                session["step"] = "awaiting_confirm"
                set_session(from_number, session)
                ask_confirmation(from_number, session, parsed)
            else:
                session["step"] = "awaiting_nombre"
                set_session(from_number, session)
                send_text_message(
                    to=from_number,
                    text="Por favor enviá tu nombre y apellido. Ejemplo: Juan Pérez",
                )
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

    # Seleccionar reserva para cambiar
    if step == "awaiting_select_reserva" and button_id.startswith("cambiar_"):
        handle_select_reserva(from_number, button_id, session)
        return

    # Confirmar cambio de horario
    if step == "awaiting_confirm_cambio":
        if button_id == "cambio_si":
            confirm_cambio_horario(from_number, session)
            return
        if button_id == "cambio_no":
            session["step"] = "awaiting_nuevo_horario"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Decime otro día y horario.",
            )
            return

    # Alternativas de horario para cambio
    if step == "awaiting_alt_cambio":
        if button_id == "altcam_otro":
            session["step"] = "awaiting_nuevo_horario"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Decime otro día y horario.",
            )
            return

        if button_id.startswith("altcam_"):
            from datetime import datetime
            alt_index = int(button_id.replace("altcam_", ""))
            alternatives = session.get("alternatives", [])
            if alt_index < len(alternatives):
                session["nuevo_horario"] = alternatives[alt_index]
                session["step"] = "awaiting_confirm_cambio"
                set_session(from_number, session)
                parsed = datetime.fromisoformat(alternatives[alt_index])
                send_interactive_buttons(
                    to=from_number,
                    body_text=f"¿Confirmás el cambio a {parsed.strftime('%A %d/%m a las %H:%Mhs')}?",
                    buttons=[
                        {"id": "cambio_si", "title": "Sí, confirmar"},
                        {"id": "cambio_no", "title": "Otro horario"},
                    ],
                )
            return

    # Intencionar masaje
    if step == "awaiting_intencionar":
        if button_id == "intencionar_si":
            start_masaje_questionnaire(from_number, session)
            return
        if button_id == "intencionar_no":
            send_text_message(
                to=from_number,
                text="¡Perfecto! Te esperamos en Lakshmi. 💆",
            )
            clear_session(from_number)
            return


# ── Cambiar horario ──────────────────────────────────────────

def start_cambiar_horario(from_number):
    from datetime import datetime

    reservas = list(
        Reserva.objects.filter(
            telefono=from_number,
            horario__isnull=False,
        ).order_by("horario")
    )

    if not reservas:
        send_text_message(
            to=from_number,
            text="No tenés reservas activas para modificar.",
        )
        return

    if len(reservas) == 1:
        r = reservas[0]
        session = {
            "bot": "lakshmi",
            "flow": "cambiar",
            "step": "awaiting_nuevo_horario",
            "cambiar_reserva_id": r.id,
            "pareja": r.es_pareja,
            "duracion": r.duracion,
        }
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"Reserva encontrada:\n"
                f"📅 {r.horario.strftime('%A %d/%m a las %H:%Mhs')}\n"
                f"💆 {r.duracion} min - {r.nombre}\n\n"
                f"¿Para qué día y horario querés cambiarla?\n\n"
                f"Podés escribir, por ejemplo:\n"
                f"• mañana a las 15\n"
                f"• viernes a las 18"
            ),
        )
        return

    # Múltiples reservas: mostrar botones (máximo 3 por limitación de WhatsApp)
    session = {
        "bot": "lakshmi",
        "flow": "cambiar",
        "step": "awaiting_select_reserva",
        "reservas_cambiar": [
            {
                "id": r.id,
                "horario": r.horario.isoformat(),
                "duracion": r.duracion,
                "nombre": r.nombre,
                "es_pareja": r.es_pareja,
            }
            for r in reservas[:3]
        ],
    }
    set_session(from_number, session)

    buttons = []
    for i, r in enumerate(reservas[:3]):
        label = f"{r.horario.strftime('%d/%m %H:%M')} - {r.duracion}min"
        buttons.append({"id": f"cambiar_{i}", "title": label[:20]})

    send_interactive_buttons(
        to=from_number,
        body_text="¿Cuál reserva querés modificar?",
        buttons=buttons,
    )


def handle_select_reserva(from_number, button_id, session):
    idx = int(button_id.replace("cambiar_", ""))
    reservas_data = session.get("reservas_cambiar", [])

    if idx >= len(reservas_data):
        send_text_message(to=from_number, text="Opción inválida. Intentá de nuevo.")
        return

    selected = reservas_data[idx]
    session["cambiar_reserva_id"] = selected["id"]
    session["pareja"] = selected["es_pareja"]
    session["duracion"] = selected["duracion"]
    session["step"] = "awaiting_nuevo_horario"
    set_session(from_number, session)

    send_text_message(
        to=from_number,
        text=(
            f"¿Para qué día y horario querés cambiarla?\n\n"
            f"Podés escribir, por ejemplo:\n"
            f"• mañana a las 15\n"
            f"• viernes a las 18"
        ),
    )


def handle_nuevo_horario(from_number, text, session):
    parsed = parse_horario(text)

    if not parsed:
        send_text_message(
            to=from_number,
            text="No pude entender la fecha. Probá con algo como: mañana a las 15, viernes a las 10",
        )
        return

    parsed = parsed.replace(minute=0, second=0, microsecond=0)
    es_pareja = session.get("pareja", False)

    if es_pareja:
        has_availability = is_available(parsed) and len(get_consecutive_pairs(parsed)) > 0
    else:
        has_availability = is_available(parsed) and len(get_free_camillas(parsed)) >= 1

    if has_availability:
        session["nuevo_horario"] = parsed.isoformat()
        session["step"] = "awaiting_confirm_cambio"
        set_session(from_number, session)

        send_interactive_buttons(
            to=from_number,
            body_text=f"¿Confirmás el cambio de horario a {parsed.strftime('%A %d/%m a las %H:%Mhs')}?",
            buttons=[
                {"id": "cambio_si", "title": "Sí, confirmar"},
                {"id": "cambio_no", "title": "Otro horario"},
            ],
        )
    else:
        alternatives = suggest_alternatives(parsed, pareja=es_pareja)
        if alternatives:
            session["alternatives"] = [a.isoformat() for a in alternatives]
            session["step"] = "awaiting_alt_cambio"
            set_session(from_number, session)

            buttons = []
            for i, alt in enumerate(alternatives):
                label = alt.strftime("%A %H:%Mhs").capitalize()
                buttons.append({"id": f"altcam_{i}", "title": label[:20]})
            buttons.append({"id": "altcam_otro", "title": "Otro horario"})

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


def confirm_cambio_horario(from_number, session):
    from datetime import datetime

    reserva_id = session["cambiar_reserva_id"]
    nuevo_horario = datetime.fromisoformat(session["nuevo_horario"])
    es_pareja = session.get("pareja", False)

    try:
        reserva = Reserva.objects.get(id=reserva_id)
    except Reserva.DoesNotExist:
        send_text_message(to=from_number, text="No se encontró la reserva. Intentá de nuevo.")
        clear_session(from_number)
        return

    try:
        camillas = assign_camilla(nuevo_horario, pareja=es_pareja)
    except ValueError:
        send_text_message(
            to=from_number,
            text="Ya no quedan camillas para ese horario. Probá con otro.",
        )
        session["step"] = "awaiting_nuevo_horario"
        set_session(from_number, session)
        return

    # Si es pareja, buscar la segunda reserva del mismo horario/teléfono
    if es_pareja:
        pareja_reservas = list(
            Reserva.objects.filter(
                telefono=from_number,
                horario=reserva.horario,
                es_pareja=True,
            ).order_by("id")[:2]
        )
        for i, r in enumerate(pareja_reservas):
            suc, cam = camillas[i] if i < len(camillas) else camillas[0]
            r.horario = nuevo_horario
            r.sucursal = suc
            r.camilla = cam
            r.save()
    else:
        suc, cam = camillas[0]
        reserva.horario = nuevo_horario
        reserva.sucursal = suc
        reserva.camilla = cam
        reserva.save()

    send_text_message(
        to=from_number,
        text=(
            f"✅ ¡Horario actualizado!\n\n"
            f"📅 Nuevo horario: {nuevo_horario.strftime('%A %d/%m a las %H:%Mhs')}\n\n"
            f"¡Te esperamos en Lakshmi!"
        ),
    )
    clear_session(from_number)


# ── Helpers ──────────────────────────────────────────────────

def send_welcome(from_number):
    prices = get_prices()
    p60 = prices.get(60, 50000)
    p90 = prices.get(90, 65000)
    p120 = prices.get(120, 80000)

    set_session(from_number, {"bot": "lakshmi", "step": "welcome"})
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "Muchas gracias por tu interés!\n"
            "Lakshmi 💆🏼 es una gran experiencia para regalar y regalarte.\n"
            "Te compartimos nuestro menú de propuestas para disfrutar:\n\n"
            f"💆🏻‍♀️ Masaje Relajante y Descontracturante de 60 minutos ${p60:,}\n"
            f"🦶 + Reflexología de Pies, 90 minutos de Masaje ${p90:,}\n"
            f"💆🏼 Masaje Full (todo lo anterior + piedras calientes) 120 minutos ${p120:,}\n\n"
            "➡️ Los precios son por persona.\n"
            "➡️ Aceptamos todas las formas de pago.\n"
            "➡️ Abiertos todos los días, hasta las 22 hs."
        ),
        buttons=[
            {"id": "btn_reserva", "title": "Reservar"},
            {"id": "btn_voucher", "title": "Tengo un voucher"},
            {"id": "btn_cambiar", "title": "Cambiar horario"},
        ],
    )


def get_price(session):
    duracion = session.get("duracion", 60)
    prices = get_prices()
    precio = prices.get(duracion, 50000)
    if session.get("pareja"):
        precio *= 2
    return precio


def send_payment_info(from_number, session):
    precio = get_price(session)
    send_text_message(
        to=from_number,
        text=(
            f"💰 El precio total es ${precio:,}\n\n"
            f"Realizá la transferencia al siguiente CBU:\n\n"
            f"🏦 CBU: 0000000000000000000000\n"
            f"👤 Titular: Lakshmi Masajes\n\n"
            f"Envianos el comprobante de transferencia por este mismo chat."
        ),
    )


def ask_confirmation(from_number, session, dt):
    precio = get_price(session)
    adelanto = precio // 2
    pareja_text = "para pareja" if session.get("pareja") else "individual"
    duracion = session.get("duracion", 60)

    send_interactive_buttons(
        to=from_number,
        body_text=(
            f"Resumen de tu reserva:\n\n"
            f"👤 {session['nombre']}\n"
            f"💆 {duracion} minutos ({pareja_text})\n"
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

    horario = datetime.fromisoformat(session["horario"])
    es_pareja = session.get("pareja", False)
    duracion = session.get("duracion", 60)
    precio = get_price(session)
    adelanto = precio // 2

    try:
        camillas = assign_camilla(horario, pareja=es_pareja)
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

    flow = session.get("flow")

    if flow == "voucher":
        # Update existing voucher reserva with horario and camilla
        reserva = Reserva.objects.get(id=session["reserva_id"])
        suc, cam = camillas[0]
        reserva.horario = horario
        reserva.sucursal = suc
        reserva.camilla = cam
        reserva.save()

        session["reserva_ids"] = [reserva.id]

        send_text_message(
            to=from_number,
            text=(
                f"✅ ¡Voucher canjeado exitosamente!\n\n"
                f"📅 {horario.strftime('%A %d/%m a las %H:%Mhs')}\n"
                f"💆 {duracion} minutos\n\n"
                f"¡Te esperamos en Lakshmi!"
            ),
        )
        # Offer intencionar
        session["step"] = "awaiting_intencionar"
        set_session(from_number, session)
        ask_intencionar(from_number)

    else:
        # Normal reservation
        reserva_ids = []
        for sucursal, camilla in camillas:
            r = Reserva.objects.create(
                nombre=session["nombre"],
                es_pareja=es_pareja,
                duracion=duracion,
                horario=horario,
                sucursal=sucursal,
                camilla=camilla,
                es_regalo=False,
                telefono=from_number,
            )
            reserva_ids.append(r.id)

        session["reserva_ids"] = reserva_ids

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

        # Offer intencionar
        session["step"] = "awaiting_intencionar"
        set_session(from_number, session)
        ask_intencionar(from_number)


def ask_intencionar(from_number):
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "🧘 ¿Querés intencionar tu masaje?\n\n"
            "Contanos tu situación actual o por qué necesitás el masaje. "
            "Esto nos permite personalizar los aceites para tu sesión."
        ),
        buttons=[
            {"id": "intencionar_si", "title": "Sí, quiero"},
            {"id": "intencionar_no", "title": "No, gracias"},
        ],
    )


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
    elif step == "awaiting_duracion":
        send_interactive_buttons(
            to=from_number,
            body_text="Por favor elegí la duración del masaje:",
            buttons=DURACION_BUTTONS,
        )
    elif step == "awaiting_regalo":
        send_interactive_buttons(
            to=from_number,
            body_text="¿Es para regalar?",
            buttons=[
                {"id": "regalo_si", "title": "Sí, para regalar"},
                {"id": "regalo_no", "title": "No, es para mí"},
            ],
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
    elif step == "awaiting_comprobante":
        send_text_message(
            to=from_number,
            text="Envianos el comprobante de transferencia para continuar.",
        )
    elif step == "awaiting_voucher_code":
        send_text_message(
            to=from_number,
            text="Por favor enviá el código de tu voucher.",
        )
    elif step and step.startswith("awaiting_mq"):
        idx = session.get("mq_index", 0)
        if idx < len(MASAJE_QUESTIONS):
            send_text_message(to=from_number, text=MASAJE_QUESTIONS[idx])
    elif step == "awaiting_nuevo_horario":
        send_text_message(
            to=from_number,
            text="Decime un día y horario. Ejemplo: mañana a las 15",
        )
    elif step == "awaiting_select_reserva":
        send_text_message(
            to=from_number,
            text="Por favor seleccioná una reserva de las opciones.",
        )
    else:
        send_welcome(from_number)


# ── Superadmin ───────────────────────────────────────────────

def start_admin(from_number):
    set_session(from_number, {"bot": "lakshmi", "step": "admin_menu", "admin": True})
    send_interactive_buttons(
        to=from_number,
        body_text="🔐 Panel de administración\n\n¿Qué querés hacer?",
        buttons=[
            {"id": "admin_cancelar", "title": "Cancelar reserva"},
            {"id": "admin_precios", "title": "Modificar precios"},
        ],
    )


def admin_search_reservas(from_number, text, session):
    telefono = normalize_ar_number(text.strip().replace("+", ""))
    logger.info("Admin searching reservas for telefono: '%s' (raw: '%s')", telefono, text)
    reservas = list(
        Reserva.objects.filter(
            telefono=telefono,
            horario__isnull=False,
        ).order_by("-horario")[:3]
    )
    logger.info("Admin found %d reservas for %s", len(reservas), telefono)

    if not reservas:
        send_text_message(
            to=from_number,
            text=f"No se encontraron reservas activas para el teléfono {telefono}.",
        )
        start_admin(from_number)
        return

    if len(reservas) == 1:
        r = reservas[0]
        session["admin_reserva_id"] = r.id
        session["admin_cliente_tel"] = telefono
        session["step"] = "admin_awaiting_confirm_cancel"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text=(
                f"{r.nombre} - {r.horario.strftime('%d/%m %H:%Mhs')} "
                f"{r.duracion}min\n¿Cancelar?"
            ),
            buttons=[
                {"id": "admin_cancel_confirm", "title": "Sí, cancelar"},
                {"id": "admin_cancel_abort", "title": "No, volver"},
            ],
        )
        return

    # Múltiples reservas (máx 3 botones)
    session["admin_reservas"] = [
        {"id": r.id, "nombre": r.nombre, "horario": r.horario.isoformat(), "duracion": r.duracion}
        for r in reservas[:3]
    ]
    session["admin_cliente_tel"] = telefono
    session["step"] = "admin_awaiting_select_cancel"
    set_session(from_number, session)

    buttons = []
    for i, r in enumerate(reservas[:3]):
        label = f"{r.horario.strftime('%d/%m %H:%M')} {r.duracion}min"
        buttons.append({"id": f"admin_cancel_{i}", "title": label[:20]})

    send_interactive_buttons(
        to=from_number,
        body_text=f"Reservas de {telefono}:\n¿Cuál querés cancelar?",
        buttons=buttons,
    )


def admin_confirm_cancel(from_number, button_id, session):
    idx = int(button_id.replace("admin_cancel_", ""))
    reservas_data = session.get("admin_reservas", [])

    if idx >= len(reservas_data):
        send_text_message(to=from_number, text="Opción inválida.")
        start_admin(from_number)
        return

    selected = reservas_data[idx]
    session["admin_reserva_id"] = selected["id"]
    session["step"] = "admin_awaiting_confirm_cancel"
    set_session(from_number, session)

    from datetime import datetime
    horario = datetime.fromisoformat(selected["horario"])

    send_interactive_buttons(
        to=from_number,
        body_text=(
            f"¿Confirmar cancelación?\n\n"
            f"👤 {selected['nombre']}\n"
            f"📅 {horario.strftime('%A %d/%m a las %H:%Mhs')}\n"
            f"💆 {selected['duracion']} min"
        ),
        buttons=[
            {"id": "admin_cancel_confirm", "title": "Sí, cancelar"},
            {"id": "admin_cancel_abort", "title": "No, volver"},
        ],
    )


def admin_execute_cancel(from_number, session):
    reserva_id = session.get("admin_reserva_id")
    cliente_tel = session.get("admin_cliente_tel", "")

    try:
        reserva = Reserva.objects.get(id=reserva_id)
        info = (
            f"📅 {reserva.horario.strftime('%A %d/%m a las %H:%Mhs')}\n"
            f"💆 {reserva.duracion} min - {reserva.nombre}"
        )

        # Si es pareja, cancelar ambas reservas del mismo horario
        if reserva.es_pareja:
            Reserva.objects.filter(
                telefono=reserva.telefono,
                horario=reserva.horario,
                es_pareja=True,
            ).delete()
        else:
            reserva.delete()

        send_text_message(
            to=from_number,
            text=f"✅ Reserva cancelada:\n{info}",
        )

        # Notificar al cliente
        if cliente_tel:
            send_text_message(
                to=cliente_tel,
                text=(
                    f"Hola, te informamos que tu reserva ha sido cancelada:\n{info}\n\n"
                    f"Si tenés consultas, escribinos."
                ),
            )

    except Reserva.DoesNotExist:
        send_text_message(to=from_number, text="No se encontró la reserva.")

    start_admin(from_number)


def admin_show_precios(from_number):
    prices = get_prices()
    lines = "\n".join(f"• {dur} min → ${precio:,}" for dur, precio in sorted(prices.items()))

    session = {"bot": "lakshmi", "step": "admin_precios", "admin": True}
    set_session(from_number, session)

    send_interactive_buttons(
        to=from_number,
        body_text=f"Precios actuales:\n\n{lines}\n\n¿Cuál querés modificar?",
        buttons=[
            {"id": "admin_precio_60", "title": "60 minutos"},
            {"id": "admin_precio_90", "title": "90 minutos"},
            {"id": "admin_precio_120", "title": "120 minutos"},
        ],
    )


def admin_select_duracion(from_number, button_id, session):
    dur_str = button_id.replace("admin_precio_", "")
    duracion = int(dur_str)
    prices = get_prices()
    precio_actual = prices.get(duracion, 0)

    session = {
        "bot": "lakshmi",
        "step": "admin_awaiting_nuevo_precio",
        "admin": True,
        "admin_duracion": duracion,
    }
    set_session(from_number, session)

    send_text_message(
        to=from_number,
        text=f"Precio actual de {duracion} min: ${precio_actual:,}\n\nEnviá el nuevo precio (solo números, ej: 55000)",
    )


def admin_set_precio(from_number, text, session):
    duracion = session.get("admin_duracion")
    try:
        nuevo_precio = int(text.strip().replace(".", "").replace(",", "").replace("$", ""))
    except ValueError:
        send_text_message(to=from_number, text="Precio inválido. Enviá solo números, ej: 55000")
        return

    Precio.objects.update_or_create(
        duracion=duracion,
        defaults={"precio": nuevo_precio},
    )

    send_text_message(
        to=from_number,
        text=f"✅ Precio actualizado: {duracion} min → ${nuevo_precio:,}",
    )
    admin_show_precios(from_number)
