from rest_framework import viewsets

from chatbot.models import Intencionate, Memoria, Reserva

from .serializers import IntencionateSerializer, MemoriaSerializer, ReservaSerializer


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("-horario")
    serializer_class = ReservaSerializer


class MemoriaViewSet(viewsets.ModelViewSet):
    queryset = Memoria.objects.all().order_by("-id")
    serializer_class = MemoriaSerializer


class IntencionateViewSet(viewsets.ModelViewSet):
    queryset = Intencionate.objects.all().order_by("-date")
    serializer_class = IntencionateSerializer
