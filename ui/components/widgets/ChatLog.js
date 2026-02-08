// ui/components/widgets/ChatLog.js
import { styles } from "../styles.js";

export default function ChatLog({ messages, scrollRef }) {
  function renderBubble(m) {
    const rowStyle = { ...styles.bubbleRow };
    const bubbleStyle = { ...styles.bubble };

    if (m.role === "user") Object.assign(bubbleStyle, styles.bubbleUser);
    if (m.role === "assistant") Object.assign(bubbleStyle, styles.bubbleAssistant);
    if (m.role === "system") Object.assign(bubbleStyle, styles.bubbleSystem);
    if (m.role === "system") rowStyle.justifyContent = "center";

    return React.createElement("div", { key: m.id, style: rowStyle }, React.createElement("div", { style: bubbleStyle }, m.text));
  }

  return React.createElement("div", { style: styles.chatLog, ref: scrollRef }, (messages || []).map(renderBubble));
}
