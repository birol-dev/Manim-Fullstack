import { useState } from "react";

import type { ActiveRender, RenderOutcome } from "@/hooks/useRenderSession";
import { overallPercent } from "@/lib/progress";

/**
 * What screen readers hear about the open file's render: milestones only (queued,
 * started, 25/50/75%, stopping, then rendered / failed / cancelled), never every
 * progress tick. The text only changes at a milestone, so a polite live region
 * announces each one once.
 */
export function useRenderAnnouncement(
  active: ActiveRender | null,
  stepCount: number,
  stopping: boolean,
  lastOutcome: RenderOutcome | null,
): string {
  // The render this pane saw running (its outcome is announced, not one from before mount)
  // and the highest milestone reached, so progress that dips doesn't announce 50% twice.
  const [seen, setSeen] = useState<{ id: string; milestone: number } | null>(null);
  if (active) {
    const percent = active.queued ? null : overallPercent(active, stepCount);
    const reached = percent === null ? 0 : percent >= 75 ? 75 : percent >= 50 ? 50 : percent >= 25 ? 25 : 0;
    const milestone = seen?.id === active.id ? Math.max(seen.milestone, reached) : reached;
    if (seen?.id !== active.id || seen.milestone !== milestone) setSeen({ id: active.id, milestone });
    const scene = active.request.scene;
    if (stopping) return active.queued ? `Leaving the queue for ${scene}` : `Stopping the render of ${scene}`;
    if (active.queued) return `${scene} is waiting to render${active.queuePosition ? `, position ${active.queuePosition}` : ""}`;
    return milestone ? `Rendering ${scene}: ${milestone}%` : `Rendering ${scene}`;
  }
  if (lastOutcome && lastOutcome.id === seen?.id) {
    const scene = lastOutcome.request.scene;
    if (lastOutcome.success) return `${scene} rendered`;
    if (lastOutcome.status === "cancelled") return `Render of ${scene} cancelled`;
    return `${scene} didn't render`;
  }
  return "";
}
