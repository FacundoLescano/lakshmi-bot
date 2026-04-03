from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    HorarioNoDisponibleViewSet,
    IntencionateViewSet,
    MemoriaViewSet,
    PrecioViewSet,
    ReservaViewSet,
)

router = DefaultRouter()
router.register(r"reservas", ReservaViewSet)
router.register(r"memorias", MemoriaViewSet)
router.register(r"intencionate", IntencionateViewSet)
router.register(r"precios", PrecioViewSet)
router.register(r"horarios-no-disponibles", HorarioNoDisponibleViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
