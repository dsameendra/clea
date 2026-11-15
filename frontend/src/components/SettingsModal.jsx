import { Anchor, Button, Group, Modal, PasswordInput, SegmentedControl, Stack, Switch, Text, useMantineColorScheme } from "@mantine/core";
import { useState } from "react";
import { isStatic } from "../lib/searchClient.js";
import { load, save } from "../lib/storage.js";

export function SettingsModal({ opened, onClose, settings, onChange }) {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const [token, setToken] = useState(() => load("clea.adminToken", ""));
  const [saved, setSaved] = useState(false);

  const addToBrowser = () => {
    // Firefox and some Chromium builds pick up the <link rel="search"> automatically; this is a hint.
    window.open("https://developer.mozilla.org/docs/Web/XML/Guides/OpenSearch#autodiscovery_of_search_plugins", "_blank", "noopener");
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Settings" centered>
      <Stack gap="lg">
        <div>
          <Text fw={600} size="sm" mb={6}>
            Theme
          </Text>
          <SegmentedControl
            fullWidth
            value={colorScheme}
            onChange={setColorScheme}
            data={[
              { label: "System", value: "auto" },
              { label: "Light", value: "light" },
              { label: "Dark", value: "dark" },
            ]}
          />
        </div>
        <div>
          <Text fw={600} size="sm" mb={6}>
            Results per page
          </Text>
          <SegmentedControl
            fullWidth
            value={String(settings.perPage)}
            onChange={(v) => onChange({ perPage: Number(v) })}
            data={["10", "20", "30", "50"]}
          />
        </div>
        <Switch
          checked={settings.newTab}
          onChange={(e) => onChange({ newTab: e.currentTarget.checked })}
          label="Open results in a new tab"
        />
        {!isStatic && (
          <div>
            <PasswordInput
              label="Admin token"
              description="Only needed when the server sets CLEA_ADMIN_TOKEN. Stored in this browser only."
              value={token}
              onChange={(e) => {
                setToken(e.currentTarget.value);
                setSaved(false);
              }}
              autoComplete="off"
            />
            <Group justify="flex-end" mt="xs">
              <Button
                size="xs"
                variant="light"
                onClick={() => {
                  save("clea.adminToken", token.trim());
                  setSaved(true);
                }}
              >
                {saved ? "Saved" : "Save token"}
              </Button>
            </Group>
          </div>
        )}
        <Text size="xs" c="dimmed">
          Clea can be your browser&apos;s search engine: it publishes an OpenSearch description, so most browsers
          offer to add it after you search once.{" "}
          <Anchor component="button" type="button" size="xs" onClick={addToBrowser}>
            How?
          </Anchor>
        </Text>
      </Stack>
    </Modal>
  );
}
