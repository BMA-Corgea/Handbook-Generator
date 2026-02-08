// ui/components/widgets/JsonViewer.js
import Pre from "../ui/Pre.js";

export default function JsonViewer({ value, emptyText }) {
  const out = value && String(value).trim().length ? value : (emptyText || "");
  return React.createElement(Pre, null, out);
}
