// ui/components/cards/LongWriteCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Button from "../ui/Button.js";
import Notice from "../ui/Notice.js";
import Code from "../ui/Code.js";

import useLocalStorageState from "../hooks/useLocalStorageState.js";
import { fetchJsonOrThrow } from "../api.js";

import { NumberInput, TextInput, FieldRow, Label } from "../ui/Field.js";
import { LS_KEY_ACTIVE_DOC } from "../constants.js";

const { useEffect, useMemo, useRef, useState } = React;

// LocalStorage keys for persistence
const LS_KEY_HANDBOOK_REQUEST = "lunar_handbook_request";
const LS_KEY_HANDBOOK_TARGET_WORDS = "lunar_handbook_target_words";
const LS_KEY_HANDBOOK_MIN_SECTION_WORDS = "lunar_handbook_min_section_words";
const LS_KEY_HANDBOOK_MAX_SECTION_WORDS = "lunar_handbook_max_section_words";
const LS_KEY_HANDBOOK_MAX_SECTIONS = "lunar_handbook_max_sections";

function countWords(text) {
  const s = String(text || "").trim();
  if (!s) return 0;
  return s.split(/\s+/).filter(Boolean).length;
}

export default function LongWriteCard({ apiBase }) {
  // Selected doc from SupabaseDocsCard
  const [activeDocId] = useLocalStorageState(LS_KEY_ACTIVE_DOC, "");

  // Handbook request (implicit instruction manual)
  const [handbookRequest, setHandbookRequest] = useLocalStorageState(
    LS_KEY_HANDBOOK_REQUEST,
    "Generate a comprehensive handbook (instruction manual) based ONLY on the selected document. " +
      "Explain concepts, procedures, troubleshooting, and practical guidance. Use clear headings and structure."
  );

  // Params framed as handbook controls
  const [targetWords, setTargetWords] = useLocalStorageState(LS_KEY_HANDBOOK_TARGET_WORDS, 20000);
  const [minSectionWords, setMinSectionWords] = useLocalStorageState(LS_KEY_HANDBOOK_MIN_SECTION_WORDS, 500);
  const [maxSectionWords, setMaxSectionWords] = useLocalStorageState(LS_KEY_HANDBOOK_MAX_SECTION_WORDS, 900);
  const [maxSections, setMaxSections] = useLocalStorageState(LS_KEY_HANDBOOK_MAX_SECTIONS, 30);

  const [running, setRunning] = useState(false);
  const [err, setErr] = useState("");

  const [outlineText, setOutlineText] = useState("");
  const [outputText, setOutputText] = useState("");
  const [diagnostics, setDiagnostics] = useState(null);

  const outRef = useRef(null);

  useEffect(() => {
    const el = outRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [outputText]);

  const wordsSoFar = useMemo(() => countWords(outputText), [outputText]);

  function clearAll() {
    setErr("");
    setOutlineText("");
    setOutputText("");
    setDiagnostics(null);
  }

  function renderDocContextLine() {
    if (!activeDocId) {
      return React.createElement(
        Notice,
        { variant: "warning", title: "No Active Document" },
        "Select a document in the ",
        React.createElement(Code, null, "Supabase Documents + Retrieval"),
        " card first. Handbook generation is derived from that document."
      );
    }

    return React.createElement(
      "div",
      { style: { marginTop: 8, fontSize: 12, opacity: 0.85 } },
      "Active doc_id: ",
      React.createElement(Code, null, String(activeDocId).slice(0, 32) + "…")
    );
  }

  function renderParamHelp() {
    return React.createElement(
      "div",
      { style: { marginTop: 8, fontSize: 12, opacity: 0.85, lineHeight: 1.4 } },
      React.createElement("div", null, React.createElement(Code, null, "Target handbook size"), " = approximate final word count goal."),
      React.createElement("div", null, React.createElement(Code, null, "Section size"), " = how long each generated section should be (used to build the outline)."),
      React.createElement("div", null, React.createElement(Code, null, "Max sections"), " = safety cap (prevents runaway).")
    );
  }

  async function runHandbook() {
    const reqText = String(handbookRequest || "").trim();
    if (!reqText) {
      setErr("Handbook request is required.");
      return;
    }
    if (!activeDocId) {
      setErr("No active document selected. Pick a document in SupabaseDocsCard first.");
      return;
    }

    setErr("");
    setRunning(true);
    setOutlineText("");
    setOutputText("");
    setDiagnostics(null);

    setOutlineText("Thinking… building handbook outline from the selected document…");
    setOutputText("");

    try {
      const payload = {
        doc_id: String(activeDocId),
        handbook_request: reqText,
        target_words: Number(targetWords || 0),
        min_section_words: Number(minSectionWords || 0),
        max_section_words: Number(maxSectionWords || 0),
        max_sections: Number(maxSections || 0),
      };

      const res = await fetchJsonOrThrow(`${apiBase}/longwrite/handbook`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      const outline = res?.outline || "";
      const text = res?.text || "";
      setOutlineText(outline || "(No outline returned)");
      setOutputText(text || "(No text returned)");
      setDiagnostics(res?.diagnostics || null);
    } catch (e) {
      const msg = e?.message || String(e);
      setErr(msg);
      setOutlineText("");
      setOutputText(`Error: ${msg}`);
    } finally {
      setRunning(false);
    }
  }

  function renderDiagnostics() {
    if (!diagnostics) return null;
    const d = diagnostics || {};
    return React.createElement(
      "div",
      { style: { marginTop: 10, fontSize: 12, opacity: 0.9, lineHeight: 1.4 } },
      React.createElement("div", null, "Model: ", React.createElement(Code, null, String(d.model || ""))),
      React.createElement("div", null, "Sections written: ", React.createElement(Code, null, String(d.sections_written ?? ""))),
      React.createElement("div", null, "Final word count: ", React.createElement(Code, null, String(d.final_word_count ?? ""))),
      React.createElement("div", null, "Target words: ", React.createElement(Code, null, String(d.target_words ?? ""))),
      React.createElement("div", null, "Retrieved chunks used: ", React.createElement(Code, null, String(d.retrieved_chunks ?? ""))),
      React.createElement("div", null, "Max tokens per call: ", React.createElement(Code, null, String(d.max_tokens ?? "")))
    );
  }

  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "Handbook Generator (Outline → Write)",
      subtitle: "Creates a structured instruction-manual based on the selected Supabase document. Long-form generation uses section-by-section writing (experiment mode).",
      right: React.createElement(Badge, null, "handbook"),
    }),

    renderDocContextLine(),

    err ? React.createElement(Notice, { variant: "error", title: "Handbook Error" }, err) : null,

    React.createElement(
      "div",
      { style: { marginTop: 10 } },
      React.createElement(Label, null, "Handbook request"),
      React.createElement(
        "textarea",
        {
          value: handbookRequest,
          onChange: (e) => setHandbookRequest(e.target.value),
          disabled: running,
          placeholder: "Describe the handbook you want (derived from the selected document)…",
          style: {
            width: "100%",
            minHeight: 110,
            resize: "vertical",
            padding: 10,
            borderRadius: 10,
            border: "1px solid rgba(255,255,255,0.12)",
            background: "rgba(0,0,0,0.20)",
            color: "inherit",
            fontSize: 13,
            lineHeight: 1.35,
          },
        },
        null
      )
    ),

    React.createElement(
      "div",
      { style: { marginTop: 12 } },
      React.createElement(Label, null, "Handbook controls (optional)"),
      renderParamHelp(),
      React.createElement(
        FieldRow,
        null,
        React.createElement(NumberInput, {
          value: targetWords,
          onChange: (v) => setTargetWords(Number(v || 0)),
          width: 160,
          title: "Target handbook size (words)",
        }),
        React.createElement(NumberInput, {
          value: minSectionWords,
          onChange: (v) => setMinSectionWords(Number(v || 0)),
          width: 170,
          title: "Min section size (words)",
        }),
        React.createElement(NumberInput, {
          value: maxSectionWords,
          onChange: (v) => setMaxSectionWords(Number(v || 0)),
          width: 170,
          title: "Max section size (words)",
        }),
        React.createElement(NumberInput, {
          value: maxSections,
          onChange: (v) => setMaxSections(Number(v || 0)),
          width: 150,
          title: "Max sections (safety cap)",
        })
      )
    ),

    React.createElement(
      Card.Footer,
      null,
      React.createElement(
        Button,
        { onClick: () => runHandbook().catch(() => {}), disabled: running || !activeDocId },
        running ? "Generating…" : "Generate Handbook"
      ),
      React.createElement(
        Button,
        { onClick: () => clearAll(), disabled: running, variant: "ghost" },
        "Clear"
      ),
      React.createElement(
        "div",
        { style: { marginLeft: "auto", fontSize: 12, opacity: 0.85 } },
        "Words so far: ",
        React.createElement(Code, null, String(wordsSoFar))
      )
    ),

    renderDiagnostics(),

    React.createElement(
      "div",
      { style: { marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 } },

      React.createElement(
        "div",
        { style: { minHeight: 280, display: "flex", flexDirection: "column" } },
        React.createElement(Label, null, "Outline"),
        React.createElement(
          "pre",
          {
            style: {
              marginTop: 8,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              padding: 10,
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(0,0,0,0.20)",
              flex: 1,
              overflow: "auto",
              fontSize: 12,
              lineHeight: 1.35,
            },
          },
          outlineText || "(Outline will appear here.)"
        )
      ),

      React.createElement(
        "div",
        { style: { minHeight: 280, display: "flex", flexDirection: "column" } },
        React.createElement(Label, null, "Handbook output"),
        React.createElement(
          "pre",
          {
            ref: outRef,
            style: {
              marginTop: 8,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              padding: 10,
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(0,0,0,0.20)",
              flex: 1,
              overflow: "auto",
              fontSize: 12,
              lineHeight: 1.35,
            },
          },
          outputText || "(Handbook output will appear here.)"
        )
      )
    )
  );
}
