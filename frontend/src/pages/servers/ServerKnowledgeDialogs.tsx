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
  knowledgeActive,
  knowledgeCategory,
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
            <DialogTitle>{knowledgeEditingId ? t("srv.edit") : t("srv.add_entry")}</DialogTitle>
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
              <select
                value={knowledgeCategory}
                onChange={(event) => setKnowledgeCategory(event.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {activeKnowledgeCategories.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
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
            <DialogTitle>{t("srv.ai_knowledge_dialog_title")}</DialogTitle>
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
    </>
  );
}
