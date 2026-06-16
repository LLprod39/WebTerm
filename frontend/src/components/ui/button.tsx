import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex touch-manipulation select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium ring-offset-background transition-[color,background-color,border-color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-y-px disabled:pointer-events-none disabled:translate-y-0 disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[0_0_0_1px_hsl(var(--primary)_/_0.22),0_10px_24px_hsl(var(--primary)_/_0.12)] hover:bg-primary/90 hover:shadow-[0_0_0_1px_hsl(var(--primary)_/_0.3),0_14px_30px_hsl(var(--primary)_/_0.16)]",
        destructive:
          "bg-destructive text-destructive-foreground shadow-[0_0_0_1px_hsl(var(--destructive)_/_0.24)] hover:bg-destructive/90",
        outline: "border border-border/80 bg-card/70 text-foreground shadow-sm hover:border-border hover:bg-secondary/70",
        secondary: "border border-border/70 bg-secondary/80 text-secondary-foreground hover:bg-secondary",
        ghost: "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        xs: "h-8 rounded-md px-2.5 text-xs",
        sm: "h-9 rounded-lg px-3",
        lg: "h-11 rounded-lg px-8",
        icon: "h-10 w-10 rounded-lg",
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
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...(!asChild ? { type: type ?? "button" } : type ? { type } : {})}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
