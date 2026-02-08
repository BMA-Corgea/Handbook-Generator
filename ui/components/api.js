// ui/components/api.js
import { DEFAULT_API_BASE } from "./constants.js";

export function getApiBase() {
  if (typeof window !== "undefined" && window.LUNAR_API_BASE) {
    return String(window.LUNAR_API_BASE).replace(/\/+$/, "");
  }
  return DEFAULT_API_BASE.replace(/\/+$/, "");
}

export function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function fetchJsonOrThrow(url, opts) {
  const res = await fetch(url, opts);
  const text = await res.text();
  const parsed = safeJsonParse(text);
  if (!res.ok) {
    const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return parsed ?? {};
}
