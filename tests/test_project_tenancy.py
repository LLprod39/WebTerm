from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core_ui.models.projects import ProjectMembership
from core_ui.projects import activate_project, active_project_for_user, create_project, ensure_default_project
from servers.models_agents import ServerAgent
from servers.models_inventory import Server, ServerShare
from servers.models_playbooks import Playbook
from servers.services.playbooks.access import playbooks_visible_to
from servers.services.server_query import get_servers_for_user
from studio.views.agent_helpers import _agent_read_queryset_for_user
from studio.views.mcp_views import _mcp_read_queryset_for_user
from studio.views.pipeline_helpers import _pipeline_queryset_for_user

pytestmark = pytest.mark.django_db


def _user(username: str, *, staff: bool = False) -> User:
    return User.objects.create_user(username=username, password="project-test", is_staff=staff)


def _server(user: User, name: str) -> Server:
    return Server.objects.create(user=user, name=name, host=f"{name}.example.test", username="root")


def _studio_models():
    from django.apps import apps

    return (
        apps.get_model("studio", "AgentConfig"),
        apps.get_model("studio", "MCPServerPool"),
        apps.get_model("studio", "Pipeline"),
    )


def test_operational_resources_do_not_require_project_switching():
    AgentConfig, MCPServerPool, Pipeline = _studio_models()
    owner = _user("tenant-owner", staff=True)
    personal = ensure_default_project(owner)
    personal_server = _server(owner, "personal-server")
    personal_agent = ServerAgent.objects.create(user=owner, name="personal-agent")
    personal_playbook = Playbook.objects.create(user=owner, name="personal-playbook", tasks=[{"name": "status"}])
    personal_mcp = MCPServerPool.objects.create(owner=owner, name="personal-mcp")
    personal_studio_agent = AgentConfig.objects.create(owner=owner, name="personal-studio-agent")
    personal_pipeline = Pipeline.objects.create(owner=owner, name="personal-pipeline")

    team = create_project(owner=owner, name="Production team")
    team_server = _server(owner, "team-server")
    team_agent = ServerAgent.objects.create(user=owner, name="team-agent")
    team_playbook = Playbook.objects.create(user=owner, name="team-playbook", tasks=[{"name": "status"}])
    team_mcp = MCPServerPool.objects.create(owner=owner, name="team-mcp")
    team_studio_agent = AgentConfig.objects.create(owner=owner, name="team-studio-agent")
    team_pipeline = Pipeline.objects.create(owner=owner, name="team-pipeline")

    assert {item.id for item in get_servers_for_user(owner)} == {personal_server.id, team_server.id}
    assert {item.id for item in playbooks_visible_to(owner)} == {personal_playbook.id, team_playbook.id}
    assert {item.id for item in _mcp_read_queryset_for_user(owner)} == {team_mcp.id}
    assert {item.id for item in _agent_read_queryset_for_user(owner)} == {team_studio_agent.id}
    assert {item.id for item in _pipeline_queryset_for_user(owner)} == {team_pipeline.id}
    assert team_agent.project_id == team.id

    activate_project(owner, personal)
    assert {item.id for item in get_servers_for_user(owner)} == {personal_server.id, team_server.id}
    assert {item.id for item in playbooks_visible_to(owner)} == {personal_playbook.id, team_playbook.id}
    assert {item.id for item in _mcp_read_queryset_for_user(owner)} == {personal_mcp.id}
    assert {item.id for item in _agent_read_queryset_for_user(owner)} == {personal_studio_agent.id}
    assert {item.id for item in _pipeline_queryset_for_user(owner)} == {personal_pipeline.id}
    assert personal_agent.project_id == personal.id


def test_legacy_server_share_is_visible_without_project_activation():
    owner = _user("share-owner")
    member = _user("share-member")
    owner_project = ensure_default_project(owner)
    member_project = ensure_default_project(member)
    personal_server = _server(member, "personal-member-server")
    server = _server(owner, "shared-server")

    ServerShare.objects.create(server=server, user=member, shared_by=owner, can_execute_command=True)
    membership = ProjectMembership.objects.get(project=owner_project, user=member)
    assert membership.role == ProjectMembership.ROLE_OPERATOR
    assert active_project_for_user(member).id == member_project.id
    assert get_servers_for_user(member).filter(pk=personal_server.pk).exists()
    assert get_servers_for_user(member).filter(pk=server.pk).exists()

    activate_project(member, owner_project)
    assert get_servers_for_user(member).filter(pk=server.pk).exists()


def test_viewer_cannot_create_project_resources():
    owner = _user("role-owner")
    viewer = _user("role-viewer")
    project = create_project(owner=owner, name="Read only team")
    ProjectMembership.objects.create(project=project, user=viewer, role=ProjectMembership.ROLE_VIEWER)
    activate_project(viewer, project)

    with pytest.raises(PermissionDenied, match="operator"):
        _server(viewer, "denied-server")


def test_cross_project_agent_links_are_rejected():
    AgentConfig, MCPServerPool, _Pipeline = _studio_models()
    owner = _user("relation-owner")
    first_project = ensure_default_project(owner)
    first_server = _server(owner, "first-server")
    second_project = create_project(owner=owner, name="Second project")
    second_agent = ServerAgent.objects.create(user=owner, name="second-agent")
    second_mcp = MCPServerPool.objects.create(owner=owner, name="second-mcp")

    with pytest.raises(ValidationError, match="same project"), transaction.atomic():
        second_agent.servers.add(first_server)

    activate_project(owner, first_project)
    first_studio_agent = AgentConfig.objects.create(owner=owner, name="first-studio-agent")
    with pytest.raises(ValidationError, match="same project"), transaction.atomic():
        first_studio_agent.mcp_servers.add(second_mcp)
    assert second_agent.project_id == second_project.id


def test_project_api_manages_members_and_switches_active_project(client):
    owner = _user("api-owner")
    member = _user("api-member")
    client.force_login(owner)

    created = client.post(
        "/api/projects/",
        data=json.dumps({"name": "API team"}),
        content_type="application/json",
    )
    assert created.status_code == 201
    project_id = created.json()["project"]["id"]

    invited = client.post(
        f"/api/projects/{project_id}/members/",
        data=json.dumps({"username": member.username, "role": "operator"}),
        content_type="application/json",
    )
    assert invited.status_code == 201
    assert invited.json()["member"]["role"] == "operator"

    client.force_login(member)
    switched = client.post(f"/api/projects/{project_id}/activate/")
    assert switched.status_code == 200
    assert switched.json()["project"]["is_active"] is True

    session = client.get("/api/auth/session/")
    assert session.status_code == 200
    assert session.json()["user"]["active_project"]["id"] == project_id
