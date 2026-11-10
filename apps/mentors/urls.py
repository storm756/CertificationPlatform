from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="mentor_home"),
    path("batches/new/", views.batch_new, name="mentor_batch_new"),
    path("batches/<int:pk>/", views.batch_detail, name="mentor_batch"),
    path("batches/<int:pk>/settings/", views.batch_settings, name="mentor_batch_settings"),
    path("learners/<int:learner_id>/", views.learner_detail, name="mentor_learner"),
    path("learners/<int:learner_id>/move/", views.learner_move, name="mentor_learner_move"),
    path("learners/<int:learner_id>/name/", views.learner_name, name="mentor_learner_name"),
    path(
        "learners/<int:learner_id>/reset-link/",
        views.learner_reset_link,
        name="mentor_learner_reset_link",
    ),
]
