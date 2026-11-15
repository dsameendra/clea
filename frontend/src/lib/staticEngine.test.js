import { describe, expect, it } from "vitest";
import { parseQuery } from "./query.js";
import { createEngine } from "./staticEngine.js";
import { makeSnippet, stem } from "./text.js";

const documents = [
  { id: 1, url: "https://example.com/python", host: "example.com", title: "Python release notes", description: "", body: "Python 3.12 brings a faster interpreter and better error messages.", indexed_at: "2026-01-01T00:00:00Z" },
  { id: 2, url: "https://example.com/rust", host: "example.com", title: "Rust ownership", description: "", body: `${"The borrow checker enforces ownership rules. ".repeat(20)}Mentions python once.`, indexed_at: "" },
  { id: 3, url: "https://blog.example.com/cooking", host: "blog.example.com", title: "Cooking pasta", description: "Pasta basics", body: "Boil water, add salt and cook the pasta until al dente.", indexed_at: "" },
  { id: 4, url: "https://other.org/cpp", host: "other.org", title: "C++ templates", description: "", body: "Templates in c++ allow generic programming with zero overhead.", indexed_at: "" },
];
const words = [["python", 2], ["interpreter", 1], ["templates", 1], ["template", 1], ["pasta", 1], ["ownership", 1]];
const engine = createEngine({ documents, words, generated_at: "2026-01-02T00:00:00Z" });
const urls = (res) => res.results.map((r) => r.url);

describe("query parser", () => {
  it("parses the full syntax", () => {
    expect(parseQuery('foo "exact phrase" -bar -"no way" pre* site:www.Example.com intitle:Hello 3.12')).toEqual({
      terms: ["foo"],
      prefixes: ["pre"],
      phrases: ["exact phrase", "3 12"],
      excluded: ["bar", "no way"],
      titleTerms: ["hello"],
      sites: ["example.com"],
    });
  });
});

describe("static engine", () => {
  it("ranks title matches first", () => {
    expect(urls(engine.search("python"))[0]).toBe("https://example.com/python");
  });

  it("supports numbers, stems, phrases, exclusion, site:, intitle:, prefixes", () => {
    expect(urls(engine.search("3.12"))).toEqual(["https://example.com/python"]);
    expect(urls(engine.search("cooked"))).toContain("https://blog.example.com/cooking");
    expect(urls(engine.search('"borrow checker"'))).toEqual(["https://example.com/rust"]);
    expect(urls(engine.search('"checker borrow"'))).toEqual([]);
    expect(urls(engine.search("python -borrow"))).toEqual(["https://example.com/python"]);
    expect(urls(engine.search("pasta site:example.com"))).toEqual(["https://blog.example.com/cooking"]);
    expect(urls(engine.search("pasta site:other.org"))).toEqual([]);
    expect(urls(engine.search("intitle:ownership"))).toEqual(["https://example.com/rust"]);
    expect(urls(engine.search("templ*"))).toContain("https://other.org/cpp");
    expect(engine.search("site:example.com").total).toBe(3);
  });

  it("tolerates typos and suggests corrections", () => {
    expect(urls(engine.search("interpretr"))).toEqual(["https://example.com/python"]);
    expect(engine.search("interpretr").suggestion).toBe("interpreter");
  });

  it("falls back to any word", () => {
    const res = engine.search("pasta zebra");
    expect(res.relaxed).toBe(true);
    expect(urls(res)).toEqual(["https://blog.example.com/cooking"]);
  });

  it("highlights matches in title and snippet", () => {
    const [first] = engine.search("interpreter").results;
    expect(first.snippet.some((s) => s.match && s.text === "interpreter")).toBe(true);
  });

  it("paginates", () => {
    const many = Array.from({ length: 25 }, (_, i) => ({ id: i + 1, url: `https://e.com/${i}`, host: "e.com", title: `Widget ${i}`, description: "", body: "widget docs", indexed_at: "" }));
    const e = createEngine({ documents: many, words: [] });
    const p3 = e.search("widget", { page: 3, perPage: 10 });
    expect(p3.total).toBe(25);
    expect(p3.results).toHaveLength(5);
  });

  it.each(['"', "c++", "*", "-", "site:", "intitle:", "(", "'; DROP TABLE", "constructor", "__proto__"])("handles %j", (q) => {
    expect(Array.isArray(engine.search(q).results)).toBe(true);
  });

  it("autocompletes from the vocabulary", () => {
    expect(engine.autocomplete("tem")).toEqual(["templates", "template"]);
    expect(engine.autocomplete("c++ tem")[0]).toBe("c++ templates");
    expect(engine.autocomplete("t")).toEqual([]);
  });

  it("reports stats", () => {
    const s = engine.stats();
    expect(s.documents).toBe(4);
    expect(s.top_hosts[0]).toEqual({ host: "example.com", documents: 2 });
  });
});

describe("text helpers", () => {
  it("stems consistently", () => {
    expect(stem("cooking")).toBe(stem("cooked"));
    expect(stem("running")).toBe("run");
    expect(stem("templates")).toBe(stem("template"));
  });

  it("centres snippets on matches", () => {
    const text = `${"filler ".repeat(100)}the needle is here ${"filler ".repeat(100)}`;
    const snippet = makeSnippet(text, (w) => w === "needle");
    expect(snippet.some((s) => s.match)).toBe(true);
    expect(snippet[0].text.startsWith("…")).toBe(true);
  });
});

describe("relaxed fallback", () => {
  it("ignores stop words and bare numbers", () => {
    const res = engine.search("10 km in pasta");
    expect(res.relaxed).toBe(true);
    expect(urls(res)).toEqual(["https://blog.example.com/cooking"]);
  });
});

describe("link-heavy pages", () => {
  // Two identical pages that differ only in link density: the link-heavy one must rank second,
  // whichever order they were indexed in (without the penalty they would tie and keep index order).
  const make = (densityA, densityB) =>
    createEngine({
      documents: [
        { id: 1, url: "https://d.org/a", host: "d.org", title: "Widget functions", description: "", body: "widget function notes", indexed_at: "", link_density: densityA },
        { id: 2, url: "https://d.org/b", host: "d.org", title: "Widget functions", description: "", body: "widget function notes", indexed_at: "", link_density: densityB },
      ],
      words: [],
    });

  it("rank below otherwise identical pages", () => {
    expect(make(0.95, 0.05).search("widget function").results[0].url).toBe("https://d.org/b");
    expect(make(0.05, 0.95).search("widget function").results[0].url).toBe("https://d.org/a");
  });
});
