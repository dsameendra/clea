import { useCallback, useState } from "react";
import { load, save } from "../lib/storage.js";

const DEFAULTS = { perPage: 10, newTab: false };

export function useSettings() {
  const [settings, setSettings] = useState(() => ({ ...DEFAULTS, ...load("clea.settings", {}) }));
  const update = useCallback((patch) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      save("clea.settings", next);
      return next;
    });
  }, []);
  return [settings, update];
}
