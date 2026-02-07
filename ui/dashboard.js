// ui/dashboard.js
// No JSX. No build step. Works with React + ReactDOM via CDN.

const { useMemo, useState, useRef, useEffect } = React;

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

const LS_KEY = "lunar_uploaded_pdfs_v2"; // bumped schema
const LS_ACTIVE_DOC_KEY = "lunar_active_doc_id_v1";

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

function loadActiveDocId() {
  try {
    return localStorage.getItem(LS_ACTIVE_DOC_KEY) || "";
  } catch {
    return "";
  }
}

function saveActiveDocId(docId) {
  try {
    if (!docId) localStorage.removeItem(LS_ACTIVE_DOC_KEY);
    else localStorage.setItem(LS_ACTIVE_DOC_KEY, String(docId));
  } catch {}
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function fmtDocLabel(d) {
  const id = d?.doc_id ? String(d.doc_id) : "";
  const path = d?.file_path ? String(d.file_path) : "";
  const meta = d?.metadata || {};
  const source = meta?.source ? String(meta.source) : "";
  const best = path || source || "";
  if (best) return `${id.slice(0, 8)}… — ${best}`;
  return `${id}`;
}

// Row status model:
// - staged: uploaded to ./pdf_imports, not digested
// - digesting: in progress
// - digested: LightRAG artifacts exist in ./lightrag_cache/<doc_key>/
// - uploading: syncing that doc_key to Supabase
// - uploaded: synced successfully
// - error: failure at any step
function statusIcon(status) {
  if (status === "uploaded") return "✓";
  if (status === "error") return "X";
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
  // PDF Upload State (staging only)
  // -----------------------------
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [pdfErr, setPdfErr] = useState("");
  const [latestJson, setLatestJson] = useState("");

  // rows:
  // {
  //   id, original_name, saved_name, bytes, timestamp,
  //   status, error,
  //   doc_key, working_dir, // set after digestion
  //   supabase_doc_id        // set after upload (optional)
  // }
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
      status: "staged",
      error: "",
      doc_key: "",
      working_dir: "",
      supabase_doc_id: "",
    };

    setPdfRows((prev) => [optimisticRow].concat(prev));

    try {
      const fd = new FormData();
      fd.append("file", pdfFile);

      const res = await fetch(`${apiBase}/dashboard/upload-pdf`, {
        method: "POST",
        body: fd,
      });

      const bodyText = await res.text();
      const parsed = safeJsonParse(bodyText);

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || bodyText || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      setLatestJson(JSON.stringify(parsed, null, 2));

      setPdfRows((prev) =>
        prev.map((r) => {
          if (r.id !== tempId) return r;
          return {
            ...r,
            original_name: parsed?.original_name || r.original_name,
            saved_name: parsed?.saved_name || r.saved_name,
            bytes: parsed?.bytes ?? r.bytes,
            timestamp: parsed?.timestamp || r.timestamp,
            status: "staged",
            error: "",
          };
        })
      );

      setPdfFile(null);
      const fileEl = document.getElementById("pdf-file-input");
      if (fileEl) fileEl.value = "";
    } catch (e) {
      const msg = e?.message || String(e);
      setPdfErr(msg);

      setPdfRows((prev) =>
        prev.map((r) => (r.id === tempId ? { ...r, status: "error", error: msg } : r))
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
  // Per-row LightRAG digestion
  // -----------------------------
  const [digestJson, setDigestJson] = useState("");
  const [digestErr, setDigestErr] = useState("");

  async function digestRow(rowId) {
    const row = pdfRows.find((r) => r.id === rowId);
    if (!row) return;
    if (!row.saved_name) {
      setDigestErr("Row has no saved_name yet (upload might not have completed).");
      return;
    }
    if (row.status === "digesting" || row.status === "uploading") return;

    setDigestErr("");
    setDigestJson("");

    // optimistic status
    setPdfRows((prev) =>
      prev.map((r) => (r.id === rowId ? { ...r, status: "digesting", error: "" } : r))
    );

    try {
      const payload = {
        saved_name: row.saved_name,
        original_name: row.original_name || row.saved_name,
        // optional override; backend can slugify original_name if not provided
        doc_key: row.doc_key || "",
      };

      const res = await fetch(`${apiBase}/lightrag/ingest-staged`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      const text = await res.text();
      const parsed = safeJsonParse(text);

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      setDigestJson(JSON.stringify(parsed, null, 2));

      // update row with digestion outputs
      setPdfRows((prev) =>
        prev.map((r) => {
          if (r.id !== rowId) return r;
          return {
            ...r,
            status: "digested",
            error: "",
            doc_key: parsed?.doc_key || r.doc_key,
            working_dir: parsed?.working_dir || r.working_dir,
          };
        })
      );
    } catch (e) {
      const msg = e?.message || String(e);
      setDigestErr(msg);
      setPdfRows((prev) =>
        prev.map((r) => (r.id === rowId ? { ...r, status: "error", error: msg } : r))
      );
    }
  }

  // -----------------------------
  // Supabase upload (selected digested doc only)
  // -----------------------------
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [batchSize, setBatchSize] = useState(200);
  const [storeDocText, setStoreDocText] = useState(true);

  // dropdown selection: pick from digested rows
  const digestedRows = pdfRows.filter((r) => r.status === "digested" || r.status === "uploading" || r.status === "uploaded");
  const [selectedRowId, setSelectedRowId] = useState("");

  useEffect(() => {
    // keep selection sane
    if (selectedRowId && !digestedRows.find((r) => r.id === selectedRowId)) {
      setSelectedRowId("");
    }
    if (!selectedRowId && digestedRows.length) {
      // auto-pick the most recent digested
      setSelectedRowId(digestedRows[0].id);
    }
  }, [pdfRows]);

  async function uploadSelectedToSupabase() {
    const row = pdfRows.find((r) => r.id === selectedRowId);
    if (!row) {
      setErr("Pick a digested document first.");
      return;
    }
    if (!row.working_dir) {
      setErr("Selected row has no working_dir. Digest it first.");
      return;
    }

    setLoading(true);
    setErr("");
    setRaw("");

    // optimistic row status
    setPdfRows((prev) =>
      prev.map((r) => (r.id === row.id ? { ...r, status: "uploading", error: "" } : r))
    );

    try {
      const qs = new URLSearchParams({
        working_dir: String(row.working_dir),
        batch_size: String(batchSize || 200),
        store_doc_text: storeDocText ? "true" : "false",
      });

      const res = await fetch(`${apiBase}/lightrag/sync-to-supabase?${qs.toString()}`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      const text = await res.text();
      const parsed = safeJsonParse(text);

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      setRaw(JSON.stringify(parsed, null, 2));

      // mark ONLY this row as uploaded
      setPdfRows((prev) =>
        prev.map((r) =>
          r.id === row.id
            ? {
                ...r,
                status: "uploaded",
                error: "",
                supabase_doc_id: parsed?.doc_id || parsed?.document_id || r.supabase_doc_id,
              }
            : r
        )
      );

      // optional: refresh doc dropdown after upload (below)
      await refreshDocuments({ keepSelection: true });
    } catch (e) {
      const msg = e?.message || String(e);
      setErr(msg);
      setPdfRows((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, status: "error", error: msg } : r))
      );
    } finally {
      setLoading(false);
    }
  }

  // -----------------------------
  // Supabase documents dropdown + retrieval (unchanged)
  // -----------------------------
  const [docs, setDocs] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsErr, setDocsErr] = useState("");
  const [activeDocId, setActiveDocId] = useState(() => loadActiveDocId());
  const [activeDoc, setActiveDoc] = useState(null);

  const [topK, setTopK] = useState(8);
  const [minSim, setMinSim] = useState(""); // optional, empty = unset
  const [lastRetrieveJson, setLastRetrieveJson] = useState("");

  useEffect(() => {
    saveActiveDocId(activeDocId);
  }, [activeDocId]);

  async function refreshDocuments({ keepSelection } = { keepSelection: true }) {
    setDocsLoading(true);
    setDocsErr("");

    try {
      const res = await fetch(`${apiBase}/supabase/documents?limit=500`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });

      const text = await res.text();
      const parsed = safeJsonParse(text);

      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
        throw new Error(msg);
      }

      const list = parsed?.documents || [];
      setDocs(Array.isArray(list) ? list : []);

      if (!keepSelection) {
        setActiveDocId("");
        setActiveDoc(null);
      } else {
        if (activeDocId) {
          const found = (Array.isArray(list) ? list : []).find((d) => d.doc_id === activeDocId);
          if (!found && list.length) setActiveDocId(list[0].doc_id);
        } else if (list.length) {
          setActiveDocId(list[0].doc_id);
        }
      }
    } catch (e) {
      setDocsErr(e?.message || String(e));
      setDocs([]);
      setActiveDoc(null);
    } finally {
      setDocsLoading(false);
    }
  }

  async function fetchActiveDocDetails(docId) {
    if (!docId) {
      setActiveDoc(null);
      return;
    }
    try {
      const res = await fetch(`${apiBase}/supabase/documents/${encodeURIComponent(docId)}`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      const text = await res.text();
      const parsed = safeJsonParse(text);
      if (!res.ok) {
        const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      setActiveDoc(parsed?.document || null);
    } catch {
      setActiveDoc(null);
    }
  }

  useEffect(() => {
    refreshDocuments({ keepSelection: true });
  }, []);

  useEffect(() => {
    fetchActiveDocDetails(activeDocId);
  }, [activeDocId]);

  async function retrieveForQuery(queryText) {
    const docId = activeDocId;
    if (!docId) throw new Error("No active document selected. Pick a document from the dropdown first.");

    const payload = { doc_id: docId, query: queryText, top_k: Number(topK || 8) };
    const sim = (minSim || "").trim();
    if (sim) payload.min_similarity = Number(sim);

    const res = await fetch(`${apiBase}/supabase/retrieve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });

    const text = await res.text();
    const parsed = safeJsonParse(text);

    if (!res.ok) {
      const msg = parsed?.detail || parsed?.error || text || `HTTP ${res.status}`;
      throw new Error(msg);
    }

    setLastRetrieveJson(JSON.stringify(parsed, null, 2));
    return parsed;
  }

  function buildContextFromChunks(chunks) {
    const arr = Array.isArray(chunks) ? chunks : [];
    return arr
      .map((c, i) => {
        const meta = c?.metadata || {};
        const page = meta?.page ?? c?.page ?? null;
        const cid = c?.chunk_id ? String(c.chunk_id) : `chunk_${i + 1}`;
        const header = page ? `[p${page} #${cid}]` : `[#${cid}]`;
        const content = c?.content ? String(c.content) : "";
        return `${header}\n${content}`;
      })
      .join("\n\n---\n\n");
  }

  // -----------------------------
  // Chat state (unchanged)
  // -----------------------------
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState("");

  const [messages, setMessages] = useState(() => [
    {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: "system",
      text:
        "Chat scaffold ready. Select a document, then ask questions. Retrieved chunks (RAG) are fetched from Supabase and can be fed to Grok.",
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

  function pushSystemNote(text) {
    pushMessage("system", text);
  }

  async function sendChat() {
    const text = (chatInput || "").trim();
    if (!text || chatSending) return;

    setChatError("");
    setChatSending(true);

    pushMessage("user", text);
    setChatInput("");

    try {
      const retrieval = await retrieveForQuery(text);
      const chunks = retrieval?.chunks || [];
      const context = buildContextFromChunks(chunks);

      if (!chunks.length) pushSystemNote("No chunks returned from retrieval. Grok may not be able to answer from the document.");
      else pushSystemNote(`Retrieved ${chunks.length} chunks from Supabase for doc_id=${activeDocId.slice(0, 8)}…`);

      let replyText = null;

      try {
        const grokPayload = { doc_id: activeDocId, query: text, context, chunks };
        const grokRes = await fetch(`${apiBase}/grok/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(grokPayload),
        });

        const grokBodyText = await grokRes.text();
        const grokParsed = safeJsonParse(grokBodyText);

        if (!grokRes.ok) {
          const msg = grokParsed?.detail || grokParsed?.error || grokBodyText || `HTTP ${grokRes.status}`;
          throw new Error(msg);
        }

        replyText = grokParsed?.response ?? grokParsed?.answer ?? grokParsed?.text ?? "(No response field from /grok/chat)";
      } catch (e) {
        const fallbackRes = await fetch(`${apiBase}/grok/test_grok`, {
          method: "GET",
          headers: { Accept: "application/json" },
        });

        const fallbackText = await fallbackRes.text();
        const fallbackParsed = safeJsonParse(fallbackText);

        if (!fallbackRes.ok) {
          const msg = fallbackParsed?.detail || fallbackParsed?.error || fallbackText || `HTTP ${fallbackRes.status}`;
          throw new Error(`Grok chat failed AND fallback failed: ${msg}`);
        }

        const fallbackReply = fallbackParsed?.response ?? "(No response field)";
        replyText =
          `NOTE: /grok/chat not available (or errored). Showing /grok/test_grok instead.\n\n` +
          `Retrieved context length: ${context.length} chars.\n\n` +
          fallbackReply;
      }

      pushMessage("assistant", replyText || "(Empty reply)");
    } catch (e) {
      const msg = e?.message || String(e);
      setChatError(msg);
      pushMessage("assistant", `Error: ${msg}`);
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
  // Styles (same look, plus small tweaks)
  // -----------------------------
  const styles = {
    page: {
      minHeight: "100vh",
      padding: 24,
      background: "#0b0f14",
      color: "#e6edf3",
      fontFamily: 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial',
    },
    container: { maxWidth: 1100, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 },
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
    statusCell: { width: 72, fontFamily: "monospace", fontWeight: 900, textAlign: "center" },
    smallMuted: { opacity: 0.7, fontSize: 12 },
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
    smallNote: { opacity: 0.75, fontSize: 12, marginTop: 8 },
  };

  function renderBubble(m) {
    const rowStyle = { ...styles.bubbleRow };
    const bubbleStyle = { ...styles.bubble };

    if (m.role === "user") Object.assign(bubbleStyle, styles.bubbleUser);
    if (m.role === "assistant") Object.assign(bubbleStyle, styles.bubbleAssistant);
    if (m.role === "system") Object.assign(bubbleStyle, styles.bubbleSystem);
    if (m.role === "system") rowStyle.justifyContent = "center";

    return React.createElement("div", { key: m.id, style: rowStyle }, React.createElement("div", { style: bubbleStyle }, m.text));
  }

  function renderPdfTable() {
    if (!pdfRows.length) {
      return React.createElement("div", { style: { marginTop: 12, opacity: 0.75, fontSize: 13 } }, "No PDFs uploaded yet.");
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
            React.createElement("th", { style: styles.th }, "Doc Key"),
            React.createElement("th", { style: styles.th }, "Bytes"),
            React.createElement("th", { style: styles.th }, "Timestamp")
          )
        ),
        React.createElement(
          "tbody",
          null,
          pdfRows.map((r) => {
            const canDigest = r.status === "staged" || r.status === "error";
            const isDigesting = r.status === "digesting";
            const icon = statusIcon(r.status);

            const statusCell =
              r.status === "staged"
                ? React.createElement(
                    "button",
                    {
                      style: styles.tinyBtn,
                      onClick: () => digestRow(r.id),
                      title: "Digest into LightRAG (creates ./lightrag_cache/<doc_key>/)",
                      disabled: isDigesting || !r.saved_name,
                    },
                    `${icon} Digest`
                  )
                : r.status === "digested"
                ? React.createElement("span", null, `${icon} Ready`)
                : r.status === "uploaded"
                ? React.createElement("span", null, `${icon} Done`)
                : r.status === "uploading"
                ? React.createElement("span", null, `… Uploading`)
                : r.status === "digesting"
                ? React.createElement("span", null, `… Digesting`)
                : r.status === "error"
                ? React.createElement(
                    "button",
                    {
                      style: styles.tinyBtn,
                      onClick: () => (r.saved_name ? digestRow(r.id) : null),
                      title: r.error ? `Error: ${r.error}` : "Retry digest",
                      disabled: !r.saved_name,
                    },
                    `${icon} Retry`
                  )
                : React.createElement("span", null, icon);

            return React.createElement(
              "tr",
              { key: r.id },
              React.createElement("td", { style: { ...styles.td, ...styles.statusCell } }, statusCell),
              React.createElement("td", { style: styles.td }, r.original_name || ""),
              React.createElement("td", { style: styles.td }, r.saved_name ? r.saved_name : React.createElement("span", { style: styles.smallMuted }, "—")),
              React.createElement("td", { style: styles.td }, r.doc_key ? React.createElement("span", { style: styles.code }, r.doc_key) : React.createElement("span", { style: styles.smallMuted }, "—")),
              React.createElement("td", { style: styles.td }, typeof r.bytes === "number" ? String(r.bytes) : React.createElement("span", { style: styles.smallMuted }, "—")),
              React.createElement("td", { style: styles.td }, r.timestamp || "")
            );
          })
        )
      )
    );
  }

  function renderActiveDocInfo() {
    if (!activeDocId) {
      return React.createElement("div", { style: { marginTop: 10, opacity: 0.8, fontSize: 13 } }, "Select a document to scope retrieval.");
    }

    const d = activeDoc || docs.find((x) => x.doc_id === activeDocId) || null;
    const fp = d?.file_path || d?.metadata?.source || "";
    const created = d?.created_at || "";
    const updated = d?.updated_at || "";
    const shortId = activeDocId ? `${String(activeDocId).slice(0, 12)}…` : "";

    return React.createElement(
      "div",
      { style: { marginTop: 10, fontSize: 13, opacity: 0.88, lineHeight: 1.35 } },
      React.createElement("div", null, "Active doc_id: ", React.createElement("span", { style: styles.code }, shortId)),
      fp ? React.createElement("div", null, "File: ", React.createElement("span", { style: styles.code }, fp)) : null,
      created ? React.createElement("div", null, "Created: ", React.createElement("span", { style: styles.code }, created)) : null,
      updated ? React.createElement("div", null, "Updated: ", React.createElement("span", { style: styles.code }, updated)) : null
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
            React.createElement("div", { style: styles.title }, "PDF Staging → Digest"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Upload stages PDF into ",
              React.createElement("span", { style: styles.code }, "./pdf_imports/"),
              " via ",
              React.createElement("span", { style: styles.code }, "POST /dashboard/upload-pdf"),
              ". Then click ",
              React.createElement("span", { style: styles.code }, "! Digest"),
              " per-row to create ",
              React.createElement("span", { style: styles.code }, "./lightrag_cache/<doc_key>/"),
              "."
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
            { style: { ...styles.button, ...(pdfUploading || !pdfFile ? styles.buttonDisabled : {}) }, onClick: uploadPdf, disabled: pdfUploading || !pdfFile },
            pdfUploading ? "Uploading…" : "Upload PDF"
          ),
          React.createElement(
            "button",
            { style: { ...styles.button, ...(pdfRows.length ? {} : styles.buttonDisabled) }, onClick: clearPdfHistory, disabled: !pdfRows.length },
            "Clear List"
          )
        ),

        pdfErr ? React.createElement("div", { style: styles.errorBox }, React.createElement("div", { style: { fontWeight: 800 } }, "Upload Error"), React.createElement("div", null, pdfErr)) : null,

        renderPdfTable()
      ),

      // --------- Latest Upload JSON ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement("div", null, React.createElement("div", { style: styles.title }, "Most Recent Upload JSON"), React.createElement("div", { style: styles.subtitle }, "Server response for latest PDF upload.")),
          React.createElement("div", { style: styles.badge }, "dashboard")
        ),
        React.createElement("pre", { style: styles.pre }, latestJson || "Upload a PDF to see its JSON response here.")
      ),

      // --------- Digest Debug ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement("div", null, React.createElement("div", { style: styles.title }, "LightRAG Digest Debug"), React.createElement("div", { style: styles.subtitle }, "Shows the server response for the most recent digest.")),
          React.createElement("div", { style: styles.badge }, "lightrag")
        ),
        digestErr ? React.createElement("div", { style: styles.errorBox }, React.createElement("div", { style: { fontWeight: 800 } }, "Digest Error"), React.createElement("div", null, digestErr)) : null,
        React.createElement("pre", { style: styles.pre }, digestJson || "Click “! Digest” on a staged PDF row to see digest output here.")
      ),

      // --------- Supabase Upload (selected digested doc only) ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Digest → Supabase Upload"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Uploads ONE digested LightRAG working dir to Supabase via ",
              React.createElement("span", { style: styles.code }, "POST /lightrag/sync-to-supabase?working_dir=..."),
              " (so there’s no accidental “everything in cache” syncing)."
            )
          ),
          React.createElement("div", { style: styles.badge }, apiBase)
        ),

        React.createElement(
          "div",
          { style: styles.actions },

          React.createElement(
            "select",
            {
              style: styles.select,
              value: selectedRowId || "",
              onChange: (e) => setSelectedRowId(e.target.value || ""),
              title: "Pick a digested document to upload",
            },
            React.createElement("option", { value: "" }, digestedRows.length ? "Select a digested PDF…" : "No digested PDFs yet…"),
            digestedRows.map((r) =>
              React.createElement("option", { key: r.id, value: r.id }, `${r.original_name || r.saved_name} — ${r.doc_key || "?"}`)
            )
          ),

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
            { style: styles.checkboxRow, title: "Store full document text in documents.content (recommended for re-chunking later)" },
            React.createElement("input", { type: "checkbox", checked: storeDocText, onChange: (e) => setStoreDocText(!!e.target.checked) }),
            "store_doc_text"
          ),

          React.createElement(
            "button",
            { style: { ...styles.button, ...(!selectedRowId || loading ? styles.buttonDisabled : {}) }, onClick: uploadSelectedToSupabase, disabled: !selectedRowId || loading },
            loading ? "Uploading…" : "Upload Selected → Supabase"
          ),

          React.createElement(
            "button",
            { style: { ...styles.button, ...(docsLoading ? styles.buttonDisabled : {}) }, onClick: () => refreshDocuments({ keepSelection: true }), disabled: docsLoading },
            docsLoading ? "Refreshing…" : "Refresh Supabase Docs"
          )
        ),

        err ? React.createElement("div", { style: styles.errorBox }, React.createElement("div", { style: { fontWeight: 800 } }, "Upload Error"), React.createElement("div", null, err)) : null,

        React.createElement("pre", { style: styles.pre }, raw || "Upload a digested doc to see JSON response here.")
      ),

      // --------- Grok Chatbot (RAG-enabled) ----------
      React.createElement(
        "div",
        { style: styles.card },
        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Grok Chatbot (RAG-enabled)"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Select a document (doc_id) from Supabase. Each question runs ",
              React.createElement("span", { style: styles.code }, "POST /supabase/retrieve"),
              " then tries ",
              React.createElement("span", { style: styles.code }, "POST /grok/chat"),
              " (fallback to ",
              React.createElement("span", { style: styles.code }, "GET /grok/test_grok"),
              ")."
            )
          ),
          React.createElement("div", { style: styles.badge }, apiBase)
        ),

        React.createElement(
          "div",
          { style: { ...styles.actions, marginTop: 12 } },
          React.createElement(
            "select",
            { style: styles.select, value: activeDocId || "", onChange: (e) => setActiveDocId(e.target.value || ""), disabled: docsLoading },
            React.createElement("option", { value: "" }, docsLoading ? "Loading documents…" : "Select a document…"),
            (docs || []).map((d) => React.createElement("option", { key: d.doc_id, value: d.doc_id }, fmtDocLabel(d)))
          ),
          React.createElement("input", { style: { ...styles.input, width: 90 }, placeholder: "top_k", value: topK, type: "number", min: 1, max: 50, step: 1, onChange: (e) => setTopK(Number(e.target.value || 8)) }),
          React.createElement("input", { style: { ...styles.input, width: 140 }, placeholder: "min_similarity (opt)", value: minSim, type: "number", step: 0.01, onChange: (e) => setMinSim(e.target.value) }),
          React.createElement("button", { style: { ...styles.button, ...(docsLoading ? styles.buttonDisabled : {}) }, onClick: () => refreshDocuments({ keepSelection: true }), disabled: docsLoading }, docsLoading ? "Refreshing…" : "Refresh")
        ),

        docsErr ? React.createElement("div", { style: styles.errorBox }, React.createElement("div", { style: { fontWeight: 800 } }, "Documents Error"), React.createElement("div", null, docsErr)) : null,

        renderActiveDocInfo(),

        React.createElement(
          "div",
          { style: styles.chatShell },
          React.createElement("div", { style: styles.chatLog, ref: chatScrollRef }, messages.map(renderBubble)),
          chatError ? React.createElement("div", { style: styles.errorBox }, React.createElement("div", { style: { fontWeight: 800 } }, "Chat Error"), React.createElement("div", null, chatError)) : null,
          React.createElement(
            "div",
            { style: styles.composer },
            React.createElement("textarea", {
              style: styles.textarea,
              value: chatInput,
              placeholder: activeDocId ? "Ask a question… (Enter to send)" : "Select a doc first…",
              onChange: (e) => setChatInput(e.target.value),
              onKeyDown: onChatKeyDown,
              disabled: chatSending,
            }),
            React.createElement(
              "button",
              { style: { ...styles.button, ...(chatSending || !chatInput.trim() || !activeDocId ? styles.buttonDisabled : {}) }, onClick: sendChat, disabled: chatSending || !chatInput.trim() || !activeDocId },
              chatSending ? "Sending…" : "Send"
            )
          ),
          React.createElement("div", { style: styles.smallNote }, "RAG debug: last retrieval JSON is shown below."),
          React.createElement("pre", { style: styles.pre }, lastRetrieveJson || "Ask a question to see retrieval results here.")
        )
      )
    )
  );
}
