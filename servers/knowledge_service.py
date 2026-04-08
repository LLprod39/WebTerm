"""
Server Knowledge Service

Collects and manages knowledge context for AI agents:
- Global rules (per user)
- Group rules
- Server-specific knowledge
- AI-generated insights

Usage:
    from servers.knowledge_service import ServerKnowledgeService

    # Get full context for a server
    context = ServerKnowledgeService.get_full_context(server, user)

    # Save AI-generated knowledge after task
    ServerKnowledgeService.save_ai_knowledge(
        server=server,
        title="Обнаружен nginx",
        content="На сервере установлен nginx 1.24, конфиг в /etc/nginx/",
        category="services",
        task_id=123
    )
"""
from typing import Optional, List, Dict, Any
from django.contrib.auth.models import User
from django.utils import timezone
from loguru import logger

from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.memory.store import DjangoServerMemoryStore


class ServerKnowledgeService:
    """Service for managing server knowledge and context"""

    _memory_store = DjangoServerMemoryStore()

    @staticmethod
    def get_full_context(server, user: User) -> str:
        """
        Get full hierarchical context for a server.

        Order (from general to specific):
        1. Global rules (user-level)
        2. Group rules + group knowledge
        3. Server notes + corporate_context
        4. Server knowledge (AI-generated + manual)

        Args:
            server: Server instance
            user: User requesting context

        Returns:
            Formatted context string for AI
        """
        from servers.models import GlobalServerRules, ServerKnowledge, ServerGroupKnowledge

        parts = []

        # 1. Global rules
        try:
            global_rules = GlobalServerRules.objects.filter(user=user).first()
            if global_rules:
                ctx = global_rules.get_context_for_ai()
                if ctx:
                    parts.append(ctx)
        except Exception as e:
            logger.debug(f"No global rules: {e}")

        # 2. Group context
        if server.group:
            group = server.group
            group_ctx = group.get_context_for_ai()
            if group_ctx:
                parts.append(f"=== ПРАВИЛА ГРУППЫ '{group.name}' ===\n{group_ctx}")

            # Group knowledge
            group_knowledge = ServerGroupKnowledge.objects.filter(
                group=group,
                is_active=True
            ).order_by('-updated_at')[:10]

            if group_knowledge:
                knowledge_texts = [f"• [{k.category}] {k.title}: {k.content}" for k in group_knowledge]
                parts.append(f"=== ЗНАНИЯ ГРУППЫ ===\n" + "\n".join(knowledge_texts))

        # 3. Server basic info
        server_parts = []

        if server.notes:
            server_parts.append(f"Заметки: {server.notes}")

        if server.corporate_context:
            server_parts.append(f"Корпоративный контекст: {server.corporate_context}")

        network_ctx = server.get_network_context_summary()
        if network_ctx and network_ctx != "Стандартная сеть":
            server_parts.append(f"Сеть: {network_ctx}")

        if server_parts:
            parts.append(f"=== СЕРВЕР '{server.name}' ===\n" + "\n".join(server_parts))

        # 4. Server knowledge (AI-generated + manual)
        knowledge = ServerKnowledge.objects.filter(
            server=server,
            is_active=True
        ).order_by('-updated_at')[:20]

        if knowledge:
            knowledge_by_category = {}
            for k in knowledge:
                cat = k.get_category_display()
                if cat not in knowledge_by_category:
                    knowledge_by_category[cat] = []
                knowledge_by_category[cat].append(f"• {k.title}: {k.content}")

            knowledge_text = []
            for cat, items in knowledge_by_category.items():
                knowledge_text.append(f"\n[{cat}]")
                knowledge_text.extend(items[:5])  # Max 5 per category

            parts.append(f"=== НАКОПЛЕННЫЕ ЗНАНИЯ О СЕРВЕРЕ ===\n" + "\n".join(knowledge_text))

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def get_ops_memory_prompt(server, user: User | None = None) -> str:
        """Get a compacted DevOps-first memory prompt for a server."""
        try:
            card = ServerKnowledgeService._memory_store._get_server_card_sync(server.id)
            return render_server_cards_prompt([card], max_cards=1, max_records=4)
        except Exception as exc:
            logger.debug(f"Failed to build ops memory prompt: {exc}")
            return ServerKnowledgeService.get_full_context(server, user) if user else ""

    @staticmethod
    def get_forbidden_commands(server, user: User) -> List[str]:
        """
        Get list of forbidden commands for a server.
        Combines: global + group + server-specific forbidden commands.
        """
        from servers.models import GlobalServerRules

        forbidden = set()

        # Global
        try:
            global_rules = GlobalServerRules.objects.filter(user=user).first()
            if global_rules and global_rules.forbidden_commands:
                forbidden.update(global_rules.forbidden_commands)
        except Exception:
            pass

        # Group
        if server.group and server.group.forbidden_commands:
            forbidden.update(server.group.forbidden_commands)

        return list(forbidden)

    @staticmethod
    def get_environment_vars(server, user: User) -> Dict[str, str]:
        """
        Get merged environment variables for a server.
        Priority: server network_config > group > global
        """
        from servers.models import GlobalServerRules

        env_vars = {}

        # Global
        try:
            global_rules = GlobalServerRules.objects.filter(user=user).first()
            if global_rules and global_rules.environment_vars:
                env_vars.update(global_rules.environment_vars)
        except Exception:
            pass

        # Group
        if server.group and server.group.environment_vars:
            env_vars.update(server.group.environment_vars)

        # Server-specific from network_config
        if server.network_config and server.network_config.get('env_vars'):
            env_vars.update(server.network_config['env_vars'])

        return env_vars

    @staticmethod
    def save_ai_knowledge(
        server,
        title: str,
        content: str,
        category: str = 'other',
        task_id: int = None,
        user: User = None,
        confidence: float = 0.9
    ):
        """
        Save AI-generated knowledge about a server.

        Args:
            server: Server instance
            title: Short title for the knowledge
            content: Full content
            category: Category (system, services, network, etc.)
            task_id: ID of the task that generated this knowledge
            user: User who initiated the task
            confidence: Confidence level (0.0-1.0)
        """
        from servers.models import ServerKnowledge
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        # Check for duplicates (similar title + category)
        existing = ServerKnowledge.objects.filter(
            server=server,
            category=category,
            title__iexact=title.strip()
        ).first()

        if existing:
            # Update existing knowledge
            existing.content = content
            existing.confidence = max(existing.confidence, confidence)
            existing.updated_at = timezone.now()
            existing.task_id = task_id or existing.task_id
            existing.save()
            DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(existing.id)
            logger.info(f"Updated server knowledge: {server.name} - {title}")
            return existing

        # Create new
        knowledge = ServerKnowledge.objects.create(
            server=server,
            category=category,
            title=title.strip(),
            content=content,
            source='ai_task' if task_id else 'ai_auto',
            confidence=confidence,
            task_id=task_id,
            created_by=user
        )
        DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(knowledge.id)
        logger.info(f"Created server knowledge: {server.name} - {title}")
        return knowledge

    @staticmethod
    def analyze_and_save_knowledge(
        server,
        command_output: str,
        command: str,
        task_id: int = None,
        user: User = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze command output and extract knowledge.
        This is called after task execution to learn about the server.

        Returns list of created knowledge items.
        """
        created = []

        # Simple pattern matching for common discoveries
        output_lower = command_output.lower()

        # Detect OS
        if 'ubuntu' in output_lower:
            k = ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="ОС Ubuntu",
                content=f"Обнаружена ОС Ubuntu. Команда: {command[:100]}",
                category='system',
                task_id=task_id,
                user=user
            )
            created.append({'id': k.id, 'title': k.title})

        elif 'centos' in output_lower or 'red hat' in output_lower:
            k = ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="ОС CentOS/RHEL",
                content=f"Обнаружена ОС CentOS или Red Hat",
                category='system',
                task_id=task_id,
                user=user
            )
            created.append({'id': k.id, 'title': k.title})

        # Detect services
        services_detected = []
        for service in ['nginx', 'apache', 'mysql', 'postgresql', 'redis', 'docker', 'kubernetes']:
            if service in output_lower:
                services_detected.append(service)

        if services_detected:
            k = ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="Обнаруженные сервисы",
                content=f"Сервисы: {', '.join(services_detected)}",
                category='services',
                task_id=task_id,
                user=user
            )
            created.append({'id': k.id, 'title': k.title})

        # Detect disk issues
        if 'no space left' in output_lower or ('disk' in output_lower and '100%' in output_lower):
            k = ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="Проблема с диском",
                content="Обнаружена нехватка места на диске",
                category='issues',
                task_id=task_id,
                user=user,
                confidence=0.95
            )
            created.append({'id': k.id, 'title': k.title})

        # Detect memory issues
        if 'out of memory' in output_lower or 'oom' in output_lower:
            k = ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="Проблема с памятью",
                content="Обнаружена нехватка оперативной памяти (OOM)",
                category='issues',
                task_id=task_id,
                user=user,
                confidence=0.95
            )
            created.append({'id': k.id, 'title': k.title})

        return created

    @staticmethod
    def get_or_create_global_rules(user: User):
        """Get or create global rules for user"""
        from servers.models import GlobalServerRules

        rules, created = GlobalServerRules.objects.get_or_create(
            user=user,
            defaults={
                'rules': '',
                'forbidden_commands': [],
                'required_checks': [],
                'environment_vars': {}
            }
        )
        return rules

    @staticmethod
    def get_context_summary(server, user: User) -> Dict[str, Any]:
        """Get summary of all context sources (for UI display)"""
        from servers.models import GlobalServerRules, ServerKnowledge, ServerGroupKnowledge

        summary = {
            'has_global_rules': False,
            'has_group_rules': False,
            'has_group_knowledge': 0,
            'has_server_notes': bool(server.notes or server.corporate_context),
            'server_knowledge_count': 0,
            'forbidden_commands_count': 0,
        }

        # Global
        try:
            global_rules = GlobalServerRules.objects.filter(user=user).first()
            if global_rules and (global_rules.rules or global_rules.forbidden_commands):
                summary['has_global_rules'] = True
                summary['forbidden_commands_count'] += len(global_rules.forbidden_commands or [])
        except Exception:
            pass

        # Group
        if server.group:
            if server.group.rules or server.group.forbidden_commands:
                summary['has_group_rules'] = True
                summary['forbidden_commands_count'] += len(server.group.forbidden_commands or [])

            summary['has_group_knowledge'] = ServerGroupKnowledge.objects.filter(
                group=server.group, is_active=True
            ).count()

        # Server knowledge
        summary['server_knowledge_count'] = ServerKnowledge.objects.filter(
            server=server, is_active=True
        ).count()

        return summary
