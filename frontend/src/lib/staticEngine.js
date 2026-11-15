// In-browser search over the static index exported by `python -m clea export`.
// Used on GitHub Pages, where there is no backend. Returns the same response
// shape as the API's /api/search so the UI doesn't care which one it talks to.

import MiniSearch from "minisearch";
import { hasText, isEmptyQuery, parseQuery, tokenize } from "./query.js";
import { makeSnippet, markText, stem } from "./text.js";

const STOP_WORDS = new Set(
  ("a an and are as at be but by for from how if in into is it its no not of on or so such that the their then " +
    "there these they this to was what when where which who why will with you your").split(" "),
);
const MAX_PER_PAGE = 50;
// Same demotion as the server (clea/servir.py): pages that are mostly links rank lower.
const LINK_DENSITY_THRESHOLD = 0.8;
const LINK_PENALTY_SLOPE = 3.0;
const MAX_LINK_PENALTY = 0.6;

export function linkPenalty(density = 0) {
  return 1 - Math.min(MAX_LINK_PENALTY, Math.max(0, density - LINK_DENSITY_THRESHOLD) * LINK_PENALTY_SLOPE);
}

function urlTerms(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "").split(".").slice(0, -1);
    return [...host, ...u.pathname.split(/[^0-9A-Za-z]+/)].filter((w) => w && !["html", "htm", "php", "index"].includes(w)).join(" ");
  } catch {
    return "";
  }
}

function processTerm(term) {
  const t = term.toLowerCase();
  return STOP_WORDS.has(t) ? null : stem(t);
}

function levenshtein(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      rowMin = Math.min(rowMin, cur[j]);
    }
    if (rowMin > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}

export function createEngine(data) {
  const documents = data.documents || [];
  const docs = new Map(documents.map((d) => [d.id, d]));
  const words = data.words || []; // [[word, df], ...] most frequent first
  const vocab = new Set(words.map(([w]) => w));
  const normCache = new Map();

  const index = new MiniSearch({
    fields: ["title", "description", "body", "urlTerms"],
    extractField: (doc, field) => (field === "urlTerms" ? urlTerms(doc.url) : doc[field]),
    processTerm,
    searchOptions: {
      boost: { title: 4, description: 2, urlTerms: 2 },
      boostDocument: (id) => linkPenalty(docs.get(id)?.link_density),
    },
  });
  index.addAll(documents);

  function normalized(doc) {
    let text = normCache.get(doc.id);
    if (text === undefined) {
      text = ` ${tokenize(`${doc.title} ${doc.description} ${doc.body}`).join(" ")} `;
      if (normCache.size > 2000) normCache.clear();
      normCache.set(doc.id, text);
    }
    return text;
  }

  function onSite(doc, sites) {
    return sites.some((s) => doc.host === s || doc.host === `www.${s}` || doc.host.endsWith(`.${s}`));
  }

  function passes(doc, q) {
    if (!doc) return false;
    if (q.sites.length && !onSite(doc, q.sites)) return false;
    if (q.phrases.length || q.excluded.length) {
      const text = normalized(doc);
      if (q.phrases.some((p) => !text.includes(` ${p} `))) return false;
      if (q.excluded.some((e) => text.includes(` ${e} `))) return false;
    }
    if (q.titleTerms.length) {
      const title = new Set(tokenize(doc.title).map(stem));
      if (q.titleTerms.some((t) => !title.has(stem(t)))) return false;
    }
    return true;
  }

  function closestWord(term) {
    const word = term.toLowerCase();
    if (word.length < 3 || vocab.has(word)) return null;
    const max = word.length >= 7 ? 2 : 1;
    let best = null;
    let bestDist = max + 1;
    for (const [candidate] of words) {
      if (candidate[0] !== word[0] || Math.abs(candidate.length - word.length) > max) continue;
      const d = levenshtein(word, candidate, max);
      if (d < bestDist) { best = candidate; bestDist = d; if (d === 1) break; }
    }
    return best;
  }

  function suggestion(raw, q) {
    let corrected = raw;
    let changed = false;
    for (const term of q.terms) {
      const fix = closestWord(term);
      if (fix) {
        corrected = corrected.replace(new RegExp(`(?<![\\w:-])${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\w)`, "i"), fix);
        changed = true;
      }
    }
    return changed ? corrected : null;
  }

  function search(raw, { page = 1, perPage = 10 } = {}) {
    const started = performance.now();
    page = Math.max(1, Math.floor(page) || 1);
    perPage = Math.min(MAX_PER_PAGE, Math.max(1, Math.floor(perPage) || 10));
    const q = parseQuery(raw);
    const response = { query: raw, results: [], total: 0, page, per_page: perPage, relaxed: false, suggestion: null, took_ms: 0 };
    if (isEmptyQuery(q)) return response;

    let hits;
    if (!hasText(q)) {
      hits = documents.filter((d) => passes(d, q)).sort((a, b) => a.url.length - b.url.length || a.url.localeCompare(b.url))
        .map((d) => ({ id: d.id, terms: [] }));
    } else {
      const positives = [...q.terms, ...q.prefixes, ...q.phrases.flatMap((p) => p.split(" ")), ...q.titleTerms];
      const prefixes = new Set(q.prefixes.map(processTerm));
      const run = (combineWith) =>
        index.search(positives.join(" "), {
          combineWith,
          prefix: (term) => prefixes.has(term),
          fuzzy: (term) => (term.length >= 5 ? 0.2 : false),
          filter: (r) => passes(docs.get(r.id), q),
        });
      hits = run("AND");
      if (!hits.length && positives.length > 1) {
        // Any-word fallback: ignore stop words and bare numbers unless nothing else is left.
        const meaningful = positives.filter((t) => !STOP_WORDS.has(t) && !/^\d+$/.test(t));
        if (meaningful.length) positives.splice(0, positives.length, ...meaningful);
        hits = run("OR");
        response.relaxed = hits.length > 0;
      }
    }

    response.total = hits.length;
    response.results = hits.slice((page - 1) * perPage, page * perPage).map((hit) => {
      const doc = docs.get(hit.id);
      const matched = new Set(hit.terms);
      const isMatch = (word) => matched.has(processTerm(word) || "");
      let snippet = makeSnippet(doc.body, isMatch);
      if (!snippet.some((s) => s.match) && doc.description) snippet = markText(doc.description, isMatch);
      return {
        url: doc.url,
        title: doc.title ? markText(doc.title, isMatch) : [{ text: doc.url, match: false }],
        snippet,
        host: doc.host,
        indexed_at: doc.indexed_at,
      };
    });
    if (response.total < 3 && q.terms.length) response.suggestion = suggestion(raw, q);
    response.took_ms = Math.round((performance.now() - started) * 10) / 10;
    return response;
  }

  function autocomplete(prefix, limit = 8) {
    const m = /([\p{L}]+)$/u.exec((prefix || "").toLowerCase());
    if (!m || m[1].length < 2) return [];
    const head = prefix.slice(0, prefix.length - m[1].length);
    const out = [];
    for (const [w] of words) {
      if (w !== m[1] && w.startsWith(m[1])) {
        out.push(head + w);
        if (out.length >= limit) break;
      }
    }
    return out;
  }

  function stats() {
    const hosts = new Map();
    for (const d of documents) hosts.set(d.host, (hosts.get(d.host) || 0) + 1);
    return {
      documents: documents.length,
      sites: hosts.size,
      words: words.length,
      last_indexed_at: data.generated_at || null,
      last_crawled_at: data.generated_at || null,
      top_hosts: [...hosts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([host, count]) => ({ host, documents: count })),
    };
  }

  return { search, autocomplete, stats };
}
