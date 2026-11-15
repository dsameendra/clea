import { API_BASE } from "./config.js";
import { load } from "./storage.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function request(path, { method = "GET", body, signal } = {}) {
  const headers = { Accept: "application/json" };
  const token = load("clea.adminToken", "");
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError("Can't reach the Clea server. Is it running? (python -m clea serve)", 0);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) throw new ApiError(data?.error || `Request failed (HTTP ${res.status})`, res.status);
  return data;
}

export const api = {
  config: () => request("/config"),
  search: (q, { page = 1, perPage = 10 } = {}, signal) =>
    request(`/search?${new URLSearchParams({ q, page, per_page: perPage })}`, { signal }),
  suggest: (q, signal) => request(`/suggest?${new URLSearchParams({ q })}`, { signal }).then((d) => d.suggestions),
  stats: () => request("/stats"),
  sites: () => request("/sites").then((d) => d.sites),
  addSites: (urls, limits) => request("/sites", { method: "POST", body: { urls, ...limits } }),
  updateSite: (id, limits) => request(`/sites/${id}`, { method: "PATCH", body: limits }),
  removeSite: (id) => request(`/sites/${id}`, { method: "DELETE" }),
  siteUrls: (id, status) => request(`/sites/${id}/urls?${new URLSearchParams(status ? { status } : {})}`).then((d) => d.urls),
  crawl: (body) => request("/crawl", { method: "POST", body }).then((d) => d.job),
  jobs: () => request("/jobs").then((d) => d.jobs),
  cancelJob: (id) => request(`/jobs/${id}/cancel`, { method: "POST", body: {} }).then((d) => d.job),
};
