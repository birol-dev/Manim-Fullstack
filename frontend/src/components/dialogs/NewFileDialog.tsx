import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { toScriptName, validateScriptName } from "@/lib/format";

export interface NewFileRequest {
  /** Suggested name (without forcing .py). */
  suggestedName: string;
  /** Template title shown in the description, if starting from one. */
  templateTitle?: string;
}

interface NewFileDialogProps {
  request: NewFileRequest | null;
  existing: string[];
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}

function NewFileForm({ request, existing, onClose, onCreate }: NewFileDialogProps & { request: NewFileRequest }) {
  const [value, setValue] = useState(request.suggestedName);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const name = toScriptName(value);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const problem = validateScriptName(name, existing);
    if (problem) return setError(problem);
    setBusy(true);
    try {
      await onCreate(name);
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the file."));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <DialogHeader>
        <DialogTitle>New script</DialogTitle>
        <DialogDescription>
          {request.templateTitle ? `Starts from the “${request.templateTitle}” template.` : "Starts with a minimal scene you can build on."}
        </DialogDescription>
      </DialogHeader>
      <Field
        label="File name"
        htmlFor="new-file-name"
        error={error}
        hint={value.trim() && !value.trim().toLowerCase().endsWith(".py") ? `Will be saved as ${name}` : undefined}
      >
        <Input
          id="new-file-name"
          autoFocus
          value={value}
          aria-invalid={error ? true : undefined}
          placeholder="my_scene.py"
          onFocus={(event) => event.currentTarget.setSelectionRange(0, value.replace(/\.py$/i, "").length)}
          onChange={(event) => {
            setValue(event.target.value);
            setError(null);
          }}
          className="h-8 font-mono"
          spellCheck={false}
          autoComplete="off"
        />
      </Field>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={busy || !value.trim()}>
          Create
        </Button>
      </DialogFooter>
    </form>
  );
}

export function NewFileDialog(props: NewFileDialogProps) {
  return (
    <Dialog open={props.request !== null} onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="max-w-sm">
        {/* Remount per request so the form starts fresh. */}
        {props.request && <NewFileForm key={props.request.suggestedName} {...props} request={props.request} />}
      </DialogContent>
    </Dialog>
  );
}
