import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { studioPipelines } from "@/lib/api";

type CreatePipelineDialogProps = {
  open: boolean;
  onClose: () => void;
};

export function CreatePipelineDialog({ open, onClose }: CreatePipelineDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("W");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; description: string; icon: string }) =>
      studioPipelines.create({ ...payload, nodes: [], edges: [] }),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      setName("");
      setDescription("");
      setIcon("W");
      onClose();
      toast({ description: localize(lang, `Пайплайн "${pipeline.name}" создан.`, `Pipeline "${pipeline.name}" created.`) });
      navigate(`/studio/pipeline/${pipeline.id}`);
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{localize(lang, "Новый пайплайн", "New pipeline")}</DialogTitle>
          <DialogDescription>{localize(lang, "Создать пустой runbook и открыть редактор.", "Create an empty runbook and open the editor.")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex gap-2">
            <Input
              value={icon}
              onChange={(event) => setIcon(event.target.value)}
              placeholder="W"
              className="h-10 w-16 text-center"
              aria-label={localize(lang, "Иконка пайплайна", "Pipeline icon")}
            />
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={localize(lang, "Название пайплайна", "Pipeline name")}
              aria-label={localize(lang, "Название пайплайна", "Pipeline name")}
              autoFocus
            />
          </div>
          <Input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={localize(lang, "Краткое назначение", "Description")}
            aria-label={localize(lang, "Описание пайплайна", "Pipeline description")}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={onClose}>
            {localize(lang, "Отмена", "Cancel")}
          </Button>
          <Button
            className="h-10"
            onClick={() => createMutation.mutate({ name: name.trim(), description: description.trim(), icon: icon.trim() || "W" })}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {localize(lang, "Создать", "Create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
