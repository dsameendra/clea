import { Alert, Badge, Button, Group, NumberInput, Select, Stack, Switch, Text, Title } from "@mantine/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { timeAgo } from "../lib/time.js";

// Settings are stored in minutes (discover) and hours (refresh); show them in the friendliest unit.
function split(value, small, big, factor) {
  return value >= factor && value % factor === 0 ? { amount: value / factor, unit: big } : { amount: value, unit: small };
}

function toForm(s) {
  const discover = split(s.discover_minutes, "minutes", "hours", 60);
  const refresh = split(s.refresh_hours, "hours", "days", 24);
  return {
    discover_enabled: s.discover_enabled,
    discover_amount: discover.amount,
    discover_unit: discover.unit,
    refresh_enabled: s.refresh_enabled,
    refresh_amount: refresh.amount,
    refresh_unit: refresh.unit,
    max_run_minutes: s.max_run_minutes,
    workers: s.workers,
  };
}

function fromForm(f) {
  return {
    discover_enabled: f.discover_enabled,
    discover_minutes: Number(f.discover_amount) * (f.discover_unit === "hours" ? 60 : 1),
    refresh_enabled: f.refresh_enabled,
    refresh_hours: Number(f.refresh_amount) * (f.refresh_unit === "days" ? 24 : 1),
    max_run_minutes: Number(f.max_run_minutes),
    workers: Number(f.workers),
  };
}

function ScheduleStatus({ info }) {
  if (!info) return null;
  if (info.running) {
    return (
      <Badge color="orange" variant="light" size="sm">
        running now
      </Badge>
    );
  }
  if (!info.enabled) return null;
  return (
    <Text size="xs" c="dimmed">
      Next run {timeAgo(info.next_run_at)}
      {info.last_run_at && ` · last ran ${timeAgo(info.last_run_at)}`}
    </Text>
  );
}

/** "Automatic crawling": find new pages / refresh every page on a schedule, and crawl parallelism. */
export function AutomationPanel({ refreshKey, onError }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  // Keep the latest callback without making `load` (and the effect below) change on every render.
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onErrorRef.current = onError;
  });

  const load = useCallback(async () => {
    try {
      const res = await api.crawlSettings();
      setData(res);
      setForm((current) => current ?? toForm(res.settings));
    } catch (err) {
      onErrorRef.current?.(err);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const dirty = useMemo(() => {
    if (!data || !form) return false;
    const next = fromForm(form);
    return Object.keys(next).some((k) => next[k] !== data.settings[k]);
  }, [data, form]);

  if (!form || !data) return null;
  const set = (patch) => {
    setSaved(false);
    setForm((f) => ({ ...f, ...patch }));
  };
  const { limits } = data;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await api.saveCrawlSettings(fromForm(form));
      setData((d) => ({ ...d, settings: res.settings, schedule: res.schedule }));
      setForm(toForm(res.settings));
      setSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section>
      <Title order={5} mb={4}>
        Automatic crawling
      </Title>
      <Text size="sm" c="dimmed" mb="sm">
        While the server is running, Clea can check your sites on its own. Turn off a site&apos;s
        &ldquo;automatic crawls&rdquo; option to leave it out.
      </Text>
      <div className="glass" style={{ padding: 14 }}>
        <Stack gap="md">
          <div>
            <Group gap="xs" wrap="wrap" align="center">
              <Switch
                checked={form.discover_enabled}
                onChange={(e) => set({ discover_enabled: e.currentTarget.checked })}
                label="Look for new pages every"
              />
              <NumberInput
                aria-label="New page check interval"
                w={84}
                size="xs"
                min={1}
                value={form.discover_amount}
                onChange={(v) => set({ discover_amount: v })}
                disabled={!form.discover_enabled}
              />
              <Select
                aria-label="New page check unit"
                w={110}
                size="xs"
                data={["minutes", "hours"]}
                value={form.discover_unit}
                onChange={(v) => set({ discover_unit: v })}
                disabled={!form.discover_enabled}
                allowDeselect={false}
              />
            </Group>
            <Text size="xs" c="dimmed" mt={4}>
              Re-reads each start page and sitemap for new links, and re-fetches pages the sitemap says changed.
              Cheap: unchanged pages aren&apos;t downloaded again. Minimum {limits.discover_minutes.min} minutes.
            </Text>
            <ScheduleStatus info={data.schedule.discover} />
          </div>

          <div>
            <Group gap="xs" wrap="wrap" align="center">
              <Switch
                checked={form.refresh_enabled}
                onChange={(e) => set({ refresh_enabled: e.currentTarget.checked })}
                label="Refresh every page every"
              />
              <NumberInput
                aria-label="Refresh interval"
                w={84}
                size="xs"
                min={1}
                value={form.refresh_amount}
                onChange={(v) => set({ refresh_amount: v })}
                disabled={!form.refresh_enabled}
              />
              <Select
                aria-label="Refresh unit"
                w={110}
                size="xs"
                data={["hours", "days"]}
                value={form.refresh_unit}
                onChange={(v) => set({ refresh_unit: v })}
                disabled={!form.refresh_enabled}
                allowDeselect={false}
              />
            </Group>
            <Text size="xs" c="dimmed" mt={4}>
              Re-checks every known page, so edits and removed pages show up in results.
            </Text>
            <ScheduleStatus info={data.schedule.refresh} />
          </div>

          <div>
            <Group gap="md" align="flex-end" wrap="wrap">
              <NumberInput
                label="Stop a scheduled run after"
                suffix=" min"
                w={200}
                min={limits.max_run_minutes.min}
                max={limits.max_run_minutes.max}
                value={form.max_run_minutes}
                onChange={(v) => set({ max_run_minutes: v })}
              />
              <NumberInput
                label="Sites crawled in parallel"
                w={200}
                min={limits.workers.min}
                max={limits.workers.max}
                value={form.workers}
                onChange={(v) => set({ workers: v })}
              />
            </Group>
            <Text size="xs" c="dimmed" mt={4}>
              Different sites are crawled at the same time; each site still gets one request at a time.
            </Text>
          </div>

          {error && (
            <Alert color="red" variant="light" p="xs">
              {error}
            </Alert>
          )}
          <Group justify="flex-end" gap="xs">
            {saved && !dirty && (
              <Text size="xs" c="dimmed">
                Saved
              </Text>
            )}
            <Button size="xs" onClick={save} loading={saving} disabled={!dirty}>
              Save
            </Button>
          </Group>
        </Stack>
      </div>
    </section>
  );
}
