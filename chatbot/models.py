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
    sucursal = models.CharField(max_length=20, choices=SUCURSALES, blank=True, default="")
    camilla = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["horario", "sucursal", "camilla"],
                name="unique_camilla_por_horario",
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.tipo_masaje} ({self.horario}) [{self.sucursal} C{self.camilla}]"
