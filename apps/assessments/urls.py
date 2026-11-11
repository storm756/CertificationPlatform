from django.urls import path

from . import views

urlpatterns = [
    path("assess/<int:part_id>/", views.intro, name="assess_intro"),
    path("assess/<int:part_id>/start/", views.start, name="assess_start"),
    path("attempt/<int:pk>/", views.attempt_page, name="attempt_page"),
    path("attempt/<int:pk>/q/<int:position>/", views.attempt_page, name="attempt_question"),
    path("attempt/<int:pk>/answer/", views.answer, name="attempt_answer"),
    path("attempt/<int:pk>/review/", views.review, name="attempt_review"),
    path("attempt/<int:pk>/submit/", views.submit, name="attempt_submit"),
    path("attempt/<int:pk>/result/", views.result, name="attempt_result"),
]
