import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

const Tabs = TabsPrimitive.Root;

type PillRect = { x: number; y: number; w: number; h: number };

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, children, ...props }, ref) => {
  const listRef = React.useRef<HTMLDivElement | null>(null);
  const [pill, setPill] = React.useState<PillRect | null>(null);
  const reduceMotion = useReducedMotion();

  const setRefs = React.useCallback(
    (node: HTMLDivElement | null) => {
      listRef.current = node;
      if (typeof ref === "function") ref(node);
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
    },
    [ref],
  );

  const updatePill = React.useCallback(() => {
    const list = listRef.current;
    if (!list) return;

    const active = list.querySelector<HTMLElement>('[role="tab"][data-state="active"]');
    if (!active) {
      setPill(null);
      return;
    }

    // Viewport-relative delta → position inside the list's padding box (absolute child).
    // Do not add scrollLeft: absolute children of the scroll container are not scrolled content.
    const listBox = list.getBoundingClientRect();
    const tabBox = active.getBoundingClientRect();

    setPill({
      // clientLeft/Top = border width; absolute coords are relative to the padding edge
      x: tabBox.left - listBox.left - list.clientLeft,
      y: tabBox.top - listBox.top - list.clientTop,
      w: Math.max(tabBox.width, 1),
      h: Math.max(tabBox.height, 1),
    });
  }, []);

  React.useLayoutEffect(() => {
    updatePill();
    const list = listRef.current;
    if (!list) return;

    const ro = new ResizeObserver(() => updatePill());
    ro.observe(list);
    list.querySelectorAll('[role="tab"]').forEach((tab) => ro.observe(tab));

    const mo = new MutationObserver(() => {
      // Radix flips data-state; remeasure after layout settles.
      requestAnimationFrame(updatePill);
    });
    mo.observe(list, {
      attributes: true,
      subtree: true,
      attributeFilter: ["data-state", "class", "style"],
      childList: true,
    });

    list.addEventListener("scroll", updatePill, { passive: true });
    window.addEventListener("resize", updatePill);

    const t1 = window.setTimeout(updatePill, 0);
    const t2 = window.setTimeout(updatePill, 100);

    return () => {
      ro.disconnect();
      mo.disconnect();
      list.removeEventListener("scroll", updatePill);
      window.removeEventListener("resize", updatePill);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [updatePill, children]);

  return (
    <TabsPrimitive.List
      ref={setRefs}
      className={cn(
        // overflow-visible so the sliding pill is never clipped mid-animation
        "relative inline-flex h-10 items-center justify-center overflow-visible rounded-sm border border-border bg-surface-0 p-0.5 text-muted-foreground",
        className,
      )}
      {...props}
    >
      {pill ? (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute z-[1] rounded-sm bg-primary shadow-elev-1"
          initial={false}
          animate={{
            x: pill.x,
            y: pill.y,
            width: pill.w,
            height: pill.h,
          }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 420, damping: 32, mass: 0.75 }
          }
          style={{
            left: 0,
            top: 0,
          }}
        />
      ) : null}
      {children}
    </TabsPrimitive.List>
  );
});
TabsList.displayName = TabsPrimitive.List.displayName;

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      // z-10 above the sliding pill; active fill is the pill, not a solid button bg
      "relative z-10 inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-xs font-medium tracking-wide",
      "text-muted-foreground ring-offset-background transition-colors duration-150",
      "hover:text-foreground",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      "disabled:pointer-events-none disabled:opacity-50",
      className,
      // Force transparent after consumer className so the sliding pill is the only active fill
      "data-[state=active]:!bg-transparent data-[state=active]:text-primary-foreground data-[state=active]:!shadow-none",
      "data-[state=active]:hover:text-primary-foreground",
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      "data-[state=active]:animate-in data-[state=active]:fade-in-0 data-[state=active]:duration-150",
      "motion-reduce:data-[state=active]:animate-none",
      className,
    )}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
