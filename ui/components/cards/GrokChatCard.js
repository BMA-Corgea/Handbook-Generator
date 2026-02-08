// ui/components/cards/GrokChatCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Notice from "../ui/Notice.js";

import ChatLog from "../widgets/ChatLog.js";
import ChatComposer from "../widgets/ChatComposer.js";

import useLocalStorageState from "../hooks/useLocalStorageState.js";
import { LS_KEY_ACTIVE_DOC, LS_KEY_CHAT_MESSAGES } from "../constants.js";
import { fetchJsonOrThrow } from "../api.js";

const { useEffect, useRef, useState } = React;

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

export default function GrokChatCard({ apiBase }) {
  const [activeDocId] = useLocalStorageState(LS_KEY_ACTIVE_DOC, "");
  const [messages, setMessages] = useLocalStorageState(LS_KEY_CHAT_MESSAGES, [
    {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: "system",
      text:
        "Chat scaffold ready. Select a document in the Supabase card, then ask questions. Retrieved chunks (RAG) are fetched from Supabase and can be fed to Grok.",
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
  }

  async function retrieveForQuery(queryText) {
    if (!activeDocId) throw new Error("No active document selected. Pick a document in the Supabase card first.");
    const payload = { doc_id: activeDocId, query: queryText, top_k: 8 };
    return await fetchJsonOrThrow(`${apiBase}/supabase/retrieve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function send() {
    const text = String(chatInput || "").trim();
    if (!text || sending) return;

    setChatErr("");
    setSending(true);
    setChatInput("");
    push("user", text);

    try {
      const retrieval = await retrieveForQuery(text);
      const chunks = retrieval?.chunks || [];
      const context = buildContextFromChunks(chunks);

      if (!chunks.length) push("system", "No chunks returned from retrieval. Grok may not be able to answer from the document.");
      else push("system", `Retrieved ${chunks.length} chunks for doc_id=${String(activeDocId).slice(0, 8)}…`);

      let replyText = null;

      try {
        const grokPayload = { doc_id: activeDocId, query: text, context, chunks };
        const grokParsed = await fetchJsonOrThrow(`${apiBase}/grok/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(grokPayload),
        });

        replyText = grokParsed?.response ?? grokParsed?.answer ?? grokParsed?.text ?? "(No response field from /grok/chat)";
      } catch (e) {
        const fallback = await fetchJsonOrThrow(`${apiBase}/grok/test_grok`, { method: "GET", headers: { Accept: "application/json" } });
        const fallbackReply = fallback?.response ?? "(No response field)";
        replyText =
          `NOTE: /grok/chat not available (or errored). Showing /grok/test_grok instead.\n\n` +
          `Retrieved context length: ${context.length} chars.\n\n` +
          fallbackReply;
      }

      push("assistant", replyText || "(Empty reply)");
    } catch (e) {
      const msg = e?.message || String(e);
      setChatErr(msg);
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
      subtitle: "Retrieves chunks from Supabase, builds context, then calls /grok/chat (fallback /grok/test_grok).",
      right: React.createElement(Badge, null, "chat"),
    }),

    chatErr ? React.createElement(Notice, { variant: "error", title: "Chat Error" }, chatErr) : null,

    React.createElement(
      "div",
      { style: { marginTop: 12, display: "flex", flexDirection: "column", gap: 12, height: 560 } },
      React.createElement(ChatLog, { messages, scrollRef }),
      React.createElement(ChatComposer, { value: chatInput, onChange: setChatInput, onSend: send, disabled: sending })
    )
  );
}
