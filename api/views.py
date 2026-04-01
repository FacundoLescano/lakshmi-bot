from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from chatbot.models import BloqueHorario, Intencionate, Memoria, Precio, Reserva

from .serializers import (
    BloqueHorarioBulkSerializer,
    BloqueHorarioSerializer,
    IntencionateSerializer,
    MemoriaSerializer,
    PrecioSerializer,
    ReservaSerializer,
)


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


class BloqueHorarioViewSet(viewsets.ModelViewSet):
    queryset = BloqueHorario.objects.all()
    serializer_class = BloqueHorarioSerializer
    filterset_fields = ["fecha", "activo"]

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """
        Crear/actualizar múltiples bloques de un día.

        POST /api/bloques/bulk/
        {
            "fecha": "2026-04-01",
            "horas": [9, 10, 11, 14, 15, 16, 17, 18, 19, 20, 21, 22],
            "activo": true
        }

        Crea bloques para las horas indicadas. Si ya existen, actualiza el estado.
        Las horas del día NO incluidas se desactivan.
        """
        serializer = BloqueHorarioBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fecha = serializer.validated_data["fecha"]
        horas = serializer.validated_data["horas"]
        activo = serializer.validated_data["activo"]

        # Desactivar todas las horas del día que no están en la lista
        BloqueHorario.objects.filter(fecha=fecha).exclude(hora__in=horas).update(activo=False)

        # Crear o actualizar las horas indicadas
        created = 0
        updated = 0
        for hora in horas:
            obj, was_created = BloqueHorario.objects.update_or_create(
                fecha=fecha, hora=hora,
                defaults={"activo": activo},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return Response(
            {"fecha": str(fecha), "created": created, "updated": updated},
            status=status.HTTP_200_OK,
        )
