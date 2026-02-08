// ui/components/cards/SupabaseDocsCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Button from "../ui/Button.js";
import Notice from "../ui/Notice.js";
import Code from "../ui/Code.js";
import JsonViewer from "../widgets/JsonViewer.js";
import DocSelect from "../widgets/DocSelect.js";

import useAsyncAction from "../hooks/useAsyncAction.js";
import useLocalStorageState from "../hooks/useLocalStorageState.js";
import {
  LS_KEY_ACTIVE_DOC,
  LS_KEY_RETRIEVAL_TOPK,
  LS_KEY_RETRIEVAL_MINSIM,
} from "../constants.js";
import { fetchJsonOrThrow } from "../api.js";

import { NumberInput, TextInput, FieldRow, Label } from "../ui/Field.js";

const { useEffect, useState } = React;

export default function SupabaseDocsCard({ apiBase }) {
  const [docs, setDocs] = useState([]);
  const [docsErr, setDocsErr] = useState("");
  const [activeDocId, setActiveDocId] = useLocalStorageState(LS_KEY_ACTIVE_DOC, "");
  const [activeDoc, setActiveDoc] = useState(null);

  // ✅ persisted retrieval params so Chat can use the same values
  const [topK, setTopK] = useLocalStorageState(LS_KEY_RETRIEVAL_TOPK, 8);
  const [minSim, setMinSim] = useLocalStorageState(LS_KEY_RETRIEVAL_MINSIM, "");

  const [lastRetrieveJson, setLastRetrieveJson] = useState("");

  const refresh = useAsyncAction(async () => {
    const parsed = await fetchJsonOrThrow(`${apiBase}/supabase/documents?limit=500`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    const list = parsed?.documents || [];
    setDocs(Array.isArray(list) ? list : []);
    if (!activeDocId && list.length) setActiveDocId(list[0].doc_id);
    return list;
  });

  const fetchDoc = useAsyncAction(async (docId) => {
    if (!docId) {
      setActiveDoc(null);
      return null;
    }
    const parsed = await fetchJsonOrThrow(`${apiBase}/supabase/documents/${encodeURIComponent(docId)}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    setActiveDoc(parsed?.document || null);
    return parsed?.document || null;
  });

  useEffect(() => {
    refresh.run().catch((e) => setDocsErr(e?.message || String(e)));
  }, []);

  useEffect(() => {
    fetchDoc.run(activeDocId).catch(() => {});
  }, [activeDocId]);

  function renderActiveInfo() {
    if (!activeDocId) return null;
    const d = activeDoc || docs.find((x) => x.doc_id === activeDocId) || null;
    if (!d) return null;
    const fp = d?.file_path || d?.metadata?.source || "";
    const created = d?.created_at || "";
    const updated = d?.updated_at || "";
    return React.createElement(
      "div",
      { style: { marginTop: 10, fontSize: 13, opacity: 0.9, lineHeight: 1.35 } },
      React.createElement("div", null, "Active doc_id: ", React.createElement(Code, null, String(activeDocId).slice(0, 12) + "…")),
      fp ? React.createElement("div", null, "File: ", React.createElement(Code, null, fp)) : null,
      created ? React.createElement("div", null, "Created: ", React.createElement(Code, null, created)) : null,
      updated ? React.createElement("div", null, "Updated: ", React.createElement(Code, null, updated)) : null
    );
  }

  async function retrieveExample() {
    setLastRetrieveJson("");
    if (!activeDocId) {
      setLastRetrieveJson(JSON.stringify({ error: "No active document selected." }, null, 2));
      return;
    }

    const payload = { doc_id: activeDocId, query: "What is this document about?", top_k: Number(topK || 8) };
    const sim = String(minSim || "").trim();
    if (sim) payload.min_similarity = Number(sim);

    const parsed = await fetchJsonOrThrow(`${apiBase}/supabase/retrieve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });

    setLastRetrieveJson(JSON.stringify(parsed, null, 2));
  }

  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "Supabase Documents + Retrieval",
      subtitle: "Select a doc and test retrieval. Chat uses this same retrieval under the hood.",
      right: React.createElement(Badge, null, "retrieval"),
    }),

    docsErr ? React.createElement(Notice, { variant: "error", title: "Documents Error" }, docsErr) : null,
    refresh.error ? React.createElement(Notice, { variant: "error", title: "Refresh Error" }, refresh.error) : null,

    React.createElement(
      Card.Footer,
      null,
      React.createElement(Button, { onClick: () => refresh.run().catch(() => {}), disabled: refresh.loading }, refresh.loading ? "Refreshing…" : "Refresh Docs"),
      React.createElement(DocSelect, { docs, value: activeDocId, onChange: setActiveDocId })
    ),

    renderActiveInfo(),

    React.createElement(
      "div",
      { style: { marginTop: 12 } },
      React.createElement(Label, null, "Retrieval parameters"),
      React.createElement(
        FieldRow,
        null,
        React.createElement(NumberInput, {
          value: topK,
          onChange: (v) => setTopK(Number(v || 0)),
          width: 120,
          title: "top_k",
        }),
        React.createElement(TextInput, {
          value: minSim,
          onChange: setMinSim,
          width: 160,
          placeholder: "min_similarity (optional)",
          title: "min_similarity",
        }),
        React.createElement(Button, { onClick: () => retrieveExample().catch(() => {}), disabled: !activeDocId }, "Run Retrieval")
      )
    ),

    React.createElement(JsonViewer, { value: lastRetrieveJson, emptyText: "Retrieval JSON will appear here." })
  );
}
