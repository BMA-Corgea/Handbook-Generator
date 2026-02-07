// ui/dashboard.js
// No JSX. No build step. Works with React + ReactDOM via CDN.

const { useMemo, useState, useRef, useEffect } = React;

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export default function Dashboard() {
  const apiBase = useMemo(() => {
    if (typeof window !== "undefined" && window.LUNAR_API_BASE) {
      return String(window.LUNAR_API_BASE).replace(/\/+$/, "");
    }
    return DEFAULT_API_BASE.replace(/\/+$/, "");
  }, []);

  // --- PDF dump state (left panel) ---
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

      try {
        const parsed = JSON.parse(text);
        if (!res.ok) throw new Error(parsed?.detail || parsed?.error || `HTTP ${res.status}`);
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

  // --- Chat state (right panel) ---
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState("");

  // messages: { id, role: "user"|"assistant"|"system", text, ts }
  const [messages, setMessages] = useState(() => [
    {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: "system",
      text: "Chat scaffold ready. User messages show on the right. Grok responses show on the left.",
      ts: Date.now(),
    },
  ]);

  const chatScrollRef = useRef(null);

  useEffect(() => {
    // Auto-scroll to bottom on new messages
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

    // User bubble (right)
    pushMessage("user", text);
    setChatInput("");

    try {
      // For now: call the fixed smoke test endpoint.
      // Next step: create POST /grok/chat that accepts the user text.
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

      // Assistant bubble (left)
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

  const styles = {
    page: {
      minHeight: "100vh",
      padding: 24,
      background: "#0b0f14",
      color: "#e6edf3",
      fontFamily:
        'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial',
    },

    // --- Layout ---
    grid: {
      display: "grid",
      gridTemplateColumns: "1.1fr 0.9fr",
      gap: 16,
      alignItems: "start",
      maxWidth: 1200,
      margin: "0 auto",
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

    actions: { marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" },

    button: {
      padding: "10px 14px",
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.14)",
      background: "rgba(255,255,255,0.06)",
      color: "#e6edf3",
      cursor: "pointer",
      fontWeight: 700,
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
      maxHeight: 520,
      overflowY: "auto",
    },

    hint: { marginTop: 8, opacity: 0.75, fontSize: 13 },

    code: {
      padding: "2px 6px",
      borderRadius: 8,
      border: "1px solid rgba(255,255,255,0.12)",
      background: "rgba(0,0,0,0.25)",
      fontFamily: "monospace",
    },

    // --- Chat UI ---
    chatShell: {
      display: "flex",
      flexDirection: "column",
      gap: 12,
      height: 640,
    },

    chatLog: {
      flex: 1,
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.10)",
      background: "rgba(0,0,0,0.25)",
      padding: 12,
      overflowY: "auto",
    },

    bubbleRow: {
      display: "flex",
      marginBottom: 10,
    },

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

    bubbleAssistant: {
      marginRight: "auto",
      background: "rgba(255,255,255,0.06)",
    },

    bubbleSystem: {
      marginLeft: "auto",
      marginRight: "auto",
      opacity: 0.85,
      background: "rgba(255, 210, 120, 0.10)",
      border: "1px solid rgba(255, 210, 120, 0.22)",
      maxWidth: "92%",
    },

    composer: {
      display: "flex",
      gap: 10,
      alignItems: "flex-end",
    },

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

    // align system center
    if (m.role === "system") {
      rowStyle.justifyContent = "center";
    }

    return React.createElement(
      "div",
      { key: m.id, style: rowStyle },
      React.createElement("div", { style: bubbleStyle }, m.text)
    );
  }

  return React.createElement(
    "div",
    { style: styles.page },

    React.createElement(
      "div",
      { style: styles.grid },

      // ----- LEFT: PDF dump -----
      React.createElement(
        "div",
        { style: styles.card },

        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "PDF → JSON Dump"),
            React.createElement(
              "div",
              { style: styles.subtitle },
              "Calls ",
              React.createElement("span", { style: styles.code }, "GET /lightrag/dump-pdf-json"),
              " and prints the JSON output."
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
              React.createElement("div", null, err)
            )
          : null,

        React.createElement("pre", { style: styles.pre }, raw || "Click the button to fetch JSON.")
      ),

      // ----- RIGHT: Chat scaffold -----
      React.createElement(
        "div",
        { style: styles.card },

        React.createElement(
          "div",
          { style: styles.headerRow },
          React.createElement(
            "div",
            null,
            React.createElement("div", { style: styles.title }, "Chat Scaffold"),
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
      )
    )
  );
}
