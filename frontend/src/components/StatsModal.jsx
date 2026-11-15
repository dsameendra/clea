import { Alert, Anchor, Group, Loader, Modal, Progress, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { REPO_URL } from "../lib/config.js";
import { isStatic, searchClient } from "../lib/searchClient.js";
import { formatDateTime, timeAgo } from "../lib/time.js";

function Stat({ label, value }) {
  return (
    <div className="glass" style={{ padding: "12px 14px" }}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.5}>
        {label}
      </Text>
      <Text size="xl" fw={700} style={{ fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Text>
    </div>
  );
}

export function StatsModal({ opened, onClose }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!opened) return;
    setError(null);
    searchClient.stats().then(setStats).catch((err) => setError(err.message));
  }, [opened]);

  const max = stats?.top_hosts?.[0]?.documents || 1;

  return (
    <Modal opened={opened} onClose={onClose} title="About this index" size="lg" centered>
      {error && <Alert color="red" variant="light">{error}</Alert>}
      {!stats && !error && (
        <Group justify="center" p="xl">
          <Loader />
        </Group>
      )}
      {stats && (
        <Stack gap="md">
          {isStatic && (
            <Alert variant="light" icon={<IconInfoCircle size={18} />} title="Static demo">
              This copy of Clea runs entirely in your browser. A scheduled GitHub Action crawls a fixed list of
              sites and publishes the index. To crawl your own sites,{" "}
              <Anchor href={REPO_URL} target="_blank" rel="noreferrer">
                self-host Clea
              </Anchor>
              .
            </Alert>
          )}
          <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="sm">
            <Stat label="Pages" value={stats.documents.toLocaleString()} />
            <Stat label="Sites" value={stats.sites.toLocaleString()} />
            <Stat label="Words" value={stats.words.toLocaleString()} />
          </SimpleGrid>
          <Text size="sm" c="dimmed">
            Last updated {timeAgo(stats.last_indexed_at)}
            {stats.last_indexed_at && ` (${formatDateTime(stats.last_indexed_at)})`}
            {!isStatic && stats.queued > 0 && ` · ${stats.queued.toLocaleString()} pages waiting to be crawled`}
          </Text>
          {stats.top_hosts.length > 0 && (
            <div>
              <Text fw={600} mb={8}>
                Largest sites
              </Text>
              <Stack gap={8}>
                {stats.top_hosts.map((h) => (
                  <div key={h.host}>
                    <Group justify="space-between" gap="xs">
                      <Text size="sm" truncate>
                        {h.host}
                      </Text>
                      <Text size="sm" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
                        {h.documents.toLocaleString()}
                      </Text>
                    </Group>
                    <Progress value={(h.documents / max) * 100} size="sm" mt={4} aria-hidden />
                  </div>
                ))}
              </Stack>
            </div>
          )}
        </Stack>
      )}
    </Modal>
  );
}
