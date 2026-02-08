// ui/dashboard.js
// No JSX. No build step. Works with React + ReactDOM via CDN.

import { getApiBase } from "./components/api.js";
import { styles } from "./components/styles.js";

import Stack from "./components/ui/Stack.js";
import PdfStagingCard from "./components/cards/PdfStagingCard.js";
import DigestDebugCard from "./components/cards/DigestDebugCard.js";
import SupabaseUploadCard from "./components/cards/SupabaseUploadCard.js";
import SupabaseDocsCard from "./components/cards/SupabaseDocsCard.js";
import GrokChatCard from "./components/cards/GrokChatCard.js";
import LongWriteCard from "./components/cards/LongWriteCard.js";

const { useMemo, useState } = React;

export default function Dashboard() {
  const apiBase = useMemo(() => getApiBase(), []);

  // Shared “debug outputs”
  const [latestUploadJson, setLatestUploadJson] = useState("");
  const [digestJson, setDigestJson] = useState("");
  const [digestErr, setDigestErr] = useState("");

  return React.createElement(
    "div",
    { style: styles.page },
    React.createElement(
      "div",
      { style: styles.container },
      React.createElement(
        Stack,
        { gap: 16 },

        React.createElement(PdfStagingCard, {
          apiBase,
          onLatestUploadJson: setLatestUploadJson,
          onDigestJson: setDigestJson,
          onDigestErr: setDigestErr,
        }),

        React.createElement(DigestDebugCard, {
          latestUploadJson,
          digestJson,
          digestErr,
        }),

        React.createElement(SupabaseUploadCard, { apiBase }),

        React.createElement(SupabaseDocsCard, { apiBase }),

        React.createElement(GrokChatCard, { apiBase }),

        React.createElement(LongWriteCard, { apiBase })
      )
    )
  );
}
