import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ServerSecurityTabProps {
  hasMasterPassword: boolean;
  masterPassword: string;
  onClearMasterPassword: () => void;
  onRevealPassword: () => void;
  onSetMasterPassword: () => void;
  revealedPassword: string;
  setMasterPasswordText: (value: string) => void;
  t: (key: string) => string;
}

export function ServerSecurityTab({
  hasMasterPassword,
  masterPassword,
  onClearMasterPassword,
  onRevealPassword,
  onSetMasterPassword,
  revealedPassword,
  setMasterPasswordText,
  t,
}: ServerSecurityTabProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">{t("srv.master_pw")}</h3>
        <p className="mb-4 text-xs text-muted-foreground">{t("srv.security_help")}</p>
        <div className="space-y-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span className={`inline-block h-2 w-2 rounded-full ${hasMasterPassword ? "bg-primary" : "bg-muted-foreground"}`} />
            {hasMasterPassword ? t("srv.master_pw_set_status") : t("srv.master_pw_not_set_status")}
          </div>
          <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.master_pw_label")}</Label>
              <Input
                type="password"
                value={masterPassword}
                onChange={(event) => setMasterPasswordText(event.target.value)}
                className="h-9 bg-secondary/50"
                placeholder={t("srv.master_pw_placeholder")}
              />
            </div>
            <Button size="sm" className="h-9" onClick={onSetMasterPassword}>
              {t("srv.set_mp")}
            </Button>
            <Button size="sm" variant="outline" className="h-9" onClick={onClearMasterPassword}>
              {t("srv.clear_mp")}
            </Button>
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-5">
        <h3 className="mb-1 text-sm font-semibold text-foreground">{t("srv.reveal_pw")}</h3>
        <p className="mb-4 text-xs text-muted-foreground">{t("srv.reveal_help")}</p>
        <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-3">
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-xs text-muted-foreground">{t("srv.decrypted_password")}</Label>
            <Input value={revealedPassword} readOnly className="h-9 bg-secondary/50 font-mono" placeholder="•••••••••" />
          </div>
          <Button size="sm" className="h-9" onClick={onRevealPassword}>
            {t("srv.reveal_pw")}
          </Button>
        </div>
      </div>
    </div>
  );
}
