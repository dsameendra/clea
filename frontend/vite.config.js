import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const API_TARGET = "http://127.0.0.1:6942";

/**
 * OpenSearch ("add Clea to your browser"). With the Flask backend the server
 * generates /opensearch.xml; for the static build we emit one when the public
 * URL is known (VITE_PUBLIC_URL, set by the GitHub Pages workflow).
 */
function opensearch(env) {
  const isStatic = env.VITE_SEARCH_MODE === "static";
  const publicUrl = (env.VITE_PUBLIC_URL || "").replace(/\/?$/, "/");
  const enabled = !isStatic || publicUrl !== "/";
  let base = "/";
  return {
    name: "clea-opensearch",
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml() {
      if (!enabled) return [];
      const href = `${base}opensearch.xml`;
      return [{ tag: "link", attrs: { rel: "search", type: "application/opensearchdescription+xml", title: "Clea", href }, injectTo: "head" }];
    },
    generateBundle() {
      if (!isStatic || !enabled) return;
      const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
      this.emitFile({
        type: "asset",
        fileName: "opensearch.xml",
        source: `<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>Clea</ShortName>
  <Description>Clea search (static demo)</Description>
  <InputEncoding>UTF-8</InputEncoding>
  <Image height="16" width="16" type="image/svg+xml">${esc(publicUrl)}favicon.svg</Image>
  <Url type="text/html" method="get" template="${esc(publicUrl)}?q={searchTerms}"/>
</OpenSearchDescription>
`,
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const proxy = { "/api": API_TARGET, "/opensearch.xml": API_TARGET };
  return {
    base: env.VITE_BASE || "/",
    plugins: [react(), opensearch(env)],
    server: { proxy },
    preview: { proxy },
    worker: { format: "es" },
    build: {
      chunkSizeWarningLimit: 700,
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.js"],
    },
  };
});
