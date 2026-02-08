// ui/components/hooks/useLocalStorageState.js
// Full updated version: dispatches a same-tab event so other components update immediately.
// (Native "storage" event often does NOT fire in the same tab that wrote the value.)

const { useEffect, useState } = React;

export default function useLocalStorageState(key, initialValue) {
  function readValue() {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null || raw === undefined) return initialValue;

      // Try JSON parse; fall back to raw string
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    } catch {
      return initialValue;
    }
  }

  const [value, setValue] = useState(readValue);

  // Keep state in sync if another tab updates localStorage (native "storage" event)
  useEffect(() => {
    function onStorage(e) {
      if (!e) return;
      if (e.key !== key) return;
      setValue(readValue());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key]);

  // Keep state in sync for same-tab updates (custom event)
  useEffect(() => {
    function onLocalEvent() {
      setValue(readValue());
    }
    window.addEventListener("lunar:ls", onLocalEvent);
    return () => window.removeEventListener("lunar:ls", onLocalEvent);
  }, [key]);

  function writeValue(next) {
    try {
      const nextValue = typeof next === "function" ? next(readValue()) : next;

      // Store objects/arrays as JSON; primitives as JSON too for consistency
      localStorage.setItem(key, JSON.stringify(nextValue));

      // Update our own state immediately
      setValue(nextValue);

      // ✅ notify other components in SAME TAB
      window.dispatchEvent(new Event("lunar:ls"));

      return nextValue;
    } catch {
      // ignore
      return value;
    }
  }

  return [value, writeValue];
}
