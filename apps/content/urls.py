from django.urls import path

from . import views

urlpatterns = [
    path("", views.catalogue, name="learn_catalogue"),
    path("check/", views.check, name="learn_check"),
    path("heartbeat/", views.heartbeat, name="learn_heartbeat"),
    path("media/<int:pk>/", views.media_file, name="learn_media"),
    path("m<int:number>/", views.module_page, name="learn_module"),
    path("m<int:number>/<slug:slug>/", views.unit_page, name="learn_unit"),
    path("m<int:number>/<slug:slug>/complete/", views.complete, name="learn_complete"),
    path("m<int:number>/<slug:slug>/block/<int:index>/", views.block_action, name="learn_block"),
]
