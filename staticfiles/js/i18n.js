(function () {
    "use strict";

    var STORAGE_KEY = "weu_lang";
    var DEFAULT_LANG = "en";

    var TRANSLATIONS = {
        en: {
            // Sidebar nav
            "nav.main": "Main",
            "nav.dashboard": "Dashboard",
            "nav.monitor": "Monitor",
            "nav.servers_section": "Servers",
            "nav.servers": "Servers",
            "nav.tools": "Tools",
            "nav.chat": "Chat",
            "nav.ide": "IDE",
            "nav.knowledge": "Knowledge",
            "nav.settings_section": "Settings",
            "nav.settings": "Settings",
            "user.signout": "Sign Out",
            "skip.main": "Skip to main content",

            // Help panel
            "help.title": "Help",
            "help.articles": "Articles",
            "help.close": "Close help",
            "help.rag.title": "What is RAG",
            "help.rag.text": "RAG (Retrieval-Augmented Generation) is a mode where model responses are backed by search through your knowledge base. Upload documents to Knowledge Base, enable \"RAG Enabled\" in chat, and responses will reference those documents. Great for internal policies, company knowledge bases, and documentation.",
            "help.workflow.title": "What is Workflow",
            "help.workflow.text": "Workflow (Orchestrator) is a chain: input \u2192 analysis \u2192 tool actions \u2192 response. The agent plans steps, calls tools (files, SSH, web) and forms a final answer. The Orchestrator section shows available tools and status; Agents section contains ready agents and workflow runs by task.",
            "help.models.title": "How to choose a model",
            "help.models.text": "Currently only Cursor Auto is used. In Settings (Models) you set the default provider and models for chat, agent, and RAG; Gemini and Grok will be available later.",
            "help.server.title": "How to safely connect a server",
            "help.server.text": "Server connections are configured in the Servers section. Use keys (SSH) and credentials from the Passwords section \u2014 do not enter passwords in chat. Limit user permissions on the server and store keys only in secure storage (.env, password manager), not in code or chat.",

            // Server list page
            "servers.title": "Servers",
            "servers.add": "Add Server",
            "servers.global_rules": "Global Rules",
            "servers.search": "Search servers\u2026",
            "servers.all_groups": "All Groups",
            "servers.ungrouped": "Ungrouped",
            "servers.shared_with_me": "Shared with me",
            "servers.new_group": "New Group",
            "servers.empty.title": "No servers yet",
            "servers.empty.text": "Add your first server to get started",
            "servers.test_connection": "Test connection",
            "servers.edit": "Edit server",
            "servers.delete": "Delete server",
            "servers.edit_group": "Edit group",

            // Server modal
            "modal.server.add_title": "Add Server",
            "modal.server.edit_title": "Edit Server",
            "modal.tab.basic": "Basic",
            "modal.tab.network": "Network",
            "modal.tab.context": "Context",
            "modal.tab.knowledge": "Knowledge",
            "modal.tab.sharing": "Sharing",
            "modal.server.name": "Server Name *",
            "modal.server.host": "Host / IP *",
            "modal.server.port": "Port",
            "modal.server.username": "Username *",
            "modal.server.group": "Group",
            "modal.server.no_group": "\u2014 No group \u2014",
            "modal.server.type": "Server Type",
            "modal.server.auth": "Authentication",
            "modal.server.password": "Password",
            "modal.server.key_path": "SSH Key Path",
            "modal.server.save": "Save Server",
            "modal.cancel": "Cancel",
            "modal.server.crypto_info": "Passwords are encrypted with AES-256. Set your master password via the lock icon in the terminal or via MASTER_PASSWORD env variable.",

            // Network tab
            "modal.network.proxy": "HTTP Proxy",
            "modal.network.proxy_desc": "Requires proxy to connect",
            "modal.network.vpn": "VPN Required",
            "modal.network.vpn_desc": "Server behind VPN",
            "modal.network.firewall": "Behind Firewall",
            "modal.network.firewall_desc": "Restricted network access",
            "modal.network.config": "Network Config (JSON)",

            // Context tab
            "modal.context.notes": "Notes",
            "modal.context.corporate": "Corporate Context",

            // Knowledge tab
            "modal.knowledge.desc": "AI-generated and manual knowledge entries for this server",
            "modal.knowledge.add": "Add Entry",
            "modal.knowledge.empty": "Save the server first to manage knowledge entries.",
            "modal.knowledge.category": "Category",
            "modal.knowledge.title": "Title",
            "modal.knowledge.content": "Content",
            "modal.knowledge.save": "Save",

            // Sharing tab
            "modal.sharing.desc": "Share this server with other users",
            "modal.sharing.add": "Add Share",
            "modal.sharing.empty": "Save the server first to manage shares.",
            "modal.sharing.user": "User",
            "modal.sharing.expires": "Expires at",
            "modal.sharing.context": "Share context",
            "modal.sharing.save": "Share",

            // Group modal
            "modal.group.new_title": "New Group",
            "modal.group.edit_title": "Edit Group",
            "modal.group.name": "Group Name *",
            "modal.group.color": "Color",
            "modal.group.description": "Description",
            "modal.group.save": "Save Group",

            // Terminal page
            "terminal.disconnected": "Disconnected",
            "terminal.connected": "Connected",
            "terminal.connecting": "Connecting\u2026",
            "terminal.error": "Error",
            "terminal.clear": "Clear terminal",
            "terminal.credentials": "Credentials",
            "terminal.fullscreen": "Fullscreen",
            "terminal.add_tab": "Open another server",
            "terminal.master_pw": "Master Password",
            "terminal.password": "Password / Passphrase",
            "terminal.connect": "Connect",
            "terminal.disconnect": "Disconnect",
            "terminal.reconnect": "Reconnect",
            "terminal.connection_lost": "Connection lost",

            // AI panel
            "ai.title": "AI Assistant",
            "ai.ready": "Ready",
            "ai.thinking": "Thinking\u2026",
            "ai.stop": "Stop AI",
            "ai.close": "Close AI panel",
            "ai.welcome": "Ask me anything about this server or give me a task to run.",
            "ai.placeholder": "Ask AI or describe a task\u2026",
            "ai.suggestion.disk": "Check disk usage and free space",
            "ai.suggestion.memory": "Show memory usage and top processes",
            "ai.suggestion.network": "Check network connections and open ports",
            "ai.suggestion.os": "Show OS info and uptime",

            // Admin dashboard
            "admin.title": "Admin Dashboard",
            "admin.subtitle": "System monitoring and operational overview",
            "admin.online_users": "Online Users",
            "admin.of_registered": "of {n} registered",
            "admin.ai_requests": "AI Requests Today",
            "admin.active_terminals": "Active Terminals",
            "admin.api_calls": "API Calls Today",
            "admin.system_health": "System Health",
            "admin.enabled": "Enabled",
            "admin.disabled": "Disabled",
            "admin.no_providers": "No providers configured",
            "admin.servers": "Servers",
            "admin.active": "active",
            "admin.tasks": "Tasks",
            "admin.in_progress": "in progress",
            "admin.api_usage": "API Usage Today",
            "admin.total_cost": "Total Cost",
            "admin.activity_24h": "Activity (24h)",
            "admin.agent_perf": "Agent Performance",
            "admin.running_now": "Running Now",
            "admin.total_today": "Total Today",
            "admin.success_rate": "Success Rate",
            "admin.succeeded": "succeeded (24h)",
            "admin.failed": "failed (24h)",
            "admin.online_users_list": "Online Users",
            "admin.terminal_sessions": "Terminal Sessions",
            "admin.recent_activity": "Recent Activity",
            "admin.no_users_online": "No users online",
            "admin.no_sessions": "No active sessions",
            "admin.no_activity": "No recent activity",
            "admin.top_users": "Top Users (7 days)",
            "admin.th_user": "User",
            "admin.th_actions": "Total Actions",
            "admin.th_ai": "AI Requests",
            "admin.th_terminal": "Terminal Sessions",
            "admin.no_data": "No data available",
        },

        ru: {
            // Sidebar nav
            "nav.main": "\u0413\u043b\u0430\u0432\u043d\u043e\u0435",
            "nav.dashboard": "\u041f\u0430\u043d\u0435\u043b\u044c",
            "nav.monitor": "\u041c\u043e\u043d\u0438\u0442\u043e\u0440",
            "nav.servers_section": "\u0421\u0435\u0440\u0432\u0435\u0440\u044b",
            "nav.servers": "\u0421\u0435\u0440\u0432\u0435\u0440\u044b",
            "nav.tools": "\u0418\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u044b",
            "nav.chat": "\u0427\u0430\u0442",
            "nav.ide": "IDE",
            "nav.knowledge": "\u0417\u043d\u0430\u043d\u0438\u044f",
            "nav.settings_section": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
            "nav.settings": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
            "user.signout": "\u0412\u044b\u0439\u0442\u0438",
            "skip.main": "\u041f\u0435\u0440\u0435\u0439\u0442\u0438 \u043a \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u043c\u0443 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u043c\u043e\u043c\u0443",

            // Help panel
            "help.title": "\u0421\u043f\u0440\u0430\u0432\u043a\u0430",
            "help.articles": "\u0421\u0442\u0430\u0442\u044c\u0438",
            "help.close": "\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u0441\u043f\u0440\u0430\u0432\u043a\u0443",
            "help.rag.title": "\u0427\u0442\u043e \u0442\u0430\u043a\u043e\u0435 RAG",
            "help.rag.text": "RAG (Retrieval-Augmented Generation) \u2014 \u044d\u0442\u043e \u0440\u0435\u0436\u0438\u043c, \u043f\u0440\u0438 \u043a\u043e\u0442\u043e\u0440\u043e\u043c \u043e\u0442\u0432\u0435\u0442\u044b \u043c\u043e\u0434\u0435\u043b\u0438 \u043f\u043e\u0434\u043a\u0440\u0435\u043f\u043b\u044f\u044e\u0442\u0441\u044f \u043f\u043e\u0438\u0441\u043a\u043e\u043c \u043f\u043e \u0432\u0430\u0448\u0435\u0439 \u0431\u0430\u0437\u0435 \u0437\u043d\u0430\u043d\u0438\u0439. \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u0432 Knowledge Base, \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u00abRAG Enabled\u00bb \u0432 \u0447\u0430\u0442\u0435 \u2014 \u0438 \u043e\u0442\u0432\u0435\u0442\u044b \u0431\u0443\u0434\u0443\u0442 \u043e\u043f\u0438\u0440\u0430\u0442\u044c\u0441\u044f \u043d\u0430 \u044d\u0442\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b. \u0423\u0434\u043e\u0431\u043d\u043e \u0434\u043b\u044f \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0438\u0445 \u0440\u0435\u0433\u043b\u0430\u043c\u0435\u043d\u0442\u043e\u0432, \u0431\u0430\u0437\u044b \u0437\u043d\u0430\u043d\u0438\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438, \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0446\u0438\u0438.",
            "help.workflow.title": "\u0427\u0442\u043e \u0442\u0430\u043a\u043e\u0435 Workflow",
            "help.workflow.text": "Workflow (Orchestrator) \u2014 \u0446\u0435\u043f\u043e\u0447\u043a\u0430 \u00ab\u0432\u0432\u043e\u0434 \u2192 \u0430\u043d\u0430\u043b\u0438\u0437 \u2192 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u0430\u043c\u0438 \u2192 \u043e\u0442\u0432\u0435\u0442\u00bb. \u0410\u0433\u0435\u043d\u0442 \u043f\u043b\u0430\u043d\u0438\u0440\u0443\u0435\u0442 \u0448\u0430\u0433\u0438, \u0432\u044b\u0437\u044b\u0432\u0430\u0435\u0442 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u044b (\u0444\u0430\u0439\u043b\u044b, SSH, \u0432\u0435\u0431) \u0438 \u0444\u043e\u0440\u043c\u0438\u0440\u0443\u0435\u0442 \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442.",
            "help.models.title": "\u041a\u0430\u043a \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u043c\u043e\u0434\u0435\u043b\u044c",
            "help.models.text": "\u041f\u043e\u043a\u0430 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e Cursor Auto. \u0412 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445 (Models) \u0437\u0430\u0434\u0430\u0451\u0442\u0441\u044f \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u0438 \u043c\u043e\u0434\u0435\u043b\u0438 \u0434\u043b\u044f \u0447\u0430\u0442\u0430, \u0430\u0433\u0435\u043d\u0442\u0430 \u0438 RAG; Gemini \u0438 Grok \u0431\u0443\u0434\u0443\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u043f\u043e\u0437\u0436\u0435.",
            "help.server.title": "\u041a\u0430\u043a \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0430\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "help.server.text": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043a \u0441\u0435\u0440\u0432\u0435\u0440\u0430\u043c \u0437\u0430\u0434\u0430\u0451\u0442\u0441\u044f \u0432 \u0440\u0430\u0437\u0434\u0435\u043b\u0435 Servers. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u043a\u043b\u044e\u0447\u0438 (SSH) \u0438 \u0443\u0447\u0451\u0442\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0438\u0437 \u0440\u0430\u0437\u0434\u0435\u043b\u0430 Passwords \u2014 \u043d\u0435 \u0432\u0432\u043e\u0434\u0438\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u0438 \u0432 \u0447\u0430\u0442. \u041e\u0433\u0440\u0430\u043d\u0438\u0447\u044c\u0442\u0435 \u043f\u0440\u0430\u0432\u0430 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u043d\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0435 \u0438 \u0445\u0440\u0430\u043d\u0438\u0442\u0435 \u043a\u043b\u044e\u0447\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 \u0437\u0430\u0449\u0438\u0449\u0451\u043d\u043d\u043e\u043c \u0445\u0440\u0430\u043d\u0438\u043b\u0438\u0449\u0435 (.env, \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440 \u043f\u0430\u0440\u043e\u043b\u0435\u0439), \u043d\u0435 \u0432 \u043a\u043e\u0434\u0435 \u0438 \u043d\u0435 \u0432 \u0447\u0430\u0442\u0435.",

            // Server list page
            "servers.title": "\u0421\u0435\u0440\u0432\u0435\u0440\u044b",
            "servers.add": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "servers.global_rules": "\u0413\u043b\u043e\u0431\u0430\u043b\u044c\u043d\u044b\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u0430",
            "servers.search": "\u041f\u043e\u0438\u0441\u043a \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432\u2026",
            "servers.all_groups": "\u0412\u0441\u0435 \u0433\u0440\u0443\u043f\u043f\u044b",
            "servers.ungrouped": "\u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b",
            "servers.shared_with_me": "\u041e\u0431\u0449\u0438\u0435 \u0434\u043b\u044f \u043c\u0435\u043d\u044f",
            "servers.new_group": "\u041d\u043e\u0432\u0430\u044f \u0433\u0440\u0443\u043f\u043f\u0430",
            "servers.empty.title": "\u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442",
            "servers.empty.text": "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c",
            "servers.test_connection": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435",
            "servers.edit": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "servers.delete": "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "servers.edit_group": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",

            // Server modal
            "modal.server.add_title": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "modal.server.edit_title": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "modal.tab.basic": "\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0435",
            "modal.tab.network": "\u0421\u0435\u0442\u044c",
            "modal.tab.context": "\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442",
            "modal.tab.knowledge": "\u0417\u043d\u0430\u043d\u0438\u044f",
            "modal.tab.sharing": "\u0414\u043e\u0441\u0442\u0443\u043f",
            "modal.server.name": "\u0418\u043c\u044f \u0441\u0435\u0440\u0432\u0435\u0440\u0430 *",
            "modal.server.host": "\u0425\u043e\u0441\u0442 / IP *",
            "modal.server.port": "\u041f\u043e\u0440\u0442",
            "modal.server.username": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c *",
            "modal.server.group": "\u0413\u0440\u0443\u043f\u043f\u0430",
            "modal.server.no_group": "\u2014 \u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b \u2014",
            "modal.server.type": "\u0422\u0438\u043f \u0441\u0435\u0440\u0432\u0435\u0440\u0430",
            "modal.server.auth": "\u0410\u0443\u0442\u0435\u043d\u0442\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044f",
            "modal.server.password": "\u041f\u0430\u0440\u043e\u043b\u044c",
            "modal.server.key_path": "\u041f\u0443\u0442\u044c \u043a SSH-\u043a\u043b\u044e\u0447\u0443",
            "modal.server.save": "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            "modal.cancel": "\u041e\u0442\u043c\u0435\u043d\u0430",
            "modal.server.crypto_info": "\u041f\u0430\u0440\u043e\u043b\u0438 \u0437\u0430\u0448\u0438\u0444\u0440\u043e\u0432\u0430\u043d\u044b AES-256. \u0423\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u043c\u0430\u0441\u0442\u0435\u0440-\u043f\u0430\u0440\u043e\u043b\u044c \u0447\u0435\u0440\u0435\u0437 \u0438\u043a\u043e\u043d\u043a\u0443 \u0437\u0430\u043c\u043a\u0430 \u0432 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u0435 \u0438\u043b\u0438 \u0447\u0435\u0440\u0435\u0437 \u043f\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u0443\u044e MASTER_PASSWORD.",

            // Network tab
            "modal.network.proxy": "HTTP \u041f\u0440\u043e\u043a\u0441\u0438",
            "modal.network.proxy_desc": "\u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u043f\u0440\u043e\u043a\u0441\u0438 \u0434\u043b\u044f \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f",
            "modal.network.vpn": "VPN \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u0435\u043d",
            "modal.network.vpn_desc": "\u0421\u0435\u0440\u0432\u0435\u0440 \u0437\u0430 VPN",
            "modal.network.firewall": "\u0417\u0430 \u0444\u0430\u0439\u0440\u0432\u043e\u043b\u043e\u043c",
            "modal.network.firewall_desc": "\u041e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u043d\u044b\u0439 \u0441\u0435\u0442\u0435\u0432\u043e\u0439 \u0434\u043e\u0441\u0442\u0443\u043f",
            "modal.network.config": "\u0421\u0435\u0442\u0435\u0432\u0430\u044f \u043a\u043e\u043d\u0444\u0438\u0433\u0443\u0440\u0430\u0446\u0438\u044f (JSON)",

            // Context tab
            "modal.context.notes": "\u0417\u0430\u043c\u0435\u0442\u043a\u0438",
            "modal.context.corporate": "\u041a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442",

            // Knowledge tab
            "modal.knowledge.desc": "\u0417\u043d\u0430\u043d\u0438\u044f \u0441\u0435\u0440\u0432\u0435\u0440\u0430: \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0435 AI \u0438 \u0440\u0443\u0447\u043d\u044b\u0435 \u0437\u0430\u043f\u0438\u0441\u0438",
            "modal.knowledge.add": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
            "modal.knowledge.empty": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440 \u0434\u043b\u044f \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u0437\u043d\u0430\u043d\u0438\u044f\u043c\u0438.",
            "modal.knowledge.category": "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f",
            "modal.knowledge.title": "\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a",
            "modal.knowledge.content": "\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435",
            "modal.knowledge.save": "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c",

            // Sharing tab
            "modal.sharing.desc": "\u041f\u043e\u0434\u0435\u043b\u0438\u0442\u044c\u0441\u044f \u044d\u0442\u0438\u043c \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c \u0441 \u0434\u0440\u0443\u0433\u0438\u043c\u0438 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f\u043c\u0438",
            "modal.sharing.add": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f",
            "modal.sharing.empty": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440 \u0434\u043b\u044f \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u0434\u043e\u0441\u0442\u0443\u043f\u043e\u043c.",
            "modal.sharing.user": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c",
            "modal.sharing.expires": "\u0414\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0434\u043e",
            "modal.sharing.context": "\u041f\u0435\u0440\u0435\u0434\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442",
            "modal.sharing.save": "\u041f\u043e\u0434\u0435\u043b\u0438\u0442\u044c\u0441\u044f",

            // Group modal
            "modal.group.new_title": "\u041d\u043e\u0432\u0430\u044f \u0433\u0440\u0443\u043f\u043f\u0430",
            "modal.group.edit_title": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",
            "modal.group.name": "\u0418\u043c\u044f \u0433\u0440\u0443\u043f\u043f\u044b *",
            "modal.group.color": "\u0426\u0432\u0435\u0442",
            "modal.group.description": "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435",
            "modal.group.save": "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443",

            // Terminal page
            "terminal.disconnected": "\u041e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
            "terminal.connected": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
            "terminal.connecting": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435\u2026",
            "terminal.error": "\u041e\u0448\u0438\u0431\u043a\u0430",
            "terminal.clear": "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b",
            "terminal.credentials": "\u0423\u0447\u0451\u0442\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435",
            "terminal.fullscreen": "\u041f\u043e\u043b\u043d\u044b\u0439 \u044d\u043a\u0440\u0430\u043d",
            "terminal.add_tab": "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0434\u0440\u0443\u0433\u043e\u0439 \u0441\u0435\u0440\u0432\u0435\u0440",
            "terminal.master_pw": "\u041c\u0430\u0441\u0442\u0435\u0440-\u043f\u0430\u0440\u043e\u043b\u044c",
            "terminal.password": "\u041f\u0430\u0440\u043e\u043b\u044c / \u041f\u0430\u0440\u043e\u043b\u044c\u043d\u0430\u044f \u0444\u0440\u0430\u0437\u0430",
            "terminal.connect": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
            "terminal.disconnect": "\u041e\u0442\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
            "terminal.reconnect": "\u041f\u0435\u0440\u0435\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f",
            "terminal.connection_lost": "\u0421\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043d\u043e",

            // AI panel
            "ai.title": "AI-\u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442",
            "ai.ready": "\u0413\u043e\u0442\u043e\u0432",
            "ai.thinking": "\u0414\u0443\u043c\u0430\u044e\u2026",
            "ai.stop": "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c AI",
            "ai.close": "\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u043f\u0430\u043d\u0435\u043b\u044c AI",
            "ai.welcome": "\u0421\u043f\u0440\u043e\u0441\u0438\u0442\u0435 \u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0435 \u0438\u043b\u0438 \u043e\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443 \u0434\u043b\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044f.",
            "ai.placeholder": "\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u0438\u043b\u0438 \u043e\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443\u2026",
            "ai.suggestion.disk": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435 \u0434\u0438\u0441\u043a\u0430 \u0438 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e\u0435 \u043c\u0435\u0441\u0442\u043e",
            "ai.suggestion.memory": "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u043f\u0430\u043c\u044f\u0442\u044c \u0438 \u0442\u043e\u043f \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0432",
            "ai.suggestion.network": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u0435\u0442\u0435\u0432\u044b\u0435 \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u044f \u0438 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0435 \u043f\u043e\u0440\u0442\u044b",
            "ai.suggestion.os": "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0438\u043d\u0444\u043e \u043e\u0431 \u041e\u0421 \u0438 \u0430\u043f\u0442\u0430\u0439\u043c",

            // Admin dashboard
            "admin.title": "\u041f\u0430\u043d\u0435\u043b\u044c \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430",
            "admin.subtitle": "\u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433 \u0441\u0438\u0441\u0442\u0435\u043c\u044b \u0438 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0439 \u043e\u0431\u0437\u043e\u0440",
            "admin.online_users": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438 \u043e\u043d\u043b\u0430\u0439\u043d",
            "admin.of_registered": "\u0438\u0437 {n} \u0437\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043e",
            "admin.ai_requests": "\u0417\u0430\u043f\u0440\u043e\u0441\u044b AI \u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            "admin.active_terminals": "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u044b",
            "admin.api_calls": "\u0412\u044b\u0437\u043e\u0432\u044b API \u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            "admin.system_health": "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u0441\u0438\u0441\u0442\u0435\u043c\u044b",
            "admin.enabled": "\u0412\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
            "admin.disabled": "\u041e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
            "admin.no_providers": "\u041f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440\u044b \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u044b",
            "admin.servers": "\u0421\u0435\u0440\u0432\u0435\u0440\u044b",
            "admin.active": "\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445",
            "admin.tasks": "\u0417\u0430\u0434\u0430\u0447\u0438",
            "admin.in_progress": "\u0432 \u0440\u0430\u0431\u043e\u0442\u0435",
            "admin.api_usage": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435 API \u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            "admin.total_cost": "\u041e\u0431\u0449\u0430\u044f \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c",
            "admin.activity_24h": "\u0410\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c (24\u0447)",
            "admin.agent_perf": "\u041f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u0430\u0433\u0435\u043d\u0442\u043e\u0432",
            "admin.running_now": "\u0420\u0430\u0431\u043e\u0442\u0430\u044e\u0442 \u0441\u0435\u0439\u0447\u0430\u0441",
            "admin.total_today": "\u0412\u0441\u0435\u0433\u043e \u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            "admin.success_rate": "\u0423\u0441\u043f\u0435\u0448\u043d\u043e\u0441\u0442\u044c",
            "admin.succeeded": "\u0443\u0441\u043f\u0435\u0448\u043d\u043e (24\u0447)",
            "admin.failed": "\u043e\u0448\u0438\u0431\u043a\u0438 (24\u0447)",
            "admin.online_users_list": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438 \u043e\u043d\u043b\u0430\u0439\u043d",
            "admin.terminal_sessions": "\u0421\u0435\u0441\u0441\u0438\u0438 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u043e\u0432",
            "admin.recent_activity": "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c",
            "admin.no_users_online": "\u041d\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 \u043e\u043d\u043b\u0430\u0439\u043d",
            "admin.no_sessions": "\u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0441\u0435\u0441\u0441\u0438\u0439",
            "admin.no_activity": "\u041d\u0435\u0442 \u043d\u0435\u0434\u0430\u0432\u043d\u0435\u0439 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u0438",
            "admin.top_users": "\u0422\u043e\u043f \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 (7 \u0434\u043d\u0435\u0439)",
            "admin.th_user": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c",
            "admin.th_actions": "\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u044f",
            "admin.th_ai": "\u0417\u0430\u043f\u0440\u043e\u0441\u044b AI",
            "admin.th_terminal": "\u0421\u0435\u0441\u0441\u0438\u0438 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u043e\u0432",
            "admin.no_data": "\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445",
        },
    };

    function getLang() {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
    }

    function setLang(lang) {
        if (!TRANSLATIONS[lang]) return;
        localStorage.setItem(STORAGE_KEY, lang);
        applyTranslations(lang);
        updateToggleButtons(lang);
        document.documentElement.setAttribute("lang", lang);
    }

    function t(key, lang) {
        lang = lang || getLang();
        var dict = TRANSLATIONS[lang] || TRANSLATIONS[DEFAULT_LANG];
        return dict[key] || TRANSLATIONS[DEFAULT_LANG][key] || key;
    }

    function applyTranslations(lang) {
        lang = lang || getLang();
        var els = document.querySelectorAll("[data-i18n]");
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            var key = el.getAttribute("data-i18n");
            var val = t(key, lang);
            if (val === key) continue;

            if (el.tagName === "INPUT" && el.type !== "submit" && el.type !== "button") {
                el.placeholder = val;
            } else if (el.tagName === "OPTION") {
                el.textContent = val;
            } else {
                el.textContent = val;
            }
        }

        var titleEls = document.querySelectorAll("[data-i18n-title]");
        for (var j = 0; j < titleEls.length; j++) {
            var tel = titleEls[j];
            var tkey = tel.getAttribute("data-i18n-title");
            var tval = t(tkey, lang);
            if (tval !== tkey) {
                tel.setAttribute("title", tval);
                tel.setAttribute("aria-label", tval);
            }
        }
    }

    function updateToggleButtons(lang) {
        var btns = document.querySelectorAll(".lang-toggle-btn");
        for (var i = 0; i < btns.length; i++) {
            var btn = btns[i];
            if (btn.dataset.lang === lang) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        }
    }

    function init() {
        var lang = getLang();
        document.documentElement.setAttribute("lang", lang);
        applyTranslations(lang);
        updateToggleButtons(lang);

        document.addEventListener("click", function (e) {
            var btn = e.target.closest(".lang-toggle-btn");
            if (btn && btn.dataset.lang) {
                setLang(btn.dataset.lang);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.WEU_I18N = { t: t, setLang: setLang, getLang: getLang, applyTranslations: applyTranslations };
})();
