from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RagDocumentViewSet, RagSearchView, RagStatusView

router = DefaultRouter()
router.register(r'documents', RagDocumentViewSet, basename='rag-document')

urlpatterns = [
    path('', include(router.urls)),
    path('status/', RagStatusView.as_view(), name='rag-status'),
    path('search/', RagSearchView.as_view(), name='rag-search'),
]
