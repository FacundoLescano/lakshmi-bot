import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)


def _get_client():
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", None),
    )


def _get_model():
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def generate_daily_message(user_info: dict, memories: list[str]) -> str:
    system = (
        "Eres un guía espiritual llamado Intencionate. Tu rol es enviar un mensaje "
        "motivador/inspirador diario personalizado para el usuario. "
        "El mensaje debe ser breve (2-3 oraciones), intrigante y que invite a la reflexión. "
        "Usá un tono cálido, cercano y profundo.\n\n"
        f"Información del usuario:\n"
        f"- Nombre: {user_info.get('nombre', 'desconocido')}\n"
        f"- Lugar de nacimiento: {user_info.get('lugar_nacimiento', 'desconocido')}\n"
        f"- Fecha de nacimiento: {user_info.get('fecha_nacimiento', 'desconocido')}\n\n"
    )

    if memories:
        system += "Últimas interacciones del usuario:\n"
        for m in memories:
            system += f"- {m}\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Generá el mensaje motivador del día."},
            ],
            max_tokens=200,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate daily message")
        return "Hoy es un buen día para conectar con vos mismo. ¿Qué te dice tu interior?"


def deepen_message(original_message: str, user_info: dict, memories: list[str]) -> str:
    system = (
        "Eres un guía espiritual llamado Intencionate. El usuario quiere profundizar "
        "sobre un mensaje que le enviaste. Expandí el contenido con mayor profundidad, "
        "herramientas prácticas o reflexiones más detalladas. "
        "Usá un tono cálido, cercano y profundo. Máximo 4-5 oraciones.\n\n"
        f"Información del usuario:\n"
        f"- Nombre: {user_info.get('nombre', 'desconocido')}\n"
        f"- Lugar de nacimiento: {user_info.get('lugar_nacimiento', 'desconocido')}\n"
        f"- Fecha de nacimiento: {user_info.get('fecha_nacimiento', 'desconocido')}\n\n"
    )

    if memories:
        system += "Últimas interacciones del usuario:\n"
        for m in memories:
            system += f"- {m}\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Profundizá sobre este mensaje:\n\n{original_message}"},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to deepen message")
        return "Tomate un momento para respirar profundo y sentir qué necesita tu cuerpo hoy."


def chat_response(user_message: str, user_info: dict, memories: list[str]) -> str:
    system = (
        "Eres un guía espiritual llamado Intencionate. Tu rol es acompañar al usuario "
        "en su proceso emocional y espiritual. Respondé de forma empática, cálida y "
        "profunda. Usá un tono cercano. Máximo 3-4 oraciones.\n\n"
        f"Información del usuario:\n"
        f"- Nombre: {user_info.get('nombre', 'desconocido')}\n"
        f"- Lugar de nacimiento: {user_info.get('lugar_nacimiento', 'desconocido')}\n"
        f"- Fecha de nacimiento: {user_info.get('fecha_nacimiento', 'desconocido')}\n\n"
    )

    if memories:
        system += "Últimas interacciones del usuario:\n"
        for m in memories:
            system += f"- {m}\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate chat response")
        return "Gracias por compartir. Tomate un momento para respirar y conectar con lo que sentís."


def generate_integration_message(user_info: dict, memories: list[str]) -> str:
    system = (
        "Eres un guía espiritual llamado Intencionate. Es el final del día y debés "
        "enviar un mensaje de agradecimiento y cierre del día al usuario. "
        "Debe ser breve (2-3 oraciones), reflexivo y que invite a integrar las "
        "experiencias del día. Usá un tono cálido y profundo.\n\n"
        f"Información del usuario:\n"
        f"- Nombre: {user_info.get('nombre', 'desconocido')}\n"
        f"- Lugar de nacimiento: {user_info.get('lugar_nacimiento', 'desconocido')}\n"
        f"- Fecha de nacimiento: {user_info.get('fecha_nacimiento', 'desconocido')}\n\n"
    )

    if memories:
        system += "Últimas interacciones del usuario:\n"
        for m in memories:
            system += f"- {m}\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Generá el mensaje de integración/agradecimiento de cierre del día."},
            ],
            max_tokens=200,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate integration message")
        return "Gracias por este día. Descansá sabiendo que cada paso cuenta."
