from rest_framework import serializers

from chatbot.models import BloqueHorario, Intencionate, Memoria, Precio, Reserva


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


class BloqueHorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = BloqueHorario
        fields = "__all__"


class BloqueHorarioBulkSerializer(serializers.Serializer):
    """Para crear/actualizar múltiples bloques de un día de golpe."""
    fecha = serializers.DateField()
    horas = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=23))
    activo = serializers.BooleanField(default=True)
