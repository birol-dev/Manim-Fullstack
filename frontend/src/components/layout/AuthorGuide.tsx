import { ArrowRight, FileCode2, Play, ScanLine } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/panel";
import { MOD_KEY } from "@/lib/constants";

interface AuthorGuideProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onBrowseStarters: () => void;
  onShowTimeline: () => void;
}

export function AuthorGuide({ open, onOpenChange, onBrowseStarters, onShowTimeline }: AuthorGuideProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="author-guide max-w-[580px] gap-0 overflow-y-auto p-6 sm:p-8">
        <span className="author-kicker">Manim Studio / Author mode</span>
        <DialogTitle className="author-guide-title">From script to screen</DialogTitle>
        <DialogDescription className="text-sm text-fg-muted">
          Write a scene in Python, render a draft, then use the preview and timeline to refine it.
        </DialogDescription>
        <ol className="author-guide-steps">
          <li>
            <FileCode2 aria-hidden="true" />
            <div><h3>Open a script</h3><p>Start from a working example or create a script with a <code>Scene</code> class and a <code>construct()</code> method.</p></div>
          </li>
          <li>
            <Play aria-hidden="true" />
            <div><h3>Render a scene</h3><p>Choose the scene above the editor and use <strong>Low</strong> quality for a fast draft. Press <span className="inline-flex items-center gap-1 whitespace-nowrap"><Kbd>{MOD_KEY}</Kbd><Kbd>Enter</Kbd></span> to render.</p></div>
          </li>
          <li>
            <ScanLine aria-hidden="true" />
            <div><h3>Review and revise</h3><p>Watch the preview and use Timeline to jump to a step in the script. If a render fails, open Console and select the traceback line.</p></div>
          </li>
        </ol>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={() => { onBrowseStarters(); onOpenChange(false); }}>
            Browse starters <ArrowRight />
          </Button>
          <Button variant="secondary" onClick={() => { onShowTimeline(); onOpenChange(false); }}>Open timeline</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
