from django.urls import path

from .views import (
    agent_views,
    mcp_views,
    notification_views,
    pipeline_assistant_views,
    pipeline_views,
    run_views,
    server_views,
    share_views,
    skill_views,
    template_views,
    trigger_views,
)

app_name = "studio"

urlpatterns = [
    # Pipelines
    path("pipelines/", pipeline_views.api_pipelines, name="pipelines"),
    path("pipelines/assistant/", pipeline_assistant_views.api_pipeline_assistant, name="pipeline_assistant"),
    path("pipelines/<int:pipeline_id>/", pipeline_views.api_pipeline_detail, name="pipeline_detail"),
    path("pipelines/<int:pipeline_id>/run/", pipeline_views.api_pipeline_run, name="pipeline_run"),
    path("pipelines/<int:pipeline_id>/clone/", pipeline_views.api_pipeline_clone, name="pipeline_clone"),
    path("pipelines/<int:pipeline_id>/runs/", pipeline_views.api_pipeline_runs, name="pipeline_runs"),
    # Runs
    path("runs/", run_views.api_runs, name="runs"),
    path("runs/<int:run_id>/", run_views.api_run_detail, name="run_detail"),
    path("runs/<int:run_id>/stop/", run_views.api_run_stop, name="run_stop"),
    path("runs/<int:run_id>/approve/<str:node_id>/", run_views.api_run_approve, name="run_approve"),
    # Agent Configs
    path("agents/", agent_views.api_agents, name="agents"),
    path("agents/<int:agent_id>/", agent_views.api_agent_detail, name="agent_detail"),
    path("skills/", skill_views.api_skills, name="skills"),
    path("skills/templates/", skill_views.api_skill_templates, name="skill_templates"),
    path("skills/scaffold/", skill_views.api_skill_scaffold, name="skill_scaffold"),
    path("skills/validate/", skill_views.api_skill_validate, name="skill_validate"),
    path("skills/<slug:slug>/workspace/", skill_views.api_skill_workspace, name="skill_workspace"),
    path("skills/<slug:slug>/workspace/file/", skill_views.api_skill_workspace_file, name="skill_workspace_file"),
    path("skills/<slug:slug>/", skill_views.api_skill_detail, name="skill_detail"),
    path("share-users/", share_views.api_share_users, name="share_users"),
    # MCP Pool
    path("mcp/", mcp_views.api_mcp_list, name="mcp_list"),
    path("mcp/templates/", mcp_views.api_mcp_templates, name="mcp_templates"),
    path("mcp/<int:mcp_id>/", mcp_views.api_mcp_detail, name="mcp_detail"),
    path("mcp/<int:mcp_id>/test/", mcp_views.api_mcp_test, name="mcp_test"),
    path("mcp/<int:mcp_id>/tools/", mcp_views.api_mcp_tools, name="mcp_tools"),
    # Triggers
    path("triggers/", trigger_views.api_triggers, name="triggers"),
    path("triggers/<int:trigger_id>/", trigger_views.api_trigger_detail, name="trigger_detail"),
    path("triggers/<str:token>/receive/", trigger_views.api_trigger_receive, name="trigger_receive"),
    # Templates
    path("templates/", template_views.api_templates, name="templates"),
    path("templates/<slug:slug>/use/", template_views.api_template_use, name="template_use"),
    # Servers (for node dropdowns)
    path("servers/", server_views.api_studio_servers, name="servers"),
    # Notification settings
    path("notifications/", notification_views.api_notification_settings, name="notifications"),
    path(
        "notifications/test-telegram/",
        notification_views.api_notification_test_telegram,
        name="notifications_test_telegram",
    ),
    path("notifications/test-email/", notification_views.api_notification_test_email, name="notifications_test_email"),
]
