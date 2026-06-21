import type { ReactNode } from "react";
import { toast as sonnerToast, type ExternalToast } from "sonner";

import type { StatusTone } from "@/design/status";

type NotifyVariant = Exclude<StatusTone, "ai"> | "default" | "error";

export interface NotifyOptions {
  title: ReactNode;
  description?: ReactNode;
  variant?: NotifyVariant;
  action?: ExternalToast["action"];
  duration?: number;
}

function show({ title, description, variant = "default", action, duration }: NotifyOptions) {
  const options: ExternalToast = {
    description,
    action,
    duration,
  };

  if (variant === "success") return sonnerToast.success(title, options);
  if (variant === "warning") return sonnerToast.warning(title, options);
  if (variant === "danger" || variant === "error") return sonnerToast.error(title, options);
  if (variant === "info") return sonnerToast.info(title, options);
  return sonnerToast(title, options);
}

export const notify = {
  show,
  success: (options: Omit<NotifyOptions, "variant">) => show({ ...options, variant: "success" }),
  warning: (options: Omit<NotifyOptions, "variant">) => show({ ...options, variant: "warning" }),
  error: (options: Omit<NotifyOptions, "variant">) => show({ ...options, variant: "error" }),
  info: (options: Omit<NotifyOptions, "variant">) => show({ ...options, variant: "info" }),
  dismiss: sonnerToast.dismiss,
};
