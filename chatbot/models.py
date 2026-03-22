from django.db import models


class Reserva(models.Model):
    MASAJE_CHOICES = [
        ("relajante", "Relajante"),
        ("descontracturante", "Descontracturante"),
        ("piedras_calientes", "Piedras calientes"),
    ]

    nombre = models.CharField(max_length=200)
    es_pareja = models.BooleanField(default=False)
    tipo_masaje = models.CharField(max_length=30, choices=MASAJE_CHOICES)
    horario = models.DateTimeField()

    def __str__(self):
        return f"{self.nombre} - {self.tipo_masaje} ({self.horario})"
