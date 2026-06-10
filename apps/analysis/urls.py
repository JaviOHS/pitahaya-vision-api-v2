from django.urls import path

from .views import AnalysisListCreateView, AnalysisDetailView

urlpatterns = [
    path('', AnalysisListCreateView.as_view(), name='analysis-list-create'),
    path('<int:pk>/', AnalysisDetailView.as_view(), name='analysis-detail'),
]
