import { UiStylePicker } from "@/components/UiStylePicker";

/** Backward-compatible dashboard entry point for the shared appearance picker. */
export function DashboardUiStyleSwitcher({ className }: { className?: string }) {
  return <UiStylePicker className={className} />;
}
