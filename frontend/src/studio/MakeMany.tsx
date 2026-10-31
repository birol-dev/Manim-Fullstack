/** Make many: a list on the left, the row's real poster on the right, three quiet steps. */
import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight, Download, FileSpreadsheet, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiUrl } from "@/lib/api";

import { friendlyError, getProject, listExports, parseBatch, previewProblem, startBatch } from "./api";
import { Spinner } from "./components";
import { fieldErrorsOf, friendlyFieldMessage } from "./errors";
import { usePoster } from "./hooks";
import { EXPORT_FORMATS, formatSeconds, initialSettings, QUALITIES, toDate } from "./options";
import { readBrandKit } from "./preferences";
import { navigate, type Route } from "./router";
import { initialParams } from "./schemaForm";
import type {
  BatchField,
  BatchFieldKind,
  BatchRowProblem,
  Catalog,
  ExportFormat,
  ExportQuality,
  JsonSchema,
  Params,
  ParsedBatch,
  RenderSettings,
  TemplateInfo,
} from "./types";
import "./makemany.css";

type ManyRoute = Extract<Route, { kind: "many" } | { kind: "many-project" }>;

interface Base {
  template: TemplateInfo;
  params: Params;
  settings: RenderSettings;
}

const TEXT_WIDGETS = new Set(["text", "textarea"]);
const NUMBER_WIDGETS = new Set(["number", "integer", "duration", "sparkle"]);
const SKIP_WIDGETS = new Set(["image", "icon", "list", "table", "toggle", "choice"]);
const COLOR = /^#[0-9a-f]{6}$/i;
const BARE_COLOR = /^[0-9a-f]{6}$/i;

function resolveProp(root: JsonSchema, raw: JsonSchema | undefined): JsonSchema {
  if (!raw) return {};
  if (raw.$ref) {
    const name = raw.$ref.split("/").pop() ?? "";
    return (root.$defs ?? root.definitions ?? {})[name] ?? {};
  }
  const variants = raw.anyOf ?? raw.oneOf;
  const stringVariant = variants?.find((variant) => variant.type === "string");
  return stringVariant ? { ...raw, ...stringVariant } : raw;
}

/** The simple top-level fields a column can fill, mirroring the server's list. */
function fillableFields(root: JsonSchema): BatchField[] {
  const required = new Set(root.required ?? []);
  const fields: BatchField[] = [];
  for (const [name, raw] of Object.entries(root.properties ?? {})) {
    const prop = resolveProp(root, raw);
    const widget = prop["x-widget"];
    let kind: BatchFieldKind | null = null;
    if (widget === "color") kind = "color";
    else if (widget && TEXT_WIDGETS.has(widget as string)) kind = "text";
    else if (widget && NUMBER_WIDGETS.has(widget as string) && !prop["x-choice-of"]) kind = "number";
    else if ((widget && SKIP_WIDGETS.has(widget as string)) || prop["x-choice-of"]) continue;
    else if (prop.type === "string" && !prop.enum) kind = "text";
    else if ((prop.type === "number" || prop.type === "integer") && !prop.enum) kind = "number";
    if (!kind) continue;
    fields.push({
      field: name,
      label: prop.title ?? name.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase()),
      kind,
      max_length: kind === "text" ? prop.maxLength ?? null : null,
      required: required.has(name),
    });
  }
  return fields;
}

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function sampleValue(field: BatchField, index: number): string {
  if (field.kind === "number") return String(index + 1);
  if (field.kind === "color") return index === 0 ? "#2563EB" : "#F97316";
  return index === 0 ? "First example" : "Second example";
}

/** A CSV the person can open, fill in, and bring back: the design's fields and two rows. */
function sampleCsv(template: TemplateInfo): string {
  const fields = fillableFields(template.schema);
  if (!fields.length) return "Name\r\nFirst video\r\nSecond video\r\n";
  const headers = fields.map((field) => csvCell(field.label));
  const rows = [0, 1].map((index) => fields.map((field) => csvCell(sampleValue(field, index))).join(","));
  return [headers.join(","), ...rows].join("\r\n") + "\r\n";
}

function normalizeColor(value: string): string {
  const text = value.trim();
  if (COLOR.test(text)) return text.toUpperCase();
  if (BARE_COLOR.test(text)) return `#${text.toUpperCase()}`;
  return text;
}

/** The row's values on top of the design's own text; an empty cell keeps the design. */
function rowParams(base: Params, fields: BatchField[], mapping: Record<string, number>, row: string[]): Params {
  const next: Params = { ...base };
  for (const field of fields) {
    const index = mapping[field.field];
    if (index == null || index < 0) continue;
    const value = (row[index] ?? "").trim();
    if (!value) continue;
    next[field.field] = field.kind === "color" ? normalizeColor(value) : value;
  }
  return next;
}

function rowLabel(row: string[], column: number | null, fallback: string): string {
  const text = column == null ? "" : (row[column] ?? "").trim();
  return text || fallback;
}

/** Why a row's poster could not be drawn: the row's own problem, in plain words. */
function rowPreviewProblem(error: unknown): string {
  const fields = fieldErrorsOf(error);
  return fields.length
    ? `This row needs a fix first: ${friendlyFieldMessage(fields[0].message)}`
    : previewProblem(error);
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

function readFileBytes(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error("That file couldn't be read."));
    reader.readAsArrayBuffer(file);
  });
}

const ACCEPTED = /\.(csv|tsv|txt|xlsx)$/i;
const MAX_BYTES = 2 * 1024 * 1024;

function downloadSample(template: TemplateInfo) {
  const csv = sampleCsv(template);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const name = template.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "list";
  const url = typeof URL.createObjectURL === "function"
    ? URL.createObjectURL(blob)
    : `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}-example.csv`;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  if (url.startsWith("blob:") && typeof URL.revokeObjectURL === "function") {
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function Faded({ children }: { children: ReactNode }) {
  return <span className="studio-many-fade">{children}</span>;
}

function templateBase(catalog: Catalog, templateId: string, presetId: string): { base?: Base; error?: Error } {
  const template = catalog.templates.find((item) => item.id === templateId);
  if (!template) return { error: new Error("This design isn't available anymore.") };
  const preset = template.presets.find((item) => item.id === presetId);
  const settings = initialSettings(template, preset?.settings);
  const kit = readBrandKit();
  if (kit) settings.brand = { ...settings.brand, ...kit };
  return { base: { template, params: initialParams(template.defaults, preset?.params), settings } };
}

export function MakeManyPage({ catalog, route }: { catalog: Catalog; route: ManyRoute }) {
  const [initial] = useState<{ base?: Base; error?: Error }>(
    () => (route.kind === "many" ? templateBase(catalog, route.template, route.preset) : {}),
  );
  const [base, setBase] = useState<Base | null>(initial.base ?? null);
  const [baseError, setBaseError] = useState<unknown>(initial.error ?? null);
  const [step, setStep] = useState(0);
  const [parsed, setParsed] = useState<ParsedBatch | null>(null);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [titleColumn, setTitleColumn] = useState<number | null>(null);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [paste, setPaste] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [fileProblem, setFileProblem] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkProblem, setCheckProblem] = useState<string | null>(null);
  const [rowProblems, setRowProblems] = useState<BatchRowProblem[]>([]);
  const [validRows, setValidRows] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [format, setFormat] = useState<ExportFormat>("mp4");
  const [quality, setQuality] = useState<ExportQuality>("1080p");
  const [estimate, setEstimate] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [lastPoster, setLastPoster] = useState<string | null>(null);
  const [brokenPoster, setBrokenPoster] = useState<string | null>(null);

  useEffect(() => {
    if (route.kind !== "many-project") return;
    let live = true;
    getProject(route.id).then(
      (project) => {
        if (!live) return;
        const template = catalog.templates.find((item) => item.id === project.template);
        if (!template) {
          setBaseError(new Error("This video uses a design that isn't available anymore."));
          return;
        }
        setBase({
          template,
          params: initialParams(template.defaults, project.params),
          settings: initialSettings(template, project.settings),
        });
      },
      (error) => live && setBaseError(error),
    );
    return () => { live = false; };
  }, [route, catalog]);

  const readList = async (body: { filename?: string; data?: string; text?: string }) => {
    if (!base || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const result = await parseBatch({ template: base.template.id, ...body });
      setParsed(result);
      setMapping(result.suggested_mapping ?? {});
      setTitleColumn(result.suggested_title_column ?? null);
      setPreviewIndex(0);
      setRowProblems([]);
      setValidRows(null);
      setStep(1);
    } catch (error) {
      setProblem(friendlyError(error, "Couldn't read that list. Check the file and try again."));
    } finally {
      setBusy(false);
    }
  };

  const acceptFile = async (file: File | undefined) => {
    setFileProblem(null);
    if (!file) return;
    if (!ACCEPTED.test(file.name)) {
      setFileProblem("Choose a CSV, TSV or .xlsx file.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setFileProblem("That file is larger than 2 MB. Split it into a smaller list.");
      return;
    }
    try {
      const data = toBase64(await readFileBytes(file));
      await readList({ filename: file.name, data });
    } catch (error) {
      setFileProblem(friendlyError(error, "That file couldn't be read. Try another one."));
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    void acceptFile(event.dataTransfer.files?.[0]);
  };

  const rows = parsed?.rows ?? [];
  const fields = parsed?.fields ?? [];
  const previewRow = rows[previewIndex] ?? [];
  const previewParams = useMemo(() => {
    if (!base) return null;
    if (!parsed || step === 0) return base.params;
    return rowParams(base.params, parsed.fields, mapping, parsed.rows[previewIndex] ?? []);
  }, [base, parsed, step, mapping, previewIndex]);
  const previewRequest = useMemo(() => (base && previewParams
    ? { template: base.template.id, params: previewParams, settings: base.settings, mode: "poster" as const }
    : null), [base, previewParams]);
  const poster = usePoster(previewRequest);
  const responseUrl = poster.response?.url ?? null;
  if (responseUrl && responseUrl !== lastPoster) setLastPoster(responseUrl);
  const shownPoster = responseUrl ?? lastPoster;
  const healthyPoster = shownPoster && brokenPoster !== shownPoster ? shownPoster : null;
  const previewFailed = !!poster.error;

  const checkKey = useMemo(() => (parsed ? JSON.stringify({ mapping, titleColumn, rows: parsed.rows }) : ""),
    [parsed, mapping, titleColumn]);
  useEffect(() => {
    if (step !== 2 || !base || !parsed) return;
    let live = true;
    const check = async () => {
      setChecking(true);
      setCheckProblem(null);
      try {
        const result = await parseBatch({ template: base.template.id, rows: parsed.rows, mapping,
          params: base.params, settings: base.settings, title_column: titleColumn });
        if (!live) return;
        setRowProblems(result.row_errors ?? []);
        setValidRows(result.valid_rows ?? parsed.rows.length);
      } catch (error) {
        if (!live) return;
        setCheckProblem(friendlyError(error, "Couldn't check the rows right now. You can still try."));
        setValidRows(parsed.rows.length);
      } finally {
        if (live) setChecking(false);
      }
    };
    void check();
    return () => { live = false; };
  }, [step, base, parsed, mapping, titleColumn, checkKey]);

  const readyCount = validRows ?? rows.length;
  useEffect(() => {
    if (step !== 2 || !base || readyCount === 0) return;
    let live = true;
    listExports().then((jobs) => {
      if (!live) return;
      const measured = jobs
        .filter((job) => job.status === "done" && job.template === base.template.id && job.finished && job.created)
        .map((job) => {
          const start = toDate(job.created)?.getTime() ?? 0;
          const end = toDate(job.finished)?.getTime() ?? 0;
          return end > start ? (end - start) / 1000 : 0;
        })
        .filter((seconds) => seconds > 0);
      if (!measured.length) {
        setEstimate(null);
        return;
      }
      const average = measured.reduce((total, seconds) => total + seconds, 0) / measured.length;
      setEstimate(`About ${formatSeconds(average * readyCount)} for ${readyCount} video${readyCount === 1 ? "" : "s"}, from your earlier exports.`);
    }, () => {});
    return () => { live = false; };
  }, [step, base, readyCount]);

  const setFieldColumn = (field: string, value: number) => {
    setMapping((current) => {
      const next = { ...current };
      if (value < 0) delete next[field];
      else next[field] = value;
      return next;
    });
  };

  const backToEditor = route.kind === "many-project"
    ? `#/project/${encodeURIComponent(route.id)}`
    : `#/new/${encodeURIComponent(route.template)}/${encodeURIComponent(route.preset ?? "")}`;

  const make = async () => {
    if (!base || !parsed || creating) return;
    setCreating(true);
    setProblem(null);
    try {
      const result = await startBatch({
        template: base.template.id,
        params: base.params,
        settings: base.settings,
        mapping,
        rows: parsed.rows,
        title_column: titleColumn,
        format,
        quality,
      });
      if (result.row_errors.length) setRowProblems(result.row_errors);
      if (!result.export_ids.length) {
        setProblem("None of these rows can be made yet. Fix the rows above, then try again.");
        setCreating(false);
        return;
      }
      toast.success(`Making ${result.export_ids.length} video${result.export_ids.length === 1 ? "" : "s"}`);
      navigate({ kind: "exports" });
    } catch (error) {
      setProblem(friendlyError(error, "Couldn't start making these videos."));
      setCreating(false);
    }
  };

  if (baseError) {
    const missing = baseError instanceof Error ? baseError.message : "";
    return <div className="studio-many">
      <div className="studio-empty">
        <div className="studio-empty-picture" aria-hidden><FileSpreadsheet /></div>
        <h1 className="studio-empty-title">Couldn't open this list maker.</h1>
        <p className="studio-empty-line">{missing || friendlyError(baseError)}</p>
        <div className="studio-empty-actions"><Button asChild size="md"><a href="#/templates">Choose a design</a></Button></div>
      </div>
    </div>;
  }
  if (!base) {
    return <div className="studio-many studio-many-loading" role="status"><Spinner /> Getting things ready…</div>;
  }

  const countLabel = `${readyCount} video${readyCount === 1 ? "" : "s"}`;
  const ledes = [
    "A spreadsheet, a CSV, or rows you paste. The first line should say what each column is.",
    "We matched the columns we could. Change any that are wrong; an empty cell keeps the design's own text.",
    rowProblems.length
      ? `Rows with problems are skipped. The other ${countLabel} can start right away.`
      : "Choose the file type, then start. Everything stays on this computer.",
  ];

  const caption = step === 0
    ? "Your design"
    : rows.length
      ? `Row ${previewIndex + 1} of ${rows.length} · ${rowLabel(previewRow, titleColumn, "Untitled")}`
      : "Your design";

  return <main className="studio-many" aria-labelledby="studio-many-title">
    <div className="studio-many-inner">
      <header className="studio-many-top">
        <a className="studio-many-back" href={backToEditor}><ArrowLeft aria-hidden /> Back to your video</a>
        <span className="studio-many-kicker">Make many</span>
      </header>

      <div className="studio-many-steps">
        <div className="studio-many-progress" role="progressbar" aria-label="Your progress" aria-valuemin={1}
          aria-valuemax={3} aria-valuenow={step + 1} aria-valuetext={`Step ${step + 1} of 3`}>
          <span style={{ width: `${((step + 1) / 3) * 100}%` }} />
        </div>
        <p>Step {step + 1} of 3</p>
      </div>

      <div className="studio-many-stage">
        <section className="studio-many-form" aria-labelledby="studio-many-title">
          <h1 id="studio-many-title" className="studio-many-question">
            <Faded>{step === 0 ? "Where's your" : step === 1 ? "Match your" : "Ready to make"}</Faded>{" "}
            {step === 0 ? <em>list</em> : step === 1 ? <em>columns</em> : <em>{countLabel}</em>}
            {step === 0 ? "?" : "."}
          </h1>
          <p className="studio-many-lede">{ledes[step]}</p>
          <span className="sr-only" aria-live="polite">{`Step ${step + 1} of 3`}</span>

          {step === 0 && <div className="studio-many-list-source">
            <div
              className="studio-many-drop"
              data-over={dragging ? "true" : undefined}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <span className="studio-many-drop-icon" aria-hidden><FileSpreadsheet /></span>
              <p className="studio-many-drop-title">Drop your spreadsheet here</p>
              <p className="studio-many-drop-line">CSV, TSV or Excel. Up to 200 rows and 2 MB.</p>
              <label className="studio-many-pill">
                <Upload aria-hidden /> Choose a file
                <input
                  ref={fileRef}
                  id="studio-many-file"
                  type="file"
                  accept=".csv,.tsv,.txt,.xlsx"
                  className="sr-only"
                  onChange={(event) => { void acceptFile(event.target.files?.[0]); event.target.value = ""; }}
                />
              </label>
              <button type="button" className="studio-many-sample" onClick={() => downloadSample(base.template)}>
                <Download aria-hidden /> Get a sample file
              </button>
              {fileProblem && <p className="studio-many-problem-line" role="alert">{fileProblem}</p>}
            </div>

            <div className="studio-many-or" aria-hidden><span />or paste your list<span /></div>

            <label className="studio-many-paste" htmlFor="studio-many-paste">
              <span className="studio-many-label">Paste rows from a spreadsheet</span>
              <textarea
                id="studio-many-paste"
                value={paste}
                placeholder={"Title,Date\nFirst video,14 June 2026\nSecond video,21 June 2026"}
                onChange={(event) => setPaste(event.target.value)}
              />
            </label>
            <div className="studio-many-actions">
              <Button variant="primary" size="md" disabled={!paste.trim() || busy} onClick={() => void readList({ text: paste })}>
                {busy ? <Spinner /> : null} Use this list
              </Button>
              {busy && <span className="studio-many-hint" role="status">Reading your list…</span>}
            </div>
            {problem && <p className="studio-many-problem-line" role="alert">{problem}</p>}
          </div>}

          {step === 1 && parsed && <div className="studio-many-match">
            <div className="studio-many-list">
              {fields.length === 0 && <p className="studio-many-hint">This design has no fields a list can fill. Each video will look the same.</p>}
              {fields.map((field) => <div key={field.field} className="studio-many-map-row">
                <div className="studio-many-field">
                  <label htmlFor={`studio-many-field-${field.field}`}>{field.label}</label>
                  <small>{field.kind === "number" ? "A number" : field.kind === "color" ? "A color" : "Text"}</small>
                </div>
                <select
                  id={`studio-many-field-${field.field}`}
                  className="studio-many-select"
                  value={mapping[field.field] ?? -1}
                  onChange={(event) => setFieldColumn(field.field, Number(event.target.value))}
                >
                  <option value={-1}>Keep the design's text</option>
                  {parsed.headers.map((header, index) => <option key={`${header}-${index}`} value={index}>{header}</option>)}
                </select>
              </div>)}
            </div>
            <label className="studio-many-title-column" htmlFor="studio-many-title-column">
              <span>Name each video from</span>
              <select
                id="studio-many-title-column"
                className="studio-many-select"
                value={titleColumn ?? -1}
                onChange={(event) => setTitleColumn(Number(event.target.value) < 0 ? null : Number(event.target.value))}
              >
                <option value={-1}>The design's title and the row number</option>
                {parsed.headers.map((header, index) => <option key={`${header}-${index}`} value={index}>{header}</option>)}
              </select>
            </label>
            <div className="studio-many-actions">
              <Button variant="ghost" size="md" onClick={() => setStep(0)}>Back</Button>
              <Button variant="primary" size="md" onClick={() => setStep(2)}>Continue</Button>
            </div>
          </div>}

          {step === 2 && parsed && <div className="studio-many-ready">
            <div className="studio-many-summary">
              <span>{rows.length} row{rows.length === 1 ? "" : "s"} in your list</span>
              <span>{checking ? <><Spinner className="size-3" /> Checking the rows…</> : `${readyCount} ready to make`}</span>
            </div>
            <div className="studio-many-pickers">
              <label className="studio-many-format" htmlFor="studio-many-format">
                <span>File type</span>
                <select
                  id="studio-many-format"
                  className="studio-many-select"
                  value={format}
                  onChange={(event) => setFormat(event.target.value as ExportFormat)}
                >
                  {EXPORT_FORMATS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label className="studio-many-format" htmlFor="studio-many-quality">
                <span>Quality</span>
                <select
                  id="studio-many-quality"
                  className="studio-many-select"
                  value={quality}
                  onChange={(event) => setQuality(event.target.value as ExportQuality)}
                >
                  {QUALITIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
            </div>
            <p className="studio-many-hint">{EXPORT_FORMATS.find((item) => item.value === format)?.hint}</p>
            <p className="studio-many-hint">{QUALITIES.find((item) => item.value === quality)?.hint}</p>
            {format === "mp4" && base.settings.background?.kind === "transparent" && (
              <p className="studio-many-hint">A see-through background makes MOV files. Choose MOV to know what you get.</p>
            )}
            {(format === "webm" || format === "mov") && base.settings.background?.kind !== "transparent" && (
              <p className="studio-many-hint">The video keeps its own background. Set Background to None in the editor to make it see-through.</p>
            )}
            {estimate && <p className="studio-many-hint">{estimate}</p>}
            {rowProblems.length > 0 && <div className="studio-many-problems" role="status">
              <p>{rowProblems.length === 1
                ? "Skip this row. It needs a fix first:"
                : `Skip these ${rowProblems.length}. They need a fix first:`}</p>
              <ul>
                {rowProblems.map((problem) => <li key={`${problem.row}-${problem.title}`}>
                  <strong>Row {problem.row}{problem.title ? ` · ${problem.title}` : ""}</strong>
                  <span>{problem.errors.map((error) => `${error.label}: ${error.message}`).join(" · ")}</span>
                </li>)}
              </ul>
            </div>}
            {checkProblem && <p className="studio-many-hint">{checkProblem}</p>}
            {problem && <p className="studio-many-problem-line" role="alert">{problem}</p>}
            <div className="studio-many-actions">
              <Button variant="ghost" size="md" onClick={() => setStep(1)}>Back</Button>
              <Button variant="primary" size="md" onClick={make} disabled={creating || checking || readyCount === 0}>
                {creating ? <Spinner /> : null}
                Make {readyCount} video{readyCount === 1 ? "" : "s"}
              </Button>
              {checking && <span className="studio-many-hint" role="status">Checking each row…</span>}
            </div>
          </div>}
        </section>

        <aside className="studio-many-preview" aria-label="Preview">
          <div className="studio-many-preview-well" data-state={previewFailed ? "failed" : healthyPoster ? "ready" : "waiting"}>
            {healthyPoster && !previewFailed
              ? <img src={apiUrl(healthyPoster)} alt={step === 0 ? "Preview of your design" : `Preview of row ${previewIndex + 1}`}
                  onError={() => setBrokenPoster(healthyPoster)} />
              : previewFailed
                ? <span className="studio-many-preview-note">{rowPreviewProblem(poster.error)}</span>
                : <span className="studio-many-preview-note" role="status"><Spinner /> Getting the preview ready…</span>}
          </div>
          <div className="studio-many-preview-bar">
            <p className="studio-many-caption" aria-live="polite">{caption}</p>
            {step === 1 && rows.length > 0 && <div className="studio-many-arrows">
              <Button variant="secondary" size="icon" aria-label="Previous row" disabled={previewIndex <= 0}
                onClick={() => setPreviewIndex((index) => Math.max(0, index - 1))}><ChevronLeft /></Button>
              <Button variant="secondary" size="icon" aria-label="Next row" disabled={previewIndex >= rows.length - 1}
                onClick={() => setPreviewIndex((index) => Math.min(rows.length - 1, index + 1))}><ChevronRight /></Button>
            </div>}
          </div>
        </aside>
      </div>
    </div>
  </main>;
}
