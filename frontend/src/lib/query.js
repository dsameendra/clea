// Query syntax shared with the Python backend (clea/servir.py):
//   word word        all words (falls back to any word when nothing matches)
//   "exact phrase"   phrase
//   -word            exclude
//   prefix*          prefix match
//   site:host        restrict to a host and its subdomains
//   intitle:word     word must be in the title

const TOKEN_RE = /[\p{L}\p{N}_]+/gu;
export const MAX_QUERY_LENGTH = 512;

export function tokenize(text) {
  return (text || "").toLowerCase().match(TOKEN_RE) || [];
}

export function parseQuery(raw) {
  const q = { terms: [], prefixes: [], phrases: [], excluded: [], titleTerms: [], sites: [] };
  const input = (raw || "").slice(0, MAX_QUERY_LENGTH);
  const re = /(-?)"([^"]*)"?|(\S+)/g;
  let m;
  while ((m = re.exec(input))) {
    const [, negated, phrase, word] = m;
    if (phrase !== undefined) {
      const tokens = tokenize(phrase);
      if (!tokens.length) continue;
      if (negated) q.excluded.push(tokens.join(" "));
      else if (tokens.length === 1) q.terms.push(tokens[0]);
      else q.phrases.push(tokens.join(" "));
      continue;
    }
    const lower = word.toLowerCase();
    if (lower.startsWith("site:") && word.length > 5) {
      const host = lower.slice(5).replace(/^\/+|\/+$/g, "").replace(/^www\./, "");
      if (host) q.sites.push(host);
      continue;
    }
    if (lower.startsWith("intitle:") && word.length > 8) {
      q.titleTerms.push(...tokenize(word.slice(8)));
      continue;
    }
    if (word.startsWith("-") && word.length > 1) {
      q.excluded.push(...tokenize(word.slice(1)));
      continue;
    }
    const tokens = tokenize(word);
    if (!tokens.length) continue;
    if (tokens.length > 1) q.phrases.push(tokens.join(" "));
    else if (word.endsWith("*")) q.prefixes.push(tokens[0]);
    else q.terms.push(tokens[0]);
  }
  return q;
}

export function hasText(q) {
  return q.terms.length + q.prefixes.length + q.phrases.length + q.titleTerms.length > 0;
}

export function isEmptyQuery(q) {
  return !hasText(q) && q.sites.length === 0;
}
