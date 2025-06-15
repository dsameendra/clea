import { useState, useEffect } from "react";
import {
  MantineProvider,
  Container,
  Title,
  TextInput,
  Button,
  Card,
  Text,
  Group,
  Stack,
  Tabs,
  Table,
  Badge,
  Textarea,
  NumberInput,
  LoadingOverlay,
  Notification,
  Alert,
} from "@mantine/core";
import "@mantine/core/styles.css";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Sitemap state
  const [sitemapUrls, setSitemapUrls] = useState([]);
  const [newUrl, setNewUrl] = useState("");
  const [newUrls, setNewUrls] = useState("");
  const [isLoadingSitemap, setIsLoadingSitemap] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [notification, setNotification] = useState(null);

  const API_BASE = "http://localhost:6942/api";

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/search?q=${encodeURIComponent(query)}`
      );
      if (!response.ok) throw new Error("Search failed");

      const data = await response.json();
      setResults(data.results || []);
    } catch (err) {
      setError(
        "Failed to perform search. Please ensure the search server is running."
      );
      console.error("Search error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Sitemap functions
  const loadSitemap = async () => {
    setIsLoadingSitemap(true);
    try {
      const response = await fetch(`${API_BASE}/sitemap`);
      if (!response.ok) throw new Error("Failed to load sitemap");

      const data = await response.json();
      setSitemapUrls(data.sitemap || []);
    } catch (err) {
      setNotification({ type: "error", message: "Failed to load sitemap" });
      console.error("Sitemap load error:", err);
    } finally {
      setIsLoadingSitemap(false);
    }
  };

  const addUrlToSitemap = async (url) => {
    try {
      const response = await fetch(`${API_BASE}/sitemap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) throw new Error("Failed to add URL");

      const data = await response.json();
      setNotification({ type: "success", message: data.message });
      loadSitemap();
      setNewUrl("");
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to add URL to sitemap",
      });
      console.error("Add URL error:", err);
    }
  };

  const addMultipleUrls = async () => {
    if (!newUrls.trim()) return;

    const urls = newUrls
      .split("\n")
      .map((url) => url.trim())
      .filter((url) => url);

    try {
      const response = await fetch(`${API_BASE}/sitemap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls }),
      });

      if (!response.ok) throw new Error("Failed to add URLs");

      const data = await response.json();
      setNotification({ type: "success", message: data.message });
      loadSitemap(); // Refresh the list
      setNewUrls("");
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to add URLs to sitemap",
      });
      console.error("Add URLs error:", err);
    }
  };

  const removeFromSitemap = async (url) => {
    try {
      const response = await fetch(
        `${API_BASE}/sitemap/${encodeURIComponent(url)}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) throw new Error("Failed to remove URL");

      setNotification({ type: "success", message: "URL removed from sitemap" });
      loadSitemap(); // Refresh the list
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to remove URL from sitemap",
      });
      console.error("Remove URL error:", err);
    }
  };

  const forceCrawl = async () => {
    setIsCrawling(true);
    try {
      const response = await fetch(`${API_BASE}/crawl/force`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 10 }),
      });

      if (!response.ok) throw new Error("Failed to start force crawl");

      const data = await response.json();
      setNotification({
        type: "success",
        message: `${data.message}. Found ${data.links_found} links.`,
      });
      loadSitemap(); // Refresh the list to see updated statuses
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to start force crawl",
      });
      console.error("Force crawl error:", err);
    } finally {
      setIsCrawling(false);
    }
  };

  const crawlNewSites = async () => {
    setIsCrawling(true);
    try {
      const response = await fetch(`${API_BASE}/crawl/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 10 }),
      });

      if (!response.ok) throw new Error("Failed to start new crawl");

      const data = await response.json();
      setNotification({
        type: "success",
        message: `${data.message}. Found ${data.links_found} links.`,
      });
      loadSitemap(); // Refresh the list to see updated statuses
    } catch (err) {
      setNotification({ type: "error", message: "Failed to start new crawl" });
      console.error("New crawl error:", err);
    } finally {
      setIsCrawling(false);
    }
  };

  // Indexing Functions
  const forceIndex = async () => {
    setIsIndexing(true);
    try {
      const response = await fetch(`${API_BASE}/index/force`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 10 }),
      });

      if (!response.ok) throw new Error("Failed to start force indexing");

      const data = await response.json();
      setNotification({
        type: "success",
        message: `${data.message}. Indexed ${data.indexed_count} pages.`,
      });
      loadSitemap(); // Refresh the list to see updated statuses
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to start force indexing",
      });
      console.error("Force index error:", err);
    } finally {
      setIsIndexing(false);
    }
  };

  const indexNewSites = async () => {
    setIsIndexing(true);
    try {
      const response = await fetch(`${API_BASE}/index/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 10 }),
      });

      if (!response.ok) throw new Error("Failed to start new indexing");

      const data = await response.json();
      setNotification({
        type: "success",
        message: `${data.message}. Indexed ${data.indexed_count} pages.`,
      });
      loadSitemap(); // Refresh the list to see updated statuses
    } catch (err) {
      setNotification({
        type: "error",
        message: "Failed to start new indexing",
      });
      console.error("New index error:", err);
    } finally {
      setIsIndexing(false);
    }
  };

  return (
    <MantineProvider withGlobalStyles withNormalizeCSS>
      <Container size="lg" py="xl">
        <Stack spacing="xl">
          <Title order={2} align="center">
            Web Crawler and Indexer
          </Title>

          {/* Notification for errors and success messages */}
          {notification && (
            <Alert
              title={notification.type === "error" ? "Error" : "Success"}
              color={notification.type === "error" ? "red" : "green"}
              onClose={() => setNotification(null)}
              style={{ position: "relative" }}
            >
              <Text size="sm">{notification.message}</Text>
            </Alert>
          )}

          {/* Tabs for Search and Sitemap */}
          <Tabs defaultValue="search" style={{ width: "100%" }}>
            <Tabs.List grow>
              <Tabs.Tab value="search">Search</Tabs.Tab>
              <Tabs.Tab value="sitemap">Sitemap Management</Tabs.Tab>
            </Tabs.List>

            {/* Search Tab */}
            <Tabs.Panel value="search" pt="md">
              <Stack align="center" gap="xl">
                <form
                  onSubmit={handleSearch}
                  style={{ width: "100%", maxWidth: "600px" }}
                >
                  <Group gap="sm">
                    <TextInput
                      placeholder="Search the web..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      style={{ flex: 1 }}
                      size="lg"
                    />
                    <Button type="submit" loading={isLoading} size="lg">
                      Search
                    </Button>
                  </Group>
                </form>

                {/* Error Message */}
                {error && (
                  <Text c="red" ta="center">
                    {error}
                  </Text>
                )}

                {/* Results Section */}
                <Stack gap="md" style={{ width: "100%" }}>
                  {results.map((result, index) => (
                    <Card key={index} withBorder shadow="sm" radius="md">
                      <Stack gap="xs">
                        <Text
                          component="a"
                          href={result.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          size="lg"
                          c="blue"
                          fw={500}
                        >
                          {result.title || result.url}
                        </Text>
                        <Text size="sm" c="dimmed">
                          {result.url}
                        </Text>
                        <Text>{result.snippet}</Text>
                        <Group gap="xs" c="dimmed" size="sm">
                          <Text>Relevance: {result.relevance_score}</Text>
                          <Text>•</Text>
                          <Text>Matches: {result.matching_terms}</Text>
                        </Group>
                      </Stack>
                    </Card>
                  ))}
                  {query && results.length === 0 && !isLoading && !error && (
                    <Text ta="center" c="dimmed">
                      No results found for "{query}"
                    </Text>
                  )}
                </Stack>
              </Stack>
            </Tabs.Panel>

            {/* Sitemap Management Tab */}
            <Tabs.Panel value="sitemap" pt="md">
              <Stack gap="md">
                {/* Add URL Section */}
                <Card withBorder shadow="sm" radius="md">
                  <Stack gap="md">
                    <Text size="lg" fw={500}>
                      Add URLs to Sitemap
                    </Text>

                    {/* Single URL */}
                    <Group gap="sm">
                      <TextInput
                        placeholder="Enter URL to add..."
                        value={newUrl}
                        onChange={(e) => setNewUrl(e.target.value)}
                        style={{ flex: 1 }}
                      />
                      <Button
                        onClick={() => addUrlToSitemap(newUrl)}
                        disabled={!newUrl.trim()}
                      >
                        Add URL
                      </Button>
                    </Group>

                    {/* Multiple URLs */}
                    <Textarea
                      placeholder="Enter multiple URLs (one per line)..."
                      value={newUrls}
                      onChange={(e) => setNewUrls(e.target.value)}
                      rows={4}
                    />
                    <Button
                      onClick={addMultipleUrls}
                      disabled={!newUrls.trim()}
                      style={{ alignSelf: "flex-start" }}
                    >
                      Add Multiple URLs
                    </Button>
                  </Stack>
                </Card>

                {/* Crawl Actions */}
                <Card withBorder shadow="sm" radius="md">
                  <Stack gap="md">
                    <Text size="lg" fw={500}>
                      Crawl Actions
                    </Text>
                    <Text size="sm" c="dimmed">
                      Crawling collects web pages but doesn't make them
                      searchable yet.
                    </Text>
                    <Group gap="md">
                      <Button
                        onClick={forceCrawl}
                        loading={isCrawling}
                        color="orange"
                        title="Crawl all URLs in sitemap regardless of previous crawl status"
                      >
                        Force Crawl All URLs
                      </Button>
                      <Button
                        onClick={crawlNewSites}
                        loading={isCrawling}
                        color="green"
                        title="Only crawl URLs that haven't been crawled yet"
                      >
                        Crawl New Sites Only
                      </Button>
                      <Button
                        onClick={loadSitemap}
                        variant="light"
                        loading={isLoadingSitemap}
                      >
                        Refresh Sitemap
                      </Button>
                    </Group>
                  </Stack>
                </Card>

                {/* Index Actions */}
                <Card withBorder shadow="sm" radius="md">
                  <Stack gap="md">
                    <Text size="lg" fw={500}>
                      Index Actions
                    </Text>
                    <Text size="sm" c="dimmed">
                      Indexing makes crawled pages searchable by analyzing and
                      storing their content.
                    </Text>
                    <Group gap="md">
                      <Button
                        onClick={forceIndex}
                        loading={isIndexing}
                        color="violet"
                        title="Index all crawled pages, even if previously indexed"
                      >
                        Force Index All Crawled Pages
                      </Button>
                      <Button
                        onClick={indexNewSites}
                        loading={isIndexing}
                        color="indigo"
                        title="Only index pages that haven't been indexed yet"
                      >
                        Index New Pages Only
                      </Button>
                    </Group>
                  </Stack>
                </Card>

                {/* Sitemap Table */}
                <Card
                  withBorder
                  shadow="sm"
                  radius="md"
                  style={{ position: "relative" }}
                >
                  <LoadingOverlay visible={isLoadingSitemap} />
                  <Stack gap="md">
                    <Group justify="space-between">
                      <Text size="lg" fw={500}>
                        Sitemap URLs ({sitemapUrls.length})
                      </Text>
                    </Group>

                    {sitemapUrls.length === 0 ? (
                      <Text ta="center" c="dimmed">
                        No URLs in sitemap
                      </Text>
                    ) : (
                      <Table striped highlightOnHover>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>URL</Table.Th>
                            <Table.Th>Status</Table.Th>
                            <Table.Th>Last Crawled</Table.Th>
                            <Table.Th>Actions</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {sitemapUrls.map((item) => (
                            <Table.Tr key={item.id}>
                              <Table.Td>
                                <Text
                                  size="sm"
                                  style={{
                                    maxWidth: 300,
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                  }}
                                >
                                  {item.url}
                                </Text>
                              </Table.Td>
                              <Table.Td>
                                <Badge
                                  color={
                                    item.crawl_status === "crawled"
                                      ? "green"
                                      : item.crawl_status === "error"
                                      ? "red"
                                      : "blue"
                                  }
                                >
                                  {item.crawl_status}
                                </Badge>
                              </Table.Td>
                              <Table.Td>
                                {item.last_crawled
                                  ? new Date(
                                      item.last_crawled
                                    ).toLocaleDateString()
                                  : "Never"}
                              </Table.Td>
                              <Table.Td>
                                <Button
                                  size="xs"
                                  color="red"
                                  variant="light"
                                  onClick={() => removeFromSitemap(item.url)}
                                >
                                  Remove
                                </Button>
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    )}
                  </Stack>
                </Card>
              </Stack>
            </Tabs.Panel>
          </Tabs>
        </Stack>
      </Container>
    </MantineProvider>
  );
}

export default App;
