from django.urls import path

from . import customer_views as c
from . import views as v

urlpatterns = [
    path("public/pharmacies/<slug:slug>/catalogue/", v.PublicCatalogueView.as_view()),
    path("public/pharmacies/<slug:slug>/categories/", v.PublicCategoriesView.as_view()),
    path("public/pharmacies/<slug:slug>/branches/", v.PublicBranchesView.as_view()),
    path("public/menu/<str:token>/", v.PublicMenuView.as_view()),
    path("public/menu/<str:token>/catalogue/", v.PublicMenuCatalogueView.as_view()),
    path("public/menu/<str:token>/requests/", v.PublicQrRequestView.as_view()),
    path("shop/register/", v.RegisterView.as_view()),
    path("shop/google/", v.GoogleView.as_view()),
    path("shop/verify-email/", v.VerifyEmailView.as_view()),
    path("shop/resend-code/", v.ResendCodeView.as_view()),
    path("shop/me/", v.MeView.as_view()),
    path("shop/summary/", v.SummaryView.as_view()),
    path("shop/orders/", v.ShopOrdersView.as_view()),
    path("shop/orders/<int:pk>/", v.ShopOrderDetailView.as_view()),
    path("shop/orders/<int:pk>/cancel/", v.ShopOrderCancelView.as_view()),
    path("shop/orders/<int:pk>/request-refund/", v.ShopOrderRefundView.as_view()),
    path("shop/orders/<int:pk>/prescription/", v.ShopOrderPrescriptionView.as_view()),
    path("customers/", c.CustomerListView.as_view()),
    path("customers/<int:pk>/", c.CustomerDetailView.as_view()),
    path("orders/", v.StaffOrdersView.as_view()),
    path("orders/<int:pk>/", v.StaffOrderDetailView.as_view()),
    path("orders/<int:pk>/transition/", v.StaffTransitionView.as_view()),
    path("qr-requests/", v.StaffQrRequestsView.as_view()),
    path("qr-requests/<int:pk>/status/", v.StaffQrStatusView.as_view()),
    path("branches/<int:pk>/qr/", v.BranchQrView.as_view()),
]
