// Build-time configuration (see frontend/.env.example).
export const SEARCH_MODE = import.meta.env.VITE_SEARCH_MODE === "static" ? "static" : "api";
export const API_BASE = (import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`).replace(/\/$/, "");
export const DATA_URL = `${import.meta.env.BASE_URL}data/index.json`;
export const REPO_URL = "https://github.com/dsameendra/clea";
