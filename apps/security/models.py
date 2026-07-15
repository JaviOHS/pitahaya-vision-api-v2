from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .utils import dni_validator, phone_validator


class User(AbstractUser):
    dni = models.CharField(
        max_length=10,
        blank=True,
        default='',
        validators=[dni_validator],
    )
    phone = models.CharField(
        max_length=10,
        blank=True,
        default='',
        validators=[phone_validator],
    )
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name='Última IP')
    last_password_change = models.DateTimeField(blank=True, null=True, verbose_name='Último cambio de contraseña')
    account_locked_until = models.DateTimeField(blank=True, null=True, verbose_name='Bloqueado hasta')
    email_verified = models.BooleanField(default=False, verbose_name='Correo verificado')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['dni'],
                condition=~models.Q(dni=''),
                name='unique_dni_when_set',
            ),
            models.UniqueConstraint(
                fields=['phone'],
                condition=~models.Q(phone=''),
                name='unique_phone_when_set',
            ),
        ]

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        return self.get_full_name().strip() or self.username

    def set_password(self, raw_password):
        if self.pk:
            old_hash = User.objects.filter(pk=self.pk).values_list('password', flat=True).first()
            if old_hash:
                from .models import PasswordHistory
                PasswordHistory.objects.get_or_create(user=self, password_hash=old_hash)
        super().set_password(raw_password)
        self.last_password_change = timezone.now()

    def is_locked(self):
        if self.account_locked_until and timezone.now() < self.account_locked_until:
            return True
        if self.account_locked_until and timezone.now() >= self.account_locked_until:
            self.account_locked_until = None
            self.save(update_fields=['account_locked_until'])
        return False


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Usuario',
    )
    notifications_enabled = models.BooleanField(default=True, verbose_name='Notificaciones activadas')
    NOTIFY_SEVERITY_CHOICES = [
        ('ninguna', 'Ninguna'),
        ('baja', 'Baja'),
        ('moderada', 'Moderada'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
        ('todas', 'Todas'),
    ]
    notify_severity_threshold = models.CharField(
        max_length=10,
        choices=NOTIFY_SEVERITY_CHOICES,
        default='todas',
        verbose_name='Severidad mínima para notificar por correo',
    )
    preferences = models.JSONField(default=dict, blank=True, verbose_name='Preferencias adicionales')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def __str__(self):
        return f'Perfil de {self.user.username}'


class LoginAttempt(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='login_attempts',
        verbose_name='Usuario',
    )
    username = models.CharField(max_length=150, db_index=True, verbose_name='Usuario intentado')
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name='Dirección IP')
    user_agent = models.TextField(blank=True, default='', verbose_name='User-Agent')
    successful = models.BooleanField(default=False, verbose_name='Exitoso')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Fecha y hora')

    class Meta:
        verbose_name = 'Intento de inicio de sesión'
        verbose_name_plural = 'Intentos de inicio de sesión'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.username} - {"OK" if self.successful else "FAIL"} - {self.timestamp}'


class PasswordHistory(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_history',
        verbose_name='Usuario',
    )
    password_hash = models.CharField(max_length=255, verbose_name='Hash de contraseña')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')

    class Meta:
        verbose_name = 'Historial de contraseña'
        verbose_name_plural = 'Historial de contraseñas'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.created_at}'
