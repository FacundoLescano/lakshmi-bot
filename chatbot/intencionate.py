import logging
from datetime import datetime, timedelta

from .conversation import clear_session, get_session, set_session
from .llm_chat import chat_response, deepen_message
from .models import ConfiguracionSistema, Intencionate, Memoria, Reserva
from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)

PLAN_EXPERIENCIAS = {"basico": 1, "intermedio": 3, "premium": 5}

SATISFACCION_BUTTONS = [
    {"id": "sat_muy_bien", "title": "Me entendió muy bien"},
    {"id": "sat_sentido", "title": "Tiene sentido"},
    {"id": "sat_no_representa", "title": "No me representa"},
]

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


# ── Helpers ──────────────────────────────────────────────────

def get_int_prices():
    """Lee precios de planes desde DB con fallback a valores por defecto."""
    return {
        "basico":      int(ConfiguracionSistema.get("int_precio_basico",      "15000")),
        "intermedio":  int(ConfiguracionSistema.get("int_precio_intermedio",   "25000")),
        "premium":     int(ConfiguracionSistema.get("int_precio_premium",      "40000")),
    }


def get_plan_buttons():
    prices = get_int_prices()
    return [
        {"id": "int_plan_basico",      "title": f"Básico ${prices['basico']:,}"},
        {"id": "int_plan_intermedio",  "title": f"Intermedio ${prices['intermedio']:,}"},
        {"id": "int_plan_premium",     "title": f"Premium ${prices['premium']:,}"},
    ]


def get_cbu():
    return ConfiguracionSistema.get("cbu", "0000000000000000000000")


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
    return PLAN_EXPERIENCIAS.get(plan, 1)


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

        if key != "hora_integrar":
            Memoria.objects.create(id_user=from_number, context=text[:200])

        next_index = q_index + 1
        if next_index < len(SUBSCRIPTION_QUESTIONS):
            session["q_index"] = next_index
            session["step"] = f"int_awaiting_q{next_index}"
            set_session(from_number, session)
            send_text_message(to=from_number, text=SUBSCRIPTION_QUESTIONS[next_index])
        else:
            session["step"] = "int_awaiting_plan"
            set_session(from_number, session)
            prices = get_int_prices()
            send_interactive_buttons(
                to=from_number,
                body_text=(
                    "¡Gracias por compartir! Ahora elegí tu plan:\n\n"
                    f"🌱 *Básico* - ${prices['basico']:,}/mes (1 experiencia diaria)\n"
                    f"🌿 *Intermedio* - ${prices['intermedio']:,}/mes (3 experiencias diarias)\n"
                    f"🌳 *Premium* - ${prices['premium']:,}/mes (5 experiencias diarias)"
                ),
                buttons=get_plan_buttons(),
            )
        return

    # ── Menú principal para usuarios suscriptos ──
    # (las opciones son botones, no texto — si llega texto acá es un caso inesperado)
    if step == "int_menu":
        send_welcome_suscripto(from_number)
        return

    # ── Menú cambiar plan ──
    if step == "int_menu_cambiar_plan":
        handle_menu_cambiar_plan(from_number, text, session)
        return

    # ── Flujo "Intenciona tu experiencia" ──
    if step == "int_experiencia_chat":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            send_welcome_intencionate(from_number)
            return

        memories = get_recent_memories(from_number)
        Memoria.objects.create(id_user=from_number, context=f"[experiencia] {text[:185]}")

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
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            clear_session(from_number)
            return

        memories = get_recent_memories(from_number)
        Memoria.objects.create(id_user=from_number, context=text[:200])

        user_info = get_user_info(sub)
        response = chat_response(text, user_info, memories)

        send_text_message(to=from_number, text=response)
        clear_session(from_number)
        return

    # ── Entry point: usuario sin sesión activa ──
    try:
        sub = Intencionate.objects.get(telefono=from_number, activo=True)
        # Usuario suscripto → mostrar menú de bienvenida
        send_welcome_suscripto(from_number)
    except Intencionate.DoesNotExist:
        send_welcome_intencionate(from_number)


def handle_menu_cambiar_plan(from_number, text, session):
    prices = get_int_prices()
    opcion = text.strip()

    plan_map = {
        "1": ("basico",     prices["basico"]),
        "2": ("intermedio", prices["intermedio"]),
        "3": ("premium",    prices["premium"]),
    }

    if opcion in plan_map:
        nuevo_plan, precio = plan_map[opcion]
        session["int_nuevo_plan"] = nuevo_plan
        session["int_precio"] = precio
        session["step"] = "int_awaiting_comprobante_cambio_plan"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"Cambiás al plan *{nuevo_plan.capitalize()}* — ${precio:,}/mes\n\n"
                f"Realizá la transferencia al siguiente CBU:\n\n"
                f"🏦 CBU: {get_cbu()}\n"
                f"👤 Titular: Intencionate\n\n"
                f"Envianos el comprobante por este mismo chat."
            ),
        )
        return

    if opcion == "4":
        # Cancelar suscripción
        session["step"] = "int_confirm_cancelar"
        set_session(from_number, session)
        send_interactive_buttons(
            to=from_number,
            body_text="¿Confirmás que querés cancelar tu suscripción?",
            buttons=[
                {"id": "int_cancelar_confirm", "title": "Sí, cancelar"},
                {"id": "int_cancelar_abort", "title": "No, volver"},
            ],
        )
        return

    if opcion == "5":
        clear_session(from_number)
        send_text_message(to=from_number, text="¡Hasta pronto! Estamos acá cuando lo necesites. 🙏")
        return

    send_text_message(
        to=from_number,
        text="Por favor respondé con un número del 1 al 5.",
    )


# ── Button handler ───────────────────────────────────────────

def handle_button(from_number, button_id, session):
    if not session:
        session = {"bot": "intencionate"}

    step = session.get("step")

    # ── Suscribirse / No ──
    if button_id == "int_suscribir_si":
        session["bot"] = "intencionate"

        has_lugar = Memoria.objects.filter(
            id_user=from_number, context__startswith="[lugar]"
        ).exists()
        has_fecha = Memoria.objects.filter(
            id_user=from_number, context__startswith="[fecha_nac]"
        ).exists()
        has_cuestionario = has_lugar and Memoria.objects.filter(
            id_user=from_number,
        ).exclude(
            context__startswith="[lugar]"
        ).exclude(
            context__startswith="[fecha_nac]"
        ).exclude(
            context__startswith="[experiencia]"
        ).count() >= 6

        if has_cuestionario and has_lugar and has_fecha:
            lugar_mem = Memoria.objects.filter(id_user=from_number, context__startswith="[lugar]").first()
            fecha_mem = Memoria.objects.filter(id_user=from_number, context__startswith="[fecha_nac]").first()
            session["int_lugar"] = lugar_mem.context.replace("[lugar] ", "") if lugar_mem else ""
            session["int_fecha_nac"] = fecha_mem.context.replace("[fecha_nac] ", "") if fecha_mem else ""
            reserva = Reserva.objects.filter(telefono=from_number).order_by("-id").first()
            session["int_nombre"] = reserva.nombre if reserva else ""
            session["step"] = "int_awaiting_plan"
            set_session(from_number, session)
            send_text_message(
                to=from_number,
                text="Ya tenemos tus datos de un cuestionario anterior. ¡Elegí tu plan!",
            )
            prices = get_int_prices()
            send_interactive_buttons(
                to=from_number,
                body_text=(
                    f"🌱 *Básico* - ${prices['basico']:,}/mes (1 experiencia diaria)\n"
                    f"🌿 *Intermedio* - ${prices['intermedio']:,}/mes (3 experiencias diarias)\n"
                    f"🌳 *Premium* - ${prices['premium']:,}/mes (5 experiencias diarias)"
                ),
                buttons=get_plan_buttons(),
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

    # ── Botones del menú principal (usuario suscripto) ──
    if button_id == "int_menu_experiencia":
        usage = get_daily_usage_count(from_number)
        try:
            sub = Intencionate.objects.get(telefono=from_number, activo=True)
            limit = get_plan_limit(sub.tipo_plan)
        except Intencionate.DoesNotExist:
            send_welcome_intencionate(from_number)
            return

        if usage >= limit:
            send_text_message(
                to=from_number,
                text=(
                    f"Ya usaste tus {limit} experiencia(s) de hoy según tu plan "
                    f"{sub.tipo_plan}. ¡Mañana podés volver a conectar!"
                ),
            )
            clear_session(from_number)
            return

        session["step"] = "int_experiencia_chat"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text="Contame, ¿qué experiencia querés intencionar? (reunión, proyecto, vínculo, etc.)",
        )
        return

    if button_id == "int_menu_masaje":
        from .views import send_welcome
        send_welcome(from_number)
        return

    if button_id == "int_menu_suscripcion":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            send_welcome_intencionate(from_number)
            return
        show_estado_suscripcion(from_number, sub, session)
        return

    # ── Selección de plan (nueva suscripción) ──
    if step == "int_awaiting_plan" and button_id in ("int_plan_basico", "int_plan_intermedio", "int_plan_premium"):
        plan_key = button_id.replace("int_plan_", "")
        prices = get_int_prices()
        precio = prices[plan_key]
        session["int_plan"] = plan_key
        session["int_precio"] = precio
        session["step"] = "int_awaiting_comprobante"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"💰 El precio del plan es ${precio:,}/mes\n\n"
                f"Realizá la transferencia al siguiente CBU:\n\n"
                f"🏦 CBU: {get_cbu()}\n"
                f"👤 Titular: Intencionate\n\n"
                f"Envianos el comprobante de transferencia por este mismo chat."
            ),
        )
        return

    # ── Menú suscripto: Abonar suscripción ──
    if button_id == "int_abonar":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            send_welcome_intencionate(from_number)
            return
        prices = get_int_prices()
        precio = prices.get(sub.tipo_plan, 0)
        session["step"] = "int_awaiting_comprobante_abonar"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"💰 Monto a abonar: ${precio:,}/mes (plan {sub.tipo_plan.capitalize()})\n\n"
                f"Realizá la transferencia al siguiente CBU:\n\n"
                f"🏦 CBU: {get_cbu()}\n"
                f"👤 Titular: Intencionate\n\n"
                f"Envianos el comprobante por este mismo chat."
            ),
        )
        return

    # ── Menú suscripto: Cambiar plan ──
    if button_id == "int_cambiar_plan":
        prices = get_int_prices()
        session["step"] = "int_menu_cambiar_plan"
        set_session(from_number, session)
        send_text_message(
            to=from_number,
            text=(
                f"Elegí tu nuevo plan:\n\n"
                f"1 🌱 Básico — ${prices['basico']:,}/mes | 1 experiencia diaria\n"
                f"2 🌿 Intermedio — ${prices['intermedio']:,}/mes | 3 experiencias diarias\n"
                f"3 🌳 Premium — ${prices['premium']:,}/mes | 5 experiencias diarias\n"
                f"4 Cancelar suscripción\n"
                f"5 Finalizar conversación\n\n"
                f"Respondé con el número de tu elección."
            ),
        )
        return

    # ── Menú suscripto: Finalizar ──
    if button_id == "int_finalizar":
        clear_session(from_number)
        send_text_message(to=from_number, text="¡Hasta pronto! Estamos acá cuando lo necesites. 🙏")
        return

    # ── Cancelar suscripción: confirmación ──
    if button_id == "int_cancelar_confirm":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
            sub.activo = False
            sub.save()
            send_text_message(
                to=from_number,
                text=(
                    "Tu suscripción fue cancelada. ✅\n\n"
                    "Podés volver a activarla cuando quieras escribiéndonos. "
                    "¡Gracias por haber sido parte de Intencionate! 🙏"
                ),
            )
        except Intencionate.DoesNotExist:
            send_text_message(to=from_number, text="No encontramos tu suscripción.")
        clear_session(from_number)
        return

    if button_id == "int_cancelar_abort":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
        except Intencionate.DoesNotExist:
            send_welcome_intencionate(from_number)
            return
        show_estado_suscripcion(from_number, sub, session)
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

    # ── Profundizar integración ──
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


# ── File handler ─────────────────────────────────────────────

def handle_file(from_number, session):
    if not session:
        return

    step = session.get("step")

    # ── Comprobante nueva suscripción ──
    if step == "int_awaiting_comprobante":
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

    # ── Comprobante pago de renovación ──
    if step == "int_awaiting_comprobante_abonar":
        try:
            sub = Intencionate.objects.get(telefono=from_number)
            sub.activo = True
            sub.fecha_pago = datetime.now()
            sub.save()
            send_text_message(
                to=from_number,
                text=(
                    "✅ ¡Pago registrado! Tu suscripción sigue activa.\n\n"
                    f"🌿 Plan: {sub.tipo_plan.capitalize()}\n"
                    "¡Gracias por continuar con Intencionate! 🙏"
                ),
            )
        except Intencionate.DoesNotExist:
            send_text_message(to=from_number, text="No encontramos tu suscripción.")
        clear_session(from_number)
        return

    # ── Comprobante cambio de plan ──
    if step == "int_awaiting_comprobante_cambio_plan":
        nuevo_plan = session.get("int_nuevo_plan", "basico")
        try:
            sub = Intencionate.objects.get(telefono=from_number)
            sub.tipo_plan = nuevo_plan
            sub.activo = True
            sub.fecha_pago = datetime.now()
            sub.save()
            send_text_message(
                to=from_number,
                text=(
                    f"✅ ¡Plan actualizado a {nuevo_plan.capitalize()}!\n\n"
                    "Tu suscripción sigue activa con el nuevo plan. 🙏"
                ),
            )
        except Intencionate.DoesNotExist:
            send_text_message(to=from_number, text="No encontramos tu suscripción.")
        clear_session(from_number)
        return


# ── Pantallas de bienvenida ───────────────────────────────────

def send_welcome_suscripto(from_number):
    """Menú principal para usuarios con suscripción activa."""
    set_session(from_number, {"bot": "intencionate", "step": "int_menu"})
    send_text_message(
        to=from_number,
        text=(
            "Hola ✨ Bienvenido/a a INTENCIONATE\n\n"
            "Sistema de sincronización personal\n\n"
            "Antes de avanzar, frená un segundo.\n\n"
            "Entrá en vos.\n"
            "Respirá.\n\n"
            "(Inhalá por nariz… exhalá por boca… 3 veces)\n\n"
            "Ahora sí.\n\n"
            "Contame, ¿qué te gustaría intencionar hoy?"
        ),
    )
    send_interactive_buttons(
        to=from_number,
        body_text="Estoy para acompañarte.",
        buttons=[
            {"id": "int_menu_experiencia", "title": "Intencionar experiencia"},
            {"id": "int_menu_masaje",      "title": "Reservar masaje"},
            {"id": "int_menu_suscripcion", "title": "Mi suscripción"},
        ],
    )


def send_welcome_intencionate(from_number):
    """Bienvenida para usuarios sin suscripción activa."""
    prices = get_int_prices()
    set_session(from_number, {"bot": "intencionate", "step": "int_welcome"})
    send_interactive_buttons(
        to=from_number,
        body_text=(
            "✨ *Bienvenido/a a Intencionate* ✨\n\n"
            "Intencionate es un servicio de acompañamiento espiritual diario "
            "que te ayuda a conectar con tus emociones y transformar tu día a día.\n\n"
            f"🌱 *Básico* - ${prices['basico']:,}/mes\n"
            f"   → 1 experiencia diaria\n"
            f"🌿 *Intermedio* - ${prices['intermedio']:,}/mes\n"
            f"   → 3 experiencias diarias\n"
            f"🌳 *Premium* - ${prices['premium']:,}/mes\n"
            f"   → 5 experiencias diarias\n\n"
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


def show_estado_suscripcion(from_number, sub, session):
    """Muestra el estado de la suscripción con opciones de acción."""
    estado = "✅ Activa" if sub.activo else "❌ Inactiva"
    ultimo_pago = sub.fecha_pago.strftime("%d/%m/%Y") if sub.fecha_pago else "—"
    proximo_pago = (
        (sub.fecha_pago + timedelta(days=30)).strftime("%d/%m/%Y")
        if sub.fecha_pago else "—"
    )

    session["step"] = "int_menu_estado"
    set_session(from_number, session)

    send_interactive_buttons(
        to=from_number,
        body_text=(
            f"📋 *Tu suscripción*\n\n"
            f"Estado: {estado}\n"
            f"Plan: {sub.tipo_plan.capitalize()}\n"
            f"Último pago: {ultimo_pago}\n"
            f"Próximo pago: {proximo_pago}"
        ),
        buttons=[
            {"id": "int_abonar",       "title": "Abonar suscripción"},
            {"id": "int_cambiar_plan", "title": "Cambiar plan"},
            {"id": "int_finalizar",    "title": "Finalizar"},
        ],
    )


# ── Mensajes programados ──────────────────────────────────────

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
