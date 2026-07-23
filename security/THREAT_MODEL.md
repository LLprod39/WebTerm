# WebTerm Threat Model (Stage 1 / F-03 → F-10)

Last reviewed: 2026-07-23  
Plan ID: F-10 (GER-19)  
Supersedes informal notes in `docs/local/SECURITY_QA_FOR_IS_REVIEW.md` for release gating; that Q&A remains useful operational background.

## 1. System summary

WebTerm is a **self-hosted internal ops platform**:

- Django + Channels backend;
- React/Vite SPA;
- SSH terminal and file operations;
- AI agents / terminal assistant;
- Studio pipelines (MCP, approvals, webhooks, notifications);
- optional Kubernetes ops admin surface;
- private plugin extensions.

It is **not** public multi-tenant SaaS. Isolation assumptions are single organization / controlled network unless operators add their own controls.

## 2. Assets

| Asset | Why it matters |
| --- | --- |
| SSH credentials and host keys | Direct infrastructure access |
| Session cookies / CSRF tokens | Account takeover |
| Managed secrets / provider API keys | Lateral movement to cloud and LLM providers |
| Pipeline / agent execution capability | Remote code on managed hosts |
| Plugin packages | Code execution inside the platform trust boundary |
| Audit logs and memory | Forensics integrity; may contain sensitive operational data |
| Kubernetes admin credentials / tokens | Cluster-admin impact |
| Release artifacts (images, SBOMs) | Supply-chain integrity |

## 3. Trust boundaries

```text
Browser SPA  --HTTPS/session-->  Django API / Channels
                                     |
                    +----------------+----------------+
                    |                |                |
                 PostgreSQL        Redis          Celery workers
                    |                |                |
                 SSH targets    MCP servers     LLM providers
                    |                |                |
              K8s providers    Plugin sandbox   External webhooks
```

Untrusted relative to the control plane: browser clients, untrusted plugin packages, remote MCP endpoints, LLM providers, SSH hosts, Kubernetes API servers, inbound webhooks.

## 4. Checklist surfaces (F-03)

### 4.1 Auth / session / CSRF

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Session hijack | HTTPS in production, secure cookie flags, session middleware | Misconfigured reverse proxy |
| CSRF on state-changing HTTP | Django CSRF for cookie sessions; SPA must send token | Missing token on new endpoints |
| Privilege escalation (staff) | Django staff/superuser + feature permissions | Over-granted staff accounts |

**Tests:** core_ui auth smoke, 403 on staff-only routes.

### 4.2 SSH host-key trust

| Threat | Controls | Residual risk |
| --- | --- | --- |
| MITM on first connect | Host-key storage / trust policy in server inventory | Weak “accept any” operator workflows |
| Credential theft from storage | Encrypted secret helpers; no secrets in frontend | Encryption migration still recommended |

### 4.3 WebSocket authz

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Unauthorized terminal stream | Authenticated consumer + server ownership/share | Capability model not fully fine-grained |
| Cross-user agent live updates | Run ownership checks | Gaps on new WS routes |

### 4.4 Agent / pipeline execution policy

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Destructive commands | Execution policy, approvals, safety classifiers | Policy not fully unified across all paths |
| Auto-escalation | Policy engine + audit | Residual automation surprises |

**Tests:** `tests/test_agent_and_pipeline_policy_enforcement.py`, Studio policy tests.

### 4.5 MCP egress / redaction

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Secret exfil via MCP/LLM | `app/egress_redaction.py`, prompt sanitizers | Not every egress path proven |
| SSRF via MCP HTTP | Destination policy (hardening open) | Allowlist incomplete |

### 4.6 Plugin trust / sandbox

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Malicious `.wtp` package | Marketplace scan, attestations, sandbox flags | External scanner optional |
| Supply-chain tamper | Provenance fields on packages | Signing pipeline still Stage 1 scaffold |

### 4.7 Managed secrets leakage

| Channel | Control | Status |
| --- | --- | --- |
| Frontend JSON payloads | Never serialize raw secrets; key-hint redaction | Enforced in serializers/services; tests required |
| Logs / activity | `redacted_logging` + activity redaction | Covered by unit tests |
| Reports / memory | `redact_for_storage` / memory redaction exports | Covered in part |
| LLM prompts | `sanitize_prompt_context_text` | Covered in part |

### 4.8 Kubernetes admin mode

| Threat | Controls | Residual risk |
| --- | --- | --- |
| Cluster-admin abuse | Fail-closed terminal/exec/port-forward; staff gates; audit | Interactive transport requires evidence refs |
| Secret bleed in describe/YAML | Ownership helpers redact labels/tokens | Keep negative tests green |

**Tests:** kubernetes_ops action lifecycle, admin actions, permission matrix.

## 5. Abuse cases (priority)

1. Stolen session cookie → SSH to owned servers.
2. Low-privilege user hits mutation API for another user’s resource.
3. Agent/pipeline sends secret material to external LLM.
4. Plugin or MCP tool performs unapproved egress.
5. Dependency CVE (npm/Python) reaches production image.
6. Tampered release artifact without checksum/provenance verification.

## 6. Security process links

| Artifact | Path |
| --- | --- |
| Disclosure / SLA | `SECURITY.md` |
| Findings + risk acceptances | `security/FINDINGS_LEDGER.md` |
| Third-party notices | `THIRD_PARTY_NOTICES.md` |
| IS Q&A background | `docs/local/SECURITY_QA_FOR_IS_REVIEW.md` |
| SBOM / provenance scripts | `scripts/generate_sbom.py`, `scripts/generate_release_checksums.py`, `scripts/generate_provenance.py` |
| GitHub signed attestations | `.github/workflows/security.yml` job `sbom-provenance` (`actions/attest-build-provenance`) |

## 7. Change control

Update this threat model when adding:

- new mutation surfaces;
- new trust boundaries (device agent plane, public SaaS, etc.);
- changes to secret storage or LLM providers;
- enabling previously fail-closed K8s interactive transports.
