import { useCallback, useEffect, useState } from "react";

import { readStored, writeStored } from "@/lib/storage";

/**
 * useState that is mirrored to localStorage under *key*. With *sync*, it also follows the
 * value other tabs store (a setting changed there applies here without a reload).
 */
export function usePersistentState<T>(key: string, initial: T | (() => T), options: { sync?: boolean } = {}) {
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

  const { sync = false } = options;
  useEffect(() => {
    if (!sync) return;
    const onStorage = (event: StorageEvent) => {
      // A removed key (or a cleared storage) keeps the value this tab has.
      if (event.storageArea !== window.localStorage || event.key !== key || event.newValue === null) return;
      try {
        setValue(JSON.parse(event.newValue) as T);
      } catch {
        // Not JSON: not a value this hook wrote.
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key, sync]);

  return [value, update] as const;
}
