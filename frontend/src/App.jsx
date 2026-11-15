import { ActionIcon, Anchor, Chip, Group, Popover, Tooltip, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { IconChartBar, IconHelpCircle, IconMoon, IconSettings, IconSitemap, IconSun } from "@tabler/icons-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Logo } from "./components/Logo.jsx";
import { Results } from "./components/Results.jsx";
import { SearchBox } from "./components/SearchBox.jsx";
import { SearchTips } from "./components/SearchTips.jsx";
import { SettingsModal } from "./components/SettingsModal.jsx";
import { StatsModal } from "./components/StatsModal.jsx";
import { useSettings } from "./hooks/useSettings.js";
import { REPO_URL } from "./lib/config.js";
import { instantAnswer } from "./lib/instant/index.js";
import { isStatic, searchClient } from "./lib/searchClient.js";
import { timeAgo } from "./lib/time.js";
import { useUrlState } from "./lib/urlState.js";

// Only the self-hosted build has an admin panel; load it on demand.
const AdminDrawer = lazy(() => import("./components/AdminDrawer.jsx").then((m) => ({ default: m.AdminDrawer })));

function useSpotlight(ref) {
  useEffect(() => {
    if (window.matchMedia("(hover: none), (prefers-reduced-motion: reduce)").matches) return undefined;
    let frame = 0;
    const onMove = (e) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        ref.current?.style.setProperty("--spot-x", `${(e.clientX / window.innerWidth) * 100}%`);
        ref.current?.style.setProperty("--spot-y", `${(e.clientY / window.innerHeight) * 100}%`);
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, [ref]);
}

function IconButton({ label, onClick, children }) {
  return (
    <Tooltip label={label} withArrow>
      <ActionIcon variant="subtle" color="gray" size="lg" radius="md" onClick={onClick} aria-label={label}>
        {children}
      </ActionIcon>
    </Tooltip>
  );
}

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("dark");
  const next = computed === "dark" ? "light" : "dark";
  return (
    <IconButton label={`Switch to ${next} mode`} onClick={() => setColorScheme(next)}>
      {computed === "dark" ? <IconSun size={20} /> : <IconMoon size={20} />}
    </IconButton>
  );
}

export default function App() {
  const [{ q, page }, navigate] = useUrlState();
  const [settings, updateSettings] = useSettings();
  const [input, setInput] = useState(q);
  const [state, setState] = useState({ status: "idle", data: null, error: null });
  const [stats, setStats] = useState(null);
  const [statsVersion, setStatsVersion] = useState(0);
  const [panel, setPanel] = useState(null); // "admin" | "stats" | "settings"
  const backdropRef = useRef(null);
  useSpotlight(backdropRef);

  useEffect(() => setInput(q), [q]);

  useEffect(() => {
    searchClient.stats().then(setStats).catch(() => setStats(null));
  }, [statsVersion]);

  useEffect(() => {
    document.title = q ? `${q} – Clea` : "Clea";
    if (!q) {
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setState((prev) => ({ status: "loading", data: prev.data, error: null }));
    searchClient
      .search(q, { page, perPage: settings.perPage }, controller.signal)
      .then((data) => setState({ status: "done", data, error: null }))
      .catch((err) => {
        if (err.name !== "AbortError") setState({ status: "error", data: null, error: err.message });
      });
    return () => controller.abort();
  }, [q, page, settings.perPage, statsVersion]);

  const answer = useMemo(() => (q ? instantAnswer(q) : null), [q]);
  const search = useCallback((query) => {
    const trimmed = query.trim();
    navigate(trimmed, 1);
    window.scrollTo({ top: 0 });
  }, [navigate]);
  const goHome = () => navigate("", 1);
  const onIndexChanged = useCallback(() => setStatsVersion((v) => v + 1), []);
  const onResults = Boolean(q);
  const examples = [
    stats?.top_hosts?.[0] && `site:${stats.top_hosts[0].host}`,
    "10 km in miles",
    "15% of 240",
  ].filter(Boolean);

  return (
    <>
      <div className="backdrop" ref={backdropRef} aria-hidden />
      <div className="shell">
        <header className="topbar" data-results={onResults}>
          <div className="topbar-inner">
            {onResults && <Logo onClick={goHome} />}
            {onResults && (
              <div className="topbar-search">
                <SearchBox value={input} onChange={setInput} onSearch={search} loading={state.status === "loading"} />
              </div>
            )}
            <nav className="topbar-actions" aria-label="Tools">
              <Popover width={360} position="bottom-end" withArrow shadow="md">
                <Popover.Target>
                  <ActionIcon variant="subtle" color="gray" size="lg" radius="md" aria-label="Search tips">
                    <IconHelpCircle size={20} />
                  </ActionIcon>
                </Popover.Target>
                <Popover.Dropdown>
                  <SearchTips />
                </Popover.Dropdown>
              </Popover>
              <IconButton label="Index statistics" onClick={() => setPanel("stats")}>
                <IconChartBar size={20} />
              </IconButton>
              {!isStatic && (
                <IconButton label="Manage sites & crawls" onClick={() => setPanel("admin")}>
                  <IconSitemap size={20} />
                </IconButton>
              )}
              <ThemeToggle />
              <IconButton label="Settings" onClick={() => setPanel("settings")}>
                <IconSettings size={20} />
              </IconButton>
            </nav>
          </div>
        </header>

        <main className="main" id="main">
          {onResults ? (
            <Results
              query={q}
              page={page}
              state={state}
              answer={answer}
              settings={settings}
              onSearch={search}
              onPage={(p) => {
                navigate(q, p);
                window.scrollTo({ top: 0 });
              }}
              canAdmin={!isStatic}
              onShowAdmin={() => setPanel("admin")}
            />
          ) : (
            <section className="hero">
              <Logo size="hero" onClick={goHome} />
              <p className="hero-tagline">Cléa — from <i>clé</i>, the key. A search engine for the sites you care about.</p>
              <div className="hero-search">
                <SearchBox value={input} onChange={setInput} onSearch={search} size="lg" autoFocus />
              </div>
              <div className="hero-meta" role="status">
                {stats
                  ? stats.documents > 0
                    ? `Searching ${stats.documents.toLocaleString()} pages from ${stats.sites.toLocaleString()} site${stats.sites === 1 ? "" : "s"} · updated ${timeAgo(stats.last_indexed_at)}`
                    : isStatic
                      ? "The index is empty."
                      : "The index is empty — add a site to get started."
                  : " "}
              </div>
              {stats?.documents === 0 && !isStatic ? (
                <Anchor component="button" type="button" onClick={() => setPanel("admin")}>
                  Add your first site
                </Anchor>
              ) : (
                <Group className="examples" gap={8}>
                  {examples.map((ex) => (
                    <Chip key={ex} checked={false} variant="outline" size="sm" onClick={() => search(ex)}>
                      {ex}
                    </Chip>
                  ))}
                </Group>
              )}
            </section>
          )}
        </main>

        <footer className="footer">
          Clea is open source ·{" "}
          <Anchor href={REPO_URL} target="_blank" rel="noreferrer" size="sm" c="dimmed" underline="always">
            GitHub
          </Anchor>
          {isStatic && " · static demo"}
        </footer>
      </div>

      {!isStatic && panel === "admin" && (
        <Suspense fallback={null}>
          <AdminDrawer opened onClose={() => setPanel(null)} onIndexChanged={onIndexChanged} />
        </Suspense>
      )}
      <StatsModal opened={panel === "stats"} onClose={() => setPanel(null)} />
      <SettingsModal opened={panel === "settings"} onClose={() => setPanel(null)} settings={settings} onChange={updateSettings} />
    </>
  );
}
