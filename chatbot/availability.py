import logging
import random
from datetime import timedelta

from .models import ALL_CAMILLAS, Reserva

logger = logging.getLogger(__name__)

OPENING_HOUR = 9
CLOSING_HOUR = 21

# Total camillas across all branches
TOTAL_CAMILLAS = len(ALL_CAMILLAS)

PRICES = {
    "relajante": 15000,
    "descontracturante": 18000,
    "piedras_calientes": 22000,
}


def get_occupied_camillas(dt):
    """Return set of (sucursal, camilla) occupied at datetime dt."""
    reservas = Reserva.objects.filter(horario=dt).values_list("sucursal", "camilla")
    return set(reservas)


def get_free_camillas(dt):
    """Return list of (sucursal, camilla) available at datetime dt."""
    occupied = get_occupied_camillas(dt)
    return [c for c in ALL_CAMILLAS if c not in occupied]


def is_available(dt):
    """Check if there's at least one free camilla at dt."""
    outside_hours = dt.hour < OPENING_HOUR or dt.hour >= CLOSING_HOUR

    if outside_hours:
        logger.info("is_available(%s) -> hour=%s, outside business hours", dt, dt.hour)
        return False

    free = get_free_camillas(dt)
    logger.info(
        "is_available(%s) -> hour=%s, free_camillas=%d/%d",
        dt, dt.hour, len(free), TOTAL_CAMILLAS,
    )
    return len(free) > 0


def assign_camilla(dt, count=1):
    """
    Assign `count` random free camillas for datetime dt.
    Returns list of (sucursal, camilla) tuples.
    Raises ValueError if not enough camillas available.
    """
    free = get_free_camillas(dt)
    if len(free) < count:
        raise ValueError(
            f"Not enough camillas: need {count}, only {len(free)} free at {dt}"
        )
    return random.sample(free, count)


def suggest_alternatives(dt):
    suggestions = []
    for offset in [-1, 1, -2, 2]:
        alt = dt + timedelta(hours=offset)
        if OPENING_HOUR <= alt.hour < CLOSING_HOUR and is_available(alt):
            suggestions.append(alt)
        if len(suggestions) == 2:
            break
    return suggestions
