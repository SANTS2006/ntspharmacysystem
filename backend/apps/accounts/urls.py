from django.urls import path

from . import profile_views, views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("me/profile/", profile_views.ProfileView.as_view()),
    path("me/avatar/", profile_views.AvatarView.as_view()),
    path("me/email/", profile_views.EmailChangeView.as_view()),
    path("me/email/confirm/", profile_views.EmailChangeConfirmView.as_view()),
    path("change-password/", views.ChangePasswordView.as_view(), name="auth-change-password"),
    path("accept-invitation/", views.AcceptInvitationView.as_view(), name="auth-accept-invitation"),
    path("password-reset/", views.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
]
