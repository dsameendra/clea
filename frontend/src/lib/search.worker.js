// Runs the static search engine off the main thread: downloading and indexing
// the exported JSON doesn't block typing.
import { createEngine } from "./staticEngine.js";

let enginePromise = null;

function load(dataUrl) {
  if (!enginePromise) {
    enginePromise = fetch(dataUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load the search index (HTTP ${res.status})`);
        return res.json();
      })
      .then((data) => createEngine(data));
    enginePromise.catch(() => { enginePromise = null; });
  }
  return enginePromise;
}

self.onmessage = async (event) => {
  const { id, type, dataUrl, args } = event.data;
  try {
    const engine = await load(dataUrl);
    let result;
    if (type === "search") result = engine.search(args.query, args.options);
    else if (type === "suggest") result = engine.autocomplete(args.query);
    else if (type === "stats") result = engine.stats();
    else if (type === "warmup") result = true;
    else throw new Error(`Unknown request ${type}`);
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
