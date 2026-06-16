"""Built-in pipeline templates for Agent Studio.

Each template defines nodes and edges in React Flow format.
Node types: trigger/manual, agent/react, agent/multi, agent/ssh_cmd,
            agent/llm_query, logic/condition, logic/wait, logic/human_approval,
            output/report, output/webhook, output/email, output/telegram
"""

from .pipeline_templates.core import CORE_TEMPLATES
from .pipeline_templates.pilot_delivery import PILOT_DELIVERY_TEMPLATES
from .pipeline_templates.pilot_maintenance import PILOT_MAINTENANCE_TEMPLATES
from .pipeline_templates.pilot_operations import PILOT_OPERATIONS_TEMPLATES
from .pipeline_templates.server_update import SERVER_UPDATE_APPROVAL_TEMPLATE

PIPELINE_TEMPLATES = [
    *CORE_TEMPLATES,
    SERVER_UPDATE_APPROVAL_TEMPLATE,
    *PILOT_DELIVERY_TEMPLATES,
    *PILOT_OPERATIONS_TEMPLATES,
    *PILOT_MAINTENANCE_TEMPLATES,
]
