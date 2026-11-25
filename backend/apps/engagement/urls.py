from django.urls import path

from . import views as v

urlpatterns = [
    path("public/pharmacies/<slug:slug>/services/", v.PublicServicesView.as_view()),
    path("public/pharmacies/<slug:slug>/institutional-requests/", v.PublicInstitutionalView.as_view()),
    path("services/", v.ServicesView.as_view()),
    path("services/<int:pk>/", v.ServiceDetailView.as_view()),
    path("shop/appointments/", v.MyAppointmentsView.as_view()),
    path("shop/appointments/<int:pk>/cancel/", v.MyAppointmentCancelView.as_view()),
    path("shop/inquiries/", v.MyInquiriesView.as_view()),
    path("shop/feedback/", v.MyFeedbackView.as_view()),
    path("appointments/", v.StaffAppointmentsView.as_view()),
    path("appointments/<int:pk>/status/", v.StaffAppointmentStatusView.as_view()),
    path("inquiries/", v.StaffInquiriesView.as_view()),
    path("inquiries/<int:pk>/respond/", v.StaffInquiryRespondView.as_view()),
    path("feedback/", v.StaffFeedbackView.as_view()),
    path("feedback/<int:pk>/respond/", v.StaffFeedbackRespondView.as_view()),
    path("institutional-requests/", v.StaffInstitutionalView.as_view()),
    path("institutional-requests/<int:pk>/respond/", v.StaffInstitutionalRespondView.as_view()),
]
