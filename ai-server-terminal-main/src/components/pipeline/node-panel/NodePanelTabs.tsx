import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { t, type NodePanelLang } from "./shared";

export type NodePanelTabValue = "settings" | "prompts" | "policies";

type NodePanelTabsProps = {
  lang: NodePanelLang;
  value: NodePanelTabValue;
  onValueChange: (value: NodePanelTabValue) => void;
  children: ReactNode;
};

export function NodePanelTabs({
  lang,
  value,
  onValueChange,
  children,
}: NodePanelTabsProps) {
  return (
    <Tabs
      value={value}
      onValueChange={(nextValue) => onValueChange(nextValue as NodePanelTabValue)}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="px-4 pt-4">
        <TabsList className="grid h-auto w-full grid-cols-3 rounded-2xl border border-border/70 bg-muted/30 p-1">
          <TabsTrigger value="settings" className="rounded-xl px-3 py-2 text-xs">
            {t(lang, "Настройки", "Settings")}
          </TabsTrigger>
          <TabsTrigger value="prompts" className="rounded-xl px-3 py-2 text-xs">
            {t(lang, "Промпты", "Prompts")}
          </TabsTrigger>
          <TabsTrigger value="policies" className="rounded-xl px-3 py-2 text-xs">
            {t(lang, "Политики", "Policies")}
          </TabsTrigger>
        </TabsList>
      </div>
      {children}
    </Tabs>
  );
}

export const NodePanelTabContent = TabsContent;
