import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Play, Upload, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { apiUrl } from "@/lib/api";
import { friendlyError, uploadAudio } from "./api";
import type { MusicTrack, SoundSettings } from "./types";
import { soundSettings } from "./sound";
import "./sound.css";

export function SoundPanel({ value, onChange, tracks = [], errors = {} }: {
  value: SoundSettings | undefined; onChange: (sound: SoundSettings) => void; tracks?: MusicTrack[]; errors?: Record<string, string[]>;
}) {
  const sound = useMemo(() => soundSettings(value), [value]);
  const id = useId();
  const player = useRef<HTMLAudioElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const current = useRef(sound);
  useEffect(() => { current.current = sound; }, [sound]);
  const [yourMusic, setYourMusic] = useState(!!sound.music.asset);
  const [title, setTitle] = useState("Your uploaded music");
  const [progress, setProgress] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [sample, setSample] = useState<string | null>(null);
  useEffect(() => {
    const audio = player.current;
    return () => { controller.current?.abort(); audio?.pause(); };
  }, []);
  useEffect(() => {
    if (player.current) player.current.volume = player.current.dataset.kind === "effect" ? sound.effects_volume : sound.music.volume * .32;
  }, [sound.effects_volume, sound.music.volume]);
  const music = (patch: Partial<SoundSettings["music"]>) => {
    if ("track" in patch || "asset" in patch) { player.current?.pause(); setSample(null); }
    onChange({ ...sound, music: { ...sound.music, ...patch } });
  };
  const listen = (url: string, label: string, volume: number) => {
    if (!player.current) return;
    setProblem(null);
    setSample(label);
    player.current.src = apiUrl(url);
    player.current.dataset.kind = url.includes("/effects/") ? "effect" : "music";
    player.current.volume = volume;
    void player.current.play().catch(() => setProblem("Couldn't play the sample. Use the player to try again."));
  };
  const upload = async (file: File | undefined) => {
    if (!file || controller.current) return;
    const active = new AbortController();
    controller.current = active;
    setProgress(0); setProblem(null);
    try {
      const result = await uploadAudio(file, setProgress, active.signal);
      if (active.signal.aborted) return;
      setTitle(result.title);
      onChange({ ...current.current, music: { ...current.current.music, asset: result.name, track: null } });
      setYourMusic(true);
    } catch (error) {
      if (!active.signal.aborted) setProblem(friendlyError(error, "Couldn't upload this music."));
    } finally {
      if (!active.signal.aborted) setProgress(null);
      if (controller.current === active) controller.current = null;
    }
  };
  const selected = sound.music.asset ? "upload" : sound.music.track ?? (yourMusic ? "upload" : "none");
  const soundErrors = Object.entries(errors).filter(([path]) => path.startsWith("settings.sound")).flatMap(([, messages]) => messages);
  return <section className="studio-look-section studio-sound" aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}><Volume2 aria-hidden className="size-4" /> Sound</h2>
    <div className="studio-setting-row">
      <div><label htmlFor={`${id}-effects`}>Sound effects</label><p>Gentle cues at useful moments.</p></div>
      <Switch id={`${id}-effects`} checked={sound.effects} onCheckedChange={(effects) => onChange({ ...sound, effects })} />
    </div>
    {sound.effects && <>
      <Volume label="Effects volume" value={sound.effects_volume} onChange={(effects_volume) => onChange({ ...sound, effects_volume })} />
      <Button size="sm" onClick={() => listen("/api/studio/sounds/effects/finish.wav", "Finish chime", sound.effects_volume)}><Play /> Hear an effect</Button>
    </>}
    <fieldset className="studio-sound-tracks" disabled={progress !== null}>
      <legend>Music</legend>
      <label><input type="radio" name={`${id}-music`} checked={selected === "none"} onChange={() => { setYourMusic(false); music({ track: null, asset: null }); }} />None</label>
      {tracks.map((track) => <div key={track.id} className="studio-sound-track">
        <label><input type="radio" name={`${id}-music`} checked={selected === track.id} onChange={() => { setYourMusic(false); music({ track: track.id, asset: null }); }} /><span>{track.title}<small>{track.description}</small></span></label>
        <Button size="icon-sm" variant="ghost" aria-label={`Listen to ${track.title}`} onClick={() => listen(track.url, track.title, sound.music.volume * .32)}><Play /></Button>
      </div>)}
      <label><input type="radio" name={`${id}-music`} checked={selected === "upload"} onChange={() => { setYourMusic(true); music({ track: null }); }} />Your music</label>
    </fieldset>
    {selected === "upload" && <div className="studio-sound-upload">
      {sound.music.asset && <div className="studio-sound-track"><span className="truncate text-xs text-fg-muted">{title}</span><Button size="sm" variant="ghost" onClick={() => listen(`/api/studio/audio/${sound.music.asset}`, title, sound.music.volume * .32)}><Play /> Listen</Button></div>}
      <Button size="sm" disabled={progress !== null} onClick={() => fileInput.current?.click()}><Upload />{sound.music.asset ? "Replace music" : "Upload music"}</Button>
      <input ref={fileInput} type="file" hidden accept=".mp3,.m4a,.aac,.wav,.ogg,audio/*" onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }} />
      <p>MP3, M4A/AAC, WAV or OGG. Up to 50 MB and 10 minutes.</p>
      {progress !== null && <div role="status"><span>{progress < 99 ? `Uploading music: ${progress}%` : "Preparing your music…"}</span><progress aria-label="Music upload" max={100} value={progress} /><Button size="sm" variant="ghost" onClick={() => { controller.current?.abort(); controller.current = null; setProgress(null); }}>Cancel upload</Button></div>}
    </div>}
    {selected !== "none" && <>
      <Volume label="Music volume" value={sound.music.volume} onChange={(volume) => music({ volume })} />
      <div className="studio-setting-row"><label htmlFor={`${id}-fade`}>Fade out at the end</label><Switch id={`${id}-fade`} checked={sound.music.fade_out} onCheckedChange={(fade_out) => music({ fade_out })} /></div>
      <div className="studio-setting-row"><label htmlFor={`${id}-loop`}>Repeat short music</label><Switch id={`${id}-loop`} checked={sound.music.loop} onCheckedChange={(loop) => music({ loop })} /></div>
    </>}
    <audio ref={player} controls hidden={!sample} aria-label={sample ? `${sample} sample` : "Sound sample"} onError={() => setProblem("Couldn't play this sample. Try again.")} />
    <p className="text-xs leading-relaxed text-fg-subtle">Play the animation, then choose Unmute to hear the mix. Pictures and GIFs are always silent.</p>
    {(problem || soundErrors.length > 0) && <p role="alert" className="text-xs text-danger">{problem || soundErrors.join(" ")}</p>}
  </section>;
}

function Volume({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const id = useId();
  return <div className="studio-sound-volume"><label htmlFor={id}>{label}</label><input id={id} className="studio-range" type="range" min={0} max={100} step={5} value={Math.round(value * 100)} aria-valuetext={`${Math.round(value * 100)} percent`} onChange={(event) => onChange(Number(event.target.value) / 100)} /><output htmlFor={id}>{Math.round(value * 100)}%</output></div>;
}
