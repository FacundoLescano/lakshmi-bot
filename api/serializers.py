from rest_framework import serializers

from chatbot.models import Intencionate, Memoria, Precio, Reserva


class MemoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Memoria
        fields = "__all__"


class ReservaSerializer(serializers.ModelSerializer):
    memorias = MemoriaSerializer(many=True, read_only=True)

    class Meta:
        model = Reserva
        fields = "__all__"


class IntencionateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intencionate
        fields = "__all__"


class PrecioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Precio
        fields = "__all__"
