import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileArchive, TerminalSquare, Upload } from "lucide-react";

import { installLocalPluginPackageUpload } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

const AUTHOR_COMMANDS = [
  "python manage.py plugin_scaffold acme.ops-panel --template dashboard",
  "cd webtrerm-plugin-acme-ops-panel",
  "python manage.py plugin_validate .",
  "python manage.py plugin_pack . --overwrite",
  "python manage.py plugin_install_local .\\dist\\webtrerm-plugin-acme-ops-panel.wtp",
];

export function LocalPackageInstallPanel() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "review"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "impact"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "surfaces"] }),
    ]);
  };

  const installUpload = useMutation({
    mutationFn: installLocalPluginPackageUpload,
    onSuccess: async (result) => {
      await invalidate();
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      toast({ description: localize(lang, `${result.plugin_id}: пакет установлен.`, `${result.plugin_id}: package installed.`) });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return (
    <SectionCard
      title={localize(lang, "Локальный пакет", "Local package")}
      description={localize(lang, "Загрузите пакет .wtp. После установки плагин останется выключенным.", "Upload a .wtp package. The plugin remains disabled after installation.")}
      icon={<FileArchive className="h-4 w-4" />}
      actions={<StatusBadge label={localize(lang, "локальный", "self-hosted")} tone="info" />}
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            <TerminalSquare className="h-4 w-4" />
            {localize(lang, "Команды для сборки", "Build commands")}
          </div>
          <div className="space-y-2">
            {AUTHOR_COMMANDS.map((command) => (
              <code key={command} className="block overflow-x-auto rounded-md bg-background/80 px-3 py-2 text-xs text-foreground">
                {command}
              </code>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-border/70 bg-card px-4 py-4">
          <div className="mb-3 text-xs font-semibold text-muted-foreground">{localize(lang, "Установить пакет", "Install package")}</div>
          <Input
            ref={fileInputRef}
            type="file"
            accept=".wtp,.zip,application/zip"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {localize(lang, "Сервер проверит архив и установит плагин в выключенном состоянии.", "The server validates the archive and installs the plugin in a disabled state.")}
          </p>
          <Button
            className="mt-3"
            size="sm"
            onClick={() => file && installUpload.mutate(file)}
            disabled={!file || installUpload.isPending}
          >
            <Upload className="h-4 w-4" />
            {localize(lang, "Загрузить и установить", "Upload and install")}
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}
