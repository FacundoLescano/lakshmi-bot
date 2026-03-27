from rest_framework import viewsets

from chatbot.models import Intencionate, Memoria, Precio, Reserva

from .serializers import IntencionateSerializer, MemoriaSerializer, PrecioSerializer, ReservaSerializer


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
