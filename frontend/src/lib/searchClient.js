// One interface over both back ends: the Flask API, or the static index in a Web Worker.
import { api } from "./api.js";
import { DATA_URL, SEARCH_MODE } from "./config.js";

let worker = null;
let nextId = 1;
const pending = new Map();

function workerCall(type, args) {
  if (!worker) {
    worker = new Worker(new URL("./search.worker.js", import.meta.url), { type: "module" });
    worker.onmessage = ({ data }) => {
      const entry = pending.get(data.id);
      if (!entry) return;
      pending.delete(data.id);
      if (data.error) entry.reject(new Error(data.error));
      else entry.resolve(data.result);
    };
    worker.onerror = (event) => {
      for (const entry of pending.values()) entry.reject(new Error(event.message || "Search worker failed"));
      pending.clear();
    };
  }
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, dataUrl: DATA_URL, args });
  });
}

export const isStatic = SEARCH_MODE === "static";

export const searchClient = isStatic
  ? {
      warmup: () => workerCall("warmup"),
      search: (query, options) => workerCall("search", { query, options }),
      suggest: (query) => workerCall("suggest", { query }),
      stats: () => workerCall("stats"),
    }
  : {
      warmup: () => Promise.resolve(true),
      search: (query, options, signal) => api.search(query, options, signal),
      suggest: (query, signal) => api.suggest(query, signal),
      stats: () => api.stats(),
    };
