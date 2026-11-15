import "@fontsource-variable/inter";
import "@mantine/core/styles.css";
import "./styles.css";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { theme } from "./theme.js";

const colorSchemeManager = localStorageColorSchemeManager({ key: "clea.colorScheme" });

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto" colorSchemeManager={colorSchemeManager}>
      <App />
    </MantineProvider>
  </StrictMode>,
);
