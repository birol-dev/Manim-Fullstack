import { useEffect, useRef, useState, type ReactNode } from "react";
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
  /**
   * The button focused when the dialog opens (Enter presses it). Defaults to
   * Cancel for destructive or multi-choice dialogs, else the confirm button.
   */
  defaultFocus?: "cancel" | "confirm" | "secondary";
  /** A save-conflict question (outside-change notices wait while it is open). */
  conflict?: boolean;
  /** Focus target on close when the opener no longer exists (e.g. the deleted row). */
  fallbackFocus?: () => void;
}

interface ConfirmDialogProps {
  request: ConfirmRequest | null;
  /** Close *request* (the one shown when the action started; a newer one stays open). */
  onClose: (request: ConfirmRequest | null) => void;
}

export function ConfirmDialog({ request, onClose }: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const secondaryRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  // The request is already null when the dialog finishes closing; keep its fallback for then.
  const lastRequest = useRef<ConfirmRequest | null>(null);
  useEffect(() => {
    if (request) lastRequest.current = request;
  }, [request]);
  const focusTarget = request?.defaultFocus ?? (request?.tone === "danger" || request?.secondaryLabel || request?.conflict ? "cancel" : "confirm");

  const run = async (action?: () => void | Promise<void>) => {
    const shown = request;
    setBusy(true);
    try {
      await action?.();
      // The action may have opened a new request (a save that conflicted again): keep that one.
      onClose(shown);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && !busy && onClose(request)}>
      <DialogContent
        className="max-w-sm"
        hideClose
        onOpenAutoFocus={(event) => {
          const target = { cancel: cancelRef, secondary: secondaryRef, confirm: confirmRef }[focusTarget].current ?? cancelRef.current;
          if (!target) return;
          event.preventDefault();
          target.focus();
        }}
        onFocusFallback={() => lastRequest.current?.fallbackFocus?.()}
      >
        {request && (
          <>
            <DialogHeader>
              <DialogTitle>{request.title}</DialogTitle>
              <DialogDescription>{request.description}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button ref={cancelRef} variant="ghost" onClick={() => onClose(request)} disabled={busy}>
                Cancel
              </Button>
              {request.secondaryLabel && (
                <Button ref={secondaryRef} onClick={() => void run(request.onSecondary)} disabled={busy}>
                  {request.secondaryLabel}
                </Button>
              )}
              <Button
                ref={confirmRef}
                variant={request.tone === "danger" ? "danger" : "primary"}
                onClick={() => void run(request.onConfirm)}
                disabled={busy}
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
