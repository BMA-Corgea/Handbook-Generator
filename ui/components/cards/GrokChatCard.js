// ui/components/cards/GrokChatCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Notice from "../ui/Notice.js";
import Code from "../ui/Code.js";

import ChatLog from "../widgets/ChatLog.js";
import ChatComposer from "../widgets/ChatComposer.js";

import useLocalStorageState from "../hooks/useLocalStorageState.js";
import {
  LS_KEY_ACTIVE_DOC,
  LS_KEY_CHAT_MESSAGES,
  LS_KEY_RETRIEVAL_TOPK,
  LS_KEY_RETRIEVAL_MINSIM,
} from "../constants.js";
import { fetchJsonOrThrow } from "../api.js";

const { useEffect, useRef, useState } = React;

function summarizeVerdict(v) {
  const s = String(v || "").toLowerCase();
  if (s === "relevant") return "relevant";
  if (s === "partially_relevant") return "partially relevant";
  return "not relevant";
}

function safeJsonParse(raw, fallback) {
  if (raw === null || raw === undefined) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

export default function GrokChatCard({ apiBase }) {
  // Hook values (already parsed by your hook)
  const [activeDocId] = useLocalStorageState(LS_KEY_ACTIVE_DOC, "");
  const [topK] = useLocalStorageState(LS_KEY_RETRIEVAL_TOPK, 8);
  const [minSim] = useLocalStorageState(LS_KEY_RETRIEVAL_MINSIM, "");

  // Live values (kept in sync across cards without refresh)
  const [activeDocIdLive, setActiveDocIdLive] = useState(String(activeDocId || ""));
  const [topKLive, setTopKLive] = useState(Number(topK || 8));
  const [minSimLive, setMinSimLive] = useState(String(minSim || ""));

  const [messages, setMessages] = useLocalStorageState(LS_KEY_CHAT_MESSAGES, [
    {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: "system",
      text:
        "Chat scaffold ready. Select a document in the Supabase card, then ask questions. " +
        "This chat calls /grok/rag-chat (server performs retrieval + guardrails).",
      ts: Date.now(),
    },
  ]);

  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [chatErr, setChatErr] = useState("");

  const scrollRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function push(role, text) {
    const id = crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random()}`;
    setMessages((prev) => prev.concat([{ id, role, text, ts: Date.now() }]));
    return id;
  }

  function replaceMessage(id, patch) {
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        return { ...m, ...patch, ts: Date.now() };
      })
    );
  }

  // Keep live state synced with hook state (if hook triggers re-render)
  useEffect(() => setActiveDocIdLive(String(activeDocId || "")), [activeDocId]);
  useEffect(() => setTopKLive(Number(topK || 8)), [topK]);
  useEffect(() => setMinSimLive(String(minSim || "")), [minSim]);

  // Also subscribe to events and read *parsed* values from localStorage for same-tab updates
  useEffect(() => {
    function readAllFromStorage() {
      try {
        const rawDoc = localStorage.getItem(LS_KEY_ACTIVE_DOC);
        const rawTopK = localStorage.getItem(LS_KEY_RETRIEVAL_TOPK);
        const rawMin = localStorage.getItem(LS_KEY_RETRIEVAL_MINSIM);

        const docParsed = safeJsonParse(rawDoc, "");
        const topParsed = safeJsonParse(rawTopK, 8);
        const minParsed = safeJsonParse(rawMin, "");

        setActiveDocIdLive(String(docParsed || ""));
        const nk = Number(topParsed);
        setTopKLive(Number.isFinite(nk) ? nk : 8);
        setMinSimLive(String(minParsed || ""));
      } catch {
        // ignore
      }
    }

    function onStorageEvent(e) {
      // Native storage event: e.newValue is raw string (JSON), so parse it.
      if (e && e.type === "storage") {
        if (e.key === LS_KEY_ACTIVE_DOC) {
          const v = safeJsonParse(e.newValue, "");
          setActiveDocIdLive(String(v || ""));
        }
        if (e.key === LS_KEY_RETRIEVAL_TOPK) {
          const v = safeJsonParse(e.newValue, 8);
          const nk = Number(v);
          setTopKLive(Number.isFinite(nk) ? nk : 8);
        }
        if (e.key === LS_KEY_RETRIEVAL_MINSIM) {
          const v = safeJsonParse(e.newValue, "");
          setMinSimLive(String(v || ""));
        }
        return;
      }

      // Custom event (same-tab): just re-read all
      readAllFromStorage();
    }

    window.addEventListener("storage", onStorageEvent);
    window.addEventListener("lunar:ls", onStorageEvent);
    return () => {
      window.removeEventListener("storage", onStorageEvent);
      window.removeEventListener("lunar:ls", onStorageEvent);
    };
  }, []);

  // Breadcrumb when doc changes
  const lastDocRef = useRef(activeDocIdLive);
  useEffect(() => {
    const prev = String(lastDocRef.current || "");
    const next = String(activeDocIdLive || "");
    if (prev !== next) {
      lastDocRef.current = next;
      if (next) push("system", `Active document changed → doc_id="${next}"`);
    }
  }, [activeDocIdLive]);

  function renderParamsLine() {
    const sim = String(minSimLive || "").trim();
    return React.createElement(
      "div",
      { style: { marginTop: 8, fontSize: 12, opacity: 0.85 } },
      "Using retrieval params from Supabase card: ",
      React.createElement(Code, null, `top_k=${Number(topKLive || 8)}`),
      " ",
      sim ? React.createElement(Code, null, `min_similarity=${sim}`) : React.createElement(Code, null, "min_similarity=∅"),
      " ",
      activeDocIdLive ? React.createElement(Code, null, `doc_id=${activeDocIdLive.slice(0, 12)}…`) : null
    );
  }

  async function send() {
    const text = String(chatInput || "").trim();
    if (!text || sending) return;

    if (!activeDocIdLive) {
      const msg = "No active document selected. Pick a document in the Supabase card first.";
      setChatErr(msg);
      push("assistant", `Error: ${msg}`);
      return;
    }

    setChatErr("");
    setSending(true);
    setChatInput("");
    push("user", text);

    const thinkingId = push("system", "Thinking… (retrieving + asking Grok)");

    try {
      const payload = {
        question: text,
        doc_id: activeDocIdLive, // ✅ now guaranteed unquoted
        top_k: Number(topKLive || 8),
      };
      const sim = String(minSimLive || "").trim();
      if (sim) payload.min_similarity = Number(sim);

      const res = await fetchJsonOrThrow(`${apiBase}/grok/rag-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      const verdict = summarizeVerdict(res?.verdict);
      const used = Array.isArray(res?.used_chunks) ? res.used_chunks : [];
      const model = res?.model || "grok";

      replaceMessage(thinkingId, {
        role: "system",
        text: `RAG verdict: ${verdict}. Used ${used.length} chunk(s). Model=${model}.`,
      });

      const answer = res?.answer || "(Empty answer)";
      push("assistant", answer);
    } catch (e) {
      const msg = e?.message || String(e);
      setChatErr(msg);
      replaceMessage(thinkingId, { role: "system", text: `Error during Grok call: ${msg}` });
      push("assistant", `Error: ${msg}`);
    } finally {
      setSending(false);
    }
  }

  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "Chat (Supabase RAG → Grok)",
      subtitle: "Calls /grok/rag-chat (server performs retrieval + guardrails).",
      right: React.createElement(Badge, null, "chat"),
    }),

    renderParamsLine(),

    chatErr ? React.createElement(Notice, { variant: "error", title: "Chat Error" }, chatErr) : null,

    React.createElement(
      "div",
      { style: { marginTop: 12, display: "flex", flexDirection: "column", gap: 12, height: 560 } },
      React.createElement(ChatLog, { messages, scrollRef }),
      React.createElement(ChatComposer, { value: chatInput, onChange: setChatInput, onSend: send, disabled: sending })
    )
  );
}
