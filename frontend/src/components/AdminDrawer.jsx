import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Drawer,
  Group,
  Loader,
  Menu,
  Modal,
  NumberInput,
  PasswordInput,
  Popover,
  Progress,
  ScrollArea,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconDots,
  IconPlayerPlay,
  IconPlayerStop,
  IconRefresh,
  IconSettings,
  IconTrash,
} from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { save } from "../lib/storage.js";
import { timeAgo } from "../lib/time.js";

const STATUS_COLORS = { ok: "green", error: "red", crawling: "orange", pending: "gray" };
const JOB_COLORS = { done: "green", failed: "red", cancelled: "gray", interrupted: "yellow", running: "orange", queued: "blue" };
const isActive = (job) => job && (job.status === "queued" || job.status === "running");

function TokenPrompt({ onSaved }) {
  const [token, setToken] = useState("");
  return (
    <Alert variant="light" color="orange" title="Admin token required" icon={<IconAlertTriangle size={18} />}>
      <Text size="sm" mb="sm">
        This server is protected by <code>CLEA_ADMIN_TOKEN</code>. Enter it to manage sites and crawls.
      </Text>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save("clea.adminToken", token.trim());
          onSaved();
        }}
      >
        <Group align="flex-end" wrap="nowrap">
          <PasswordInput
            aria-label="Admin token"
            value={token}
            onChange={(e) => setToken(e.currentTarget.value)}
            style={{ flex: 1 }}
            autoComplete="off"
          />
          <Button type="submit" disabled={!token.trim()}>
            Unlock
          </Button>
        </Group>
      </form>
    </Alert>
  );
}

function JobCard({ job, onCancel }) {
  const active = isActive(job);
  return (
    <div className="glass" style={{ padding: 14 }}>
      <Group justify="space-between" mb={6}>
        <Group gap={8}>
          <Text fw={600}>Crawl #{job.id}</Text>
          <Badge color={JOB_COLORS[job.status] || "gray"} variant="light">
            {job.status}
          </Badge>
        </Group>
        {active && (
          <Button size="xs" variant="light" color="red" leftSection={<IconPlayerStop size={14} />} onClick={() => onCancel(job.id)}>
            Stop
          </Button>
        )}
      </Group>
      {active && <Progress value={100} animated striped size="sm" mb={8} aria-label="Crawl in progress" />}
      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
        {job.pages_indexed} indexed · {job.pages_fetched} fetched · {job.pages_skipped} skipped · {job.pages_failed} failed
      </Text>
      {active && job.current_url && (
        <Text size="xs" className="job-url mono" mt={4} title={job.current_url}>
          {job.current_url}
        </Text>
      )}
      {!active && (
        <Text size="xs" c="dimmed" mt={4}>
          {job.message}
          {job.error && ` — ${job.error}`} · {timeAgo(job.finished_at || job.created_at)}
        </Text>
      )}
    </div>
  );
}

function LimitsPopover({ site, onSave }) {
  const [opened, setOpened] = useState(false);
  const [maxPages, setMaxPages] = useState(site.max_pages);
  const [maxDepth, setMaxDepth] = useState(site.max_depth);
  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" withArrow trapFocus shadow="md">
      <Popover.Target>
        <Tooltip label="Crawl limits">
          <ActionIcon variant="subtle" color="gray" onClick={() => setOpened((o) => !o)} aria-label="Edit crawl limits">
            <IconSettings size={18} />
          </ActionIcon>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" w={220}>
          <NumberInput label="Max pages" min={1} max={100000} value={maxPages} onChange={setMaxPages} />
          <NumberInput label="Max link depth" min={0} max={20} value={maxDepth} onChange={setMaxDepth} />
          <Button
            size="xs"
            onClick={async () => {
              await onSave(site.id, { max_pages: maxPages, max_depth: maxDepth });
              setOpened(false);
            }}
          >
            Save
          </Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function FailedUrlsModal({ site, onClose }) {
  const [urls, setUrls] = useState(null);
  useEffect(() => {
    if (!site) return;
    setUrls(null);
    Promise.all([api.siteUrls(site.id, "failed"), api.siteUrls(site.id, "skipped")])
      .then(([failed, skipped]) => setUrls([...failed, ...skipped]))
      .catch(() => setUrls([]));
  }, [site]);
  return (
    <Modal opened={!!site} onClose={onClose} title={site ? `Problems on ${site.host}` : ""} size="xl" centered>
      {!urls ? (
        <Group justify="center" p="lg">
          <Loader />
        </Group>
      ) : urls.length === 0 ? (
        <Text c="dimmed">No failed or skipped pages.</Text>
      ) : (
        <ScrollArea.Autosize mah="60vh">
          <Table striped verticalSpacing={6} fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>URL</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Reason</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {urls.map((u) => (
                <Table.Tr key={u.url}>
                  <Table.Td style={{ maxWidth: 320, overflowWrap: "anywhere" }} className="mono">
                    {u.url}
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={u.status === "failed" ? "red" : "gray"}>
                      {u.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td style={{ overflowWrap: "anywhere" }}>{u.reason}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea.Autosize>
      )}
    </Modal>
  );
}

function SiteRow({ site, busy, onCrawl, onRemove, onUpdate, onShowProblems }) {
  return (
    <div className="glass site-row">
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div style={{ minWidth: 0 }}>
          <Anchor href={site.seed_url} target="_blank" rel="noreferrer" className="site-url" c="var(--clea-text)">
            {site.seed_url}
          </Anchor>
          <Group gap={6} mt={6}>
            <Tooltip label={site.last_error || "Crawl status"} disabled={!site.last_error && site.status !== "error"} multiline maw={320}>
              <Badge color={STATUS_COLORS[site.status] || "gray"} variant="light">
                {site.status}
              </Badge>
            </Tooltip>
            <Text size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
              {site.documents}/{site.max_pages} pages · depth ≤ {site.max_depth}
              {site.path_prefix !== "/" && ` · within ${site.path_prefix}`}
              {site.queued > 0 && ` · ${site.queued} queued`} · crawled {timeAgo(site.last_crawled_at)}
            </Text>
            {site.failed > 0 && (
              <Anchor component="button" type="button" size="xs" c="red" onClick={() => onShowProblems(site)}>
                {site.failed} failed
              </Anchor>
            )}
          </Group>
        </div>
        <Group gap={2} wrap="nowrap">
          <Tooltip label="Crawl this site">
            <ActionIcon variant="subtle" onClick={() => onCrawl([site.id], false)} disabled={busy} aria-label={`Crawl ${site.host}`}>
              <IconPlayerPlay size={18} />
            </ActionIcon>
          </Tooltip>
          <LimitsPopover site={site} onSave={onUpdate} />
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <ActionIcon variant="subtle" color="gray" aria-label="More actions">
                <IconDots size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconRefresh size={16} />} disabled={busy} onClick={() => onCrawl([site.id], true)}>
                Recrawl all pages
              </Menu.Item>
              <Menu.Item leftSection={<IconAlertTriangle size={16} />} onClick={() => onShowProblems(site)}>
                Failed &amp; skipped pages
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" leftSection={<IconTrash size={16} />} disabled={busy} onClick={() => onRemove(site)}>
                Remove site
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>
    </div>
  );
}

export function AdminDrawer({ opened, onClose, onIndexChanged }) {
  const [sites, setSites] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [needsToken, setNeedsToken] = useState(false);
  const [error, setError] = useState(null);
  const [newUrls, setNewUrls] = useState("");
  const [limits, setLimits] = useState({ max_pages: 200, max_depth: 3 });
  const [adding, setAdding] = useState(false);
  const [addErrors, setAddErrors] = useState([]);
  const [confirmRemove, setConfirmRemove] = useState(null);
  const [problemsSite, setProblemsSite] = useState(null);

  const activeJob = jobs.find(isActive);

  const refresh = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([api.sites(), api.jobs()]);
      setSites(s);
      setJobs(j);
      setNeedsToken(false);
      setError(null);
    } catch (err) {
      if (err.status === 401) setNeedsToken(true);
      else setError(err.message);
    }
  }, []);

  useEffect(() => {
    if (opened) refresh();
  }, [opened, refresh]);

  // Poll while a crawl is running; refresh the index stats when it finishes.
  useEffect(() => {
    if (!opened || !activeJob) return undefined;
    const timer = setInterval(async () => {
      try {
        const latest = await api.jobs();
        setJobs(latest);
        if (!latest.some(isActive)) {
          setSites(await api.sites());
          onIndexChanged?.();
        }
      } catch {
        /* transient; keep polling */
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [opened, activeJob, onIndexChanged]);

  const run = async (fn) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      if (err.status === 401) setNeedsToken(true);
      else setError(err.message);
    }
    await refresh();
  };

  const addSites = async (e) => {
    e.preventDefault();
    const urls = newUrls.split(/[\n,\s]+/).map((u) => u.trim()).filter(Boolean);
    if (!urls.length) return;
    setAdding(true);
    setAddErrors([]);
    await run(async () => {
      try {
        const res = await api.addSites(urls, limits);
        setAddErrors(res.errors || []);
        setNewUrls("");
      } catch (err) {
        if (err.status === 400) setAddErrors(urls.map((url) => ({ url, error: err.message })));
        else throw err;
      }
    });
    setAdding(false);
  };

  const crawl = (siteIds, recrawl) => run(() => api.crawl({ site_ids: siteIds, recrawl }));

  return (
    <Drawer opened={opened} onClose={onClose} title={<Title order={3}>Manage index</Title>} position="right" size="xl" padding="lg">
      {needsToken ? (
        <TokenPrompt onSaved={refresh} />
      ) : (
        <Stack gap="xl">
          {error && (
            <Alert color="red" variant="light" withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          <section>
            <Title order={5} mb={4}>
              Add sites
            </Title>
            <Text size="sm" c="dimmed" mb="sm">
              Clea follows links within each site (and below its path, e.g. <code>/docs/</code>), up to the limits
              below. It respects robots.txt.
            </Text>
            <form onSubmit={addSites}>
              <Stack gap="sm">
                <Textarea
                  aria-label="Site URLs"
                  placeholder={"https://docs.python.org/3/tutorial/\nhttps://example.com"}
                  autosize
                  minRows={2}
                  maxRows={8}
                  value={newUrls}
                  onChange={(e) => setNewUrls(e.currentTarget.value)}
                />
                <Group align="flex-end" wrap="wrap">
                  <NumberInput label="Max pages per site" min={1} max={100000} w={160} value={limits.max_pages} onChange={(v) => setLimits((l) => ({ ...l, max_pages: v }))} />
                  <NumberInput label="Max link depth" min={0} max={20} w={140} value={limits.max_depth} onChange={(v) => setLimits((l) => ({ ...l, max_depth: v }))} />
                  <Button type="submit" loading={adding} disabled={!newUrls.trim()}>
                    Add
                  </Button>
                </Group>
                {addErrors.map((e) => (
                  <Text key={e.url} size="sm" c="red">
                    {e.url}: {e.error}
                  </Text>
                ))}
              </Stack>
            </form>
          </section>

          <section>
            <Group justify="space-between" mb="sm">
              <Title order={5}>Crawl</Title>
              <Group gap="xs">
                <Button
                  size="xs"
                  leftSection={<IconPlayerPlay size={14} />}
                  disabled={!!activeJob || !sites?.length}
                  onClick={() => crawl(null, false)}
                >
                  Crawl new pages
                </Button>
                <Tooltip label="Re-fetch every known page (unchanged pages are cheap: Clea uses conditional requests)" multiline maw={260}>
                  <Button
                    size="xs"
                    variant="light"
                    leftSection={<IconRefresh size={14} />}
                    disabled={!!activeJob || !sites?.length}
                    onClick={() => crawl(null, true)}
                  >
                    Recrawl everything
                  </Button>
                </Tooltip>
              </Group>
            </Group>
            <Stack gap="xs">
              {jobs.length === 0 ? (
                <Text size="sm" c="dimmed">
                  No crawls yet.
                </Text>
              ) : (
                jobs.slice(0, activeJob ? 3 : 2).map((job) => (
                  <JobCard key={job.id} job={job} onCancel={(id) => run(() => api.cancelJob(id))} />
                ))
              )}
            </Stack>
          </section>

          <section>
            <Title order={5} mb="sm">
              Sites {sites ? `(${sites.length})` : ""}
            </Title>
            {!sites ? (
              <Group justify="center" p="lg">
                <Loader />
              </Group>
            ) : sites.length === 0 ? (
              <Text size="sm" c="dimmed">
                No sites yet. Add one above, then press “Crawl new pages”.
              </Text>
            ) : (
              <Stack gap="xs">
                {sites.map((site) => (
                  <SiteRow
                    key={site.id}
                    site={site}
                    busy={!!activeJob}
                    onCrawl={crawl}
                    onUpdate={(id, l) => run(() => api.updateSite(id, l))}
                    onRemove={setConfirmRemove}
                    onShowProblems={setProblemsSite}
                  />
                ))}
              </Stack>
            )}
          </section>
        </Stack>
      )}

      <Modal opened={!!confirmRemove} onClose={() => setConfirmRemove(null)} title="Remove site?" centered>
        <Text size="sm">
          This removes <b>{confirmRemove?.seed_url}</b> and its {confirmRemove?.documents} indexed pages from the index.
        </Text>
        <Group justify="flex-end" mt="lg">
          <Button variant="default" onClick={() => setConfirmRemove(null)}>
            Cancel
          </Button>
          <Button
            color="red"
            onClick={async () => {
              const site = confirmRemove;
              setConfirmRemove(null);
              await run(() => api.removeSite(site.id));
              onIndexChanged?.();
            }}
          >
            Remove
          </Button>
        </Group>
      </Modal>
      <FailedUrlsModal site={problemsSite} onClose={() => setProblemsSite(null)} />
    </Drawer>
  );
}
