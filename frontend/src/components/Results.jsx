import { Alert, Anchor, Button, Pagination, Skeleton, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconSearchOff } from "@tabler/icons-react";
import { InstantAnswer } from "./InstantAnswer.jsx";
import { ResultCard } from "./ResultCard.jsx";

const MAX_PAGES = 100;

function LoadingList() {
  return Array.from({ length: 4 }, (_, i) => (
    <div key={i} className="glass skeleton" aria-hidden>
      <Skeleton height={12} width="40%" radius="sm" mb={12} />
      <Skeleton height={18} width="70%" radius="sm" mb={10} />
      <Skeleton height={10} radius="sm" mb={6} />
      <Skeleton height={10} width="85%" radius="sm" />
    </div>
  ));
}

export function Results({ query, page, state, answer, settings, onSearch, onPage, onShowAdmin, canAdmin }) {
  const { status, error } = state;
  // A conversion like "10 km in miles" only loosely matches pages ("10", "km"); the answer is what matters.
  const data = answer && state.data?.relaxed ? { ...state.data, results: [], total: 0, relaxed: false, suggestion: null } : state.data;
  const loading = status === "loading";
  const total = data?.total ?? 0;
  const pages = data ? Math.min(MAX_PAGES, Math.ceil(total / data.per_page)) : 0;

  return (
    <div className="results" aria-busy={loading}>
      {data && !loading && !(answer && data.total === 0) && (
        <div className="results-meta" role="status">
          {total === 0
            ? "No results"
            : `${total.toLocaleString()} result${total === 1 ? "" : "s"}${page > 1 ? ` · page ${page} of ${pages}` : ""} · ${data.took_ms} ms`}
          {data.relaxed && total > 0 && " · showing pages that match some of your words"}
        </div>
      )}

      {data?.suggestion && !loading && (
        <Text mb="md">
          Did you mean{" "}
          <Anchor component="button" type="button" fw={600} onClick={() => onSearch(data.suggestion)}>
            {data.suggestion}
          </Anchor>
          ?
        </Text>
      )}

      {answer && <InstantAnswer answer={answer} />}

      {status === "error" && (
        <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title="Search failed" mb="md">
          {error}
        </Alert>
      )}

      {loading && !data && <LoadingList />}

      {data && (
        <div style={{ opacity: loading ? 0.55 : 1, transition: "opacity 0.15s ease" }}>
          {data.results.map((result, i) => (
            <ResultCard key={result.url} result={result} index={i} newTab={settings.newTab} />
          ))}
        </div>
      )}

      {data && !loading && total === 0 && !answer && (
        <div className="glass empty">
          <Stack align="center" gap="xs">
            <IconSearchOff size={36} color="var(--clea-muted)" aria-hidden />
            <Text fw={600}>Nothing in the index matches “{query}”</Text>
            <Text size="sm" c="dimmed" maw={420}>
              Try fewer or different words, check the spelling, or remove filters like <code>site:</code>.
              Clea only searches the sites it has crawled.
            </Text>
            {canAdmin && (
              <Button variant="light" size="xs" mt="xs" onClick={onShowAdmin}>
                Add sites to the index
              </Button>
            )}
          </Stack>
        </div>
      )}

      {pages > 1 && (
        <Pagination
          total={pages}
          value={Math.min(page, pages)}
          onChange={onPage}
          mt="lg"
          mb="xl"
          radius="md"
          siblings={1}
          getControlProps={(control) => ({ "aria-label": `${control} page` })}
        />
      )}
    </div>
  );
}
