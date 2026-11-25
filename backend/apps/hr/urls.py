from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/staff/", v.StaffListView.as_view()),
    path("hr/staff/<int:user_id>/", v.StaffDetailView.as_view()),
    path("hr/staff/<int:user_id>/terminate/", v.TerminateView.as_view()),
    path("hr/staff/<int:user_id>/documents/", v.DocumentsView.as_view()),
    path("hr/staff/<int:user_id>/disciplinary/", v.DisciplinaryView.as_view()),
    path("hr/documents/<int:pk>/download/", v.DocumentDownloadView.as_view()),
    path("hr/attendance/", v.AttendanceListView.as_view()),
    path("hr/attendance/clock-in/", v.ClockView.as_view()),
    path("hr/attendance/clock-out/", v.ClockOutView.as_view()),
    path("hr/attendance/manual/", v.ManualAttendanceView.as_view()),
    path("hr/shifts/", v.ShiftsView.as_view()),
    path("hr/leave-types/", v.LeaveTypesView.as_view()),
    path("hr/leave/", v.LeaveListView.as_view()),
    path("hr/leave/<int:pk>/approve/", v.LeaveDecideView.as_view()),
    path("hr/leave/<int:pk>/reject/", v.LeaveRejectView.as_view()),
    path("hr/me/", v.MeView.as_view()),
    path("hr/me/attendance/", v.MyAttendanceView.as_view()),
    path("hr/me/shifts/", v.MyShiftsView.as_view()),
    path("hr/me/leave/", v.MyLeaveView.as_view()),
    path("hr/me/leave/<int:pk>/cancel/", v.MyLeaveCancelView.as_view()),
]
