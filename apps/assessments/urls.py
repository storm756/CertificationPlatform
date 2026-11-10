from django.urls import path

from . import views

urlpatterns = [
    path("assess/<int:part_id>/", views.intro, name="assess_intro"),
    path("assess/<int:part_id>/start/", views.start, name="assess_start"),
    path("exam/<slug:kind>/", views.programme_intro, name="programme_intro"),
    path("exam/<slug:kind>/start/", views.programme_start, name="programme_start"),
    path("attempt/<int:pk>/", views.attempt_page, name="attempt_page"),
    path("attempt/<int:pk>/q/<int:position>/", views.attempt_page, name="attempt_question"),
    path(
        "attempt/<int:pk>/q/<int:position>/data/", views.question_data, name="attempt_question_data"
    ),
    path("attempt/<int:pk>/q/<int:position>/image/", views.image, name="attempt_image"),
    path("attempt/<int:pk>/answer/", views.answer, name="attempt_answer"),
    path("attempt/<int:pk>/review/", views.review, name="attempt_review"),
    path("attempt/<int:pk>/submit/", views.submit, name="attempt_submit"),
    path("attempt/<int:pk>/result/", views.result, name="attempt_result"),
]
