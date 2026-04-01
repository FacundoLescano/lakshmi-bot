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
    filterset_fields = ["fecha", "activo", "sucursal", "camilla", "hora"]

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """
        Crear/actualizar celdas de un día.

        POST /api/bloques/bulk/
        {
            "fecha": "2026-04-01",
            "celdas": [
                {"hora": 9, "sucursal": "sucursal_1", "camilla": 1},
                {"hora": 9, "sucursal": "sucursal_1", "camilla": 2},
                {"hora": 10, "sucursal": "sucursal_1", "camilla": 1}
            ]
        }

        Las celdas incluidas se activan. Las demás del día se desactivan.
        """
        serializer = BloqueHorarioBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fecha = serializer.validated_data["fecha"]
        celdas = serializer.validated_data["celdas"]

        # Desactivar todas las celdas del día
        BloqueHorario.objects.filter(fecha=fecha).update(activo=False)

        # Crear o activar las celdas indicadas
        created = 0
        updated = 0
        for celda in celdas:
            obj, was_created = BloqueHorario.objects.update_or_create(
                fecha=fecha,
                hora=celda["hora"],
                sucursal=celda["sucursal"],
                camilla=celda["camilla"],
                defaults={"activo": True},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return Response(
            {"fecha": str(fecha), "created": created, "updated": updated},
            status=status.HTTP_200_OK,
        )
