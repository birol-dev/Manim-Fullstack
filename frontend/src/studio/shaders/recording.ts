export function recordingType(): string | null {
  if (typeof MediaRecorder === "undefined" || !HTMLCanvasElement.prototype.captureStream) return null;
  return ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

/** Records only the shader's canvas; timers, streams and recorder are released on every exit. */
export function recordCanvas(canvas: HTMLCanvasElement, seconds: number, signal: AbortSignal, onProgress: (progress: number) => void): Promise<Blob> {
  const type = recordingType();
  if (!type) return Promise.reject(new Error("Video export isn't supported in this browser. You can still export a PNG."));
  return new Promise((resolve, reject) => {
    const stream = canvas.captureStream(30);
    let recorder: MediaRecorder;
    try { recorder = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 8_000_000 }); }
    catch (error) { stream.getTracks().forEach((track) => track.stop()); reject(error); return; }
    const chunks: Blob[] = [];
    let interval = 0, timeout = 0, startedAt = 0;
    let error: Error | null = null;
    const abort = () => { error = new Error("Video export cancelled."); if (recorder.state !== "inactive") recorder.stop(); };
    const hidden = () => { if (document.hidden) { error = new Error("Keep this tab visible while exporting a video. Please try again."); if (recorder.state !== "inactive") recorder.stop(); } };
    const cleanup = () => {
      clearInterval(interval); clearTimeout(timeout);
      stream.getTracks().forEach((track) => track.stop());
      signal.removeEventListener("abort", abort);
      document.removeEventListener("visibilitychange", hidden);
    };
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onerror = () => { error = new Error("Couldn't record the video. Please try a shorter duration."); if (recorder.state !== "inactive") recorder.stop(); else { cleanup(); reject(error); } };
    recorder.onstop = () => {
      const duration = performance.now() - startedAt;
      cleanup();
      if (error) reject(error);
      else if (!chunks.length) reject(new Error("The recording was empty. Please try again."));
      else fixWebmDuration(new Blob(chunks, { type: "video/webm" }), duration, { logger: false }).then(resolve, reject);
    };
    if (signal.aborted) { cleanup(); reject(new Error("Video export cancelled.")); return; }
    signal.addEventListener("abort", abort, { once: true });
    document.addEventListener("visibilitychange", hidden);
    try {
      recorder.start(100);
      const start = performance.now();
      startedAt = start;
      interval = window.setInterval(() => onProgress(Math.min(1, (performance.now() - start) / (seconds * 1000))), 100);
      timeout = window.setTimeout(() => { if (recorder.state !== "inactive") recorder.stop(); }, seconds * 1000);
    } catch (problem) { cleanup(); reject(problem); }
  });
}
import { fixWebmDuration } from "@fix-webm-duration/fix";

