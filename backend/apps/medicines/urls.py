from django.urls import path

from . import views as v

urlpatterns = [
    path("categories/", v.CategoryListCreateView.as_view()),
    path("categories/<int:pk>/", v.CategoryDetailView.as_view()),
    path("medicines/", v.MedicineListCreateView.as_view()),
    path("medicines/barcode/<str:code>/", v.BarcodeLookupView.as_view()),
    path("medicines/<int:pk>/", v.MedicineDetailView.as_view()),
    path("medicines/<int:pk>/archive/", v.MedicineStatusView.as_view()),
    path("medicines/<int:pk>/restore/", v.MedicineRestoreView.as_view()),
]
