from django.urls import path

from . import views

app_name = "studio"

urlpatterns = [
    # Pipelines
    path("pipelines/", views.api_pipelines, name="pipelines"),
    path("pipelines/assistant/", views.api_pipeline_assistant, name="pipeline_assistant"),
    path("pipelines/<int:pipeline_id>/", views.api_pipeline_detail, name="pipeline_detail"),
    path("pipelines/<int:pipeline_id>/run/", views.api_pipeline_run, name="pipeline_run"),
    path("pipelines/<int:pipeline_id>/clone/", views.api_pipeline_clone, name="pipeline_clone"),
    path("pipelines/<int:pipeline_id>/runs/", views.api_pipeline_runs, name="pipeline_runs"),
    # Runs
    path("runs/", views.api_runs, name="runs"),
    path("runs/<int:run_id>/", views.api_run_detail, name="run_detail"),
    path("runs/<int:run_id>/stop/", views.api_run_stop, name="run_stop"),
    path("runs/<int:run_id>/approve/<str:node_id>/", views.api_run_approve, name="run_approve"),
    # Agent Configs
    path("agents/", views.api_agents, name="agents"),
    path("agents/<int:agent_id>/", views.api_agent_detail, name="agent_detail"),
    path("skills/", views.api_skills, name="skills"),
    path("skills/templates/", views.api_skill_templates, name="skill_templates"),
    path("skills/scaffold/", views.api_skill_scaffold, name="skill_scaffold"),
    path("skills/validate/", views.api_skill_validate, name="skill_validate"),
    path("skills/<slug:slug>/workspace/", views.api_skill_workspace, name="skill_workspace"),
    path("skills/<slug:slug>/workspace/file/", views.api_skill_workspace_file, name="skill_workspace_file"),
    path("skills/<slug:slug>/", views.api_skill_detail, name="skill_detail"),
    path("share-users/", views.api_share_users, name="share_users"),
    # MCP Pool
    path("mcp/", views.api_mcp_list, name="mcp_list"),
    path("mcp/templates/", views.api_mcp_templates, name="mcp_templates"),
    path("mcp/<int:mcp_id>/", views.api_mcp_detail, name="mcp_detail"),
    path("mcp/<int:mcp_id>/test/", views.api_mcp_test, name="mcp_test"),
    path("mcp/<int:mcp_id>/tools/", views.api_mcp_tools, name="mcp_tools"),
    # Triggers
    path("triggers/", views.api_triggers, name="triggers"),
    path("triggers/<int:trigger_id>/", views.api_trigger_detail, name="trigger_detail"),
    path("triggers/<str:token>/receive/", views.api_trigger_receive, name="trigger_receive"),
    # Templates
    path("templates/", views.api_templates, name="templates"),
    path("templates/<slug:slug>/use/", views.api_template_use, name="template_use"),
    # Servers (for node dropdowns)
    path("servers/", views.api_studio_servers, name="servers"),
    # Notification settings
    path("notifications/", views.api_notification_settings, name="notifications"),
    path("notifications/test-telegram/", views.api_notification_test_telegram, name="notifications_test_telegram"),
    path("notifications/test-email/", views.api_notification_test_email, name="notifications_test_email"),
]
