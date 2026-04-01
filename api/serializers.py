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


class CeldaSerializer(serializers.Serializer):
    hora = serializers.IntegerField(min_value=0, max_value=23)
    sucursal = serializers.ChoiceField(choices=BloqueHorario.sucursal.field.choices)
    camilla = serializers.IntegerField(min_value=1)


class BloqueHorarioBulkSerializer(serializers.Serializer):
    """
    Crear/actualizar múltiples celdas de un día.
    Las celdas incluidas se activan; las demás del día se desactivan.
    """
    fecha = serializers.DateField()
    celdas = CeldaSerializer(many=True)
