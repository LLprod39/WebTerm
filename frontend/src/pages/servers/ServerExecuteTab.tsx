import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ServerExecuteTabProps {
  execCommand: string;
  execResult: string;
  onExecuteCommand: () => void;
  setExecCommand: (value: string) => void;
  t: (key: string) => string;
}

export function ServerExecuteTab({
  execCommand,
  execResult,
  onExecuteCommand,
  setExecCommand,
  t,
}: ServerExecuteTabProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">{t("srv.exec_cmd")}</h3>
        <p className="mb-4 text-xs text-muted-foreground">{t("srv.execute_help")}</p>
        <div className="flex gap-2">
          <Input
            value={execCommand}
            onChange={(event) => setExecCommand(event.target.value)}
            className="h-9 flex-1 bg-secondary/50 font-mono"
            placeholder="hostname"
          />
          <Button size="sm" className="h-9 px-6" onClick={onExecuteCommand}>
            {t("srv.run")}
          </Button>
        </div>
      </div>
      {execResult ? (
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">{t("srv.output")}</Label>
          <Textarea className="min-h-40 border-border bg-background font-mono text-xs" value={execResult} readOnly />
        </div>
      ) : null}
    </div>
  );
}
