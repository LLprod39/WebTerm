INSERT INTO studio_pipeline (
  name, description, icon, tags, nodes, edges,
  is_shared, is_template, owner_id, created_at, updated_at
)
SELECT
  '🤖 Full DevOps Autopilot',
  'Мега-пайплайн: 5 параллельных SSH + 4 LLM-запроса + ReAct-агент устраняет проблемы + плановое обслуживание + email-отчёт + Slack. ИИ управляет всем циклом DevOps-автоматизации.',
  '🤖',
  '["autopilot","ai","email","llm-query","react-agent","mega","devops"]',
  '[
    {"id":"t1","type":"trigger/schedule","position":{"x":520,"y":0},"data":{"label":"Daily Autopilot 04:00","cron_expression":"0 4 * * *"}},
    {"id":"s_disk","type":"agent/ssh_cmd","position":{"x":0,"y":160},"data":{"label":"💾 Disk & Inodes","command":"df -h && echo ---INODES--- && df -i && echo ---LARGEST--- && du -sh /var/log /tmp /home 2>/dev/null | sort -hr | head -10"}},
    {"id":"s_mem","type":"agent/ssh_cmd","position":{"x":260,"y":160},"data":{"label":"🧠 CPU / Memory","command":"uptime && echo ---MEM--- && free -h && echo ---TOP_CPU--- && ps aux --sort=-%cpu | head -12 && echo ---TOP_MEM--- && ps aux --sort=-%mem | head -8"}},
    {"id":"s_svc","type":"agent/ssh_cmd","position":{"x":520,"y":160},"data":{"label":"⚙️ Services Status","command":"systemctl list-units --state=failed --no-pager 2>/dev/null | head -20 || echo systemd_NA && echo ---RUNNING--- && systemctl list-units --state=running --no-pager 2>/dev/null | head -20 || true && echo ---KERNEL--- && uname -a && echo ---REBOOT--- && [ -f /var/run/reboot-required ] && cat /var/run/reboot-required || echo no_reboot_pending"}},
    {"id":"s_sec","type":"agent/ssh_cmd","position":{"x":780,"y":160},"data":{"label":"🔒 Security Scan","command":"echo =PORTS= && ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null | head -20 && echo =SSH_FAIL= && grep Failed /var/log/auth.log 2>/dev/null | tail -15 || journalctl -u ssh --since 24h ago 2>/dev/null | grep -i fail | tail -10 || echo no_auth_log && echo =LAST= && last | head -10"}},
    {"id":"s_logs","type":"agent/ssh_cmd","position":{"x":1040,"y":160},"data":{"label":"📋 Recent Errors","command":"echo =SYSLOG_ERR= && journalctl -p err --since 2h ago --no-pager 2>/dev/null | tail -20 || grep -i error /var/log/syslog 2>/dev/null | tail -20 || echo no_syslog && echo =DMESG_ERR= && dmesg --level=err,crit 2>/dev/null | tail -10 || echo no_dmesg"}},
    {"id":"ai_triage","type":"agent/llm_query","position":{"x":520,"y":360},"data":{"label":"🧠 AI Triage & Scoring","system_prompt":"You are a senior SRE. Analyse server telemetry and produce a structured triage report. Respond in Russian.","prompt":"Проанализируй метрики сервера:\n\n## Диск\n{s_disk}\n\n## CPU/RAM\n{s_mem}\n\n## Сервисы\n{s_svc}\n\n## Безопасность\n{s_sec}\n\n## Ошибки\n{s_logs}\n\nФормат ответа:\nSEVERITY: <1-10>\nCRITICAL: <да/нет>\nISSUES:\n- <список>\nACTIONS:\n- <список>\nЕсли severity >= 7 или критические упавшие сервисы — добавь строку: FLAG:CRITICAL","model":"gemini-2.0-flash-exp"}},
    {"id":"c_critical","type":"logic/condition","position":{"x":520,"y":530},"data":{"label":"🔴 Critical Issues?","check_type":"contains","check_value":"FLAG:CRITICAL"}},
    {"id":"ai_plan","type":"agent/llm_query","position":{"x":100,"y":700},"data":{"label":"🧠 AI: Build Fix Plan","system_prompt":"You are a Linux SRE. Generate EXACT safe shell commands to fix the identified problems.","prompt":"На основе триажа:\n{ai_triage}\n\nНапиши план исправлений в виде безопасных bash-команд.\nФормат:\nFIX_PLAN:\n```bash\n# Restart failed services\nsystemctl restart <service> 2>/dev/null || true\n# Clear logs if disk full\njournalctl --vacuum-size=200M 2>/dev/null || true\n```","model":"gemini-2.0-flash-exp"}},
    {"id":"a_fix","type":"agent/react","position":{"x":100,"y":880},"data":{"label":"🤖 Agent: Execute Fixes","goal":"Ты SRE-агент. На основе плана: {ai_plan}\n\nВыполни:\n1. Перезапусти упавшие systemd сервисы\n2. Очисти journald если диск > 80%: journalctl --vacuum-size=200M\n3. Удали старые tmp: find /tmp -mtime +3 -delete 2>/dev/null\n4. Проверь статус после каждого действия\n5. Составь отчёт","system_prompt":"Ты автономный SRE-агент. Действуй осторожно — только безопасные операции.","max_iterations":8,"on_failure":"continue"}},
    {"id":"s_verify","type":"agent/ssh_cmd","position":{"x":100,"y":1060},"data":{"label":"✅ Verify Fixes","command":"echo =FAILED_AFTER= && systemctl list-units --state=failed --no-pager 2>/dev/null | head -10 || echo ok && echo =DISK_AFTER= && df -h / /var 2>/dev/null && echo =MEM_AFTER= && free -h && echo =REBOOT= && [ -f /var/run/reboot-required ] && echo REBOOT_NEEDED || echo no_reboot"}},
    {"id":"ai_fix_report","type":"agent/llm_query","position":{"x":100,"y":1220},"data":{"label":"🧠 AI: Fix Summary","system_prompt":"You are an SRE writing an incident report. Be factual. Respond in Russian.","prompt":"Составь incident report:\n\n**Тираж:** {ai_triage}\n\n**План:** {ai_plan}\n\n**Действия агента:** {a_fix}\n\n**Проверка:** {s_verify}\n\nФормат:\n## Инцидент-репорт\n### Что было сломано\n### Что сделано\n### Текущий статус\n### Дальнейшие действия","model":"gemini-2.0-flash-exp"}},
    {"id":"s_maint","type":"agent/ssh_cmd","position":{"x":940,"y":700},"data":{"label":"🔧 Routine Maintenance","command":"echo =PKG_UPDATE= && apt-get update -qq 2>&1 | tail -3 || yum check-update -q 2>&1 | tail -3 || echo pkg_update_done && echo =JOURNAL_VACUUM= && journalctl --vacuum-time=7d 2>/dev/null | tail -3 || echo ok && echo =TMP_CLEAN= && find /tmp -mtime +1 -delete 2>/dev/null && echo tmp_cleaned && echo =LOG_SIZE= && du -sh /var/log 2>/dev/null"}},
    {"id":"ai_maint_check","type":"agent/llm_query","position":{"x":940,"y":880},"data":{"label":"🧠 AI: Maintenance Review","system_prompt":"You are a DevOps engineer reviewing routine maintenance. Respond in Russian.","prompt":"Сервер в норме. Результаты плановых работ:\n{s_maint}\n\nТираж (всё OK):\n{ai_triage}\n\nСоставь краткий статус:\n## Плановое обслуживание выполнено\n- Что сделано\n- Метрики после\n- Рекомендации на следующую неделю\nSTATUS: OK","model":"gemini-2.0-flash-exp"}},
    {"id":"ai_exec","type":"agent/llm_query","position":{"x":520,"y":1380},"data":{"label":"🧠 AI: Executive Summary","system_prompt":"You are a CTO-level engineer writing a daily infrastructure digest. Respond in Russian. Use emojis.","prompt":"Напиши Executive Summary состояния инфраструктуры.\n\nТираж: {ai_triage}\n\nСервисы: {s_svc}\n\nБезопасность: {s_sec}\n\nФормат:\n# 📊 Daily Infrastructure Report\n\n## 🟢/🔴 Общий статус\n## 💻 Инфраструктура\n## 🔒 Безопасность\n## ⚡ Производительность\n## 📋 Выполненные работы\n## 🎯 Рекомендации на завтра","model":"gemini-2.0-flash-exp"}},
    {"id":"o_report","type":"output/report","position":{"x":260,"y":1560},"data":{"label":"📋 Full Pipeline Report","template":"# Full DevOps Autopilot Report\n\n## Executive Summary\n{ai_exec}\n\n---\n## Disk\n```\n{s_disk}\n```\n\n## CPU/Memory\n```\n{s_mem}\n```\n\n## AI Triage\n{ai_triage}"}},
    {"id":"o_email","type":"output/email","position":{"x":680,"y":1560},"data":{"label":"✉️ Email Report to Admin","to_email":"admin@example.com","subject":"🤖 Daily DevOps Autopilot Report","body":"# Daily DevOps Autopilot Report\n\n{ai_exec}\n\n---\n## AI Triage\n{ai_triage}"}},
    {"id":"o_slack","type":"output/webhook","position":{"x":1060,"y":1560},"data":{"label":"💬 Slack Notification","url":"https://hooks.slack.com/services/YOUR/WEBHOOK/URL","extra_payload":{"channel":"#devops-alerts","username":"DevOps Autopilot"}}}
  ]',
  '[
    {"id":"e01","source":"t1","target":"s_disk","animated":true},
    {"id":"e02","source":"t1","target":"s_mem","animated":true},
    {"id":"e03","source":"t1","target":"s_svc","animated":true},
    {"id":"e04","source":"t1","target":"s_sec","animated":true},
    {"id":"e05","source":"t1","target":"s_logs","animated":true},
    {"id":"e06","source":"s_disk","target":"ai_triage","animated":true},
    {"id":"e07","source":"s_mem","target":"ai_triage","animated":true},
    {"id":"e08","source":"s_svc","target":"ai_triage","animated":true},
    {"id":"e09","source":"s_sec","target":"ai_triage","animated":true},
    {"id":"e10","source":"s_logs","target":"ai_triage","animated":true},
    {"id":"e11","source":"ai_triage","target":"c_critical","animated":true},
    {"id":"e12","source":"c_critical","target":"ai_plan","sourceHandle":"true","animated":true},
    {"id":"e13","source":"ai_plan","target":"a_fix","animated":true},
    {"id":"e14","source":"a_fix","target":"s_verify","animated":true},
    {"id":"e15","source":"s_verify","target":"ai_fix_report","animated":true},
    {"id":"e16","source":"ai_fix_report","target":"ai_exec","animated":true},
    {"id":"e17","source":"c_critical","target":"s_maint","sourceHandle":"false","animated":true},
    {"id":"e18","source":"s_maint","target":"ai_maint_check","animated":true},
    {"id":"e19","source":"ai_maint_check","target":"ai_exec","animated":true},
    {"id":"e20","source":"ai_exec","target":"o_report","animated":true},
    {"id":"e21","source":"ai_exec","target":"o_email","animated":true},
    {"id":"e22","source":"ai_exec","target":"o_slack","animated":true}
  ]',
  false,
  false,
  (SELECT id FROM auth_user WHERE is_superuser = true ORDER BY id LIMIT 1),
  NOW(),
  NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM studio_pipeline WHERE name = '🤖 Full DevOps Autopilot'
);
