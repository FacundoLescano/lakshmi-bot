from rest_framework import viewsets

from chatbot.models import Reserva

from .serializers import ReservaSerializer


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("-horario")
    serializer_class = ReservaSerializer
