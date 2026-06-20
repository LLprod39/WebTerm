from __future__ import annotations

from django.dispatch import Signal

# Fired when a server-domain alert is created and remains unresolved.
server_alert_opened = Signal()
