from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class MutationSchema(BaseModel):
    model_config = ConfigDict(extra="allow", json_schema_extra={"examples": [{"name": "example"}]})

    name: str | None = Field(default=None, max_length=200)


class ServerMutationSchema(MutationSchema):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "name": "web-01",
                    "host": "server.example.internal",
                    "username": "ubuntu",
                    "auth_method": "key",
                }
            ]
        },
    )
    name: str | None = Field(default=None, max_length=200)
    host: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=100)
    key_path: str | None = Field(default=None, max_length=500)
    tags: str | None = Field(default=None, max_length=500)


class ProjectMutationSchema(MutationSchema):
    model_config = ConfigDict(extra="allow", json_schema_extra={"examples": [{"name": "Production"}]})
    name: str | None = Field(default=None, max_length=120)


class AccessUserMutationSchema(MutationSchema):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={"examples": [{"username": "operator", "email": "operator@example.com"}]},
    )
    username: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    first_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)


class StudioAgentMutationSchema(MutationSchema):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={"examples": [{"name": "Fleet observer", "model": "configured-model"}]},
    )
    name: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)


class StudioPipelineMutationSchema(MutationSchema):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={"examples": [{"name": "Deploy check", "description": "Validate a deployment"}]},
    )
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class AuthLoginMutationSchema(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={"examples": [{"username": "operator", "password": "<secret>", "auth_mode": "auto"}]},
    )

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=4096)
    auth_mode: Literal["auto", "local"] = "auto"


class ServerOwnershipTransferSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"target_user_id": 42}]})

    target_user_id: int = Field(gt=0)


class ServerGroupBulkActionParameters(BaseModel):
    value: bool | str


class ServerGroupBulkActionSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"action": "set_ai_read_only", "parameters": {"value": True}}],
        },
    )

    action: Literal["set_active", "set_ai_read_only", "set_tags"]
    parameters: ServerGroupBulkActionParameters


class PipelineRunResumeSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"confirm_non_idempotent": False}]},
    )

    confirm_non_idempotent: bool = False


ROUTE_SCHEMAS: dict[str, type[BaseModel]] = {
    "api_auth_login": AuthLoginMutationSchema,
    "api_projects": ProjectMutationSchema,
    "api_access_users": AccessUserMutationSchema,
    "servers:server_create": ServerMutationSchema,
    "servers:server_update": ServerMutationSchema,
    "servers:server_transfer_owner": ServerOwnershipTransferSchema,
    "servers:group_bulk_action_create": ServerGroupBulkActionSchema,
    "studio:agents": StudioAgentMutationSchema,
    "studio:agent_detail": StudioAgentMutationSchema,
    "studio:pipelines": StudioPipelineMutationSchema,
    "studio:pipeline_detail": StudioPipelineMutationSchema,
    "studio:run_resume": PipelineRunResumeSchema,
}


def validate_mutation_payload(view_name: str, payload: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(payload, dict):
        return None, [{"field": "$", "message": "JSON body must be an object", "type": "object_type"}]
    schema = ROUTE_SCHEMAS.get(str(view_name or ""), MutationSchema)
    try:
        validated = schema.model_validate(payload)
    except ValidationError as exc:
        errors = []
        for item in exc.errors(include_url=False, include_context=False, include_input=False):
            location = ".".join(str(part) for part in item.get("loc") or ()) or "$"
            errors.append(
                {
                    "field": location,
                    "message": str(item.get("msg") or "Invalid value"),
                    "type": str(item.get("type") or "value_error"),
                }
            )
        return None, errors
    return {**payload, **validated.model_dump(exclude_none=True)}, []
