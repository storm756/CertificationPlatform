from django.urls import path

from . import views

urlpatterns = [
    path("certificate/", views.my_certificate, name="my_certificate"),
    path("certificate/download/", views.download, name="certificate_download"),
    path("verify/", views.verify, name="verify"),
    path("verify/<str:code>/", views.verify, name="verify_code"),
]
