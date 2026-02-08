// ui/components/cards/SupabaseUploadCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Button from "../ui/Button.js";
import Notice from "../ui/Notice.js";
import JsonViewer from "../widgets/JsonViewer.js";

import useLocalStorageState from "../hooks/useLocalStorageState.js";
import { LS_KEY_PDF_ROWS } from "../constants.js";
import { fetchJsonOrThrow } from "../api.js";

import { Checkbox, NumberInput, Select } from "../ui/Field.js";

const { useEffect, useMemo, useState } = React;

export default function SupabaseUploadCard({ apiBase }) {
  const [rows, setRows] = useLocalStorageState(LS_KEY_PDF_ROWS, []);
  const [raw, setRaw] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const [batchSize, setBatchSize] = useState(200);
  const [storeDocText, setStoreDocText] = useState(true);

  const digestedRows = useMemo(
    () => (rows || []).filter((r) => r.status === "digested" || r.status === "uploading" || r.status === "uploaded"),
    [rows]
  );

  const [selectedRowId, setSelectedRowId] = useState("");

  useEffect(() => {
    if (selectedRowId && !digestedRows.find((r) => r.id === selectedRowId)) setSelectedRowId("");
    if (!selectedRowId && digestedRows.length) setSelectedRowId(digestedRows[0].id);
  }, [rows]); // keep as rows (not digestedRows) so changes propagate correctly

  const rowOptions = digestedRows.length
    ? [{ value: "", label: "— Select a digested PDF —" }].concat(
        digestedRows.map((r) => ({
          value: r.id,
          label: `${(r.doc_key || "").slice(0, 24) || "(no doc_key)"} — ${r.original_name || r.saved_name || ""}`,
        }))
      )
    : [{ value: "", label: "No digested PDFs found (digest one first)" }];

  function refreshDropdown() {
    // Force a fresh read from localStorage so the dropdown updates even if
    // another component/tab modified the value.
    try {
      const rawLs = localStorage.getItem(LS_KEY_PDF_ROWS);
      if (!rawLs) {
        setRows([]);
        return;
      }
      const parsed = JSON.parse(rawLs);
      if (!Array.isArray(parsed)) return;

      setRows(parsed);

      // Optional nicety: if current selection disappeared, auto-select most recent digested
      const dig = parsed.filter((r) => r.status === "digested" || r.status === "uploading" || r.status === "uploaded");
      if (dig.length && (!selectedRowId || !dig.find((r) => r.id === selectedRowId))) {
        setSelectedRowId(dig[0].id);
      }
    } catch (e) {
      const msg = e?.message || String(e);
      setErr(`Failed to refresh dropdown: ${msg}`);
    }
  }

  async function uploadSelected() {
    const row = (rows || []).find((r) => r.id === selectedRowId);
    if (!row) return setErr("Pick a digested document first.");
    if (!row.working_dir) return setErr("Selected row has no working_dir. Digest it first.");

    setLoading(true);
    setErr("");
    setRaw("");

    setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, status: "uploading", error: "" } : r)));

    try {
      const qs = new URLSearchParams({
        working_dir: String(row.working_dir),
        batch_size: String(Number(batchSize || 200)),
        store_doc_text: storeDocText ? "true" : "false",
      });

      const parsed = await fetchJsonOrThrow(`${apiBase}/lightrag/sync-to-supabase?${qs.toString()}`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      setRaw(JSON.stringify(parsed, null, 2));

      setRows((prev) =>
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
    } catch (e) {
      const msg = e?.message || String(e);
      setErr(msg);
      setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, status: "error", error: msg } : r)));
    } finally {
      setLoading(false);
    }
  }

  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "Sync Digested Doc → Supabase",
      subtitle: "Uploads LightRAG artifacts for the selected digested PDF.",
      right: React.createElement(Badge, null, "supabase"),
    }),

    err ? React.createElement(Notice, { variant: "error", title: "Upload Error" }, err) : null,

    React.createElement(
      Card.Footer,
      null,
      // NEW: refresh button for dropdown
      React.createElement(Button, { onClick: refreshDropdown, disabled: loading }, "Refresh"),
      React.createElement(Select, { value: selectedRowId, onChange: setSelectedRowId, options: rowOptions }),
      React.createElement(NumberInput, {
        value: batchSize,
        onChange: (v) => setBatchSize(Number(v || 0)),
        width: 140,
        title: "batch_size",
      }),
      React.createElement(Checkbox, { checked: storeDocText, onChange: setStoreDocText, label: "store_doc_text" }),
      React.createElement(Button, { onClick: uploadSelected, disabled: loading || !selectedRowId }, loading ? "Uploading…" : "Upload to Supabase")
    ),

    React.createElement(JsonViewer, { value: raw, emptyText: "Upload output will appear here." })
  );
}
