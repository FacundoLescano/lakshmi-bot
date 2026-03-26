from rest_framework import serializers

from chatbot.models import Intencionate, Memoria, Reserva


class ReservaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reserva
        fields = "__all__"


class MemoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Memoria
        fields = "__all__"


class IntencionateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intencionate
        fields = "__all__"
