import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un router de mensajes. Tu trabajo es clasificar el mensaje del usuario en UNA de estas categorías:

1. "lakshmi" — El usuario quiere hacer una reserva de masajes, tiene un voucher, quiere cambiar un horario, o habla de masajes/tratamientos corporales.
2. "intencionate" — El usuario habla de emociones, espiritualidad, bienestar emocional, conexión interior, intencionar, suscripción a intencionate, o algo relacionado a su estado emocional/espiritual.
3. "saludo" — El usuario saluda (hola, buenas, etc.) sin indicar claramente qué quiere.

Respondé SOLO con una de estas tres palabras: lakshmi, intencionate, saludo
No agregues explicaciones ni texto adicional."""


def route_message(text: str) -> str:
    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", None),
        )

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=10,
            temperature=0,
        )

        result = response.choices[0].message.content.strip().lower()
        logger.info("LLM router: '%s' -> %s", text[:50], result)

        if result in ("lakshmi", "intencionate", "saludo"):
            return result

        # Fallback: si no matchea exactamente, buscar la palabra
        for option in ("lakshmi", "intencionate", "saludo"):
            if option in result:
                return option

        return "saludo"

    except Exception:
        logger.exception("LLM router failed, defaulting to saludo")
        return "saludo"
