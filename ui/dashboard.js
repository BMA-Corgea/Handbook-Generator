// ui/dashboard.js
// No JSX. No build step. Works with React + ReactDOM via CDN.

const { useMemo, useState } = React;

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export default function Dashboard() {
  const apiBase = useMemo(() => {
    if (typeof window !== "undefined" && window.LUNAR_API_BASE) {
      return String(window.LUNAR_API_BASE).replace(/\/+$/, "");
    }
    return DEFAULT_API_BASE.replace(/\/+$/, "");
  }, []);

  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function dumpPdfs() {
    setLoading(true);
    setErr("");
    setRaw("");

    try {
      const res = await fetch(`${apiBase}/lightrag/dump-pdf-json`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });

      const text = await res.text();

      // Try to pretty-print JSON; if not JSON, show raw.
      try {
        const parsed = JSON.parse(text);
        if (!res.ok) {
          throw new Error(parsed?.detail || parsed?.error || `HTTP ${res.status}`);
        }
        setRaw(JSON.stringify(parsed, null, 2));
      } catch (e) {
        if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
        setRaw(text);
      }
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const styles = {
    page: {
      minHeight: "100vh",
      padding: 24,
      background: "#0b0f14",
      color: "#e6edf3",
      fontFamily:
        'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial',
    },
    card: {
      maxWidth: 980,
      margin: "0 auto",
      border: "1px solid rgba(255,255,255,0.08)",
      background: "rgba(255,255,255,0.04)",
      borderRadius: 16,
      padding: 18,
      boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
    },
    headerRow: {
      display: "flex",
      gap: 12,
      alignItems: "flex-start",
      justifyContent: "space-between",
      flexWrap: "wrap",
    },
    title: { fontSize: 22, fontWeight: 700 },
    subtitle: { marginTop: 6, opacity: 0.85, lineHeight: 1.4 },
    badge: {
      padding: "8px 10px",
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.10)",
      background: "rgba(255,255,255,0.03)",
      fontSize: 13,
      opacity: 0.9,
      fontFamily: "monospace",
    },
    actions: { marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" },
    button: {
      padding: "10px 14px",
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.14)",
      background: "rgba(255,255,255,0.06)",
      color: "#e6edf3",
      cursor: "pointer",
      fontWeight: 600,
    },
    errorBox: {
      marginTop: 14,
      padding: 14,
      borderRadius: 12,
      border: "1px solid rgba(255, 80, 80, 0.35)",
      background: "rgba(255, 80, 80, 0.08)",
    },
    pre: {
      marginTop: 12,
      padding: 14,
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.10)",
      background: "rgba(0,0,0,0.35)",
      overflowX: "auto",
      lineHeight: 1.35,
      fontSize: 13,
      whiteSpace: "pre-wrap",
    },
    hint: { marginTop: 8, opacity: 0.75, fontSize: 13 },
    code: {
      padding: "2px 6px",
      borderRadius: 8,
      border: "1px solid rgba(255,255,255,0.12)",
      background: "rgba(0,0,0,0.25)",
      fontFamily: "monospace",
    },
  };

  return React.createElement(
    "div",
    { style: styles.page },
    React.createElement(
      "div",
      { style: styles.card },
      React.createElement(
        "div",
        { style: styles.headerRow },
        React.createElement(
          "div",
          null,
          React.createElement("div", { style: styles.title }, "Lunar Reader Dashboard"),
          React.createElement(
            "div",
            { style: styles.subtitle },
            "Calls ",
            React.createElement("span", { style: styles.code }, "GET /lightrag/dump-pdf-json"),
            " and prints the JSON."
          )
        ),
        React.createElement("div", { style: styles.badge }, apiBase)
      ),

      React.createElement(
        "div",
        { style: styles.actions },
        React.createElement(
          "button",
          { style: styles.button, onClick: dumpPdfs, disabled: loading },
          loading ? "Running…" : "Dump PDFs → outputs/ JSON"
        )
      ),

      err
        ? React.createElement(
            "div",
            { style: styles.errorBox },
            React.createElement("div", { style: { fontWeight: 800 } }, "Error"),
            React.createElement("div", null, err),
            React.createElement(
              "div",
              { style: styles.hint },
              "If your API routes 404, make sure main.py is NOT mounting static at '/'."
            )
          )
        : null,

      React.createElement("pre", { style: styles.pre }, raw || "Click the button to fetch JSON.")
    )
  );
}
