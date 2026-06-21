import type { ReactNode } from "react";
import { notify, type NotifyOptions } from "@/lib/notify";

type Toast = {
  title?: ReactNode;
  description?: ReactNode;
  variant?: "default" | "destructive";
  action?: NotifyOptions["action"];
  duration?: number;
};

type ToasterToast = Toast & {
  id: string;
};

interface State {
  toasts: ToasterToast[];
}

function toast({ ...props }: Toast) {
  const title = props.title ?? props.description ?? "";
  const id = notify.show({
    title,
    description: props.title ? props.description : undefined,
    variant: props.variant === "destructive" ? "error" : "default",
    action: props.action,
    duration: props.duration,
  });
  const dismiss = () => notify.dismiss(id);

  return {
    id: String(id),
    dismiss,
    update: (next: Toast) => {
      notify.dismiss(id);
      return toast(next);
    },
  };
}

function useToast() {
  const state: State = { toasts: [] };

  return {
    ...state,
    toast,
    dismiss: (toastId?: string) => notify.dismiss(toastId),
  };
}

export { useToast, toast };
