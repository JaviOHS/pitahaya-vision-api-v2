import os
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate, post_save
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


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        from .models import Profile
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=get_user_model())
def save_password_history(sender, instance, created, **kwargs):
    if created and instance.password:
        from .models import PasswordHistory
        PasswordHistory.objects.get_or_create(user=instance, password_hash=instance.password)
