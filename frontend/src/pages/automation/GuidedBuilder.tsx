import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Sparkles, Wand2 } from "lucide-react";
import {
  generateGuidedPlaybook,
  listGuidedRecipes,
  type GuidedRecipe,
  type PlaybookDetail,
} from "@/api/playbooks";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { notify } from "@/lib/notify";

interface GuidedBuilderProps {
  lang: string;
  onBack: () => void;
  onCreated: (playbook: PlaybookDetail) => void;
}

export function GuidedBuilder({ lang, onBack, onCreated }: GuidedBuilderProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const recipesQuery = useQuery({
    queryKey: ["playbook-guided-recipes"],
    queryFn: listGuidedRecipes,
    staleTime: 60_000,
  });
  const recipes = recipesQuery.data?.recipes || [];

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [recipe, setRecipe] = useState<GuidedRecipe | null>(null);
  const [params, setParams] = useState<Record<string, string | boolean>>({});
  const [previewYaml, setPreviewYaml] = useState("");
  const [busy, setBusy] = useState(false);

  const fieldErrors = useMemo(() => {
    if (!recipe) return [] as string[];
    const errs: string[] = [];
    for (const field of recipe.fields || []) {
      if (!field.required) continue;
      const val = params[field.key];
      if (val === undefined || val === null || String(val).trim() === "") {
        errs.push(field.key);
      }
    }
    return errs;
  }, [recipe, params]);

  const selectRecipe = (item: GuidedRecipe) => {
    setRecipe(item);
    const defaults: Record<string, string | boolean> = {};
    for (const field of item.fields || []) {
      if (field.default !== undefined) defaults[field.key] = field.default as string | boolean;
      else if (field.type === "checkbox") defaults[field.key] = false;
      else defaults[field.key] = "";
    }
    setParams(defaults);
    setPreviewYaml("");
    setStep(2);
  };

  const preview = async () => {
    if (!recipe || fieldErrors.length) {
      notify.error({ title: tr("Заполните обязательные поля", "Fill required fields") });
      return;
    }
    setBusy(true);
    try {
      const res = await generateGuidedPlaybook({ slug: recipe.slug, params, save: false });
      const yaml = (res.playbook as PlaybookDetail & { source_yaml?: string }).source_yaml || "";
      setPreviewYaml(yaml);
      setStep(3);
    } catch (err) {
      notify.error({ title: tr("Не удалось собрать playbook", "Failed to build"), description: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const createAndOpen = async () => {
    if (!recipe) return;
    setBusy(true);
    try {
      const res = await generateGuidedPlaybook({ slug: recipe.slug, params, save: true });
      if (!res.playbook) throw new Error(res.error || "Create failed");
      notify.success({ title: tr("Playbook создан (Ansible YAML)", "Playbook created (Ansible YAML)") });
      onCreated(res.playbook);
    } catch (err) {
      notify.error({ title: tr("Ошибка", "Error"), description: String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("Каталог", "Catalog")}
          </button>
          <h2 className="mt-1 flex items-center gap-2 font-display text-lg font-semibold text-foreground">
            <Wand2 className="h-4 w-4 text-primary" />
            {tr("Простой мастер Ansible", "Simple Ansible wizard")}
          </h2>
          <p className="text-xs text-muted-foreground">
            {tr(
              "Без YAML: выберите действие → заполните поля → получите настоящий Ansible playbook.",
              "No YAML needed: pick an action → fill fields → get a real Ansible playbook.",
            )}
          </p>
        </div>
        <div className="flex gap-1">
          {[1, 2, 3].map((n) => (
            <span
              key={n}
              className={cn(
                "flex h-7 min-w-7 items-center justify-center rounded-sm border px-2 text-2xs font-mono",
                step === n
                  ? "border-primary bg-primary text-primary-foreground"
                  : step > n
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground",
              )}
            >
              {n}
            </span>
          ))}
        </div>
      </div>

      {step === 1 ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {recipesQuery.isLoading ? (
            <p className="col-span-full py-8 text-center text-sm text-muted-foreground">{tr("Загрузка…", "Loading…")}</p>
          ) : null}
          {recipes.map((item) => (
            <button
              key={item.slug}
              type="button"
              onClick={() => selectRecipe(item)}
              className="rounded-sm border border-border bg-card p-4 text-left shadow-elev-1 transition-colors hover:border-primary/40 hover:bg-primary/5"
            >
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="font-medium text-sm text-foreground">{item.name}</span>
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground line-clamp-2">{item.description}</p>
              <p className="mt-2 text-2xs uppercase tracking-wider text-muted-foreground/70">{item.category}</p>
            </button>
          ))}
        </div>
      ) : null}

      {step === 2 && recipe ? (
        <div className="max-w-xl space-y-4 rounded-sm border border-border bg-card p-4 shadow-elev-1">
          <div>
            <h3 className="text-sm font-semibold text-foreground">{recipe.name}</h3>
            <p className="text-xs text-muted-foreground">{recipe.description}</p>
          </div>
          {(recipe.fields || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {tr("Параметры не нужны — можно сразу собрать playbook.", "No parameters needed — build the playbook next.")}
            </p>
          ) : (
            <div className="space-y-3">
              {recipe.fields.map((field) => (
                <div key={field.key} className="space-y-1.5">
                  <Label className="text-2xs uppercase tracking-wider text-muted-foreground">
                    {field.label}
                    {field.required ? " *" : ""}
                  </Label>
                  {field.type === "textarea" ? (
                    <Textarea
                      value={String(params[field.key] ?? "")}
                      onChange={(e) => setParams((p) => ({ ...p, [field.key]: e.target.value }))}
                      placeholder={field.placeholder}
                      className="min-h-[100px] bg-surface-0 font-mono text-sm"
                    />
                  ) : field.type === "select" ? (
                    <select
                      value={String(params[field.key] ?? field.default ?? "")}
                      onChange={(e) => setParams((p) => ({ ...p, [field.key]: e.target.value }))}
                      className="flex h-9 w-full rounded-sm border border-border bg-surface-0 px-2 text-sm"
                    >
                      {(field.options || []).map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : field.type === "checkbox" ? (
                    <label className="flex items-center gap-2 text-sm text-foreground">
                      <input
                        type="checkbox"
                        checked={Boolean(params[field.key])}
                        onChange={(e) => setParams((p) => ({ ...p, [field.key]: e.target.checked }))}
                      />
                      {field.label}
                    </label>
                  ) : (
                    <Input
                      value={String(params[field.key] ?? "")}
                      onChange={(e) => setParams((p) => ({ ...p, [field.key]: e.target.value }))}
                      placeholder={field.placeholder}
                      className="h-9 bg-surface-0"
                    />
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-between gap-2">
            <Button size="sm" variant="outline" className="h-9 gap-1" onClick={() => setStep(1)}>
              <ArrowLeft className="h-3.5 w-3.5" />
              {tr("Назад", "Back")}
            </Button>
            <Button size="sm" className="h-9 gap-1" disabled={busy || fieldErrors.length > 0} onClick={() => void preview()}>
              {busy ? tr("Сборка…", "Building…") : tr("Далее — превью YAML", "Next — YAML preview")}
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      {step === 3 && recipe ? (
        <div className="space-y-3">
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
            <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
              {tr("Настоящий Ansible YAML (будет выполнен ansible-playbook)", "Real Ansible YAML (run by ansible-playbook)")}
            </h3>
            <pre className="mt-2 max-h-80 overflow-auto rounded-sm border border-border bg-surface-0 p-3 font-mono text-2xs text-muted-foreground whitespace-pre-wrap">
              {previewYaml || "—"}
            </pre>
          </div>
          <div className="flex flex-wrap justify-between gap-2">
            <Button size="sm" variant="outline" className="h-9 gap-1" onClick={() => setStep(2)}>
              <ArrowLeft className="h-3.5 w-3.5" />
              {tr("Назад", "Back")}
            </Button>
            <Button size="sm" className="h-9 gap-1.5 shadow-elev-1" disabled={busy} onClick={() => void createAndOpen()}>
              <Sparkles className="h-3.5 w-3.5" />
              {busy ? tr("Создание…", "Creating…") : tr("Создать и открыть", "Create & open")}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
