// ui/components/styles.js

export const styles = {
  page: {
    minHeight: "100vh",
    padding: 24,
    background: "#0b0f14",
    color: "#e6edf3",
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial',
  },
  container: { maxWidth: 1100, margin: "0 auto" },

  card: {
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(255,255,255,0.04)",
    borderRadius: 16,
    padding: 18,
    boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
  },

  headerRow: { display: "flex", gap: 12, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" },
  title: { fontSize: 18, fontWeight: 800 },
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

  actions: { marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" },

  button: {
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.14)",
    background: "rgba(255,255,255,0.06)",
    color: "#e6edf3",
    cursor: "pointer",
    fontWeight: 700,
  },
  buttonDisabled: { opacity: 0.55, cursor: "not-allowed" },

  tinyBtn: {
    padding: "6px 8px",
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.14)",
    background: "rgba(255,255,255,0.06)",
    color: "#e6edf3",
    cursor: "pointer",
    fontWeight: 800,
    fontSize: 12,
  },

  input: {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(0,0,0,0.28)",
    color: "#e6edf3",
    outline: "none",
    fontSize: 13,
    width: 140,
  },

  select: {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(0,0,0,0.28)",
    color: "#e6edf3",
    outline: "none",
    fontSize: 13,
    minWidth: 360,
    maxWidth: 680,
  },

  checkboxRow: { display: "flex", alignItems: "center", gap: 8, opacity: 0.9 },

  notice: {
    marginTop: 14,
    padding: 14,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(0,0,0,0.22)",
    opacity: 0.95,
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
    maxHeight: 420,
    overflowY: "auto",
  },

  code: {
    padding: "2px 6px",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(0,0,0,0.25)",
    fontFamily: "monospace",
  },

  tableWrap: { marginTop: 12, borderRadius: 12, border: "1px solid rgba(255,255,255,0.10)", overflow: "hidden" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: {
    textAlign: "left",
    padding: "10px 12px",
    background: "rgba(255,255,255,0.06)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    fontWeight: 800,
    opacity: 0.9,
  },
  td: { padding: "10px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", verticalAlign: "top", opacity: 0.95 },
  statusCell: { width: 92, fontFamily: "monospace", fontWeight: 900, textAlign: "center" },
  smallMuted: { opacity: 0.7, fontSize: 12 },

  chatShell: { display: "flex", flexDirection: "column", gap: 12, height: 560 },
  chatLog: {
    flex: 1,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(0,0,0,0.25)",
    padding: 12,
    overflowY: "auto",
  },
  bubbleRow: { display: "flex", marginBottom: 10 },
  bubble: {
    maxWidth: "80%",
    padding: "10px 12px",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(255,255,255,0.06)",
    lineHeight: 1.35,
    fontSize: 13,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  bubbleUser: { marginLeft: "auto", background: "rgba(80, 160, 255, 0.14)", border: "1px solid rgba(80, 160, 255, 0.25)" },
  bubbleAssistant: { marginRight: "auto", background: "rgba(255,255,255,0.06)" },
  bubbleSystem: {
    marginLeft: "auto",
    marginRight: "auto",
    opacity: 0.85,
    background: "rgba(255, 210, 120, 0.10)",
    border: "1px solid rgba(255, 210, 120, 0.22)",
    maxWidth: "92%",
  },

  composer: { display: "flex", gap: 10, alignItems: "flex-end" },
  textarea: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    resize: "vertical",
    padding: 10,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(0,0,0,0.28)",
    color: "#e6edf3",
    outline: "none",
    fontSize: 13,
    lineHeight: 1.3,
  },
};
