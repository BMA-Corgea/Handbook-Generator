// ui/components/cards/PdfStagingCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import Code from "../ui/Code.js";
import Button from "../ui/Button.js";
import Notice from "../ui/Notice.js";

import PdfUploader from "../widgets/PdfUploader.js";
import PdfRowsTable from "../widgets/PdfRowsTable.js";

import useLocalStorageState from "../hooks/useLocalStorageState.js";
import { LS_KEY_PDF_ROWS } from "../constants.js";
import { fetchJsonOrThrow } from "../api.js";

const { useState } = React;

export default function PdfStagingCard({ apiBase, onLatestUploadJson, onDigestJson, onDigestErr }) {
  const [rows, setRows] = useLocalStorageState(LS_KEY_PDF_ROWS, []);

  const [uploadErr, setUploadErr] = useState("");
  const [uploading, setUploading] = useState(false);

  async function uploadPdf(file, resetInput) {
    setUploadErr("");
    setUploading(true);

    const tempId = crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random()}`;
    const optimistic = {
      id: tempId,
      original_name: file.name,
      saved_name: "",
      bytes: file.size || null,
      timestamp: new Date().toISOString(),
      status: "staged",
      error: "",
      doc_key: "",
      working_dir: "",
      supabase_doc_id: "",
    };

    setRows((prev) => [optimistic].concat(prev));

    try {
      const fd = new FormData();
      fd.append("file", file);

      const parsed = await fetchJsonOrThrow(`${apiBase}/dashboard/upload-pdf`, { method: "POST", body: fd });

      onLatestUploadJson && onLatestUploadJson(JSON.stringify(parsed, null, 2));

      setRows((prev) =>
        prev.map((r) =>
          r.id !== tempId
            ? r
            : {
                ...r,
                original_name: parsed?.original_name || r.original_name,
                saved_name: parsed?.saved_name || r.saved_name,
                bytes: parsed?.bytes ?? r.bytes,
                timestamp: parsed?.timestamp || r.timestamp,
                status: "staged",
                error: "",
              }
        )
      );

      resetInput && resetInput();
    } catch (e) {
      const msg = e?.message || String(e);
      setUploadErr(msg);
      setRows((prev) => prev.map((r) => (r.id === tempId ? { ...r, status: "error", error: msg } : r)));
    } finally {
      setUploading(false);
    }
  }

  function clearHistory() {
    setRows([]);
    setUploadErr("");
    onLatestUploadJson && onLatestUploadJson("");
    onDigestJson && onDigestJson("");
    onDigestErr && onDigestErr("");
  }

  async function digestRow(rowId) {
    const row = (rows || []).find((r) => r.id === rowId);
    if (!row) return;

    if (!row.saved_name) {
      onDigestErr && onDigestErr("Row has no saved_name yet (upload might not have completed).");
      return;
    }

    onDigestErr && onDigestErr("");
    onDigestJson && onDigestJson("");

    setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, status: "digesting", error: "" } : r)));

    try {
      const payload = {
        saved_name: row.saved_name,
        original_name: row.original_name || row.saved_name,
        doc_key: row.doc_key || "",
      };

      const parsed = await fetchJsonOrThrow(`${apiBase}/lightrag/ingest-staged`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      onDigestJson && onDigestJson(JSON.stringify(parsed, null, 2));

      setRows((prev) =>
        prev.map((r) =>
          r.id === rowId
            ? {
                ...r,
                status: "digested",
                error: "",
                doc_key: parsed?.doc_key || r.doc_key,
                working_dir: parsed?.working_dir || r.working_dir,
              }
            : r
        )
      );
    } catch (e) {
      const msg = e?.message || String(e);
      onDigestErr && onDigestErr(msg);
      setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, status: "error", error: msg } : r)));
    }
  }

  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "PDF Staging → Digest",
      subtitle: React.createElement(
        React.Fragment,
        null,
        "Upload stages PDF into ",
        React.createElement(Code, null, "./pdf_imports/"),
        " via ",
        React.createElement(Code, null, "POST /dashboard/upload-pdf"),
        ". Then click ",
        React.createElement(Code, null, "! Digest"),
        " per-row to create ",
        React.createElement(Code, null, "./lightrag_cache/<doc_key>/"),
        "."
      ),
      right: React.createElement(Badge, null, apiBase),
    }),

    uploadErr ? React.createElement(Notice, { variant: "error", title: "Upload Error" }, uploadErr) : null,

    React.createElement(
      Card.Footer,
      null,
      React.createElement(PdfUploader, { busy: uploading, onUpload: uploadPdf }),
      React.createElement(Button, { onClick: clearHistory, disabled: !(rows || []).length }, "Clear List")
    ),

    React.createElement(PdfRowsTable, { rows, onDigest: digestRow })
  );
}
