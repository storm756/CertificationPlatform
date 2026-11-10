from django.urls import path

from . import views

urlpatterns = [
    path("questions/", views.question_list, name="staff_questions"),
    path("questions/<int:pk>/", views.question_edit, name="staff_question"),
    path("questions/<int:pk>/preview/", views.question_preview, name="staff_question_preview"),
    path("questions/<int:pk>/publish/", views.question_publish, name="staff_question_publish"),
    path("marks/", views.marks_index, name="staff_marks"),
    path("marks/<int:number>/", views.marks_edit, name="staff_marks_edit"),
    path("report/", views.report, name="staff_report"),
]
