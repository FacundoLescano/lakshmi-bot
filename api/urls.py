from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IntencionateViewSet, MemoriaViewSet, ReservaViewSet

router = DefaultRouter()
router.register(r"reservas", ReservaViewSet)
router.register(r"memorias", MemoriaViewSet)
router.register(r"intencionate", IntencionateViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
