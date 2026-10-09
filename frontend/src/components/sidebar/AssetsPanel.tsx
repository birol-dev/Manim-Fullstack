import { useRef, useState } from "react";
import { Check, Copy, CornerDownLeft, FileAudio, FileType, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Section } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { ApiError, apiUrl, errorMessage } from "@/lib/api";
import { ALLOWED_ASSET_EXTENSIONS } from "@/lib/constants";
import { assetKind, assetUsageSnippet, formatBytes } from "@/lib/format";
import type { AssetFile } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RowActions, SidebarPanel } from "./SidebarPanel";

interface AssetsPanelProps {
  assets: AssetFile[];
  canInsert: boolean;
  onUpload: (file: File, options?: { overwrite?: boolean }) => Promise<void>;
  onInsert: (code: string) => void;
  onDelete: (asset: AssetFile) => void;
}

function AssetThumb({ asset }: { asset: AssetFile }) {
  const kind = assetKind(asset.name);
  if (kind === "image" || kind === "vector") {
    return (
      <img
        src={apiUrl(asset.url)}
        alt=""
        loading="lazy"
        className="size-8 shrink-0 rounded border border-line bg-[repeating-conic-gradient(#1d1d22_0_25%,#16161a_0_50%)] bg-[length:8px_8px] object-contain"
      />
    );
  }
  const Icon = kind === "audio" ? FileAudio : FileType;
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded border border-line bg-raised text-fg-subtle">
      <Icon className="size-4" />
    </span>
  );
}

export function AssetsPanel({ assets, canInsert, onUpload, onInsert, onDelete }: AssetsPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);

  const upload = async (fileList: FileList | null) => {
    const filesToUpload = Array.from(fileList ?? []);
    for (const file of filesToUpload) {
      setUploading((count) => count + 1);
      try {
        await onUpload(file);
        toast.success(`Uploaded ${file.name}`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          const replace = window.confirm(`${file.name} already exists. Replace it?`);
          if (replace) {
            try {
              await onUpload(file, { overwrite: true });
              toast.success(`Replaced ${file.name}`);
            } catch (replaceErr) {
              toast.error(errorMessage(replaceErr, `Couldn't replace ${file.name}.`));
            }
          }
        } else {
          toast.error(errorMessage(err, `Couldn't upload ${file.name}.`));
        }
      } finally {
        setUploading((count) => count - 1);
      }
    }
  };

  const copyPath = async (asset: AssetFile) => {
    try {
      await navigator.clipboard.writeText(`assets/${asset.name}`);
      setCopied(asset.name);
      setTimeout(() => setCopied((current) => (current === asset.name ? null : current)), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard.");
    }
  };

  return (
    <SidebarPanel title="Assets">
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void upload(event.dataTransfer.files);
          }}
          className={cn(
            "flex flex-col items-center gap-1.5 rounded-lg border border-dashed px-4 py-5 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-line-strong hover:border-fg-subtle hover:bg-raised/50",
          )}
        >
          {uploading > 0 ? <Loader2 className="size-5 animate-spin text-accent" /> : <Upload className="size-5 text-fg-subtle" />}
          <span className="text-xs font-medium text-fg">{uploading > 0 ? "Uploading…" : "Drop files or click to upload"}</span>
          <span className="text-2xs text-fg-subtle">Images, SVG, audio, fonts · up to 50 MB</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          aria-label="Upload assets"
          accept={ALLOWED_ASSET_EXTENSIONS.join(",")}
          onChange={(event) => {
            void upload(event.target.files);
            event.target.value = "";
          }}
        />

        <Section title={`Library${assets.length ? ` · ${assets.length}` : ""}`}>
          {assets.length === 0 ? (
            <p className="px-1 text-xs leading-relaxed text-fg-subtle">
              Uploaded files live in <code className="font-mono">workspace/assets</code>. Insert one to get the code that loads it.
            </p>
          ) : (
            <ul className="flex flex-col gap-px">
              {assets.map((asset) => (
                <li key={asset.name} className="group flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-raised">
                  <AssetThumb asset={asset} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-fg" title={asset.name}>
                      {asset.name}
                    </p>
                    <p className="text-2xs text-fg-subtle">{formatBytes(asset.size)}</p>
                  </div>
                  <RowActions>
                    <Tooltip content={`Insert ${assetUsageSnippet(asset.name).split("(")[0]}`}>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        aria-label={`Insert ${asset.name}`}
                        disabled={!canInsert}
                        onClick={() => onInsert(assetUsageSnippet(asset.name))}
                      >
                        <CornerDownLeft />
                      </Button>
                    </Tooltip>
                    <Tooltip content="Copy path">
                      <Button variant="ghost" size="icon-xs" aria-label={`Copy path of ${asset.name}`} onClick={() => void copyPath(asset)}>
                        {copied === asset.name ? <Check className="text-success" /> : <Copy />}
                      </Button>
                    </Tooltip>
                    <Tooltip content="Delete">
                      <Button variant="danger-ghost" size="icon-xs" aria-label={`Delete ${asset.name}`} onClick={() => onDelete(asset)}>
                        <Trash2 />
                      </Button>
                    </Tooltip>
                  </RowActions>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </SidebarPanel>
  );
}
