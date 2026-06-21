import { cn } from "@/lib/utils";

import { resolveServerOs, serverOsLabelKey, type ServerOsInput, type ServerOsKind } from "@/lib/server-os";

import { useI18n } from "@/lib/i18n";

import { osBadgeStyles, osIconSrc } from "@/components/servers/os-icon-map";



const sizeMap = {

  sm: { box: "h-7 w-7 rounded-lg", icon: "h-3.5 w-3.5", text: "text-xs" },

  md: { box: "h-9 w-9 rounded-xl", icon: "h-4 w-4", text: "text-xs" },

  lg: { box: "h-11 w-11 rounded-xl", icon: "h-5 w-5", text: "text-xs" },

} as const;



function OsBrandIcon({ kind, className }: { kind: ServerOsKind; className?: string }) {

  return (

    <img

      src={osIconSrc[kind]}

      alt=""

      aria-hidden

      className={cn("shrink-0 object-contain", className)}

      width={20}

      height={20}

      loading="lazy"

      decoding="async"

    />

  );

}



export function ServerOsBadge({

  kind,

  size = "md",

  showLabel = false,

  className,

}: {

  kind: ServerOsKind;

  size?: keyof typeof sizeMap;

  showLabel?: boolean;

  className?: string;

}) {

  const { t } = useI18n();

  const style = osBadgeStyles[kind];

  const dim = sizeMap[size];

  const label = t(serverOsLabelKey(kind));



  return (

    <span className={cn("inline-flex items-center gap-1.5 min-w-0", className)}>

      <span

        className={cn(

          "flex shrink-0 items-center justify-center ring-1 ring-inset",

          dim.box,

          style.bg,

          style.ring,

        )}

        title={label}

        role={showLabel ? undefined : "img"}

        aria-label={showLabel ? undefined : label}

      >

        <OsBrandIcon kind={kind} className={dim.icon} />

      </span>

      {showLabel ? (

        <span className={cn("font-medium truncate", dim.text, style.label)}>{label}</span>

      ) : null}

    </span>

  );

}



export function ServerOsBadgeFromInput({

  input,

  size = "md",

  showLabel = false,

  className,

}: {

  input: ServerOsInput;

  size?: keyof typeof sizeMap;

  showLabel?: boolean;

  className?: string;

}) {

  const kind = resolveServerOs(input);

  return <ServerOsBadge kind={kind} size={size} showLabel={showLabel} className={className} />;

}


