from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from chatbot.models import HorarioNoDisponible, Intencionate, Memoria, Precio, Reserva

from .serializers import (
    HorarioNoDisponibleSerializer,
    IntencionateSerializer,
    MemoriaSerializer,
    PrecioSerializer,
    ReservaSerializer,
)


PREFIJO_CAMPO = {
    "[lugar]": "lugar_nacimiento",
    "[fecha_nac]": "fecha_nacimiento",
}

QUESTION_KEYS_ORDER = [
    "q_atravesando",
    "q_preocupa",
    "q_sintiendo",
    "q_cuerpo",
    "q_energia",
    "q_deseo",
]

QUESTION_KEY_LABEL = {
    "q_atravesando": "atravesando",
    "q_preocupa": "preocupa",
    "q_sintiendo": "sintiendo",
    "q_cuerpo": "cuerpo",
    "q_energia": "energia",
    "q_deseo": "deseo",
}


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("-horario")
    serializer_class = ReservaSerializer

    @action(detail=True, methods=["get"], url_path="cuestionario")
    def cuestionario(self, request, pk=None):
        reserva = self.get_object()
        memorias = list(Memoria.objects.filter(reserva=reserva).order_by("id"))

        cuestionario = {}

        # Extraer lugar y fecha (con prefijo especial)
        for mem in memorias:
            for prefijo, campo in PREFIJO_CAMPO.items():
                if mem.context.startswith(prefijo):
                    cuestionario[campo] = mem.context[len(prefijo):].strip()

        # Si no están en esta reserva, buscar en memorias previas del mismo usuario
        if "lugar_nacimiento" not in cuestionario:
            m = Memoria.objects.filter(
                id_user=reserva.telefono, context__startswith="[lugar]"
            ).order_by("-id").first()
            if m:
                cuestionario["lugar_nacimiento"] = m.context[len("[lugar]"):].strip()

        if "fecha_nacimiento" not in cuestionario:
            m = Memoria.objects.filter(
                id_user=reserva.telefono, context__startswith="[fecha_nac]"
            ).order_by("-id").first()
            if m:
                cuestionario["fecha_nacimiento"] = m.context[len("[fecha_nac]"):].strip()

        # Fallback: buscar en Intencionate
        intencionate = Intencionate.objects.filter(telefono=reserva.telefono).first()
        if intencionate:
            if "lugar_nacimiento" not in cuestionario and intencionate.lugar_nacimiento:
                cuestionario["lugar_nacimiento"] = intencionate.lugar_nacimiento
            if "fecha_nacimiento" not in cuestionario and intencionate.fecha_nacimiento:
                cuestionario["fecha_nacimiento"] = intencionate.fecha_nacimiento

        # Extraer preguntas emocionales (sin prefijo, en orden de creación)
        emocionales = [
            m.context for m in memorias
            if not any(m.context.startswith(p) for p in PREFIJO_CAMPO)
        ]
        for i, label in enumerate(["atravesando", "preocupa", "sintiendo", "cuerpo", "energia", "deseo"]):
            if i < len(emocionales):
                cuestionario[label] = emocionales[i]

        return Response({
            "reserva_id": reserva.id,
            "nombre": reserva.nombre,
            "telefono": reserva.telefono,
            "horario": reserva.horario,
            "cuestionario": cuestionario,
        })


class MemoriaViewSet(viewsets.ModelViewSet):
    queryset = Memoria.objects.all().order_by("-id")
    serializer_class = MemoriaSerializer


class IntencionateViewSet(viewsets.ModelViewSet):
    queryset = Intencionate.objects.all().order_by("-date")
    serializer_class = IntencionateSerializer


class PrecioViewSet(viewsets.ModelViewSet):
    queryset = Precio.objects.all().order_by("duracion")
    serializer_class = PrecioSerializer


class HorarioNoDisponibleViewSet(viewsets.ModelViewSet):
    queryset = HorarioNoDisponible.objects.all()
    serializer_class = HorarioNoDisponibleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        fecha = self.request.query_params.get("fecha")
        if fecha:
            qs = qs.filter(fecha_hora__date=fecha)
        return qs
