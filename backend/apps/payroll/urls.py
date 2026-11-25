from django.urls import path

from . import views as v

urlpatterns = [
    path("payroll/config/", v.ConfigView.as_view()),
    path("payroll/components/", v.ComponentsView.as_view()),
    path("payroll/structures/", v.StructuresView.as_view()),
    path("payroll/adjustments/", v.AdjustmentsView.as_view()),
    path("payroll/advances/", v.AdvancesView.as_view()),
    path("payroll/runs/", v.RunsView.as_view()),
    path("payroll/runs/<int:pk>/", v.RunDetailView.as_view()),
    path("payroll/runs/<int:pk>/recalculate/", v.RunRecalculate.as_view()),
    path("payroll/runs/<int:pk>/submit/", v.RunSubmit.as_view()),
    path("payroll/runs/<int:pk>/cancel/", v.RunCancel.as_view()),
    path("payroll/runs/<int:pk>/approve/", v.RunApprove.as_view()),
    path("payroll/lines/<int:pk>/pay/", v.PayLineView.as_view()),
    path("payroll/lines/<int:pk>/payslip/", v.PayslipView.as_view()),
    path("payroll/lines/<int:pk>/payslip/pdf/", v.PayslipPdfView.as_view()),
    path("hr/me/salary/", v.MySalaryView.as_view()),
    path("hr/me/payslips/", v.MyPayslipsView.as_view()),
    path("hr/me/payslips/<int:pk>/", v.MyPayslipView.as_view()),
    path("hr/me/payslips/<int:pk>/pdf/", v.MyPayslipPdfView.as_view()),
]
