from django.urls import path

from mars import views

app_name = "mars"

urlpatterns = [
    path("workspaces/", views.api_workspaces, name="workspaces"),
    path("workspaces/<int:workspace_id>/", views.api_workspace_detail, name="workspace_detail"),
    path("sessions/", views.api_sessions, name="sessions"),
    path("sessions/<int:session_id>/", views.api_session_detail, name="session_detail"),
    path("sessions/<int:session_id>/answer/", views.api_session_answer, name="session_answer"),
    path("sessions/<int:session_id>/approve-plan/", views.api_session_approve_plan, name="session_approve_plan"),
    path("sessions/<int:session_id>/run/", views.api_session_run, name="session_run"),
    path("runs/<int:run_id>/", views.api_run_detail, name="run_detail"),
    path("runs/<int:run_id>/events/", views.api_run_events, name="run_events"),
    path("runs/<int:run_id>/stop/", views.api_run_stop, name="run_stop"),
]
