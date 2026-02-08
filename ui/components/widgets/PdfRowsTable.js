// ui/components/widgets/PdfRowsTable.js
import Table from "../ui/Table.js";
import Code from "../ui/Code.js";
import { TinyButton } from "../ui/Button.js";
import { styles } from "../styles.js";

function statusIcon(status) {
  if (status === "uploaded") return "✓";
  if (status === "error") return "X";
  return "!";
}

export default function PdfRowsTable({ rows, onDigest }) {
  if (!rows || !rows.length) {
    return React.createElement("div", { style: { marginTop: 12, opacity: 0.75, fontSize: 13 } }, "No PDFs uploaded yet.");
  }

  const columns = [
    {
      key: "status",
      title: "Status",
      tdStyle: styles.statusCell,
      render: (r) => {
        const icon = statusIcon(r.status);
        if (r.status === "staged") {
          return React.createElement(TinyButton, { disabled: !r.saved_name, onClick: () => onDigest(r.id), title: "Digest into LightRAG" }, `${icon} Digest`);
        }
        if (r.status === "digested") return React.createElement("span", null, `${icon} Ready`);
        if (r.status === "uploading") return React.createElement("span", null, `… Uploading`);
        if (r.status === "digesting") return React.createElement("span", null, `… Digesting`);
        if (r.status === "uploaded") return React.createElement("span", null, `${icon} Done`);
        if (r.status === "error") {
          return React.createElement(TinyButton, { disabled: !r.saved_name, onClick: () => onDigest(r.id), title: r.error ? `Error: ${r.error}` : "Retry digest" }, `${icon} Retry`);
        }
        return React.createElement("span", null, icon);
      },
    },
    { key: "original", title: "Original", render: (r) => r.original_name || "" },
    { key: "saved", title: "Saved", render: (r) => (r.saved_name ? r.saved_name : React.createElement("span", { style: styles.smallMuted }, "—")) },
    { key: "doc_key", title: "Doc Key", render: (r) => (r.doc_key ? React.createElement(Code, null, r.doc_key) : React.createElement("span", { style: styles.smallMuted }, "—")) },
    { key: "bytes", title: "Bytes", render: (r) => (typeof r.bytes === "number" ? String(r.bytes) : React.createElement("span", { style: styles.smallMuted }, "—")) },
    { key: "ts", title: "Timestamp", render: (r) => r.timestamp || "" },
  ];

  return React.createElement(Table, { columns, rows, rowKey: (r) => r.id });
}
