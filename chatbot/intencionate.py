import logging
from datetime import datetime

from .conversation import clear_session, get_session, set_session
from .llm_chat import chat_response, deepen_message
from .models import Intencionate, Memoria, Reserva
from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)

PLAN_BUTTONS = [
    {"id": "int_plan_basico", "title": "Básico - $15.000"},
    {"id": "int_plan_intermedio", "title": "Intermedio - $25.000"},
    {"id": "int_plan_premium", "title": "Premium - $40.000"},
]

PLAN_MAP = {
    "int_plan_basico": ("basico", 15000, 1),
    "int_plan_intermedio": ("intermedio", 25000, 3),
    "int_plan_premium": ("premium", 40000, 5),
}

# Preguntas del cuestionario de suscripción
SUBSCRIPTION_QUESTIONS = [
    "¿Qué estás atravesando hoy?",
    "¿Qué es lo que más te mueve o te preocupa de esto?",
    "¿Cómo te estás sintiendo frente a esto?",
    "¿Dónde lo sentís en el cuerpo?",
    "¿Cómo está tu energía hoy?",
    "Si esto se ordenara, ¿qué te gustaría que pase?",
    "¿A qué hora te gustaría recibir el agradecimiento diario? (ej: 21, 22)",
]

QUESTION_KEYS = [
    "q_atravesando",
    "q_preocupa",
    "q_sintiendo",
    "q_cuerpo",
    "q_energia",
    "q_deseo",
    "hora_integrar",
]

SATISFACCION_BUTTONS = [
    {"id": "sat_muy_bien", "title": "Me entendió muy bien"},
    {"id": "sat_sentido", "title": "Tiene sentido"},
    {"id": "sat_no_representa", "title": "No me representa"},
]


def get_user_info(sub: Intencionate) -> dict:
    return {
        "nombre": sub.nombre,
        "lugar_nacimiento": sub.lugar_nacimiento,
        "fecha_nacimiento": sub.fecha_nacimiento,
    }


def get_recent_memories(phone: str, limit: int = 10) -> list[str]:
    memos = Memoria.objects.filter(id_user=phone).order_by("-created_at")[:limit]
    return [m.context for m in memos]


def get_daily_usage_count(phone: str) -> int:
    today = datetime.now().date()
    return Memoria.objects.filter(
        id_user=phone,
        created_at__date=today,
        context__startswith="[experiencia]",
    ).count()


def get_plan_limit(plan: str) -> int:
    limits = {"basico": 1, "intermedio": 3, "premium": 5}
    return limits.get(plan, 1)


# ── Entry point ──────────────────────────────────────────────

def process(from_number, msg_type, message, session):
    if msg_type == "text":
        text = message.get("text", {}).get("body", "").strip()
        handle_text(from_number, text, session)
    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        button_id = button_reply.get("id", "")
        handle_button(from_number, button_id, session)
    elif msg_type in ("image", "document"):
        handle_file(from_number, session)


# ── Text handler ─────────────────────────────────────────────

def handle_text(from_number, text, session):
    if text.lower() in ("finalizar conversación", "finalizar conversacion", "finalizar"):
        clear_session(from_number)
        send_text_message(to=from_number, text="Conversación finalizada. ¡Gracias por conectar con Intencionate!")
        return

    if not session:
        session = {"bot": "intencionate"}

    step = session.get("step")

    # ── Suscripción: nombre ──
    if step == "int_awaiting_nombre":
        session["int_nombre"] = text
        session["step"] = "int_awaiting_lugar"
        set_session(from_number, session)
        send_text_message(to=from_number, text="¿Cuál es tu lugar de nacimiento?")
        return

    # ── Suscripción: lugar de nacimiento ──
    if step == "int_awaiting_lugar":
        session["int_lugar"] = text
        session["step"] = "int_awaiting_fecha_nac"
        set_session(from_number, session)
        send_text_message(to=from_number, text="¿Cuál es tu fecha de nacimiento? (ej: 15/03/1990)")
        return

    # ── Suscripción: fecha de nacimiento ──
    if step == "int_awaiting_fecha_nac":
        session["int_fecha_nac"] = text
        session["step"] = "int_awaiting_q0"
        session["q_index"] = 0
        set_session(from_number, session)
        send_text_message(to=from_number, text=SUBSCRIPTION_QUESTIONS[0])
        return

    # ── Cuestionario de suscripción (preguntas 0-6) ──
    if step and step.startswith("int_awaiting_q"):
        q_index = session.get("q_index", 0)
        key = QUESTION_KEYS[q_index]
        session[key] = text

        # Guardar respuesta en Memoria (excepto hora_integrar)
        if key != "hora_integrar":
            Memoria.objects.create(id_user=from_number, context=text[:200])

        next_index = q_index + 1
        if next_index < len(SUBSCRIPTION_QUESTIONS):
            session["q_index"] = next_index
            session["step"] = f"int_awaiting_q{next_index}"
            set_session(from_number, session)
            send_text_message(to=from_number, text=SUBSCRIPTION_QUESTIONS[next_index])
        else:
            # Cuestionario terminado, pedir plan
            session["step"] = "int_awaiting_plan"
            set_session(from_number, session)
            send_interactive_buttons(
                to=from_number,
                body_text=(
                    "¡Gracias por compartir! Ahora elegí tu plan:\n\n"
                    "🌱 *Básico* - $15.000/mes (1 experiencia diaria)\n"
                    "🌿 *Intermedio* - $25.000/mes (3 experiencias diarias)\n"
                    "🌳 *Premium* - $40.000/mes (5 experiencias diarias)"
                ),
                buttons=PLAN_BUTTONS,
            )
        return

    # ── Flujo "Intenciona tu experiencia" ──
    if step == "int_experiencia_chat":
        sub = Intencionate.objects.get(telefono=from_number)
        memories = get_recent_memories(from_number)

        # Guardar el mensaje del usuario
        Memoria.objects.create(id_user=from_number, context=f"[experiencia] {text[:185]}")

        # Generar respuesta con LLM
        user_info = get_user_info(sub)
        response = chat_response(text, user_info, memories)

        session["last_llm_message"] = response
        session["step"] = "int_experiencia_responded"
        set_session(from_number, session)

        send_text_message(to=from_number, text=response)
        send_interactive_buttons(
            to=from_number,
            body_text="¿Querés profundizar en esto?",
            buttons=[
                {"id": "int_profundizar_exp", "title": "Profundizar"},
                {"id": "int_finalizar_exp", "title": "Finalizar"},
            ],
        )
        return

    # ── Respuesta del usuario después del mensaje diario ──
    if step == "int_daily_responded":
        sub = Intencionate.objects.get(telefono=from_number)
        memories = get_recent_memories(from_number)

        # Guardar respuesta del usuario
        Memoria.objects.create(id_user=from_number, context=text[:200])

        # Responder con LLM
        user_info = get_user_info(sub)
        response = chat_response(text, user_info, memories)

        send_text_message(to=from_number, text=response)
        clear_session(from_number)
        return

    # ── Si el usuario tiene suscripción activa y manda texto libre ──
    try:
        sub = Intencionate.objects.get(telefono=from_number, activo=True)
    except Intencionate.DoesNotExist:
        send_welcome_intencionate(from_number)
        return

    # Iniciar flujo "Intenciona tu experiencia"
    usage = get_daily_usage_count(from_number)
    limit = get_plan_limit(sub.tipo_plan)

    if usage >= limit:
        send_text_message(
            to=from_number,
            text=(
                f"Ya usaste tus {limit} experiencia(s) de hoy según tu plan {sub.tipo_plan}. "
                "¡Mañana podés volver a conectar!"
            ),
        )
        clear_session(from_number)
        return

    memories = get_recent_memories(from_number)
    user_info = get_user_info(sub)

    Memoria.objects.create(id_user=from_number, context=f"[experiencia] {text[:185]}")

    response = chat_response(text, user_info, memories)

    session["bot"] = "intencionate"
    session["last_llm_message"] = response
    session["step"] = "int_experiencia_responded"
    set_session(from_number, session)

    send_text_message(to=from_number, text=response)
    send_interactive_buttons(
        to=from_number,
        body_text="¿Querés profundizar en esto?",
        buttons=[
            {"id": "int_profundizar_exp", "title": "Profundizar"},
            {"id": "int_finalizar_exp", "title": "Finalizar"},
        ],
    )


# ── Button handler ───────────────────────────────────────────

def handle_button(from_number, button_id, session):
    if not session:
        session = {"bot": "intencionate"}

    step = session.get("step")

    # ── Suscribirse / No ──
    if button_id == "int_suscribir_si":
        session["bot"] = "intencionate"

        # Chequear si ya completó cuestionario en masaje
        has_lugar = Memoria.objects.filter(
            id_user=from_number, context__startswith="[lugar]"
        ).exists()
        has_fecha = Memoria.objects.filter(
            id_user=from_number, context__startswith="[fecha_nac]"
        ).exists()
        has_cuestionario = Memoria.objects.filter(
            id_user=from_number, context__startswith="[lugar]"
        ).exists() and Memoria.objects.filter(
            id_user=from_number,
        ).exclude(
            context__startswith="[lugar]"
        ).exclude(
            context__startswith="[fecha_nac]"
        ).exclude(
            context__startswith="[experiencia]"
        ).count() >= 6  # 6 preguntas emocionales

        if has_cuestionario and has_lugar and has_fecha:
            # Ya completó todo en masaje, ir directo a plan
            # Obtener datos de Memoria
            lugar_mem = Memoria.objects.filter(id_user=from_number, context__startswith="[lugar]").first()
            fecha_mem = Memoria.objects.filter(id_user=from_number, context__startswith="[fecha_nac]").first()
            session["int_lugar"] = lugar_mem.context.replace("[lugar] ", "") if lugar_mem else ""
            session["int_fecha_nac"] = fecha_mem.context.replace("[fecha_nac] ", "") if fecha_mem else ""
            # Necesitamos el nombre de la reserva
            reserva = Reserva.objects.filter(telefono=from_number).order_by("-id").first()
            session["int_nombre"] = reserva.nombre if reserva else ""
            session["step"] = "int_awaiting_plan"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Ya tenemos tus datos de un cuestionario anterior. ¡Elegí tu plan!",
            )
            send_interactive_buttons(
                to=from_number,
                body_text=(
                    "🌱 *Básico* - $15.000/mes (1 experiencia diaria)\n"
                    "🌿 *Intermedio* - $25.000/mes (3 experiencias diarias)\n"
                    "🌳 *Premium* - $40.000/mes (5 experiencias diarias)"
                ),
                buttons=PLAN_BUTTONS,
            )
            return

        session["step"] = "int_awaiting_nombre"
        set_session(from_number, session)
        send_text_message(to=from_number, text="¡Genial! ¿Cuál es tu nombre completo?")
        return

    if button_id == "int_suscribir_no":
        send_text_message(
            to=from_number,
            text="¡Está bien! Cuando quieras suscribirte, escribinos. ¡Te esperamos!",
        )
        clear_session(from_number)
        return

    # ── Selección de plan ──
    if step == "int_awaiting_plan" and button_id in PLAN_MAP:
        plan_key, precio, _ = PLAN_MAP[button_id]
        session["int_plan"] = plan_key
        session["int_precio"] = precio
        session["step"] = "int_awaiting_comprobante"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"💰 El precio del plan es ${precio:,}/mes\n\n"
                f"Realizá la transferencia al siguiente CBU:\n\n"
                f"🏦 CBU: 0000000000000000000000\n"
                f"👤 Titular: Intencionate\n\n"
                f"Envianos el comprobante de transferencia por este mismo chat."
            ),
        )
        return

    # ── Profundizar mensaje diario ──
    if button_id == "int_profundizar_daily":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            clear_session(from_number)
            return

        original = session.get("last_llm_message", "")
        user_info = get_user_info(sub)
        memories = get_recent_memories(from_number)
        deep = deepen_message(original, user_info, memories)

        session["step"] = "int_daily_responded"
        set_session(from_number, session)

        send_text_message(to=from_number, text=deep)
        send_text_message(
            to=from_number,
            text="Si querés compartir algo sobre cómo te sentís, escribilo. Si no, escribí 'finalizar'.",
        )
        return

    if button_id == "int_no_profundizar_daily":
        session["step"] = "int_daily_responded"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text="¡Está bien! Si querés compartir algo, escribilo. Si no, escribí 'finalizar'.",
        )
        return

    # ── Profundizar "Intenciona tu experiencia" ──
    if button_id == "int_profundizar_exp":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            clear_session(from_number)
            return

        original = session.get("last_llm_message", "")
        user_info = get_user_info(sub)
        memories = get_recent_memories(from_number)
        deep = deepen_message(original, user_info, memories)

        send_text_message(to=from_number, text=deep)
        clear_session(from_number)
        return

    if button_id == "int_finalizar_exp":
        send_text_message(to=from_number, text="¡Gracias por conectar hoy! Estamos acá cuando lo necesites. 🙏")
        clear_session(from_number)
        return

    # ── "Integra tu experiencia" - satisfacción ──
    if step == "int_awaiting_satisfaccion" and button_id in ("sat_muy_bien", "sat_sentido", "sat_no_representa"):
        sat_map = {
            "sat_muy_bien": "Me entendió muy bien",
            "sat_sentido": "Tiene sentido lo que dice",
            "sat_no_representa": "No me representa",
        }
        try:
            sub = Intencionate.objects.get(telefono=from_number)
            sub.satisfaccion_cliente = sat_map[button_id]
            sub.save()
        except Intencionate.DoesNotExist:
            pass

        # Ahora enviar profundización
        original = session.get("last_llm_message", "")
        try:
            sub = Intencionate.objects.get(telefono=from_number)
            user_info = get_user_info(sub)
        except Intencionate.DoesNotExist:
            user_info = {}

        memories = get_recent_memories(from_number)
        deep = deepen_message(original, user_info, memories)

        send_text_message(to=from_number, text=deep)
        send_text_message(to=from_number, text="Descansá bien. Mañana seguimos conectando. 🌙")
        clear_session(from_number)
        return

    # ── Profundizar integración (antes de satisfacción) ──
    if button_id == "int_profundizar_integra":
        session["step"] = "int_awaiting_satisfaccion"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text="Antes de profundizar, ¿qué tanta conexión generó este mensaje?",
            buttons=SATISFACCION_BUTTONS,
        )
        return

    if button_id == "int_no_profundizar_integra":
        send_text_message(to=from_number, text="Descansá bien. Mañana seguimos conectando. 🌙")
        clear_session(from_number)
        return


# ── File handler (comprobante de suscripción) ────────────────

def handle_file(from_number, session):
    if not session:
        return

    step = session.get("step")

    if step == "int_awaiting_comprobante":
        # Crear suscripción
        Intencionate.objects.update_or_create(
            telefono=from_number,
            defaults={
                "nombre": session.get("int_nombre", ""),
                "lugar_nacimiento": session.get("int_lugar", ""),
                "fecha_nacimiento": session.get("int_fecha_nac", ""),
                "activo": True,
                "fecha_pago": datetime.now(),
                "tipo_plan": session.get("int_plan", "basico"),
                "hora_integrar": session.get("hora_integrar", "21"),
            },
        )

        send_text_message(
            to=from_number,
            text=(
                "✅ ¡Comprobante recibido! Tu suscripción a Intencionate está activa.\n\n"
                f"🌿 Plan: {session.get('int_plan', 'basico').capitalize()}\n"
                f"⏰ Agradecimiento diario a las {session.get('hora_integrar', '21')}hs\n\n"
                "Todos los días a las 8hs vas a recibir tu mensaje motivador del día.\n"
                "¡Gracias por confiar en Intencionate! 🙏"
            ),
        )
        clear_session(from_number)
        return


# ── Bienvenida ───────────────────────────────────────────────

def send_welcome_intencionate(from_number):
    set_session(from_number, {"bot": "intencionate", "step": "int_welcome"})
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "✨ *Bienvenido/a a Intencionate* ✨\n\n"
            "Intencionate es un servicio de acompañamiento espiritual diario "
            "que te ayuda a conectar con tus emociones y transformar tu día a día.\n\n"
            "🌱 *Básico* - $15.000/mes\n"
            "   → 1 experiencia diaria\n"
            "🌿 *Intermedio* - $25.000/mes\n"
            "   → 3 experiencias diarias\n"
            "🌳 *Premium* - $40.000/mes\n"
            "   → 5 experiencias diarias\n\n"
            "Todos los planes incluyen:\n"
            "• Mensaje motivador diario (8hs)\n"
            "• Agradecimiento de cierre del día\n"
            "• Opción de profundizar cada mensaje\n\n"
            "¿Te gustaría suscribirte?"
        ),
        buttons=[
            {"id": "int_suscribir_si", "title": "Sí, quiero"},
            {"id": "int_suscribir_no", "title": "No, gracias"},
        ],
    )


# ── Mensajes programados (llamados por cron/management command) ──

def send_daily_morning_message(sub: Intencionate):
    from .llm_chat import generate_daily_message

    user_info = get_user_info(sub)
    memories = get_recent_memories(sub.telefono)
    msg = generate_daily_message(user_info, memories)

    session = {
        "bot": "intencionate",
        "step": "int_daily_message",
        "last_llm_message": msg,
    }
    set_session(sub.telefono, session)

    send_text_message(to=sub.telefono, text=f"🌅 *Intencionate Hoy*\n\n{msg}")
    send_interactive_buttons(
        to=sub.telefono,
        body_text="¿Querés profundizar en este mensaje?",
        buttons=[
            {"id": "int_profundizar_daily", "title": "Profundizar"},
            {"id": "int_no_profundizar_daily", "title": "No, gracias"},
        ],
    )


def send_integration_message(sub: Intencionate):
    from .llm_chat import generate_integration_message

    user_info = get_user_info(sub)
    memories = get_recent_memories(sub.telefono)
    msg = generate_integration_message(user_info, memories)

    session = {
        "bot": "intencionate",
        "step": "int_integration_message",
        "last_llm_message": msg,
    }
    set_session(sub.telefono, session)

    send_text_message(to=sub.telefono, text=f"🌙 *Integra tu experiencia*\n\n{msg}")
    send_interactive_buttons(
        to=sub.telefono,
        body_text="¿Querés profundizar en este mensaje?",
        buttons=[
            {"id": "int_profundizar_integra", "title": "Profundizar"},
            {"id": "int_no_profundizar_integra", "title": "No, gracias"},
        ],
    )
