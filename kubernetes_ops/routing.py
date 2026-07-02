from django.urls import path

from kubernetes_ops.admin_interactive_shell_consumers import (
    KubernetesAdminClusterTerminalStreamConsumer,
    KubernetesAdminNodeDebugStreamConsumer,
)
from kubernetes_ops.consumers import (
    KubernetesAdminExecStreamConsumer,
    KubernetesAdminLogStreamConsumer,
    KubernetesAdminPortForwardStreamConsumer,
    KubernetesAdminWatchStreamConsumer,
)

websocket_urlpatterns = [
    path("ws/kubernetes/admin/logs/<uuid:session_id>/", KubernetesAdminLogStreamConsumer.as_asgi()),
    path("ws/kubernetes/admin/watch/<uuid:session_id>/", KubernetesAdminWatchStreamConsumer.as_asgi()),
    path("ws/kubernetes/admin/exec/<uuid:session_id>/", KubernetesAdminExecStreamConsumer.as_asgi()),
    path("ws/kubernetes/admin/port-forward/<uuid:session_id>/", KubernetesAdminPortForwardStreamConsumer.as_asgi()),
    path("ws/kubernetes/admin/terminal/<uuid:session_id>/", KubernetesAdminClusterTerminalStreamConsumer.as_asgi()),
    path("ws/kubernetes/admin/node-debug/<uuid:session_id>/", KubernetesAdminNodeDebugStreamConsumer.as_asgi()),
]
