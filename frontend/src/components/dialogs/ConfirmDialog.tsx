import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";

export interface ConfirmRequest {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  /** Optional middle action, e.g. "Don't save". */
  secondaryLabel?: string;
  onConfirm: () => void | Promise<void>;
  onSecondary?: () => void | Promise<void>;
}

interface ConfirmDialogProps {
  request: ConfirmRequest | null;
  onClose: () => void;
}

export function ConfirmDialog({ request, onClose }: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);

  const run = async (action?: () => void | Promise<void>) => {
    setBusy(true);
    try {
      await action?.();
      onClose();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-w-sm" hideClose>
        {request && (
          <>
            <DialogHeader>
              <DialogTitle>{request.title}</DialogTitle>
              <DialogDescription>{request.description}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              {request.secondaryLabel && (
                <Button onClick={() => void run(request.onSecondary)} disabled={busy}>
                  {request.secondaryLabel}
                </Button>
              )}
              <Button
                variant={request.tone === "danger" ? "danger" : "primary"}
                onClick={() => void run(request.onConfirm)}
                disabled={busy}
                autoFocus
              >
                {request.confirmLabel}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
