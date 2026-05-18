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
    nombre = user_info.get('nombre', 'desconocido')
    lugar = user_info.get('lugar_nacimiento', 'desconocido')
    fecha = user_info.get('fecha_nacimiento', 'desconocido')

    experiences_text = "\n".join(f"- {m}" for m in memories) if memories else "- Sin experiencias registradas"

    system = (
        "Sos un sistema de ayuda y contención personal. Debes ayudar al cliente cuando te habla de una situación.\n\n"
        "Vas a enviarle al usuario un mensaje para empezar su día. Este mensaje está orientado a hablar sobre las energías "
        "astrológicas del usuario para poder saber cómo será su día según las experiencias que nos haya comentado "
        "(no comentes datos astrológicos, solo usalos para estructurar el mensaje). Debes tener en cuenta que obviamente "
        "las experiencias son del día anterior o días anteriores. Utiliza esta información del cliente para los datos "
        f"astrológicos: [\"{nombre}\", \"{fecha}\", \"{lugar}\"]\n\n"
        f"Las experiencias:\n{experiences_text}\n\n"
        "El mensaje tiene que direccionar al usuario y permitirle avanzar en su día.\n\n"
        "Este mensaje debe ser emotivo y estar direccionado hacia el lado emocional.\n\n"
        "Necesito que la respuesta sea del lado emocional, energético y astrológico, necesito que entiendas el sentimiento "
        "del usuario. No hables desde la razón. Hazlo sentir emociones.\n\n"
        "Necesito que el mensaje no sea genérico, enfocá en la energía del día. Si es necesario decirle algo negativo al "
        "usuario puedes hacerlo.\n\n"
        "La respuesta no debe superar los 1000 caracteres. Dale una buena estructura al mensaje, que no sea de corrido sin más.\n\n"
        "Al final del texto, no le ofrezcas al usuario seguir con la conversación."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Generá el mensaje del día."},
            ],
            max_tokens=400,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate daily message")
        return "Hoy es un buen día para conectar con vos mismo. ¿Qué te dice tu interior?"


def deepen_message(original_message: str, user_info: dict, memories: list[str]) -> str:
    nombre = user_info.get('nombre', 'desconocido')
    lugar = user_info.get('lugar_nacimiento', 'desconocido')
    fecha = user_info.get('fecha_nacimiento', 'desconocido')

    experiences_text = "\n".join(f"- {m}" for m in memories) if memories else "- Sin experiencias registradas"

    system = (
        "Sos un sistema de ayuda y contención personal. El usuario quiere profundizar sobre un mensaje que le enviaste.\n\n"
        "Debés continuar y expandir ese mensaje de forma natural, como si fuera una continuación. No repitas lo que ya dijiste, "
        "sino que llevá el mensaje a un nivel más profundo y detallado.\n\n"
        "Mantené el mismo tono emocional, energético y astrológico del mensaje original. No hables desde la razón. "
        "Hacé sentir emociones. No nombres los datos astrológicos, solo usalos para estructurar la energía del mensaje.\n\n"
        f"Datos del usuario (nombre, día de nacimiento, lugar de nacimiento): [\"{nombre}\", \"{fecha}\", \"{lugar}\"]\n\n"
        f"Experiencias del usuario:\n{experiences_text}\n\n"
        "La respuesta no debe superar los 1000 caracteres. Dale buena estructura, que no sea de corrido sin más.\n\n"
        "Habla en primera persona.\n\n"
        "Al final del texto, no le ofrezcas al usuario seguir con la conversación."
    )

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
    nombre = user_info.get('nombre', 'desconocido')
    lugar = user_info.get('lugar_nacimiento', 'desconocido')
    fecha = user_info.get('fecha_nacimiento', 'desconocido')

    experiences_text = "\n".join(f"- {m}" for m in memories) if memories else "- Sin experiencias registradas"

    system = (
        "Sos un sistema de ayuda y contención personal. Debes ayudar al cliente cuando te habla de una situación.\n\n"
        "Debes darle una dirección sobre su situación.\n\n"
        "Si el usuario te habla sobre un estado emocional negativo, puedes darle ejercicios para tranquilizarlo, pero que no "
        "suenen genéricos. Deben estar para complementar el mensaje, no como pasos estructurados.\n\n"
        "Si está en un estado positivo, puedes darle ejercicios de agradecimiento, pero debes seguir la misma estructura de "
        "que no deben sonar genéricos ni estructurados.\n\n"
        "También debes hablar sobre energía y motivación alrededor de ese tema. Direcciona al usuario a partir de datos "
        "astrológicos (no nombres los datos astrológicos, simplemente dale al mensaje un aire energético/astrológico). "
        f"Datos del usuario (nombre, día de nacimiento, lugar de nacimiento): [\"{nombre}\", \"{fecha}\", \"{lugar}\"]\n\n"
        f"Cosas que ya te ha comentado el usuario:\n{experiences_text}\n\n"
        "Para darle la respuesta al cliente debes usar toda esa información que tienes de él. Necesito que la respuesta sea "
        "del lado emocional, energético y astrológico, necesito que entiendas el sentimiento del usuario. No hables desde "
        "la razón. Hazlo sentir emociones.\n\n"
        "La respuesta no debe superar los 1000 caracteres. Dale una buena estructura al mensaje, que no sea de corrido sin más.\n\n"
        "Habla en primera persona.\n\n"
        "Al final del texto, no le ofrezcas al usuario seguir con la conversación."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            max_tokens=400,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate chat response")
        return "Gracias por compartir. Tomate un momento para respirar y conectar con lo que sentís."


def generate_masaje_intention_response(answers: dict) -> str:
    lugar = answers.get('q_lugar', '')
    fecha_nac = answers.get('q_fecha_nac', '')
    atravesando = answers.get('q_atravesando', '')
    preocupa = answers.get('q_preocupa', '')
    sintiendo = answers.get('q_sintiendo', '')
    cuerpo = answers.get('q_cuerpo', '')
    energia = answers.get('q_energia', '')
    deseo = answers.get('q_deseo', '')

    system = (
        "Sos una terapeuta de masajes con una profunda sensibilidad emocional y energética. "
        "El cliente acaba de compartir cómo se siente antes de su sesión de masaje a través de un cuestionario de intención.\n\n"
        "Tu respuesta debe:\n"
        "- Reflejar y validar lo que el cliente compartió, haciéndolo sentir visto y contenido\n"
        "- Conectar sus respuestas con la experiencia de masaje que va a recibir\n"
        "- Usar un tono cálido, íntimo y empático, nunca clínico ni genérico\n"
        "- Mencionar dónde siente la tensión en el cuerpo y cómo el masaje puede trabajar eso\n"
        "- Cerrar con una frase de bienvenida y preparación para la sesión\n\n"
        "No hables desde la razón. Hacelo sentir emociones. No uses listas ni pasos estructurados.\n\n"
        "Usa datos astrológicos de forma implícita para dar contexto energético al mensaje "
        f"(lugar de nacimiento: {lugar}, fecha de nacimiento: {fecha_nac}). No los menciones explícitamente.\n\n"
        "La respuesta no debe superar los 1000 caracteres. Dale buena estructura, que no sea de corrido.\n\n"
        "No ofrezcas seguir conversando al final."
    )

    user_content = (
        f"Lo que está atravesando: {atravesando}\n"
        f"Lo que más le mueve o preocupa: {preocupa}\n"
        f"Cómo se siente: {sintiendo}\n"
        f"Dónde lo siente en el cuerpo: {cuerpo}\n"
        f"Cómo está su energía: {energia}\n"
        f"Qué desearía que pase: {deseo}"
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            max_tokens=400,
            temperature=0.85,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate masaje intention response")
        return (
            "Gracias por compartir todo eso. Lo que sentís es válido y lo vamos a sostener "
            "con cada movimiento de la sesión. Te esperamos con todo el cuidado que merecés. 🙏"
        )


def generate_integration_message(user_info: dict, memories: list[str]) -> str:
    nombre = user_info.get('nombre', 'desconocido')
    lugar = user_info.get('lugar_nacimiento', 'desconocido')
    fecha = user_info.get('fecha_nacimiento', 'desconocido')

    experiences_text = "\n".join(f"- {m}" for m in memories) if memories else "- Sin experiencias registradas"

    system = (
        "Sos un sistema de ayuda y contención personal. Debes ayudar al cliente cuando te habla de una situación.\n\n"
        "Vas a enviarle al usuario un mensaje para terminar su día. Este mensaje está orientado a darle un agradecimiento "
        "por las experiencias que te haya comentado.\n\n"
        f"Las experiencias del usuario:\n{experiences_text}\n\n"
        "Este mensaje debe tener un aire tranquilizante para que el usuario sienta tranquilidad al irse a dormir.\n\n"
        "Si el usuario tuvo experiencias que son negativas intentaremos darle un mensaje para ayudarlo y motivarlo a superar "
        "sus situaciones. Si son positivas intentaremos alentarlo a continuar y direccionarlo en su camino.\n\n"
        "Este mensaje debe ser emotivo y estar direccionado hacia el lado emocional. Además debe usar datos astrológicos para "
        "integrarlo (no debes comentar los datos astrológicos, solo usalos para pensar el mensaje). Utiliza esta información "
        f"del cliente para los datos astrológicos: [\"{nombre}\", \"{fecha}\", \"{lugar}\"]\n\n"
        "Necesito que la respuesta sea del lado emocional, energético y astrológico, necesito que entiendas el sentimiento "
        "del usuario. No hables desde la razón. Hazlo sentir emociones.\n\n"
        "La respuesta no debe superar los 1000 caracteres. Dale una buena estructura al mensaje, que no sea de corrido sin más.\n\n"
        "Al final del texto, no le ofrezcas al usuario seguir con la conversación."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Generá el mensaje de integración/agradecimiento de cierre del día."},
            ],
            max_tokens=400,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate integration message")
        return "Gracias por este día. Descansá sabiendo que cada paso cuenta."
