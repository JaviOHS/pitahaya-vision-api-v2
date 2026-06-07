from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


dni_validator = RegexValidator(
    regex=r'^\d{10}$',
    message='La cédula debe tener exactamente 10 dígitos.',
)

phone_validator = RegexValidator(
    regex=r'^0\d{9}$',
    message='El teléfono debe tener 10 dígitos y comenzar con 0.',
)


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
