import logging
import random
from datetime import timedelta

from .models import ALL_CAMILLAS, CAMILLAS_POR_SUCURSAL, SUCURSALES, Reserva

logger = logging.getLogger(__name__)

OPENING_HOUR = 9
CLOSING_HOUR = 21

TOTAL_CAMILLAS = len(ALL_CAMILLAS)

PRICES = {
    60: 50000,
    90: 65000,
    120: 80000,
}


def get_occupied_camillas(dt):
    reservas = Reserva.objects.filter(horario=dt).values_list("sucursal", "camilla")
    return set(reservas)


def get_free_camillas(dt):
    occupied = get_occupied_camillas(dt)
    return [c for c in ALL_CAMILLAS if c not in occupied]


def is_available(dt):
    if dt.hour < OPENING_HOUR or dt.hour >= CLOSING_HOUR:
        logger.info("is_available(%s) -> hour=%s, outside business hours", dt, dt.hour)
        return False

    free = get_free_camillas(dt)
    logger.info(
        "is_available(%s) -> hour=%s, free_camillas=%d/%d",
        dt, dt.hour, len(free), TOTAL_CAMILLAS,
    )
    return len(free) > 0


def get_consecutive_pairs(dt):
    free = set(get_free_camillas(dt))
    pairs = []
    for suc_id, _ in SUCURSALES:
        for cam in range(1, CAMILLAS_POR_SUCURSAL):
            a = (suc_id, cam)
            b = (suc_id, cam + 1)
            if a in free and b in free:
                pairs.append((a, b))
    return pairs


def assign_camilla(dt, pareja=False):
    if pareja:
        pairs = get_consecutive_pairs(dt)
        if not pairs:
            raise ValueError(f"No consecutive camilla pairs available at {dt}")
        pair = random.choice(pairs)
        return list(pair)

    free = get_free_camillas(dt)
    if not free:
        raise ValueError(f"No camillas free at {dt}")
    return [random.choice(free)]


def suggest_alternatives(dt, pareja=False):
    suggestions = []
    for offset in [-1, 1, -2, 2]:
        alt = dt + timedelta(hours=offset)
        if alt.hour < OPENING_HOUR or alt.hour >= CLOSING_HOUR:
            continue
        if pareja:
            if get_consecutive_pairs(alt):
                suggestions.append(alt)
        else:
            if is_available(alt):
                suggestions.append(alt)
        if len(suggestions) == 2:
            break
    return suggestions
