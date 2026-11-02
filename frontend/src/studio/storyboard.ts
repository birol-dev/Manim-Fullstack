const GAP = 16;
const FRAME_LABEL_HEIGHT = 27;
const PADDING = 32;
const CAPTION_HEIGHT = 32;

/** Try every grid shape, including its labels and caption, to maximize each frame. */
export function fitStoryboard(count: number, ratio: number, width: number, height: number) {
  const total = Math.max(1, count);
  const availableWidth = Math.max(0, width - PADDING);
  const availableHeight = Math.max(0, height - PADDING - CAPTION_HEIGHT);
  let best = { columns: 1, rows: total, frameWidth: 0, width: 0 };
  for (let columns = 1; columns <= total; columns++) {
    const rows = Math.ceil(total / columns);
    const frameWidth = Math.max(0, Math.min(
      360,
      (availableWidth - (columns - 1) * GAP) / columns,
      (availableHeight - (rows - 1) * GAP - rows * FRAME_LABEL_HEIGHT) / rows * ratio,
    ));
    if (frameWidth > best.frameWidth || (frameWidth === best.frameWidth && rows < best.rows)) {
      best = { columns, rows, frameWidth, width: columns * frameWidth + (columns - 1) * GAP };
    }
  }
  return best;
}

export function spokenDuration(seconds: number): string {
  const rounded = seconds >= 10 ? Math.round(seconds) : Math.round(seconds * 10) / 10;
  if (rounded >= 60) {
    const minutes = Math.floor(rounded / 60);
    const rest = rounded % 60;
    return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
  }
  return `${rounded} ${rounded === 1 ? "second" : "seconds"}`;
}
