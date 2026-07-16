import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { KnowledgeIcons } from "@/lib/app-icons";

import type { ServerKnowledgeController } from "./useServerKnowledgeController";

interface ServerKnowledgeDialogsProps {
  controller: ServerKnowledgeController;
  t: (key: string) => string;
}

export function ServerKnowledgeDialogs({
  controller,
  t,
}: ServerKnowledgeDialogsProps) {
  const {
    activeKnowledgeCategories,
    aiKnowledgeContent,
    aiKnowledgeDialogOpen,
    aiKnowledgeDialogSaving,
    aiKnowledgeTitle,
    clearKnowledgeConfirmDialog,
    knowledgeActive,
    knowledgeCategory,
    knowledgeConfirmDialog,
    knowledgeContent,
    knowledgeDialogOpen,
    knowledgeDialogSaving,
    knowledgeEditingId,
    knowledgeTitle,
    onAiKnowledgeSave,
    onKnowledgeSave,
    resetAiKnowledgeDialog,
    resetKnowledgeDialog,
    setAiKnowledgeContent,
    setAiKnowledgeDialogOpen,
    setAiKnowledgeTitle,
    setKnowledgeActive,
    setKnowledgeCategory,
    setKnowledgeContent,
    setKnowledgeDialogOpen,
    setKnowledgeTitle,
  } = controller;

  return (
    <>
      <Dialog
        open={knowledgeDialogOpen}
        onOpenChange={(open) => {
          setKnowledgeDialogOpen(open);
          if (!open) {
            resetKnowledgeDialog();
          }
        }}
      >
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-sm border border-border bg-surface-0 text-primary">
                <KnowledgeIcons.entry className="h-3.5 w-3.5" strokeWidth={1.5} />
              </span>
              {knowledgeEditingId ? t("srv.edit") : t("srv.add_entry")}
            </DialogTitle>
            <DialogDescription>{t("srv.knowledge_manual_dialog_desc")}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_title")}</Label>
              <Input
                placeholder={t("srv.knowledge_title_placeholder")}
                value={knowledgeTitle}
                onChange={(event) => setKnowledgeTitle(event.target.value)}
                className="h-9 bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_category")}</Label>
              <Select
                value={knowledgeCategory}
                onValueChange={setKnowledgeCategory}
              >
                <SelectTrigger className="h-9 bg-secondary/50" aria-label={t("srv.knowledge_category")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {activeKnowledgeCategories.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_content")}</Label>
              <Textarea
                placeholder={t("srv.knowledge_content_placeholder")}
                value={knowledgeContent}
                onChange={(event) => setKnowledgeContent(event.target.value)}
                className="min-h-32 bg-secondary/50 text-sm"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={knowledgeActive}
                onChange={(event) => setKnowledgeActive(event.target.checked)}
              />
              {t("srv.enable")}
            </label>
          </DialogBody>
          <DialogFooter>
            <Button
              size="sm"
              variant="outline"
              className="h-8 px-4"
              onClick={() => {
                setKnowledgeDialogOpen(false);
                resetKnowledgeDialog();
              }}
            >
              {t("srv.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-8 px-4"
              onClick={() => void onKnowledgeSave()}
              disabled={knowledgeDialogSaving || !knowledgeTitle.trim() || !knowledgeContent.trim()}
            >
              {knowledgeDialogSaving ? t("srv.saving") : knowledgeEditingId ? t("srv.save") : t("srv.add_entry")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={aiKnowledgeDialogOpen}
        onOpenChange={(open) => {
          setAiKnowledgeDialogOpen(open);
          if (!open) {
            resetAiKnowledgeDialog();
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-sm border border-border bg-surface-0 text-primary">
                <KnowledgeIcons.ai className="h-3.5 w-3.5" strokeWidth={1.5} />
              </span>
              {t("srv.ai_knowledge_dialog_title")}
            </DialogTitle>
            <DialogDescription>{t("srv.ai_knowledge_dialog_desc")}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_title")}</Label>
              <Input
                placeholder={t("srv.knowledge_title_placeholder")}
                value={aiKnowledgeTitle}
                onChange={(event) => setAiKnowledgeTitle(event.target.value)}
                className="h-9 bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.knowledge_content")}</Label>
              <Textarea
                placeholder={t("srv.knowledge_content_placeholder")}
                value={aiKnowledgeContent}
                onChange={(event) => setAiKnowledgeContent(event.target.value)}
                className="custom-scrollbar min-h-64 bg-secondary/50 font-mono text-sm"
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button
              size="sm"
              variant="outline"
              className="h-8 px-4"
              onClick={() => {
                setAiKnowledgeDialogOpen(false);
                resetAiKnowledgeDialog();
              }}
            >
              {t("srv.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-8 px-4"
              onClick={() => void onAiKnowledgeSave()}
              disabled={aiKnowledgeDialogSaving || (!aiKnowledgeTitle.trim() && !aiKnowledgeContent.trim())}
            >
              {aiKnowledgeDialogSaving ? t("srv.saving") : t("srv.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteDialog
        open={Boolean(knowledgeConfirmDialog)}
        onOpenChange={(open) => {
          if (!open) clearKnowledgeConfirmDialog();
        }}
        title={knowledgeConfirmDialog?.title || t("srv.delete")}
        description={knowledgeConfirmDialog?.description || ""}
        confirmLabel={knowledgeConfirmDialog?.confirmLabel || t("srv.delete")}
        cancelLabel={t("srv.cancel")}
        onConfirm={() => {
          const action = knowledgeConfirmDialog?.onConfirm;
          clearKnowledgeConfirmDialog();
          return action?.();
        }}
        contentClassName="max-w-sm"
      />
    </>
  );
}
