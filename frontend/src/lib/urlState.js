import { useCallback, useEffect, useState } from "react";

function read() {
  const params = new URLSearchParams(window.location.search);
  const page = parseInt(params.get("p") || "1", 10);
  return { q: params.get("q") || "", page: Number.isFinite(page) && page > 0 ? page : 1 };
}

/** Search state lives in the URL (?q=…&p=…) so results can be shared, bookmarked and navigated with Back. */
export function useUrlState() {
  const [state, setState] = useState(read);

  useEffect(() => {
    const onPop = () => setState(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((q, page = 1) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (q && page > 1) params.set("p", String(page));
    const search = params.toString();
    const url = `${window.location.pathname}${search ? `?${search}` : ""}`;
    if (url !== `${window.location.pathname}${window.location.search}`) window.history.pushState(null, "", url);
    setState({ q, page });
  }, []);

  return [state, navigate];
}
