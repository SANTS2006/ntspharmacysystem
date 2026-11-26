from django.urls import path

from . import views as v

urlpatterns = [
    path("notifications/", v.ListView.as_view()),
    path("notifications/read-all/", v.ReadAllView.as_view()),
    path("notifications/<int:pk>/", v.DetailView.as_view()),
    path("notifications/<int:pk>/read/", v.ReadView.as_view()),
]
