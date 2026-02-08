// ui/components/widgets/PdfUploader.js
import Button from "../ui/Button.js";

const { useState } = React;

export default function PdfUploader({ busy, onUpload }) {
  const [file, setFile] = useState(null);

  function resetInput() {
    setFile(null);
    const el = document.getElementById("pdf-file-input");
    if (el) el.value = "";
  }

  async function doUpload() {
    if (!file || busy) return;
    await onUpload(file, resetInput);
  }

  return React.createElement(
    React.Fragment,
    null,
    React.createElement("input", {
      id: "pdf-file-input",
      type: "file",
      accept: "application/pdf",
      onChange: (e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null),
    }),
    React.createElement(Button, { disabled: busy || !file, onClick: doUpload }, busy ? "Uploading…" : "Upload PDF")
  );
}
