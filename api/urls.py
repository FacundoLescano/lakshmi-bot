from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IntencionateViewSet, MemoriaViewSet, PrecioViewSet, ReservaViewSet

router = DefaultRouter()
router.register(r"reservas", ReservaViewSet)
router.register(r"memorias", MemoriaViewSet)
router.register(r"intencionate", IntencionateViewSet)
router.register(r"precios", PrecioViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
