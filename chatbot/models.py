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
    id_user = models.CharField(max_length=20, db_index=True)
    context = models.CharField(max_length=200)
    reserva = models.ForeignKey(
        Reserva, on_delete=models.SET_NULL, null=True, blank=True, related_name="memorias",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id_user}: {self.context[:50]}"


class Intencionate(models.Model):
    PLAN_CHOICES = [
        ("basico", "Básico"),
        ("intermedio", "Intermedio"),
        ("premium", "Premium"),
    ]

    nombre = models.CharField(max_length=200)
    lugar_nacimiento = models.CharField(max_length=200, blank=True, default="")
    fecha_nacimiento = models.CharField(max_length=50, blank=True, default="")
    date = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=False)
    fecha_pago = models.DateTimeField(null=True, blank=True)
    tipo_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, blank=True, default="")
    hora_integrar = models.CharField(max_length=10, blank=True, default="")
    satisfaccion_cliente = models.CharField(max_length=50, blank=True, default="")
    telefono = models.CharField(max_length=20, unique=True, db_index=True)

    def __str__(self):
        return f"{self.nombre} ({self.telefono}) - {self.tipo_plan}"



class HorarioNoDisponible(models.Model):
    fecha_hora = models.DateTimeField()
    sucursal = models.CharField(
        max_length=20,
        choices=SUCURSALES,
        null=True,
        blank=True,
    )
    camilla = models.PositiveSmallIntegerField(null=True, blank=True)
    motivo = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("fecha_hora", "sucursal", "camilla")]
        ordering = ["fecha_hora"]

    def __str__(self):
        suc = self.sucursal or "todas las sucursales"
        cam = f" C{self.camilla}" if self.camilla else ""
        return f"Bloqueado: {self.fecha_hora} — {suc}{cam}"


class ConfiguracionSistema(models.Model):
    clave = models.CharField(max_length=50, unique=True)
    valor = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.clave}: {self.valor}"

    @classmethod
    def get(cls, clave, default=""):
        try:
            return cls.objects.get(clave=clave).valor
        except cls.DoesNotExist:
            return default


class Precio(models.Model):
    duracion = models.PositiveIntegerField(unique=True)
    precio = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.duracion} min → ${self.precio:,}"

    @classmethod
    def get_prices(cls):
        """Returns a dict {duracion: precio}. Falls back to defaults if table is empty."""
        precios = dict(cls.objects.values_list("duracion", "precio"))
        if not precios:
            return {60: 50000, 90: 65000, 120: 80000}
        return precios
