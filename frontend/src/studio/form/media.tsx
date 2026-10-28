/** Picture and icon widgets. */
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { ImageIcon, ImagePlus, Search, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { AssetFile } from "@/lib/types";
import { cn } from "@/lib/utils";

import { assetUrl, friendlyError, listIcons, listImages, uploadImage } from "../api";
import { inputClass, Spinner, StudioIcon } from "../components";
import { iconLabel } from "../options";
import type { WidgetProps } from "./fields";

const ACCEPT = "image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.png,.jpg,.jpeg,.gif,.webp,.svg";

function Thumb({ name, shape, className }: { name: string | null; shape?: string; className?: string }) {
  const round = shape === "circle";
  return (
    <div
      className={cn(
        "flex size-16 shrink-0 items-center justify-center overflow-hidden border border-line-strong",
        round ? "rounded-full" : "rounded-lg",
        name && shape === "logo" ? "studio-checker" : "bg-canvas",
        className,
      )}
    >
      {name ? (
        <img
          src={assetUrl(name)}
          alt=""
          className={cn("size-full", shape === "logo" ? "object-contain p-1" : "object-cover")}
        />
      ) : (
        <ImageIcon aria-hidden className="size-6 text-fg-subtle" />
      )}
    </div>
  );
}

export function ImageWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const name = typeof value === "string" && value ? value : null;
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setProblem(null);
    try {
      onChange(await uploadImage(file));
    } catch (error) {
      setProblem(friendlyError(error, "Couldn't upload that picture."));
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    void upload(event.dataTransfer.files?.[0]);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        aria-describedby={describedBy}
        className={cn(
          "flex items-center gap-3 rounded-lg border border-dashed p-2.5 transition-colors",
          dragging ? "border-accent bg-accent-soft" : invalid ? "border-danger" : "border-line-strong bg-raised/30",
        )}
      >
        <Thumb name={name} shape={field.shape} />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="truncate text-xs text-fg-muted" title={name ?? undefined}>
            {busy ? "Uploading…" : name ?? "Drop a picture here, or:"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Button id={id} size="sm" onClick={() => fileInput.current?.click()} disabled={busy}>
              {busy ? <Spinner className="size-3.5" /> : <Upload />}
              {name ? "Replace" : "Upload"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPickerOpen(true)} disabled={busy}>
              <ImagePlus />
              Your pictures
            </Button>
            {name && field.nullable !== false && (
              <Button size="sm" variant="danger-ghost" onClick={() => onChange(null)} aria-label={`Remove ${field.title.toLowerCase()}`}>
                <Trash2 />
                Remove
              </Button>
            )}
          </div>
        </div>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          className="hidden"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => {
            void upload(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>
      {problem && (
        <p role="alert" className="text-xs text-danger">
          {problem}
        </p>
      )}
      <ImagePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        selected={name}
        onPick={(picked) => {
          onChange(picked);
          setPickerOpen(false);
        }}
      />
    </div>
  );
}

function ImagePicker({
  open,
  onOpenChange,
  selected,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selected: string | null;
  onPick: (name: string) => void;
}) {
  const [state, setState] = useState<{ images: AssetFile[] | null; error: string | null }>({ images: null, error: null });
  useEffect(() => {
    if (!open) return;
    let live = true;
    listImages().then(
      (images) => live && setState({ images, error: null }),
      (error) => live && setState({ images: [], error: friendlyError(error) }),
    );
    return () => {
      live = false;
    };
  }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Your pictures</DialogTitle>
          <DialogDescription>Pictures you've uploaded before.</DialogDescription>
        </DialogHeader>
        <div className="-mx-1 max-h-[60vh] overflow-y-auto px-1">
          {state.images === null ? (
            <div className="flex items-center gap-2 py-6 text-sm text-fg-muted">
              <Spinner /> Loading…
            </div>
          ) : state.error ? (
            <p className="py-6 text-sm text-danger">{state.error}</p>
          ) : state.images.length === 0 ? (
            <p className="py-6 text-sm text-fg-muted">No pictures yet. Use Upload to add one.</p>
          ) : (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {state.images.map((image) => (
                <button
                  key={image.name}
                  type="button"
                  onClick={() => onPick(image.name)}
                  aria-pressed={image.name === selected}
                  className={cn(
                    "group flex flex-col gap-1 rounded-lg border p-1.5 text-left transition-colors hover:border-accent focus-visible:outline-2 focus-visible:outline-accent",
                    image.name === selected ? "border-accent bg-accent-soft" : "border-line",
                  )}
                >
                  <span className="studio-checker block aspect-square overflow-hidden rounded-md">
                    <img src={assetUrl(image.name)} alt="" loading="lazy" className="size-full object-contain" />
                  </span>
                  <span className="truncate text-xs text-fg-muted">{image.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function IconWidget({ field, value, onChange, id, describedBy, invalid }: WidgetProps) {
  const name = typeof value === "string" && value ? value : null;
  const [open, setOpen] = useState(false);
  return (
    <div
      aria-describedby={describedBy}
      className={cn("flex items-center gap-3 rounded-lg border p-2.5", invalid ? "border-danger" : "border-line-strong bg-raised/30")}
    >
      <div className="flex size-12 shrink-0 items-center justify-center rounded-lg border border-line-strong bg-canvas text-fg">
        {name ? <StudioIcon name={name} className="size-7" /> : <span className="text-xs text-fg-subtle">None</span>}
      </div>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        <span className="mr-auto truncate text-sm text-fg-muted">{name ? iconLabel(name) : "No icon"}</span>
        <Button id={id} size="sm" onClick={() => setOpen(true)}>
          {name ? "Change" : "Choose icon"}
        </Button>
        {name && field.nullable && (
          <Button size="sm" variant="danger-ghost" onClick={() => onChange(null)} aria-label={`Remove ${field.title.toLowerCase()}`}>
            <Trash2 />
          </Button>
        )}
      </div>
      <IconPicker
        open={open}
        onOpenChange={setOpen}
        selected={name}
        title={field.title}
        onPick={(picked) => {
          onChange(picked);
          setOpen(false);
        }}
      />
    </div>
  );
}

function IconPicker({
  open,
  onOpenChange,
  selected,
  title,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selected: string | null;
  title: string;
  onPick: (name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<{ icons: string[] | null; error: string | null }>({ icons: null, error: null });
  useEffect(() => {
    if (!open) return;
    let live = true;
    listIcons().then(
      (icons) => live && setState({ icons, error: null }),
      (error) => live && setState({ icons: [], error: friendlyError(error) }),
    );
    return () => {
      live = false;
    };
  }, [open]);
  const shown = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (state.icons ?? []).filter((icon) => words.every((word) => icon.toLowerCase().replace(/[-_]/g, " ").includes(word)));
  }, [state.icons, query]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>Pick an icon. Type to search, like "gift" or "clock".</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
          <input
            type="search"
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search icons"
            aria-label="Search icons"
            className={cn(inputClass, "h-9 pl-9")}
          />
        </div>
        <div className="-mx-1 max-h-[50vh] overflow-y-auto px-1">
          {state.icons === null ? (
            <div className="flex items-center gap-2 py-6 text-sm text-fg-muted">
              <Spinner /> Loading…
            </div>
          ) : state.error ? (
            <p className="py-6 text-sm text-danger">{state.error}</p>
          ) : shown.length === 0 ? (
            <p className="py-6 text-sm text-fg-muted">No icons match "{query}".</p>
          ) : (
            <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-7">
              {shown.map((icon) => (
                <button
                  key={icon}
                  type="button"
                  onClick={() => onPick(icon)}
                  aria-label={iconLabel(icon)}
                  aria-pressed={icon === selected}
                  title={iconLabel(icon)}
                  className={cn(
                    "flex aspect-square items-center justify-center rounded-lg border text-fg transition-colors hover:border-accent hover:bg-raised focus-visible:outline-2 focus-visible:outline-accent",
                    icon === selected ? "border-accent bg-accent-soft" : "border-line",
                  )}
                >
                  <StudioIcon name={icon} className="size-6" />
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
