from datetime import timedelta

from .models import Reserva

MASSAGE_DURATION = timedelta(hours=1)

OPENING_HOUR = 9
CLOSING_HOUR = 21

PRICES = {
    "relajante": 15000,
    "descontracturante": 18000,
    "piedras_calientes": 22000,
}


def is_available(dt):
    if dt.hour < OPENING_HOUR or dt.hour >= CLOSING_HOUR:
        return False
    return not Reserva.objects.filter(horario=dt).exists()


def suggest_alternatives(dt):
    suggestions = []
    for offset in [-1, 1, -2, 2]:
        alt = dt + timedelta(hours=offset)
        if OPENING_HOUR <= alt.hour < CLOSING_HOUR and is_available(alt):
            suggestions.append(alt)
        if len(suggestions) == 2:
            break
    return suggestions
