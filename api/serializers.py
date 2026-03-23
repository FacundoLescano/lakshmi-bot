from rest_framework import serializers

from chatbot.models import Reserva


class ReservaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reserva
        fields = "__all__"
