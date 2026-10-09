import { Fragment } from "react";

import { codeBreakSegments, fileNameSegments } from "@/lib/timeline";

/**
 * Code rendered with line-break opportunities only between tokens. Pair with
 * the `code-wrap` utility class (normal word-break) so identifiers stay whole.
 */
export function CodeText({ text }: { text: string }) {
  const segments = codeBreakSegments(text);
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
