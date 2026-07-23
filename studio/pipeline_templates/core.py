"""Core built-in pipeline templates."""

from ..webhook_smoke import WEBHOOK_SMOKE_TEMPLATE

CORE_TEMPLATES = [
    WEBHOOK_SMOKE_TEMPLATE,
    {
        "slug": "healthcheck-sweep",
        "name": "Healthcheck Sweep",
        "description": "Checks CPU, RAM, disk and load on multiple servers, generates a health report.",
        "icon": "🏥",
        "category": "Monitoring",
        "tags": ["health", "monitoring", "multi-server"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Health Check"},
            },
            {
                "id": "n2",
                "type": "agent/multi",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Multi-Server Health Agent",
                    "goal": "Check the health of all connected servers. For each server: 1) Check CPU usage (top -bn1), 2) Check RAM (free -h), 3) Check disk space (df -h), 4) Check system load (uptime). Report any anomalies (CPU>80%, RAM>90%, disk>85%).",
                    "system_prompt": "You are a DevOps monitoring agent. Be thorough but concise. Flag any concerning metrics.",
                    "max_iterations": 15,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 300, "y": 320},
                "data": {"label": "Health Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
        ],
    },
    {
        "slug": "docker-deploy",
        "name": "Docker Deploy",
        "description": "Pulls latest image, recreates container, verifies it's running.",
        "icon": "🐳",
        "category": "Deployment",
        "tags": ["docker", "deploy", "automation"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Deploy"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Deploy Agent",
                    "goal": "Deploy the application using Docker: 1) Pull latest image: docker pull {image_name}, 2) Stop old container: docker stop {container_name} || true, 3) Remove old container: docker rm {container_name} || true, 4) Start new container: docker run -d --name {container_name} --restart unless-stopped {image_name}, 5) Verify container is running: docker ps | grep {container_name}",
                    "system_prompt": "You are a deployment agent. Execute steps in order. On error, report immediately.",
                    "max_iterations": 10,
                    "on_failure": "abort",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Deploy OK?",
                    "check_type": "status_ok",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 150, "y": 470},
                "data": {"label": "Deploy Success Report"},
            },
            {
                "id": "n5",
                "type": "output/report",
                "position": {"x": 450, "y": 470},
                "data": {"label": "Deploy Failure Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true", "label": "success"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false", "label": "failed"},
        ],
    },
    {
        "slug": "log-cleanup",
        "name": "Log Cleanup",
        "description": "Finds and removes old logs and temp files, frees up disk space.",
        "icon": "🧹",
        "category": "Maintenance",
        "tags": ["cleanup", "logs", "disk"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/schedule",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Weekly Cleanup", "cron_expression": "0 2 * * 0"},
            },
            {
                "id": "n2",
                "type": "agent/ssh_cmd",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Check Disk Before",
                    "command": "df -h / && echo '---' && du -sh /var/log/* 2>/dev/null | sort -rh | head -20",
                },
            },
            {
                "id": "n3",
                "type": "agent/react",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Cleanup Agent",
                    "goal": "Clean up old logs and temporary files to free disk space: 1) Find log files older than 30 days in /var/log and remove or compress them, 2) Clean /tmp of files older than 7 days, 3) Clean apt/yum cache if on Linux, 4) Report total space freed.",
                    "system_prompt": "You are a disk maintenance agent. Be conservative — only delete clearly old/temp files. Always verify before deleting.",
                    "max_iterations": 12,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 300, "y": 490},
                "data": {"label": "Cleanup Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e3-4", "source": "n3", "target": "n4", "animated": True},
        ],
    },
    {
        "slug": "incident-response",
        "name": "Incident Response",
        "description": "Triggered by webhook alert — investigates the issue, collects diagnostics, generates a report.",
        "icon": "🚨",
        "category": "Incident",
        "tags": ["incident", "alert", "diagnostics"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/webhook",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Alert Received"},
            },
            {
                "id": "n2",
                "type": "agent/multi",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Incident Investigation Agent",
                    "goal": "Incident triggered: {alert_name} on {server_name}. Investigate: 1) Check system resources (CPU, RAM, disk), 2) Check relevant services status (systemctl status or docker ps), 3) Examine recent logs (journalctl -n 100 or app logs), 4) Check network connectivity, 5) Identify root cause, 6) Suggest remediation steps.",
                    "system_prompt": "You are an incident response agent. Act urgently but carefully. Document every finding.",
                    "max_iterations": 20,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 200, "y": 350},
                "data": {"label": "Incident Report"},
            },
            {
                "id": "n4",
                "type": "output/webhook",
                "position": {"x": 420, "y": 350},
                "data": {
                    "label": "Notify Slack",
                    "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/HERE",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e2-4", "source": "n2", "target": "n4", "animated": True},
        ],
    },
    {
        "slug": "security-audit",
        "name": "Security Audit",
        "description": "Checks open ports, outdated packages, SSH config, and sudo permissions.",
        "icon": "🔐",
        "category": "Security",
        "tags": ["security", "audit", "compliance"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Security Audit"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Security Audit Agent",
                    "goal": "Perform a security audit: 1) Check listening ports (ss -tlnp or netstat -tlnp), 2) Check for outdated packages with known CVEs (apt list --upgradable or yum check-update), 3) Check SSH config (/etc/ssh/sshd_config) for password auth and root login, 4) Check sudoers for overly broad permissions (cat /etc/sudoers), 5) Check for world-writable files in sensitive locations, 6) Report all findings with severity.",
                    "system_prompt": "You are a security auditor. Do NOT make any changes. Only audit and report. Classify findings as CRITICAL/HIGH/MEDIUM/LOW.",
                    "max_iterations": 15,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 300, "y": 340},
                "data": {"label": "Security Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
        ],
    },
    {
        "slug": "service-restart",
        "name": "Service Restart",
        "description": "Restarts a service, waits for it to come up, verifies it is healthy.",
        "icon": "🔄",
        "category": "Operations",
        "tags": ["service", "restart", "ops"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/webhook",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Restart Triggered"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Service Restart Agent",
                    "goal": "Restart service {service_name}: 1) Check current status: systemctl status {service_name}, 2) Restart: systemctl restart {service_name}, 3) Wait 10 seconds, 4) Check status again, 5) If using HTTP: curl -sf http://localhost:{port}/health, 6) Report result.",
                    "system_prompt": "You are a service management agent. Be methodical. Always verify the service is healthy after restart.",
                    "max_iterations": 8,
                    "on_failure": "abort",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Service Up?",
                    "check_type": "status_ok",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 150, "y": 470},
                "data": {"label": "Success"},
            },
            {
                "id": "n5",
                "type": "output/webhook",
                "position": {"x": 450, "y": 470},
                "data": {
                    "label": "Alert: Service Down",
                    "url": "",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3"},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false"},
        ],
    },
]
