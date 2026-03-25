from rest_framework import viewsets

from chatbot.models import Memoria, Reserva

from .serializers import MemoriaSerializer, ReservaSerializer


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("-horario")
    serializer_class = ReservaSerializer


class MemoriaViewSet(viewsets.ModelViewSet):
    queryset = Memoria.objects.all().order_by("-id")
    serializer_class = MemoriaSerializer
