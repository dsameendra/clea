import { useState, useEffect, useRef } from "react";
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
  Table,
  Badge,
  Textarea,
  NumberInput,
  LoadingOverlay,
  Notification,
  ActionIcon,
  Tooltip,
  Modal,
} from "@mantine/core";
import { IconSettings, IconSitemap, IconSearch } from "@tabler/icons-react";
import { motion, useMotionValue, AnimatePresence } from "framer-motion";
import "@mantine/core/styles.css";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [calculationResult, setCalculationResult] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Sitemap state
  const [sitemapUrls, setSitemapUrls] = useState([]);
  const [newUrl, setNewUrl] = useState("");
  const [newUrls, setNewUrls] = useState("");
  const [isLoadingSitemap, setIsLoadingSitemap] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [notification, setNotification] = useState(null);

  // UI state
  const [sitemapModalOpen, setSitemapModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [maxIndexPages, setMaxIndexPages] = useState(10);
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const [isAddingMultipleUrls, setIsAddingMultipleUrls] = useState(false);

  // Mouse position for glassmorphic effect
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const searchBoxRef = useRef(null);

  const API_BASE = "http://localhost:6942/api";

  // Effect to handle mouse movement for glassmorphic UI
  useEffect(() => {
    const handleMouseMove = (e) => {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);

      // Update light effect position
      const background = document.querySelector(".app-background");
      if (background) {
        const x = (e.clientX / window.innerWidth) * 100;
        const y = (e.clientY / window.innerHeight) * 100;
        background.style.setProperty("--x", `${x}%`);
        background.style.setProperty("--y", `${y}%`);
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

  // Load sitemap initially
  useEffect(() => {
    loadSitemap();
  }, []);

  // Effect to reload sitemap when modal is opened
  useEffect(() => {
    if (sitemapModalOpen) {
      loadSitemap();
    }
  }, [sitemapModalOpen]);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setHasSearched(true);
    setHasSearched(true);

    try {
      const response = await fetch(
        `${API_BASE}/search?q=${encodeURIComponent(query)}`
      );
      if (!response.ok) throw new Error("Search failed");

      const data = await response.json();
      setResults(data.results || []);

      // Store calculation result if present
      if (data.calculation) {
        setCalculationResult(data.calculation);
      } else {
        setCalculationResult(null);
      }
    } catch (err) {
      setError(
        "Failed to perform search. Please ensure the search server is running."
      );
      console.error("Search error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset search state
  const resetSearch = () => {
    // Clear all search-related state
    setQuery("");
    setResults([]);
    setError(null);
    setCalculationResult(null);
    setIsLoading(false);
    setHasSearched(false);

    // Scroll to the top of the page
    window.scrollTo({ top: 0, behavior: "smooth" });

    // Focus the search input after a brief delay to allow smooth scrolling
    setTimeout(() => {
      const searchInput = document.querySelector(".new-search-input");
      if (searchInput) {
        searchInput.focus();
      }
    }, 500);
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
    setIsAddingUrl(true);
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
    } finally {
      setIsAddingUrl(false);
    }
  };

  const addMultipleUrls = async () => {
    setIsAddingMultipleUrls(true);
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
    } finally {
      setIsAddingMultipleUrls(false);
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
    setNotification({
      type: "info",
      message:
        "Force crawling all URLs in sitemap regardless of previous status...",
    });
    try {
      const response = await fetch(`${API_BASE}/crawl/force`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
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
    setNotification({
      type: "info",
      message: "Crawling only new/pending URLs in sitemap...",
    });
    try {
      const response = await fetch(`${API_BASE}/crawl/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
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
        body: JSON.stringify({ max_pages: maxIndexPages }),
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
        body: JSON.stringify({ max_pages: maxIndexPages }),
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
      <div className="app-background">
        <div className="app-container">
          <Container size="lg" py="xl">
            {/* Header with Logo and Action Icons */}
            <div className="header">
              <Tooltip
                label="Click to start a new search"
                position="bottom"
                withArrow
              >
                <div
                  className="logo"
                  onClick={resetSearch}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && resetSearch()}
                >
                  <Title order={1} className="logo-text">
                    Clea
                  </Title>
                </div>
              </Tooltip>
              <div className="actions">
                <Tooltip label="Sitemap">
                  <ActionIcon
                    size="lg"
                    className="action-icon"
                    onClick={() => setSitemapModalOpen(true)}
                  >
                    <IconSitemap />
                  </ActionIcon>
                </Tooltip>
                <Tooltip label="Settings">
                  <ActionIcon
                    size="lg"
                    className="action-icon"
                    onClick={() => setSettingsModalOpen(true)}
                  >
                    <IconSettings />
                  </ActionIcon>
                </Tooltip>
              </div>
            </div>

            <Stack align="center" gap="xl" className="main-content">
              {/* Notification for errors and success messages */}
              <AnimatePresence>
                {notification && (
                  <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    className="notification-container"
                  >
                    <Notification
                      title={
                        notification.type === "error" ? "Error" : "Success"
                      }
                      color={notification.type === "error" ? "red" : "orange"}
                      onClose={() => setNotification(null)}
                      className="glass-notification"
                      withCloseButton
                      data-error={notification.type === "error"}
                    >
                      {notification.message}
                    </Notification>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Search Section */}
              <div className="new-search-wrapper" ref={searchBoxRef}>
                <form onSubmit={handleSearch} className="new-search-form">
                  <div className="new-search-container">
                    <div className="new-search-icon-wrapper">
                      <IconSearch size={24} className="new-search-icon" />
                    </div>
                    <input
                      type="text"
                      placeholder="Search the web..."
                      value={query}
                      onChange={(e) => {
                        setQuery(e.target.value);
                        // When user clears the input, reset the search state
                        if (e.target.value === "") {
                          setResults([]);
                          setCalculationResult(null);
                          setHasSearched(false);
                        }
                      }}
                      className="new-search-input"
                    />
                    <button
                      type="submit"
                      className="new-search-button"
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <span className="new-search-loading"></span>
                      ) : (
                        "Search"
                      )}
                    </button>
                  </div>
                </form>
              </div>

              {/* Error Message */}
              {error && (
                <Text c="red" ta="center" className="error-text">
                  {error}
                </Text>
              )}

              {/* Calculator Result */}
              {calculationResult && (
                <motion.div
                  className="results-container"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <Card
                      className="result-card calculator-card glass-panel"
                      radius="md"
                      p="xs"
                    >
                      <Stack gap={5}>
                        <Group position="apart" align="center" noWrap>
                          <Text fw={500} className="calculator-title">
                            Calculator
                          </Text>
                          <Badge color="orange" variant="filled" size="sm">
                            Math
                          </Badge>
                        </Group>
                        <Text className="calculator-expression">
                          {calculationResult.expression}
                        </Text>
                        <Text className="calculator-answer">
                          = {calculationResult.result}
                        </Text>
                      </Stack>
                    </Card>
                  </motion.div>
                </motion.div>
              )}

              {/* Results Section */}
              <AnimatePresence>
                <motion.div
                  className="results-container"
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ staggerChildren: 0.1 }}
                >
                  {results.map((result, index) => (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.1 }}
                    >
                      <Card
                        className="result-card glass-panel"
                        radius="md"
                        p="xs"
                      >
                        <Stack gap={5}>
                          <Text
                            component="a"
                            href={result.url}
                            size="lg"
                            c="blue"
                            fw={500}
                            className="result-title"
                          >
                            {result.title || result.url}
                          </Text>
                          <Text size="xs" c="dimmed" className="result-url">
                            {result.url}
                          </Text>
                          <Text className="result-snippet">
                            {result.snippet}
                          </Text>
                          <Group gap="xs" c="dimmed" size="xs">
                            <Text>Relevance: {result.relevance_score}</Text>
                            <Text>•</Text>
                            <Text>Matches: {result.matching_terms}</Text>
                          </Group>
                        </Stack>
                      </Card>
                    </motion.div>
                  ))}
                  {query &&
                    hasSearched &&
                    results.length === 0 &&
                    !isLoading &&
                    !error &&
                    !calculationResult && (
                      <Text ta="center" className="no-results">
                        No search results found for "
                        <span style={{ color: "#ff8800" }}>{query}</span>"
                      </Text>
                    )}
                </motion.div>
              </AnimatePresence>
            </Stack>
          </Container>
        </div>
      </div>

      {/* Sitemap Management Modal */}
      <Modal
        opened={sitemapModalOpen}
        onClose={() => setSitemapModalOpen(false)}
        title="Sitemap Management"
        size="xxl"
        className="glass-modal sitemap-modal"
        centered
        overlayProps={{
          opacity: 0.7,
          blur: 8,
        }}
      >
        <Stack gap="md">
          {/* Sitemap Table */}
          <Card
            className="glass-panel"
            radius="md"
            style={{ position: "relative" }}
          >
            <LoadingOverlay visible={isLoadingSitemap} />
            <Stack gap="md">
              <Group justify="space-between">
                <Text size="lg" fw={500}>
                  Sitemap URLs ({sitemapUrls.length})
                </Text>
                <Button
                  onClick={loadSitemap}
                  variant="light"
                  style={{ alignSelf: "flex-end" }}
                  loading={isLoadingSitemap}
                  className="glass-button"
                  loaderProps={{ size: "sm" }}
                >
                  Refresh Sitemap
                </Button>
              </Group>

              {sitemapUrls.length === 0 ? (
                <Text ta="center" className="no-items-text">
                  No URLs in sitemap
                </Text>
              ) : (
                <div className="sitemap-table-container">
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
                              variant="filled"
                            >
                              {item.crawl_status}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            {item.last_crawled
                              ? new Date(item.last_crawled).toLocaleDateString()
                              : "Never"}
                          </Table.Td>
                          <Table.Td>
                            <Button
                              size="xs"
                              color="red"
                              variant="light"
                              onClick={() => removeFromSitemap(item.url)}
                              className="glass-button-small"
                            >
                              Remove
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </div>
              )}
            </Stack>
          </Card>

          {/* Add URL Section */}
          <Card className="glass-panel" radius="md">
            <Stack gap="md">
              <Text size="lg" fw={500}>
                Add URLs to Sitemap
              </Text>

              {/* Single URL */}
              <TextInput
                placeholder="Enter URL to add..."
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                style={{ flex: 1 }}
              />
              <Button
                onClick={() => addUrlToSitemap(newUrl)}
                loading={isAddingUrl}
                disabled={!newUrl.trim()}
                className="glass-button"
                loaderProps={{ size: "sm" }}
              >
                <span className="button-text">Add URL</span>
              </Button>

              {/* Multiple URLs */}
              <Textarea
                placeholder="Enter multiple URLs (one per line)..."
                value={newUrls}
                onChange={(e) => setNewUrls(e.target.value)}
                rows={4}
                style={{ flex: 1 }}
              />
              <Button
                onClick={addMultipleUrls}
                loading={isAddingMultipleUrls}
                disabled={!newUrls.trim()}
                className="glass-button"
                loaderProps={{ size: "sm" }}
              >
                <span className="button-text">Add Multiple URLs</span>
              </Button>
            </Stack>
          </Card>

          {/* Crawl Actions */}
          <Card className="glass-panel" radius="md">
            <Stack gap="md">
              <Text size="lg" fw={500}>
                Crawl Actions
              </Text>
              <Text size="sm" className="action-description">
                Crawling collects web pages but doesn't make them searchable
                yet.
              </Text>
              <Group gap="md" wrap="wrap">
                <Button
                  onClick={crawlNewSites}
                  loading={isCrawling}
                  color="green"
                  className="glass-button action-button"
                  title="Only crawl URLs that haven't been crawled yet"
                >
                  Crawl New Sites Only
                </Button>
                <Button
                  onClick={forceCrawl}
                  loading={isCrawling}
                  color="orange"
                  className="glass-button action-button"
                  title="Crawl all URLs in sitemap regardless of previous crawl status"
                >
                  <span className="button-text">Force Crawl All URLs</span>
                </Button>
              </Group>
            </Stack>
          </Card>

          {/* Index Actions */}
          <Card className="glass-panel" radius="md">
            <Stack gap="md">
              <Text size="lg" fw={500}>
                Index Actions
              </Text>
              <Text size="sm" className="action-description">
                Indexing makes crawled pages searchable by analyzing and storing
                their content.
              </Text>
              <Group gap="md" wrap="wrap">
                <NumberInput
                  label="Max Pages"
                  description="Maximum pages to index"
                  value={maxIndexPages}
                  onChange={(val) => setMaxIndexPages(val)}
                  min={1}
                  max={10000}
                  step={10}
                />
                <Button
                  onClick={indexNewSites}
                  loading={isIndexing}
                  color="indigo"
                  className="glass-button action-button"
                  title="Only index pages that haven't been indexed yet"
                >
                  <span className="button-text">Index New Pages Only</span>
                </Button>
              </Group>
              <Group gap="md" wrap="wrap">
                <Button
                  onClick={forceIndex}
                  loading={isIndexing}
                  color="violet"
                  className="glass-button action-button"
                  title="Index all crawled pages, even if previously indexed"
                >
                  <span className="button-text">
                    Force Index All Crawled Pages
                  </span>
                </Button>
              </Group>
            </Stack>
          </Card>
        </Stack>
      </Modal>

      {/* Settings Modal */}
      <Modal
        opened={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        title="Settings"
        className="glass-modal settings-modal"
        centered
        overlayProps={{
          opacity: 0.7,
          blur: 8,
        }}
      >
        <Stack gap="md">
          <Text>Configure Clea search engine settings</Text>
          <NumberInput
            label="Default Max Index Pages"
            description="Maximum number of pages to index in one operation"
            value={maxIndexPages}
            onChange={(val) => setMaxIndexPages(val)}
            min={1}
            max={10000}
          />
          <Button
            onClick={() => setSettingsModalOpen(false)}
            className="glass-button"
            mt="md"
          >
            Save Settings
          </Button>
        </Stack>
      </Modal>
    </MantineProvider>
  );
}

export default App;
