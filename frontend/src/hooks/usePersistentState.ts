import { useCallback, useState } from "react";

import { readStored, writeStored } from "@/lib/storage";

/** useState that is mirrored to localStorage under *key*. */
export function usePersistentState<T>(key: string, initial: T | (() => T)) {
  const [value, setValue] = useState<T>(() =>
    readStored<T>(key, typeof initial === "function" ? (initial as () => T)() : initial),
  );

  const update = useCallback(
    (next: T | ((previous: T) => T)) => {
      setValue((previous) => {
        const resolved = typeof next === "function" ? (next as (previous: T) => T)(previous) : next;
        writeStored(key, resolved);
        return resolved;
      });
    },
    [key],
  );

  return [value, update] as const;
}
