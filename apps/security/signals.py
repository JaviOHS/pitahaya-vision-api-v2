import os
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def create_superuser(sender, **kwargs):
    if sender.name != 'apps.security':
        return

    User = get_user_model()
    username = os.getenv('SUPERUSER_USERNAME', 'admin')
    email = os.getenv('SUPERUSER_EMAIL', 'admin@pitahaya.local')
    password = os.getenv('SUPERUSER_PASSWORD', 'Admin1234')

    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        print(f"[security] Superuser '{username}' creado.")
