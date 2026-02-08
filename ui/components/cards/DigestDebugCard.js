// ui/components/cards/DigestDebugCard.js
import Card from "../ui/Card.js";
import Badge from "../ui/Badge.js";
import JsonViewer from "../widgets/JsonViewer.js";
import Notice from "../ui/Notice.js";

export default function DigestDebugCard({ latestUploadJson, digestJson, digestErr }) {
  return React.createElement(
    Card,
    null,
    React.createElement(Card.Header, {
      title: "Debug Output",
      subtitle: "Latest upload JSON + most recent digest response.",
      right: React.createElement(Badge, null, "debug"),
    }),

    latestUploadJson
      ? React.createElement(
          React.Fragment,
          null,
          React.createElement("div", { style: { fontWeight: 900, marginTop: 10 } }, "Most Recent Upload JSON"),
          React.createElement(JsonViewer, { value: latestUploadJson })
        )
      : null,

    digestErr ? React.createElement(Notice, { variant: "error", title: "Digest Error" }, digestErr) : null,

    React.createElement("div", { style: { fontWeight: 900, marginTop: 10 } }, "Digest JSON"),
    React.createElement(JsonViewer, { value: digestJson, emptyText: "Click “Digest” on a staged row to see output here." })
  );
}
