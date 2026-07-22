from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProfileView,
    ProfilePreferencesView,
    CustomerViewSet,
    CustomLoginView,
    CustomRegisterView,
    CustomPasswordResetView,
    delete_account_view,
    request_verification_email,
    confirm_verification_email,
    check_availability,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='rest_login'),
    path('password/reset/', CustomPasswordResetView.as_view(), name='rest_password_reset'),
    path('', include('dj_rest_auth.urls')),
    path('registration/', CustomRegisterView.as_view(), name='rest_register'),
    path('registration/', include('dj_rest_auth.registration.urls')),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/preferences/', ProfilePreferencesView.as_view(), name='profile-preferences'),
    path('account/delete/', delete_account_view, name='delete-account'),
    path('email/verify/request/', request_verification_email, name='verify-email-request'),
    path('email/verify/confirm/', confirm_verification_email, name='verify-email-confirm'),
    path('availability/', check_availability, name='check-availability'),
    path('', include(router.urls)),
]
