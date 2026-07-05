from rest_framework import permissions


def is_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def get_admin_users():
    """Todos los usuarios con rol de administrador (is_staff o is_superuser)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    User = get_user_model()
    return User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))


class IsAdmin(permissions.BasePermission):
    """Permite acceso solo a administradores (is_staff o is_superuser)."""

    message = 'No tienes permisos de administrador.'

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(permissions.BasePermission):
    """Lectura para usuarios autenticados; escritura solo para administradores."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return is_admin(request.user)
