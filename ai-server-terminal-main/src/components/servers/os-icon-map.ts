import type { ServerOsKind } from "@/lib/server-os";



import alpineIcon from "@/assets/os/alpine.svg";

import almaIcon from "@/assets/os/alma.svg";

import amazonIcon from "@/assets/os/amazon.svg";

import archIcon from "@/assets/os/arch.svg";

import centosIcon from "@/assets/os/centos.svg";

import debianIcon from "@/assets/os/debian.svg";

import dockerIcon from "@/assets/os/docker.svg";

import fedoraIcon from "@/assets/os/fedora.svg";

import freebsdIcon from "@/assets/os/freebsd.svg";

import kubernetesIcon from "@/assets/os/kubernetes.svg";

import macosIcon from "@/assets/os/macos.svg";

import opensuseIcon from "@/assets/os/opensuse.svg";

import oracleIcon from "@/assets/os/oracle.svg";

import rockyIcon from "@/assets/os/rocky.svg";

import rhelIcon from "@/assets/os/rhel.svg";

import ubuntuIcon from "@/assets/os/ubuntu.svg";

import unknownIcon from "@/assets/os/unknown.svg";

import windowsIcon from "@/assets/os/windows.svg";



export const osIconSrc: Record<ServerOsKind, string> = {

  debian: debianIcon,

  ubuntu: ubuntuIcon,

  centos: centosIcon,

  rhel: rhelIcon,

  fedora: fedoraIcon,

  alpine: alpineIcon,

  arch: archIcon,

  opensuse: opensuseIcon,

  rocky: rockyIcon,

  alma: almaIcon,

  oracle: oracleIcon,

  amazon: amazonIcon,

  windows: windowsIcon,

  macos: macosIcon,

  freebsd: freebsdIcon,

  docker: dockerIcon,

  kubernetes: kubernetesIcon,

  unknown: unknownIcon,

};



export const osBadgeStyles: Record<

  ServerOsKind,

  { ring: string; bg: string; label: string }

> = {

  debian: { ring: "ring-[#A81D33]/35", bg: "bg-[#A81D33]/10", label: "text-[#A81D33]" },

  ubuntu: { ring: "ring-[#E95420]/35", bg: "bg-[#E95420]/10", label: "text-[#E95420]" },

  centos: { ring: "ring-[#262577]/35", bg: "bg-[#262577]/10", label: "text-[#262577]" },

  rhel: { ring: "ring-[#EE0000]/35", bg: "bg-[#EE0000]/10", label: "text-[#EE0000]" },

  fedora: { ring: "ring-[#51A2DA]/35", bg: "bg-[#51A2DA]/10", label: "text-[#51A2DA]" },

  alpine: { ring: "ring-[#0D597F]/35", bg: "bg-[#0D597F]/10", label: "text-[#0D597F]" },

  arch: { ring: "ring-[#1793D1]/35", bg: "bg-[#1793D1]/10", label: "text-[#1793D1]" },

  opensuse: { ring: "ring-[#73BA25]/35", bg: "bg-[#73BA25]/10", label: "text-[#73BA25]" },

  rocky: { ring: "ring-[#10B981]/35", bg: "bg-[#10B981]/10", label: "text-[#10B981]" },

  alma: { ring: "ring-foreground/15", bg: "bg-secondary/60", label: "text-foreground" },

  oracle: { ring: "ring-[#F80000]/35", bg: "bg-[#F80000]/10", label: "text-[#F80000]" },

  amazon: { ring: "ring-[#FF9900]/35", bg: "bg-[#FF9900]/10", label: "text-[#FF9900]" },

  windows: { ring: "ring-[#0078D4]/35", bg: "bg-[#0078D4]/10", label: "text-[#0078D4]" },

  macos: { ring: "ring-foreground/15", bg: "bg-secondary/60", label: "text-foreground" },

  freebsd: { ring: "ring-[#AB2B28]/35", bg: "bg-[#AB2B28]/10", label: "text-[#AB2B28]" },

  docker: { ring: "ring-[#2496ED]/35", bg: "bg-[#2496ED]/10", label: "text-[#2496ED]" },

  kubernetes: { ring: "ring-[#326CE5]/35", bg: "bg-[#326CE5]/10", label: "text-[#326CE5]" },

  unknown: { ring: "ring-border", bg: "bg-secondary/40", label: "text-muted-foreground" },

};


