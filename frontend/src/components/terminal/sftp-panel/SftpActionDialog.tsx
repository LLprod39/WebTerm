import { FormEvent, useEffect, useRef } from "react";

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
import { InlineAlert } from "@/components/system/InlineAlert";

export function SftpActionDialog({
  open,
  title,
  description,
  label,
  value,
  placeholder,
  error,
  confirmLabel,
  cancelLabel,
  submitting = false,
  onOpenChange,
  onValueChange,
  onSubmit,
}: {
  open: boolean;
  title: string;
  description: string;
  label: string;
  value: string;
  placeholder?: string;
  error?: string;
  confirmLabel: string;
  cancelLabel: string;
  submitting?: boolean;
  onOpenChange: (open: boolean) => void;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => inputRef.current?.select(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md rounded-xl" closeLabel={cancelLabel}>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="sftp-action-value" className="text-sm">
                {label}
              </Label>
              <Input
                ref={inputRef}
                id="sftp-action-value"
                value={value}
                onChange={(event) => onValueChange(event.target.value)}
                placeholder={placeholder}
                disabled={submitting}
              />
            </div>
            {error ? <InlineAlert tone="danger" description={error} /> : null}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              {cancelLabel}
            </Button>
            <Button type="submit" disabled={submitting}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
