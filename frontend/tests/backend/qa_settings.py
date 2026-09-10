"""Isolated local QA state; external provider runtimes need separate fixtures."""

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

QA_ROOT = Path(__file__).resolve().parents[1] / ".auth"
QA_ROOT.mkdir(exist_ok=True)
QA_TEMP_ROOT = QA_ROOT / "tmp"
QA_TEMP_ROOT.mkdir(exist_ok=True)

# Some services read os.environ directly, and base settings load the working .env.
# Assign before importing Django settings so neither source can select real state.
os.environ["DJANGO_DEBUG"] = "true"
os.environ["DJANGO_SECRET_KEY"] = "frontend-qa-isolated-local-only-not-for-deployment"
os.environ["MODEL_CONFIG_PATH"] = str(QA_ROOT / "model-config.json")
os.environ["OLLAMA_CACHE_PATH"] = str(QA_ROOT / "ollama-url")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
os.environ["OLLAMA_CLOUD_BASE_URL"] = "http://127.0.0.1:1"
os.environ["MANAGED_SECRET_KEY"] = "frontend-qa-managed-secrets-local-only-not-for-deployment"
os.environ["MANAGED_SECRET_KEY_ID"] = "frontend-qa-local"
os.environ["MANAGED_SECRET_PREVIOUS_KEYS"] = "{}"
os.environ["APP_SECRET_ENCRYPTION_KEY"] = ""
os.environ["AI_CLI_SUBSCRIPTIONS_ENABLED"] = "false"
os.environ["AI_CLI_RUNNER_MANAGER_URL"] = "http://127.0.0.1:1"
os.environ["APP_LOG_FILE"] = str(QA_ROOT / "logs" / "backend.log")
os.environ["APP_LOG_SYSLOG_ENABLED"] = "false"
os.environ["DOMAIN_AUTH_ENABLED"] = "false"
os.environ["DOMAIN_AUTH_TRUSTED_PROXIES"] = ""
os.environ["LDAP_ENABLED"] = "false"
os.environ["LDAP_PASSWORD_LOGIN_ENFORCED"] = "false"
for _qa_env_name in (
    "GEMINI_API_KEY",
    "GROK_API_KEY",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_API_KEY",
    "CURSOR_API_KEY",
    "OPENAI_ADMIN_API_KEY",
    "ANTHROPIC_ADMIN_API_KEY",
    "XAI_MANAGEMENT_API_KEY",
    "XAI_TEAM_ID",
    "AI_CLI_RUNNER_MANAGER_TOKEN",
    "DOMAIN_AUTH_SHARED_SECRET",
    "LDAP_SERVER",
    "LDAP_BIND_DN",
    "LDAP_BIND_PASSWORD",
    "LDAP_SEARCH_BASE",
):
    os.environ[_qa_env_name] = ""
for _qa_env_name in ("TMPDIR", "TEMP", "TMP"):
    os.environ[_qa_env_name] = str(QA_TEMP_ROOT)
# tempfile may already have cached the host directory before this module loads.
tempfile.tempdir = str(QA_TEMP_ROOT)

# This is a fresh QA configuration, not a copy of the working model config.
# Never overwrite a previous QA save on a reload.
_qa_model_config = Path(os.environ["MODEL_CONFIG_PATH"])
if not _qa_model_config.exists():
    _qa_model_config.write_text(
        json.dumps(
            {
                "grok_enabled": False,
                "ollama_enabled": False,
                "ollama_base_url": "http://127.0.0.1:1",
                "ollama_runtime_mode": "local",
                "ollama_cloud_enabled": False,
                "ollama_cloud_base_url": "http://127.0.0.1:1",
            }
        ),
        encoding="utf-8",
    )

# A declarative local package fixture can exercise the marketplace without an
# inherited signing/scanning service, Docker worker, remote catalog or bundle host.
_qa_plugin_env = {
    "PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR": str(QA_ROOT / "plugin-packages"),
    "PLUGIN_MARKETPLACE_SIGNING_PROVIDER": "local_hmac",
    "PLUGIN_MARKETPLACE_SIGNING_KEYS": json.dumps(
        {
            "frontend-qa-local": "frontend-qa-signing-local-only-not-for-deployment",
        }
    ),
    "PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID": "frontend-qa-local",
    "PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS": "true",
    "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER": "false",
    "PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER": "local_static",
    "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER": "false",
    "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE": "in_process_no_code",
    "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED": "false",
    "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER": "disabled",
    "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED": "false",
    "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES": "false",
    "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES": "false",
    "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER": "manifest_url",
    "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_FRONTEND_BUNDLE_HOST": "false",
    "PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS": "",
    "PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS": "",
    "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS": "",
}
for _qa_suffix in (
    "SIGNING_ENDPOINT",
    "VERIFY_ENDPOINT",
    "SIGNING_AUTH_TOKEN",
    "SECURITY_SCAN_ENDPOINT",
    "SECURITY_SCAN_AUTH_TOKEN",
    "BACKEND_SANDBOX_ENDPOINT",
    "BACKEND_SANDBOX_AUTH_TOKEN",
    "FRONTEND_BUNDLE_ENDPOINT",
    "FRONTEND_BUNDLE_AUTH_TOKEN",
):
    _qa_plugin_env[f"PLUGIN_MARKETPLACE_EXTERNAL_{_qa_suffix}"] = ""
os.environ.update(_qa_plugin_env)

from web_ui.settings.development import *  # noqa: E402,F403,F401

DATABASES = deepcopy(DATABASES)  # noqa: F405
DATABASES["default"]["NAME"] = "webterm_frontend_qa_20260902"
DATABASES["default"]["CONN_MAX_AGE"] = 0
MEDIA_ROOT = QA_ROOT / "media"
UPLOADED_FILES_DIR = MEDIA_ROOT / "uploads"
SSH_PRIVATE_KEYS_DIR = QA_ROOT / "ssh-keys"
AGENT_PROJECTS_DIR = QA_ROOT / "agent-projects"
FILE_UPLOAD_TEMP_DIR = str(QA_TEMP_ROOT)
PLAYBOOK_BUNDLE_STORAGE_ROOT = QA_ROOT / "bundles"
STUDIO_SKILLS_DIRS = [QA_ROOT / "skills"]
for _qa_directory in (UPLOADED_FILES_DIR, SSH_PRIVATE_KEYS_DIR, AGENT_PROJECTS_DIR, *STUDIO_SKILLS_DIRS):
    _qa_directory.mkdir(parents=True, exist_ok=True)
SESSION_COOKIE_NAME = "webterm_frontend_qa_session"
CSRF_COOKIE_NAME = "webterm_frontend_qa_csrf"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8091", "http://localhost:8091"]
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AI_CLI_SUBSCRIPTIONS_ENABLED = False
