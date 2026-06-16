import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

type RouteState = { openRunDialog?: boolean } | null;
type ManualTriggerOption = { node_id: string };

export function useRouteRunDialogRequest({
  hasHydratedPipeline,
  manualTriggerOptions,
  setRunDialogOpen,
  setRunEntryNodeId,
}: {
  hasHydratedPipeline: boolean;
  manualTriggerOptions: ManualTriggerOption[];
  setRunDialogOpen: (value: boolean) => void;
  setRunEntryNodeId: (value: string) => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const consumedRef = useRef(false);

  useEffect(() => {
    consumedRef.current = false;
  }, [location.pathname]);

  useEffect(() => {
    const state = location.state as RouteState;
    if (!state?.openRunDialog || consumedRef.current || !hasHydratedPipeline) return;
    consumedRef.current = true;
    if (manualTriggerOptions.length === 1) setRunEntryNodeId(manualTriggerOptions[0].node_id);
    setRunDialogOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [hasHydratedPipeline, location.pathname, location.state, manualTriggerOptions, navigate, setRunDialogOpen, setRunEntryNodeId]);
}
