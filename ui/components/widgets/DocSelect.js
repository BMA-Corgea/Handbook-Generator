// ui/components/widgets/DocSelect.js
import { Select } from "../ui/Field.js";

function fmtDocLabel(d) {
  const id = d?.doc_id ? String(d.doc_id) : "";
  const path = d?.file_path ? String(d.file_path) : "";
  const meta = d?.metadata || {};
  const source = meta?.source ? String(meta.source) : "";
  const best = path || source || "";
  if (best) return `${id.slice(0, 8)}… — ${best}`;
  return `${id}`;
}

export default function DocSelect({ docs, value, onChange }) {
  const options = (docs || []).length
    ? [{ value: "", label: "— Select a document —" }].concat((docs || []).map((d) => ({ value: d.doc_id, label: fmtDocLabel(d) })))
    : [{ value: "", label: "No documents found" }];

  return React.createElement(Select, { value: value || "", onChange, options });
}
