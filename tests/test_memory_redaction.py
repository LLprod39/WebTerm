"""Tests for app.agent_kernel.memory.redaction — secret redaction layer."""
from __future__ import annotations

from app.agent_kernel.memory.redaction import redact_for_storage, redact_text


class TestRedactText:
    """Tests for raw text redaction."""

    def test_pem_block_redacted(self):
        text = "config:\n-----BEGIN RSA PRIVATE KEY-----\nMIIE...blah...=\n-----END RSA PRIVATE KEY-----\nend"
        result = redact_text(text)
        assert "BEGIN RSA PRIVATE KEY" not in result.text
        assert "[REDACTED:pem_block" in result.text
        assert result.report.get("pem_block", 0) >= 1

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        result = redact_text(text)
        assert "eyJhbGci" not in result.text
        assert result.report.get("bearer_token", 0) >= 1

    def test_connection_string_redacted(self):
        text = "DATABASE_URL=postgres://admin:secret123@db.example.com:5432/mydb"
        result = redact_text(text)
        assert "secret123" not in result.text
        assert result.report.get("connection_string", 0) >= 1

    def test_secret_assignment_redacted(self):
        text = "password=SuperSecretP@ss and token = abc123def456"
        result = redact_text(text)
        assert "SuperSecretP@ss" not in result.text
        assert result.report.get("secret_assignment", 0) >= 1

    def test_aws_access_key_redacted(self):
        text = "aws_access_key_id: AKIAIOSFODNN7EXAMPLE"
        result = redact_text(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.text
        assert result.report.get("aws_access_key", 0) >= 1

    def test_github_pat_redacted(self):
        text = "GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = redact_text(text)
        assert "ghp_ABCDEFGHIJ" not in result.text
        assert result.report.get("github_pat", 0) >= 1

    def test_openai_key_redacted(self):
        text = "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234"
        result = redact_text(text)
        assert "sk-proj-abcdefg" not in result.text
        assert result.report.get("openai_api_key", 0) >= 1

    def test_gitlab_pat_redacted(self):
        text = "token: glpat-abcdefghijklmnopqrstuv"
        result = redact_text(text)
        assert "glpat-abcdefg" not in result.text
        assert result.report.get("gitlab_pat", 0) >= 1

    def test_slack_token_redacted(self):
        text = "SLACK_TOKEN=xoxb-TESTTOKENZZ"
        result = redact_text(text)
        assert "xoxb-TEST" not in result.text
        assert result.report.get("slack_token", 0) >= 1

    def test_safe_text_not_redacted(self):
        text = "Server running on port 8080. CPU usage is 45%. nginx is healthy."
        result = redact_text(text)
        assert result.text == text
        assert sum(result.report.values()) == 0

    def test_multiple_secrets_in_one_text(self):
        text = (
            "DB: postgres://root:pass@host/db\n"
            "Token: Bearer eyJhbGci.payload.sig\n"
            "AWS: AKIAIOSFODNN7EXAMPLE\n"
        )
        result = redact_text(text)
        assert "root:pass" not in result.text
        assert "eyJhbGci" not in result.text
        assert "AKIAIOSFODNN7EXAMPLE" not in result.text
        assert sum(result.report.values()) >= 3

    def test_hashes_are_deterministic(self):
        text = "password=SecretValue123"
        result1 = redact_text(text)
        result2 = redact_text(text)
        assert result1.hashes == result2.hashes
        assert len(result1.hashes) > 0


class TestRedactForStorage:
    """Tests for combined text + payload redaction."""

    def test_payload_keys_redacted(self):
        text = "normal output"
        payload = {
            "command": "echo hello",
            "password": "s3cret",
            "nested": {"api_key": "abc123"},
        }
        redacted_text, redacted_payload, report, hashes = redact_for_storage(
            raw_text=text, payload=payload
        )
        # Sensitive payload keys should be masked
        assert redacted_payload.get("password") != "s3cret"
        assert redacted_payload.get("nested", {}).get("api_key") != "abc123"
        # Safe keys preserved
        assert redacted_payload.get("command") == "echo hello"

    def test_empty_inputs(self):
        redacted_text, redacted_payload, report, hashes = redact_for_storage(
            raw_text="", payload={}
        )
        assert redacted_text == ""
        assert redacted_payload == {}
        assert report == {}
        assert hashes == []
