from rest_framework import serializers

from chatbot.models import Memoria, Reserva


class ReservaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reserva
        fields = "__all__"


class MemoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Memoria
        fields = "__all__"
