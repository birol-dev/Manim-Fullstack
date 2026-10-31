/** The quiet pill on Your videos that opens the system's file picker. */
import { useRef } from "react";
import { FileUp } from "lucide-react";

import { Button } from "@/components/ui/button";

import { PORTABLE_SUFFIX } from "./portableFile";

export function OpenProjectButton({ busy, onPick }: { busy: boolean; onPick: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return <>
    <input
      ref={input}
      type="file"
      accept={`${PORTABLE_SUFFIX},application/zip`}
      aria-label="Open a Manim Studio file"
      className="sr-only"
      onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onPick(file);
      }}
    />
    <Button type="button" variant="secondary" size="sm" className="studio-open-pill" disabled={busy}
      title="Open a video someone saved as one file" onClick={() => input.current?.click()}>
      <FileUp aria-hidden /> {busy ? "Opening…" : "Open a file"}
    </Button>
  </>;
}
