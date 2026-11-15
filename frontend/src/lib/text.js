// Text helpers for the browser search engine: a light English stemmer and snippet builder.

const WORD_RE = /[\p{L}\p{N}_]+/gu;

/**
 * A deliberately light stemmer (plural / -ing / -ed / -ly) so "cooking" finds "cooked".
 * Applied identically to documents and queries, so its output only has to be consistent.
 */
export function stem(word) {
  let w = word.toLowerCase();
  if (w.length <= 3 || /\d/.test(w)) return w;
  if (w.endsWith("ies") && w.length > 4) w = w.slice(0, -3) + "y";
  else if (w.endsWith("sses")) w = w.slice(0, -2);
  else if (w.endsWith("s") && !w.endsWith("ss") && !w.endsWith("us") && !w.endsWith("is")) w = w.slice(0, -1);
  if (w.length > 5 && w.endsWith("ing")) w = w.slice(0, -3);
  else if (w.length > 4 && w.endsWith("ed")) w = w.slice(0, -2);
  else if (w.length > 5 && w.endsWith("ly")) w = w.slice(0, -2);
  if (w.length > 3 && /([^aeiouslz])\1$/.test(w)) w = w.slice(0, -1); // running -> runn -> run
  return w;
}

/** Split ``text`` into ``[{text, match}]`` segments, marking words whose stem satisfies ``isMatch``. */
export function markText(text, isMatch) {
  const segments = [];
  let last = 0;
  for (const m of (text || "").matchAll(WORD_RE)) {
    if (!isMatch(m[0])) continue;
    if (m.index > last) segments.push({ text: text.slice(last, m.index), match: false });
    segments.push({ text: m[0], match: true });
    last = m.index + m[0].length;
  }
  if (last < (text || "").length) segments.push({ text: text.slice(last), match: false });
  return segments;
}

/** Pick the ~``size``-character window of ``text`` with the most matching words. */
export function makeSnippet(text, isMatch, size = 220) {
  if (!text) return [];
  const hits = [];
  for (const m of text.matchAll(WORD_RE)) if (isMatch(m[0])) hits.push(m.index);
  let start = 0;
  if (hits.length) {
    let best = 0;
    let bestCount = 0;
    for (let i = 0, j = 0; i < hits.length; i++) {
      while (hits[i] - hits[j] > size * 0.8) j++;
      if (i - j + 1 > bestCount) { bestCount = i - j + 1; best = hits[j]; }
    }
    start = Math.max(0, best - 60);
    const space = text.lastIndexOf(" ", start);
    start = start === 0 ? 0 : space + 1;
  }
  let end = Math.min(text.length, start + size);
  if (end < text.length) {
    const space = text.lastIndexOf(" ", end);
    if (space > start + size / 2) end = space;
  }
  const window = (start > 0 ? "… " : "") + text.slice(start, end).trim() + (end < text.length ? " …" : "");
  return markText(window, isMatch);
}
