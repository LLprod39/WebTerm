/**
 * Slide-over panel for terminal appearance settings.
 */

import React, { useEffect } from "react";
import { X, Palette, Type, MonitorDot, PaintBucket, FileCode2 } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import type { TerminalPrefs } from "@/api/terminal-preferences";
import { THEME_PRESETS } from "./TerminalThemes";

interface TerminalSettingsPanelProps {
  prefs: TerminalPrefs;
  open: boolean;
  onClose: () => void;
  onUpdate: (patch: Partial<TerminalPrefs>) => void;
}

const FONT_OPTIONS = [
  "JetBrains Mono",
  "Fira Code",
  "Cascadia Code",
  "Consolas",
  "Source Code Pro",
  "Ubuntu Mono",
  "monospace",
];

const CURSOR_OPTIONS: { value: TerminalPrefs["cursor_style"]; labelKey: string; marker: string }[] = [
  { value: "block", labelKey: "terminal.cursorBlock", marker: "▌" },
  { value: "bar", labelKey: "terminal.cursorBar", marker: "│" },
  { value: "underline", labelKey: "terminal.cursorUnderline", marker: "▁" },
];

export const TerminalSettingsPanel: React.FC<TerminalSettingsPanelProps> = ({
  prefs,
  open,
  onClose,
  onUpdate,
}) => {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex">
      {/* backdrop */}
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      {/* panel */}
      <div
        className="relative ml-auto flex h-full w-full max-w-sm flex-col overflow-y-auto border-l border-border bg-surface-1 shadow-elev-1 sm:w-80"
        role="dialog"
        aria-modal="true"
        aria-labelledby="terminal-settings-title"
      >
        {/* header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 id="terminal-settings-title" className="text-sm font-semibold text-foreground">
            {t("terminal.settingsTitle")}
          </h2>
          <button
            onClick={onClose}
            className="rounded-sm p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label={t("terminal.closeSettings")}
            title={t("terminal.closeSettings")}
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col gap-5 p-4">
          {/* ---------- Theme ---------- */}
          <Section icon={<Palette size={14} />} title={t("terminal.themeLabel")}>
            <div className="grid grid-cols-2 gap-2">
              {THEME_PRESETS.map((p) => {
                const bg = p.theme.background ?? "#000";
                const fg = p.theme.foreground ?? "#fff";
                const colors = [
                  p.theme.red, p.theme.green, p.theme.yellow,
                  p.theme.blue, p.theme.magenta, p.theme.cyan,
                ].filter(Boolean) as string[];
                return (
                  <button
                    key={p.name}
                    onClick={() => onUpdate({ theme_name: p.name, theme_colors: {} })}
                    className={`group flex flex-col gap-1 rounded-sm border p-2 text-left transition-all ${
                      prefs.theme_name === p.name
                        ? "border-info bg-info/10 ring-1 ring-info/30"
                        : "border-border/60 bg-surface-2/60 hover:border-border-strong"
                    }`}
                  >
                    <span className={`text-xs font-medium ${
                      prefs.theme_name === p.name ? "text-info" : "text-foreground"
                    }`}>
                      {p.label}
                    </span>
                    <div
                      className="flex h-4 w-full items-center gap-px overflow-hidden rounded-sm"
                      style={{ backgroundColor: bg }}
                    >
                      <span
                        className="ml-1 text-[8px] font-mono leading-none"
                        style={{ color: fg }}
                      >
                        $
                      </span>
                      {colors.map((c, ci) => (
                        <span
                          key={ci}
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: c }}
                        />
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          </Section>

          {/* ---------- Background ---------- */}
          <Section icon={<PaintBucket size={14} />} title={t("terminal.bgLabel")}>
            <label className="flex items-center gap-3 text-xs text-muted-foreground">
              <input
                type="color"
                value={
                  prefs.theme_colors?.background ??
                  THEME_PRESETS.find((p) => p.name === prefs.theme_name)?.theme.background ??
                  "#0a0e14"
                }
                onChange={(e) =>
                  onUpdate({
                    theme_colors: { ...prefs.theme_colors, background: e.target.value },
                  })
                }
                className="h-8 w-10 cursor-pointer rounded-sm border border-border bg-transparent p-0"
              />
              <span className="font-mono text-foreground">
                {prefs.theme_colors?.background ??
                  THEME_PRESETS.find((p) => p.name === prefs.theme_name)?.theme.background ??
                  "#0a0e14"}
              </span>
              {prefs.theme_colors?.background && (
                <button
                  onClick={() => {
                    const { background: _, ...rest } = prefs.theme_colors;
                    onUpdate({ theme_colors: rest });
                  }}
                  className="ml-auto text-xs text-muted-foreground hover:text-foreground"
                >
                  {t("terminal.reset")}
                </button>
              )}
            </label>
          </Section>

          {/* ---------- Font ---------- */}
          <Section icon={<Type size={14} />} title={t("terminal.fontLabel")}>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{t("terminal.fontFamily")}</span>
              <Select
                value={prefs.font_family}
                onValueChange={(value) => onUpdate({ font_family: value })}
              >
                <SelectTrigger className="h-8 flex-1 rounded-sm border-border bg-surface-2 text-xs text-foreground" aria-label={t("terminal.fontFamily")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                {FONT_OPTIONS.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
                </SelectContent>
              </Select>
            </div>

            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {t("terminal.fontSize")}
              <input
                type="range"
                min={10}
                max={24}
                value={prefs.font_size}
                onChange={(e) => onUpdate({ font_size: Number(e.target.value) })}
                className="flex-1"
              />
              <span className="w-6 text-right text-foreground">{prefs.font_size}</span>
            </label>

            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {t("terminal.lineHeight")}
              <input
                type="range"
                min={100}
                max={200}
                value={Math.round(prefs.line_height * 100)}
                onChange={(e) =>
                  onUpdate({ line_height: Number(e.target.value) / 100 })
                }
                className="flex-1"
              />
              <span className="w-8 text-right text-foreground">
                {prefs.line_height.toFixed(1)}
              </span>
            </label>
          </Section>

          {/* ---------- Cursor ---------- */}
          <Section icon={<MonitorDot size={14} />} title={t("terminal.cursorLabel")}>
            <div className="flex gap-2">
              {CURSOR_OPTIONS.map((c) => (
                <button
                  key={c.value}
                  onClick={() => onUpdate({ cursor_style: c.value })}
                  className={`rounded-sm border px-2 py-1 text-xs ${
                    prefs.cursor_style === c.value
                      ? "border-info bg-info/20 text-info"
                      : "border-border bg-surface-2 text-muted-foreground hover:border-border-strong"
                  }`}
                >
                  {c.marker} {t(c.labelKey)}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={prefs.cursor_blink}
                onChange={(e) => onUpdate({ cursor_blink: e.target.checked })}
                className="rounded-sm"
              />
              {t("terminal.cursorBlink")}
            </label>
          </Section>

          {/* ---------- Scrollback ---------- */}
          <Section icon={<MonitorDot size={14} />} title={t("terminal.scrollback")}>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="number"
                min={500}
                max={50000}
                step={500}
                value={prefs.scrollback}
                onChange={(e) => onUpdate({ scrollback: Number(e.target.value) })}
                className="w-24 rounded-sm border border-border bg-surface-2 px-2 py-1 text-xs text-foreground"
              />
              {t("terminal.scrollbackLines")}
            </label>
          </Section>

          {/* ---------- Editor intercept ---------- */}
          <Section icon={<FileCode2 size={14} />} title={t("terminal.editorLabel")}>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={prefs.intercept_editors}
                onChange={(e) => onUpdate({ intercept_editors: e.target.checked })}
                className="rounded-sm"
              />
              {t("terminal.interceptEditors")}
            </label>
            <p className="mt-2 text-xs text-muted-foreground">{t("terminal.clickableFilesHint")}</p>
          </Section>
        </div>
      </div>
    </div>
  );
};

/* small helper */
function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}
