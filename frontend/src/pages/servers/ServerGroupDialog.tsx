import type { Dispatch, SetStateAction } from "react";
import type { FrontendGroup } from "@/lib/api";
import { Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ServerGroupForm } from "./types";

interface ServerGroupDialogProps {
  open: boolean;
  editingGroup: FrontendGroup | null;
  groupForm: ServerGroupForm;
  groupSaving: boolean;
  t: (key: string) => string;
  setGroupDialogOpen: (open: boolean) => void;
  setGroupForm: Dispatch<SetStateAction<ServerGroupForm>>;
  closeGroupDialog: () => void;
  onSaveGroup: () => void;
  openGroupRules: (groupId: number) => void;
}

export function ServerGroupDialog({
  open,
  editingGroup,
  groupForm,
  groupSaving,
  t,
  setGroupDialogOpen,
  setGroupForm,
  closeGroupDialog,
  onSaveGroup,
  openGroupRules,
}: ServerGroupDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          closeGroupDialog();
          return;
        }
        setGroupDialogOpen(true);
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{editingGroup ? t("srv.edit_group") : t("srv.create_group")}</DialogTitle>
          <DialogDescription>{t("srv.group_settings")}</DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.group_name")} *</Label>
            <Input
              value={groupForm.name}
              onChange={(e) => setGroupForm((state) => ({ ...state, name: e.target.value }))}
              placeholder={t("srv.group_name")}
              className="bg-secondary/50"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.description")}</Label>
            <Textarea
              value={groupForm.description}
              onChange={(e) => setGroupForm((state) => ({ ...state, description: e.target.value }))}
              placeholder={t("srv.description")}
              className="min-h-24 bg-secondary/50"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.group_color")}</Label>
            <div className="flex items-center gap-3 rounded-md border border-border bg-secondary/30 px-3 py-2">
              <Input
                type="color"
                value={groupForm.color}
                onChange={(e) => setGroupForm((state) => ({ ...state, color: e.target.value }))}
                className="h-8 w-12 cursor-pointer rounded border-0 bg-transparent p-0"
              />
              <div className="text-xs text-muted-foreground">{groupForm.color}</div>
            </div>
          </div>
        </DialogBody>

        <DialogFooter>
          {editingGroup?.id && (
            <Button variant="outline" size="sm" onClick={() => openGroupRules(editingGroup.id!)} className="mr-auto gap-1.5">
              <Layers className="h-3.5 w-3.5" /> {t("srv.rules_tab")}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={closeGroupDialog}>
            {t("srv.cancel")}
          </Button>
          <Button size="sm" onClick={onSaveGroup} disabled={groupSaving || !groupForm.name.trim()}>
            {groupSaving ? t("srv.saving") : editingGroup ? t("srv.update") : t("srv.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
