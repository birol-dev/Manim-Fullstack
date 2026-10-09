/** Split a path after each "/" or "\" (the separator stays on the left segment), for wrapping. */
export function pathSegments(path: string): string[] {
  return path.split(/(?<=[/\\])/).filter(Boolean);
}
