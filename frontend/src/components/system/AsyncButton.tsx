import { Loader2 } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { Button } from "@/components/ui/button";

type AsyncButtonProps = ComponentProps<typeof Button> & {
  loading?: boolean;
  loadingLabel?: ReactNode;
};

export function AsyncButton({ loading = false, loadingLabel, children, disabled, ...props }: AsyncButtonProps) {
  return (
    <Button disabled={disabled || loading} {...props}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
      {loading && loadingLabel ? loadingLabel : children}
    </Button>
  );
}
