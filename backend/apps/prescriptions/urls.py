from django.urls import path

from . import views as v

urlpatterns = [
    path("patients/", v.PatientListCreateView.as_view()),
    path("patients/<int:pk>/", v.PatientDetailView.as_view()),
    path("prescriptions/", v.PrescriptionListCreateView.as_view()),
    path("prescriptions/<int:pk>/", v.PrescriptionDetailView.as_view()),
    path("prescriptions/<int:pk>/document/", v.DocumentView.as_view()),
    path("prescriptions/<int:pk>/start-review/", v.StartReview.as_view()),
    path("prescriptions/<int:pk>/recheck-safety/", v.Recheck.as_view()),
    path("prescriptions/<int:pk>/alerts/<int:alert_id>/acknowledge/", v.AcknowledgeAlertView.as_view()),
    path("prescriptions/<int:pk>/interventions/", v.InterventionView.as_view()),
    path("prescriptions/<int:pk>/approve/", v.Approve.as_view()),
    path("prescriptions/<int:pk>/reject/", v.Reject.as_view()),
    path("prescriptions/<int:pk>/cancel/", v.Cancel.as_view()),
    path("prescriptions/<int:pk>/refill/", v.Refill.as_view()),
    path("dispensing/prescriptions/<int:pk>/", v.DispenseView.as_view()),
    path("interaction-rules/", v.InteractionListCreateView.as_view()),
    path("interaction-rules/<int:pk>/", v.InteractionDetailView.as_view()),
    path("controlled-register/", v.ControlledRegisterView.as_view()),
]
