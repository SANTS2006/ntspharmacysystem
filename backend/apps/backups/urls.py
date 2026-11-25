from django.urls import path

from . import views as v

urlpatterns = [
    path("platform/backups/", v.BackupsView.as_view()),
    path("platform/backups/health/", v.BackupHealthView.as_view()),
    path("platform/backups/<int:pk>/verify/", v.BackupVerifyView.as_view()),
    path("platform/backups/<int:pk>/download/", v.BackupDownloadView.as_view()),
    path("platform/restores/", v.RestoresView.as_view()),
    path("platform/restores/<int:pk>/approve/", v.RestoreApproveView.as_view()),
    path("platform/restores/<int:pk>/reject/", v.RestoreRejectView.as_view()),
    path("platform/restores/<int:pk>/execute/", v.RestoreExecuteView.as_view()),
]
