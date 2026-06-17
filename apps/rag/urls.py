from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RagDocumentViewSet, RagChunkViewSet

router = DefaultRouter()
router.register(r'documents', RagDocumentViewSet, basename='rag-document')
router.register(r'chunks', RagChunkViewSet, basename='rag-chunk')

urlpatterns = [
    path('', include(router.urls)),
]
