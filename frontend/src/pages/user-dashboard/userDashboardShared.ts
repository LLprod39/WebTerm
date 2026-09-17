export const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 bg-primary/5",
  success: "border-success/25 bg-success/5",
  warning: "border-warning/25 bg-warning/5",
  danger: "border-destructive/25 bg-destructive/5",
};

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

export function cpuToneClass(value: number): string {
  return value > 80 ? "text-destructive" : value > 60 ? "text-warning" : "text-success";
}
