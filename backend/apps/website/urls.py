from django.urls import path

from . import views as v

urlpatterns = [
    path("public/site-pages/<slug:key>/", v.PublicPageView.as_view()),
    path("public/contact/", v.PublicContactView.as_view()),
    path("public/pharmacies/<slug:slug>/pages/<slug:key>/", v.PublicPageView.as_view()),
    path("public/pharmacies/<slug:slug>/contact/", v.PublicContactView.as_view()),
    path("website/pages/", v.PagesView.as_view()),
    path("website/pages/<slug:key>/", v.PageView.as_view()),
    path("website/images/", v.ImageView.as_view()),
    path("website/messages/", v.MessagesView.as_view()),
    path("website/messages/<int:pk>/", v.MessageView.as_view()),
    path("website/messages/<int:pk>/reply/", v.ReplyView.as_view()),
]
