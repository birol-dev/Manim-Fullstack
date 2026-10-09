import { Fragment } from "react";

import { pathSegments } from "@/lib/paths";
import { codeBreakSegments, fileNameSegments } from "@/lib/timeline";

/** No-break spaces inside *segment*; its trailing space stays a normal one. */
function keepTogether(segment: string): string {
  const body = segment.trimEnd();
  return body.replace(/ /g, "\u00a0") + segment.slice(body.length);
}

/**
 * Code rendered with line-break opportunities only between tokens. Pair with
 * the `code-wrap` utility class (normal word-break) so identifiers stay whole.
 */
export function CodeText({ text }: { text: string }) {
  // Spaces inside a segment ("shift(UP * 0.3)") are not break points: no-break spaces keep a short
  // call on one line (a plain space let the browser wrap "shift(UP" / "* 0.3)"). Trailing spaces
  // stay normal; code-wrap still breaks a segment that alone is wider than its box.
  const segments = codeBreakSegments(text).map(keepTogether);
  return (
    <>
      {segments.map((segment, index) => (
        <Fragment key={index}>
          {segment}
          {index < segments.length - 1 && <wbr />}
        </Fragment>
      ))}
    </>
  );
}

function withBreaks(segments: string[]) {
  return segments.map((segment, index) => (
    <Fragment key={index}>
      {segment}
      {index < segments.length - 1 && <wbr />}
    </Fragment>
  ));
}

/** A file name that wraps after "_", "-", "." or camelCase steps instead of mid-word. */
export function FileNameText({ name }: { name: string }) {
  return <>{withBreaks(fileNameSegments(name))}</>;
}

/** A file system path that wraps only after "/" or "\", never mid-name. Pair with `code-wrap`. */
export function PathText({ path }: { path: string }) {
  return <>{withBreaks(pathSegments(path))}</>;
}
