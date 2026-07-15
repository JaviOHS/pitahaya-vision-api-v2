from rest_framework import serializers

from .permissions import is_admin
from .utils import _resolve_role, _resolve_role_label


class OwnerFilterMixin:
    """
    Para vistas DRF. Filtra el queryset automáticamente:
    - Admin ve todos los registros.
    - Usuario normal ve solo los que le pertenecen.

    Uso:
        class MiView(OwnerFilterMixin, generics.ListAPIView):
            owner_field = 'user'  # campo FK hacia el usuario
            ...
    """
    owner_field = 'user'

    def get_queryset(self):
        qs = super().get_queryset()
        if not is_admin(self.request.user):
            qs = qs.filter(**{self.owner_field: self.request.user})
        return qs


class CurrentUserCreateMixin:
    """
    Para ViewSets. Asigna automáticamente request.user
    al campo indicado al crear un objeto.

    Uso:
        class MiViewSet(CurrentUserCreateMixin, viewsets.ModelViewSet):
            user_field = 'user'
            ...
    """
    user_field = 'user'

    def perform_create(self, serializer):
        serializer.save(**{self.user_field: self.request.user})


class UserFieldMixin(serializers.Serializer):
    """
    Para serializers. Aporta campos calculados estándar del modelo User:
    full_name, profile_photo_url, role, role_label.
    Hereda de Serializer para que DRF registre los campos vía su metaclase.
    """
    full_name = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return obj.full_name

    def get_profile_photo_url(self, obj):
        if not obj.profile_photo:
            return ''
        request = self.context.get('request')
        url = obj.profile_photo.url
        return request.build_absolute_uri(url) if request else url

    def get_role(self, obj):
        return _resolve_role(obj)

    def get_role_label(self, obj):
        return _resolve_role_label(obj)
