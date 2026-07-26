from apps.security.utils import notifications_enabled_for, send_notification_email
from apps.security.permissions import get_admin_users

SEVERITY_RANK = {
    'ninguna': 0, 'sana': 0, 'saludable': 0,
    'baja': 1, 'leve': 1,
    'moderada': 2, 'media': 2,
    'alta': 3, 'enferma': 3,
    'critica': 4, 'crítica': 4,
}

THRESHOLD_RANK = {'baja': 1, 'moderada': 2, 'alta': 3, 'critica': 4}

ADMIN_ALERT_MIN_RANK = THRESHOLD_RANK['alta']


def _should_notify_for_severity(threshold, severity):
    if threshold == 'ninguna':
        return False
    if threshold == 'todas':
        return True
    severity_rank = SEVERITY_RANK.get((severity or '').strip().lower(), -1)
    return severity_rank >= THRESHOLD_RANK.get(threshold, 999)


def _build_analysis_details(instance):
    details = []

    details.append({
        'label': 'Fecha del análisis',
        'value': instance.created_at.strftime('%d/%m/%Y %H:%M'),
    })

    if instance.latitude is not None and instance.longitude is not None:
        details.append({
            'label': 'Coordenadas GPS',
            'value': f'{instance.latitude:.6f}, {instance.longitude:.6f}',
            'url': f'https://www.google.com/maps?q={instance.latitude},{instance.longitude}',
        })

    plot = None
    conversation = getattr(instance, 'conversation', None)
    context = getattr(conversation, 'context', None) if conversation else None
    if context:
        plot = context.plot

    if plot:
        farm = plot.farm
        farm_value = farm.name + (f' — {farm.location}' if farm.location else '')
        details.append({'label': 'Finca', 'value': farm_value})

        plot_value = plot.name
        if plot.zone:
            plot_value += f' · Zona {plot.zone}'
        if plot.hectares:
            plot_value += f' · {plot.hectares} ha'
        details.append({'label': 'Parcela', 'value': plot_value})

        if plot.gps_location:
            details.append({'label': 'GPS de la parcela', 'value': plot.gps_location})

    return details


def notify_analysis_result(instance):
    """Envía un correo al dueño del análisis si su preferencia de
    notificaciones y su umbral de severidad (Configuraciones) lo permiten."""
    user = instance.user
    if not user or not notifications_enabled_for(user):
        return

    profile = getattr(user, 'profile', None)
    threshold = profile.notify_severity_threshold if profile else 'todas'
    if not _should_notify_for_severity(threshold, instance.severity):
        return

    disease = instance.disease_name_predicted or 'una posible afección'
    confidence_pct = instance.confidence * 100 if instance.confidence <= 1 else instance.confidence
    send_notification_email(
        user,
        subject='Nuevo análisis completado · Pitahaya Vision',
        heading='Nuevo análisis completado',
        message=f'Se detectó "{disease}" con severidad "{instance.severity}" (confianza {confidence_pct:.0f}%).',
        details=_build_analysis_details(instance),
    )


def notify_admins_of_critical_analysis(instance):
    """Alerta a los administradores cuando el análisis de CUALQUIER usuario
    resulta de severidad alta/crítica. Cada admin puede afinar o silenciar
    esta alerta con su propio umbral de severidad en Configuraciones — no
    depende de su propio historial de análisis, sino del de todo el sistema.
    """
    severity_rank = SEVERITY_RANK.get((instance.severity or '').strip().lower(), -1)
    if severity_rank < ADMIN_ALERT_MIN_RANK:
        return

    user = instance.user
    disease = instance.disease_name_predicted or 'una posible afección'
    confidence_pct = instance.confidence * 100 if instance.confidence <= 1 else instance.confidence
    reporter = (user.get_full_name() or user.username) if user else 'Usuario desconocido'

    details = [{'label': 'Reportado por', 'value': f'{reporter} ({user.email})' if user else 'Desconocido'}]
    details.extend(_build_analysis_details(instance))

    for admin in get_admin_users():
        if user and admin.pk == user.pk:
            continue
        if not notifications_enabled_for(admin):
            continue
        profile = getattr(admin, 'profile', None)
        threshold = profile.notify_severity_threshold if profile else 'todas'
        if not _should_notify_for_severity(threshold, instance.severity):
            continue
        send_notification_email(
            admin,
            subject='Análisis de severidad alta detectado · Pitahaya Vision',
            heading='Análisis crítico detectado',
            message=(
                f'Se detectó "{disease}" con severidad "{instance.severity}" '
                f'(confianza {confidence_pct:.0f}%) en la cuenta de un usuario.'
            ),
            details=details,
        )
