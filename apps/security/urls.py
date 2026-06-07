from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProfileView,
    CustomerViewSet,
    CustomRegisterView,
    delete_account_view,
    request_verification_email,
    confirm_verification_email,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)

urlpatterns = [
    path('', include('dj_rest_auth.urls')),
    path('registration/', CustomRegisterView.as_view(), name='rest_register'),
    path('registration/', include('dj_rest_auth.registration.urls')),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('account/delete/', delete_account_view, name='delete-account'),
    path('email/verify/request/', request_verification_email, name='verify-email-request'),
    path('email/verify/confirm/', confirm_verification_email, name='verify-email-confirm'),
    path('', include(router.urls)),
]
