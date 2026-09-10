import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  terminalPreferencesApi,
  type TerminalPreferences as Preferences,
} from "@/api/terminal-preferences";
import { Button, Field, Feedback } from "@/components/ui";
export function TerminalPreferences({
  initial,
  onSaved,
}: {
  initial: Preferences;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => terminalPreferencesApi.update(draft),
    onSuccess: (data) => {
      client.setQueryData(["terminal-preferences"], data);
      onSaved();
    },
  });
  const change = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    setDraft((old) => ({ ...old, [key]: value }));
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <fieldset
        className="stack"
        disabled={save.isPending}
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >
        <Field label="Шрифт" htmlFor="term-font">
          <select
            id="term-font"
            value={draft.font_family}
            onChange={(e) => change("font_family", e.target.value)}
          >
            {[
              "Cascadia Code",
              "Consolas",
              "JetBrains Mono",
              "Fira Code",
              "Source Code Pro",
              "Ubuntu Mono",
              "monospace",
            ].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Размер шрифта" htmlFor="term-font-size">
            <input
              id="term-font-size"
              type="number"
              min={10}
              max={24}
              value={draft.font_size}
              onChange={(e) => change("font_size", Number(e.target.value))}
            />
          </Field>
          <Field label="Межстрочный интервал" htmlFor="term-line">
            <input
              id="term-line"
              type="number"
              min={1}
              max={2}
              step={0.05}
              value={draft.line_height}
              onChange={(e) => change("line_height", Number(e.target.value))}
            />
          </Field>
        </div>
        <Field label="Курсор" htmlFor="term-cursor">
          <select
            id="term-cursor"
            value={draft.cursor_style}
            onChange={(e) =>
              change(
                "cursor_style",
                e.target.value as Preferences["cursor_style"],
              )
            }
          >
            <option value="block">Блок</option>
            <option value="bar">Линия</option>
            <option value="underline">Подчёркивание</option>
          </select>
        </Field>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={draft.cursor_blink}
            onChange={(e) => change("cursor_blink", e.target.checked)}
          />
          Мигающий курсор
        </label>
        <Field label="Строк в истории терминала" htmlFor="term-history">
          <input
            id="term-history"
            type="number"
            min={500}
            max={50000}
            step={500}
            value={draft.scrollback}
            onChange={(e) => change("scrollback", Number(e.target.value))}
          />
        </Field>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={draft.intercept_editors}
            onChange={(e) => change("intercept_editors", e.target.checked)}
          />
          Открывать nano/vim в редакторе WebTerm
        </label>
        <Feedback error={save.error} />
        <Button type="submit" variant="primary" loading={save.isPending}>
          Сохранить настройки
        </Button>
      </fieldset>
    </form>
  );
}
