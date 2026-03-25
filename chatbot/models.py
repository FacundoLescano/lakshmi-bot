import uuid

from django.db import models


SUCURSALES = [
    ("sucursal_1", "Sucursal 1"),
    ("sucursal_2", "Sucursal 2"),
    ("sucursal_3", "Sucursal 3"),
]

CAMILLAS_POR_SUCURSAL = 4

# All possible camillas: [(sucursal, camilla_number), ...]
ALL_CAMILLAS = [
    (suc_id, camilla)
    for suc_id, _ in SUCURSALES
    for camilla in range(1, CAMILLAS_POR_SUCURSAL + 1)
]


def generate_voucher_code():
    return uuid.uuid4().hex[:8].upper()


class Reserva(models.Model):
    DURACION_CHOICES = [
        (60, "60 minutos"),
        (90, "90 minutos"),
        (120, "120 minutos"),
    ]

    nombre = models.CharField(max_length=200)
    es_pareja = models.BooleanField(default=False)
    duracion = models.PositiveIntegerField(choices=DURACION_CHOICES, default=60)
    horario = models.DateTimeField(null=True, blank=True)
    sucursal = models.CharField(max_length=20, choices=SUCURSALES, blank=True, default="")
    camilla = models.PositiveSmallIntegerField(null=True, blank=True)
    voucher = models.CharField(max_length=20, null=True, blank=True, unique=True)
    es_regalo = models.BooleanField(default=False)
    telefono = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["horario", "sucursal", "camilla"],
                name="unique_camilla_por_horario",
                condition=models.Q(horario__isnull=False, sucursal__gt="", camilla__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.duracion}min ({self.horario}) [{self.sucursal} C{self.camilla}]"


class Memoria(models.Model):
    id_user = models.CharField(max_length=20)
    context = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.id_user}: {self.context[:50]}"
