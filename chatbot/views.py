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
from .models import Memoria, Reserva, generate_voucher_code
from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)

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

    except Exception:
        logger.exception("Error processing message from %s", from_number)
    finally:
        from django.db import close_old_connections
        close_old_connections()


# ── Text handler ─────────────────────────────────────────────

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
    elif step == "awaiting_voucher_code":
        handle_voucher_code(from_number, text, session)
    elif step == "awaiting_intencion":
        handle_intencion(from_number, text, session)
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


# ── Intencion handler ───────────────────────────────────────

def handle_intencion(from_number, text, session):
    if text:
        Memoria.objects.create(
            id_user=from_number,
            context=text[:200],
        )
        send_text_message(
            to=from_number,
            text=(
                "🧘 ¡Gracias por compartir! Vamos a personalizar tu experiencia "
                "con aceites especiales para vos.\n\n"
                "¡Te esperamos en Lakshmi!"
            ),
        )
    else:
        send_text_message(
            to=from_number,
            text="¡Te esperamos en Lakshmi!",
        )
    clear_session(from_number)


# ── Button handler ───────────────────────────────────────────

def handle_button(from_number, button_id, session):
    logger.info("Button pressed: %s, session: %s", button_id, session)

    # ── Main menu buttons (no session needed) ──
    if button_id == "btn_reserva":
        set_session(from_number, {"step": "awaiting_pareja", "flow": "reserva"})
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
        send_text_message(
            to=from_number,
            text="Para cambiar el horario de tu reserva, contactanos directamente.",
        )
        return

    if button_id == "btn_voucher":
        set_session(from_number, {"step": "awaiting_voucher_code", "flow": "voucher"})
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

    # Intencionar masaje
    if step == "awaiting_intencionar":
        if button_id == "intencionar_si":
            session["step"] = "awaiting_intencion"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text=(
                    "Contanos brevemente cuál es tu situación actual "
                    "o por qué necesitás el masaje. Esto nos ayuda a "
                    "personalizar los aceites para tu sesión."
                ),
            )
            return
        if button_id == "intencionar_no":
            send_text_message(
                to=from_number,
                text="¡Perfecto! Te esperamos en Lakshmi. 💆",
            )
            clear_session(from_number)
            return


# ── Helpers ──────────────────────────────────────────────────

def send_welcome(from_number):
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "Muchas gracias por tu interés!\n"
            "Lakshmi 💆🏼 es una gran experiencia para regalar y regalarte.\n"
            "Te compartimos nuestro menú de propuestas para disfrutar:\n\n"
            "💆🏻‍♀️ Masaje Relajante y Descontracturante de 60 minutos $50.000\n"
            "🦶 + Reflexología de Pies, 90 minutos de Masaje $65.000\n"
            "💆🏼 Masaje Full (todo lo anterior + piedras calientes) 120 minutos $80.000\n\n"
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
    precio = PRICES.get(duracion, 50000)
    if session.get("pareja"):
        precio *= 2
    return precio


def send_payment_info(from_number, session):
    precio = get_price(session)
    adelanto = precio // 2
    send_text_message(
        to=from_number,
        text=(
            f"💰 El precio total es ${precio:,}\n"
            f"💳 Adelanto (50%): ${adelanto:,}\n\n"
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
        for sucursal, camilla in camillas:
            Reserva.objects.create(
                nombre=session["nombre"],
                es_pareja=es_pareja,
                duracion=duracion,
                horario=horario,
                sucursal=sucursal,
                camilla=camilla,
                es_regalo=False,
                telefono=from_number,
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
    elif step == "awaiting_intencion":
        send_text_message(
            to=from_number,
            text="Contanos brevemente tu situación o escribí 'finalizar' para terminar.",
        )
    else:
        send_welcome(from_number)
