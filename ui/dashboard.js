// ui/dashboard.js
// No JSX. No build step. Works with React + ReactDOM via CDN.

const { useMemo, useState, useRef, useEffect } = React;

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

const LS_KEY = "lunar_uploaded_pdfs_v1";

function loadPdfRows() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function savePdfRows(rows) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(rows || []));
  } catch {}
}

function iconForStatus(status) {
  if (status === "error") return "X";
  if (status === "uploaded") return "✓";
  return "!";
}

export default function Dashboard() {
  const apiBase = useMemo(() => {
    if (typeof window !== "undefined" && window.LUNAR_API_BASE) {
      return String(window.LUNAR_API_BASE).replace(/\/+$/, "");
    }
    return DEFAULT_API_BASE.replace(/\/+$/, "");
  }, []);

  // -----------------------------
  // PDF Upload State
  // -----------------------------
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [pdfErr, setPdfErr] = useState("");
  const [latestJson, setLatestJson] = useState("");

  // rows: { id, original_name, saved_name, bytes, timestamp, status }
  const [pdfRows, setPdfRows] = useState(() => loadPdfRows());

  useEffect(() => {
    savePdfRows(pdfRows);
  }, [pdfRows]);

  async function uploadPdf() {
    if (!pdfFile || pdfUploading) return;

    setPdfErr("");
    setPdfUploading(true);

    const tempId = crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random()}`;
    const optimisticRow = {
      id: tempId,
      original_name: pdfFile.name,
      saved_name: "",
      bytes: pdfFile.size || null,
      timestamp: new Date().toISOString(),
      status: "ready",
    };

    // optimistic insert (shows immediately)
    setPdfRows((prev) => [optimisticRow].concat(prev));

    try {
      const fd = new FormData();
      fd.append("file", pdfFile);

      const res = await fetch(`${apiBase}/dashboard/upload-pdf`, {
        method: "POST",
        body: fd,
      });

      const bodyText = await res.text();
      let parsed = null;
      try {
        parsed = JSON.parse(bodyText);
      } catch {
        parsed = null;
      }

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || bodyText || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      setLatestJson(JSON.stringify(parsed, null, 2));

      // update row with real info
      setPdfRows((prev) =>
        prev.map((r) => {
          if (r.id !== tempId) return r;
          return {
            ...r,
            original_name: parsed?.original_name || r.original_name,
            saved_name: parsed?.saved_name || r.saved_name,
            bytes: parsed?.bytes ?? r.bytes,
            timestamp: parsed?.timestamp || r.timestamp,
            status: "ready", // "!" until you sync to Supabase
          };
        })
      );

      // clear file input state
      setPdfFile(null);
      const fileEl = document.getElementById("pdf-file-input");
      if (fileEl) fileEl.value = "";
    } catch (e) {
      const msg = e?.message || String(e);
      setPdfErr(msg);

      // mark optimistic row as error
      setPdfRows((prev) =>
        prev.map((r) => (r.id === tempId ? { ...r, status: "error" } : r))
      );
    } finally {
      setPdfUploading(false);
    }
  }

  function clearPdfHistory() {
    setPdfRows([]);
    setLatestJson("");
    setPdfErr("");
  }

  // -----------------------------
  // Supabase sync state
  // -----------------------------
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [batchSize, setBatchSize] = useState(200);
  const [storeDocText, setStoreDocText] = useState(true);

  async function syncToSupabase() {
    setLoading(true);
    setErr("");
    setRaw("");

    try {
      const qs = new URLSearchParams({
        batch_size: String(batchSize || 200),
        store_doc_text: storeDocText ? "true" : "false",
      });

      const res = await fetch(`${apiBase}/lightrag/sync-to-supabase?${qs.toString()}`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      const text = await res.text();

      let parsed = null;
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      setRaw(JSON.stringify(parsed, null, 2));

      // When a sync succeeds, mark all "ready" PDFs as uploaded.
      // (This is coarse-grained for now; later you can mark per-file.)
      setPdfRows((prev) =>
        prev.map((r) => (r.status === "ready" ? { ...r, status: "uploaded" } : r))
      );
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // -----------------------------
  // Chat state (Grok scaffold)
  // -----------------------------
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState("");

  const [messages, setMessages] = useState(() => [
    {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: "system",
      text:
        "Chat scaffold ready. User messages show on the right. Grok responses show on the left.",
      ts: Date.now(),
    },
  ]);

  const chatScrollRef = useRef(null);

  useEffect(() => {
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function pushMessage(role, text) {
    const id = crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random()}`;
    setMessages((prev) => prev.concat([{ id, role, text, ts: Date.now() }]));
  }

  async function sendChat() {
    const text = (chatInput || "").trim();
    if (!text || chatSending) return;

    setChatError("");
    setChatSending(true);

    pushMessage("user", text);
    setChatInput("");

    try {
      const res = await fetch(`${apiBase}/grok/test_grok`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });

      const bodyText = await res.text();
      let parsed = null;
      try {
        parsed = JSON.parse(bodyText);
      } catch {
        parsed = null;
      }

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || bodyText || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      const reply = parsed?.response ?? "(No response field)";
      pushMessage("assistant", reply);
    } catch (e) {
      const msg = e?.message || String(e);
      setChatError(msg);
      pushMessage("assistant", `Error calling Grok endpoint: ${msg}`);
    } finally {
      setChatSending(false);
    }
  }

  function onChatKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  }

  // -----------------------------
  // Styles
  // -----------------------------
  const styles = {
    page: {
      minHeight: "100vh",
      padding: 24,
      background: "#0b0f14",
      color: "#e6edf3",
      fontFamily:
        'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial',
    },

    container: {
      maxWidth: 1100,
      margin: "0 auto",
      display: "flex",
      flexDirection: "column",
      gap: 16,
    },

    card: {
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

    buttonDisabled: {
      opacity: 0.55,
      cursor: "not-allowed",
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

    checkboxRow: { display: "flex", alignItems: "center", gap: 8, opacity: 0.9 },

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

    tableWrap: {
      marginTop: 12,
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.10)",
      overflow: "hidden",
    },

    table: {
      width: "100%",
      borderCollapse: "collapse",
      fontSize: 13,
    },

    th: {
      textAlign: "left",
      padding: "10px 12px",
      background: "rgba(255,255,255,0.06)",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
      fontWeight: 800,
      opacity: 0.9,
    },

    td: {
      padding: "10px 12px",
      borderBottom: "1px solid rgba(255,255,255,0.06)",
      verticalAlign: "top",
      opacity: 0.95,
    },

    statusCell: {
      width: 44,
      fontFamily: "monospace",
      fontWeight: 900,
      textAlign: "center",
    },

    smallMuted: { opacity: 0.7, fontSize: 12 },

    // --- Chat UI ---
    chatShell: { display: "flex", flexDirection: "column", gap: 12, height: 520 },
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
    bubbleUser: {
      marginLeft: "auto",
      background: "rgba(80, 160, 255, 0.14)",
      border: "1px solid rgba(80, 160, 255, 0.25)",
    },
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
    smallNote: { opacity: 0.75, fontSize: 12, marginTop: 8 },
  };

  function renderBubble(m) {
    const rowStyle = { ...styles.bubbleRow };
    const bubbleStyle = { ...styles.bubble };

    if (m.role === "user") Object.assign(bubbleStyle, styles.bubbleUser);
    if (m.role === "assistant") Object.assign(bubbleStyle, styles.bubbleAssistant);
    if (m.role === "system") Object.assign(bubbleStyle, styles.bubbleSystem);

    if (m.role === "system") rowStyle.justifyContent = "center";

    return React.createElement(
      "div",
      { key: m.id, style: rowStyle },
      React.createElement("div", { style: bubbleStyle }, m.text)
    );
  }

  function renderPdfTable() {
    if (!pdfRows.length) {
      return React.createElement(
        "div",
        { style: { marginTop: 12, opacity: 0.75, fontSize: 13 } },
        "No PDFs uploaded yet."
      );
    }

    return React.createElement(
      "div",
      { style: styles.tableWrap },
      React.createElement(
        "table",
        { style: styles.table },
        React.createElement(
          "thead",
          null,
          React.createElement(
            "tr",
            null,
            React.createElement("th", { style: styles.th }, "Status"),
            React.createElement("th", { style: styles.th }, "Original"),
            React.createElement("th", { style: styles.th }, "Saved"),
            React.createElement("th", { style: styles.th }, "Bytes"),
            React.createElement("th", { style: styles.th }, "Timestamp")
          )
        ),
        React.createElement(
          "tbody",
          null,
          pdfRows.map((r) =>
            React.createElement(
              "tr",
              { key: r.id },
              React.createElement(
                "td",
                { style: { ...styles.td, ...styles.statusCell } },
                iconForStatus(r.status)
              ),
              React.createElement("td", { style: styles.td }, r.original_name || ""),
              React.createElement(
                "td",
                { style: styles.td },
                r.saved_name ? r.saved_name : React.createElement("span", { style: styles.smallMuted }, "—")
              ),
              React.createElement(
                "td",
                { style: styles.td },
                typeof r.bytes === "number" ? String(r.bytes) : React.createElement("span", { style: styles.smallMuted }, "—")
              ),
              React.createElement("td", { style: styles.td }, r.timestamp || "")
            )
          )
        )
      )
    );
  }

  // -----------------------------
  // Render
  // -----------------------------
  return React.createElement(
    "div",
    { style: styles.page },
    React.createElement(
      "div",
      { style: styles.container },

      // --------- PDF Upload + Table ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "PDF Staging (Dashboard Upload)"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Uploads go to ",
              React.createElement("span", { style: styles.code }, "./pdf_imports/"),
              " via ",
              React.createElement("span", { style: styles.code }, "POST /dashboard/upload-pdf"),
              ". Status: ",
              React.createElement("span", { style: styles.code }, "!"),
              " ready, ",
              React.createElement("span", { style: styles.code }, "✓"),
              " synced, ",
              React.createElement("span", { style: styles.code }, "X"),
              " error."
            )
          ),
          React.createElement("div", { style: styles.badge }, apiBase)
        ),

        React.createElement(
          "div",
          { style: styles.actions },
          React.createElement("input", {
            id: "pdf-file-input",
            type: "file",
            accept: "application/pdf",
            onChange: (e) => setPdfFile(e.target.files && e.target.files[0] ? e.target.files[0] : null),
          }),
          React.createElement(
            "button",
            {
              style: { ...styles.button, ...(pdfUploading || !pdfFile ? styles.buttonDisabled : {}) },
              onClick: uploadPdf,
              disabled: pdfUploading || !pdfFile,
              title: "Upload PDF to ./pdf_imports/",
            },
            pdfUploading ? "Uploading…" : "Upload PDF"
          ),
          React.createElement(
            "button",
            {
              style: { ...styles.button, ...(pdfRows.length ? {} : styles.buttonDisabled) },
              onClick: clearPdfHistory,
              disabled: !pdfRows.length,
              title: "Clears the UI list (local only). Does not delete server files.",
            },
            "Clear List"
          )
        ),

        pdfErr
          ? React.createElement(
              "div",
              { style: styles.errorBox },
              React.createElement("div", { style: { fontWeight: 800 } }, "Upload Error"),
              React.createElement("div", null, pdfErr)
            )
          : null,

        renderPdfTable()
      ),

      // --------- Latest Upload JSON ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Most Recent Upload JSON"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Shows the server response for the latest PDF upload."
            )
          ),
          React.createElement("div", { style: styles.badge }, "dashboard")
        ),
        React.createElement(
          "pre",
          { style: styles.pre },
          latestJson || "Upload a PDF to see its JSON response here."
        )
      ),

      // --------- Supabase Sync ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "LightRAG → Supabase Sync"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Calls ",
              React.createElement("span", { style: styles.code }, "POST /lightrag/sync-to-supabase"),
              " and writes documents + chunks + embeddings into Supabase (pgvector)."
            )
          ),
          React.createElement("div", { style: styles.badge }, apiBase)
        ),

        React.createElement(
          "div",
          { style: styles.actions },

          React.createElement("input", {
            style: styles.input,
            placeholder: "batch_size",
            value: batchSize,
            type: "number",
            min: 1,
            max: 1000,
            step: 50,
            onChange: (e) => setBatchSize(Number(e.target.value || 200)),
            title: "batch_size",
          }),

          React.createElement(
            "label",
            {
              style: styles.checkboxRow,
              title: "Store full document text in documents.content (recommended for re-chunking later)",
            },
            React.createElement("input", {
              type: "checkbox",
              checked: storeDocText,
              onChange: (e) => setStoreDocText(!!e.target.checked),
            }),
            "store_doc_text"
          ),

          React.createElement(
            "button",
            { style: styles.button, onClick: syncToSupabase, disabled: loading },
            loading ? "Syncing…" : "Sync LightRAG → Supabase"
          )
        ),

        err
          ? React.createElement(
              "div",
              { style: styles.errorBox },
              React.createElement("div", { style: { fontWeight: 800 } }, "Sync Error"),
              React.createElement("div", null, err)
            )
          : null,

        React.createElement("pre", { style: styles.pre }, raw || "Click sync to fetch JSON.")
      ),

      // --------- Grok Chatbot ----------
      React.createElement(
        "div",
        { style: styles.card },

        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Grok Chatbot (Scaffold)"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "User bubbles on the right. Assistant bubbles on the left. For now, assistant calls ",
              React.createElement("span", { style: styles.code }, "GET /grok/test_grok"),
              "."
            )
          ),
          React.createElement("div", { style: styles.badge }, apiBase)
        ),

        React.createElement(
          "div",
          { style: styles.chatShell },

          React.createElement(
            "div",
            { style: styles.chatLog, ref: chatScrollRef },
            messages.map(renderBubble)
          ),

          chatError
            ? React.createElement(
                "div",
                { style: styles.errorBox },
                React.createElement("div", { style: { fontWeight: 800 } }, "Chat Error"),
                React.createElement("div", null, chatError)
              )
            : null,

          React.createElement(
            "div",
            { style: styles.composer },
            React.createElement("textarea", {
              style: styles.textarea,
              value: chatInput,
              placeholder: "Type a message… (Enter to send, Shift+Enter for newline)",
              onChange: (e) => setChatInput(e.target.value),
              onKeyDown: onChatKeyDown,
              disabled: chatSending,
            }),
            React.createElement(
              "button",
              { style: styles.button, onClick: sendChat, disabled: chatSending || !chatInput.trim() },
              chatSending ? "Sending…" : "Send"
            )
          ),

          React.createElement(
            "div",
            { style: styles.smallNote },
            "Next step: add ",
            React.createElement("span", { style: styles.code }, "POST /grok/chat"),
            " so the assistant actually responds to your message (instead of the fixed smoke test)."
          )
        )
      ),

      // --------- Handbook Button (Not functional yet) ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Handbook Builder"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Placeholder button — not wired yet."
            )
          ),
          React.createElement("div", { style: styles.badge }, "coming soon")
        ),
        React.createElement(
          "div",
          { style: styles.actions },
          React.createElement(
            "button",
            {
              style: { ...styles.button, ...styles.buttonDisabled },
              disabled: true,
              title: "Not yet functional",
            },
            "Create Handbook (soon)"
          )
        )
      )
    )
  );
}
