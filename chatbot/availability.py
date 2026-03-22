import logging
from datetime import timedelta

from .models import Reserva

logger = logging.getLogger(__name__)

OPENING_HOUR = 9
CLOSING_HOUR = 21

PRICES = {
    "relajante": 15000,
    "descontracturante": 18000,
    "piedras_calientes": 22000,
}


def is_available(dt):
    outside_hours = dt.hour < OPENING_HOUR or dt.hour >= CLOSING_HOUR
    has_reserva = Reserva.objects.filter(horario=dt).exists()
    logger.info(
        "is_available(%s) -> hour=%s, outside_hours=%s, has_reserva=%s",
        dt, dt.hour, outside_hours, has_reserva,
    )
    if outside_hours:
        return False
    return not has_reserva


def suggest_alternatives(dt):
    suggestions = []
    for offset in [-1, 1, -2, 2]:
        alt = dt + timedelta(hours=offset)
        if OPENING_HOUR <= alt.hour < CLOSING_HOUR and is_available(alt):
            suggestions.append(alt)
        if len(suggestions) == 2:
            break
    return suggestions
