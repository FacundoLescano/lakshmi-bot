from rest_framework import viewsets

from chatbot.models import HorarioNoDisponible, Intencionate, Memoria, Precio, Reserva

from .serializers import (
    HorarioNoDisponibleSerializer,
    IntencionateSerializer,
    MemoriaSerializer,
    PrecioSerializer,
    ReservaSerializer,
)


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("-horario")
    serializer_class = ReservaSerializer


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
