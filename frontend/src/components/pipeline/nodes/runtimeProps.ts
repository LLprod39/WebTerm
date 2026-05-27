export function getNodeRuntimeProps(data: unknown) {
  const d = (data || {}) as Record<string, unknown>;
  return {
    status: typeof d.status === "string" ? d.status : undefined,
    statusLabel: typeof d.status_label === "string" ? d.status_label : undefined,
    isCurrentStep: Boolean(d.is_current_step),
    isInActivePath: Boolean(d.is_in_active_path),
    isQueuedStep: Boolean(d.is_queued_step),
    isEntryPoint: Boolean(d.is_entry_point),
  };
}
