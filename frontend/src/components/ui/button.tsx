import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex touch-manipulation select-none items-center justify-center gap-2 whitespace-nowrap rounded-sm text-xs font-medium tracking-wide ring-offset-background transition-[color,background-color,border-color,box-shadow,transform] duration-150 ease-standard focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-x-px active:translate-y-px disabled:pointer-events-none disabled:translate-y-0 disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-primary bg-primary text-primary-foreground shadow-hard-sm hover:bg-primary-hover hover:shadow-hard",
        destructive:
          "border border-destructive bg-destructive text-destructive-foreground shadow-hard-sm hover:bg-destructive/90",
        outline:
          "border border-border-strong bg-transparent text-foreground hover:border-muted-foreground hover:bg-secondary/60",
        secondary:
          "border border-border bg-secondary text-secondary-foreground hover:border-border-strong hover:bg-surface-2",
        ghost: "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
        ai: "border border-ai/50 bg-ai text-ai-foreground shadow-hard-sm hover:bg-ai/90",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        xs: "h-8 rounded-sm px-3 text-2xs",
        sm: "h-8 rounded-sm px-3",
        lg: "h-10 rounded-sm px-8 text-sm",
        icon: "h-9 w-9 rounded-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** When true, shows a leading spinner and disables the button. Ignored when asChild. */
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, loading = false, disabled, children, ...props }, ref) => {
    // Slot (asChild) requires exactly one child — never inject the spinner there.
    if (asChild) {
      return (
        <Slot
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...(type ? { type } : {})}
          {...props}
        >
          {children}
        </Slot>
      );
    }
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        type={type ?? "button"}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? <Loader2 className="animate-spin" aria-hidden /> : null}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
