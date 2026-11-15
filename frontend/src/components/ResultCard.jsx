import { Marked } from "./Marked.jsx";

function displayUrl(url) {
  try {
    const u = new URL(url);
    const path = decodeURI(u.pathname + u.search).replace(/\/$/, "");
    return path ? path.split("/").filter(Boolean).join(" › ") : "";
  } catch {
    return url;
  }
}

export function ResultCard({ result, index, newTab }) {
  const host = result.host?.replace(/^www\./, "") || "";
  const path = displayUrl(result.url);
  return (
    <article className="glass result" style={{ animationDelay: `${Math.min(index, 8) * 30}ms` }}>
      <div className="result-host">
        <span className="result-host-badge" aria-hidden>{host.charAt(0) || "?"}</span>
        <span className="result-url" title={result.url}>
          {host}
          {path && ` › ${path}`}
        </span>
      </div>
      <a
        className="result-title"
        href={result.url}
        rel="noreferrer noopener"
        target={newTab ? "_blank" : undefined}
      >
        <Marked segments={result.title} />
      </a>
      {result.snippet?.length > 0 && (
        <p className="result-snippet">
          <Marked segments={result.snippet} />
        </p>
      )}
    </article>
  );
}
