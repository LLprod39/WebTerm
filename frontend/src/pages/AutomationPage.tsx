import { Navigate } from "react-router-dom";

/** Legacy route: playbooks live under Servers → Playbooks tab. */
export default function AutomationPage() {
  return <Navigate to="/servers" replace state={{ mainTab: "playbook" }} />;
}
