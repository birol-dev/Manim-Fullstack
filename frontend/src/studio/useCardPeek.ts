import { useEffect, useRef, useState } from "react";

import { apiUrl } from "@/lib/api";

// Shared across every mounted gallery, including the home rows. Taking ownership
// cancels both another card's dwell timer and its playback.
let owner: (() => void) | null = null;
const POINTER_QUERY = "(hover: hover) and (pointer: fine)";
const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function useCardPeek(url?: string | null) {
  const [node, setNode] = useState<HTMLVideoElement | null>(null);
  const start = useRef<() => void>(() => {});
  const stop = useRef<() => void>(() => {});
  const canPlay = useRef<() => void>(() => {});
  const intent = useRef(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!url || !node) return;
    const pointer = window.matchMedia(POINTER_QUERY);
    const motion = window.matchMedia(MOTION_QUERY);
    let dwell: ReturnType<typeof setTimeout> | undefined;
    let reset: ReturnType<typeof setTimeout> | undefined;
    let started = false;
    let armed = false;
    let playable = false;
    let playing = false;
    let generation = 0;
    const allowed = () => pointer.matches && !motion.matches && !document.hidden;
    const rewind = () => { node.currentTime = 0; };
    const cancel = () => {
      generation++;
      clearTimeout(dwell);
      clearTimeout(reset);
      if (owner === cancel) owner = null;
      started = false;
      armed = false;
      playable = playing = false;
      node.pause();
      setVisible(false);
      // Keep the paused frame during the fade, then rewind under the still.
      reset = setTimeout(rewind, 150);
    };
    const reveal = () => {
      if (owner === cancel && armed && playable && playing && allowed()) setVisible(true);
    };
    const ready = () => {
      if (owner !== cancel || !armed) return;
      playable = true;
      reveal();
    };
    const play = () => {
      if (owner !== cancel || !armed || started || !allowed()) return;
      started = true;
      const attempt = generation;
      node.muted = true;
      void node.play().then(() => {
        if (owner === cancel && generation === attempt) {
          playing = true;
          reveal();
        }
      }).catch(() => { if (generation === attempt) cancel(); });
    };
    const begin = () => {
      if (!allowed() || owner === cancel) return;
      owner?.();
      clearTimeout(reset);
      owner = cancel;
      dwell = setTimeout(() => {
        if (owner !== cancel || !allowed()) return;
        armed = true;
        rewind();
        if (!node.hasAttribute("src")) {
          node.src = apiUrl(url);
          node.load();
        }
        playable = node.readyState >= 2;
        // play() initiates buffering even with preload="none". Waiting for
        // canplay before calling it can leave the browser permanently idle.
        play();
      }, 300);
    };
    const preferenceChanged = () => {
      if (!allowed()) {
        cancel();
        node.removeAttribute("src");
        node.load();
      }
    };
    start.current = begin;
    stop.current = cancel;
    canPlay.current = ready;
    if (intent.current) begin(); // the still/video may mount after a slow poster response
    pointer.addEventListener("change", preferenceChanged);
    motion.addEventListener("change", preferenceChanged);
    document.addEventListener("visibilitychange", preferenceChanged);
    return () => {
      cancel();
      clearTimeout(reset);
      rewind();
      node.removeAttribute("src");
      node.load();
      start.current = stop.current = canPlay.current = () => {};
      pointer.removeEventListener("change", preferenceChanged);
      motion.removeEventListener("change", preferenceChanged);
      document.removeEventListener("visibilitychange", preferenceChanged);
    };
  }, [url, node]);

  return {
    video: setNode,
    visible,
    onCanPlay: () => canPlay.current(),
    onError: () => stop.current(),
    cardEvents: {
      onPointerEnter: (event: React.PointerEvent<HTMLAnchorElement>) => { if (event.pointerType !== "touch") { intent.current = true; start.current(); } },
      onPointerLeave: () => { intent.current = false; stop.current(); },
      onFocus: (event: React.FocusEvent<HTMLAnchorElement>) => { if (event.currentTarget.matches(":focus-visible")) { intent.current = true; start.current(); } },
      onBlur: () => { intent.current = false; stop.current(); },
    },
  };
}
