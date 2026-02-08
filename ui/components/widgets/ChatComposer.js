// ui/components/widgets/ChatComposer.js
import Button from "../ui/Button.js";
import { styles } from "../styles.js";

export default function ChatComposer({ value, onChange, onSend, disabled }) {
  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend && onSend();
    }
  }

  return React.createElement(
    "div",
    { style: styles.composer },
    React.createElement("textarea", {
      style: styles.textarea,
      value: value || "",
      onChange: (e) => onChange && onChange(e.target.value),
      onKeyDown,
      placeholder: "Ask a question… (Enter to send, Shift+Enter for newline)",
    }),
    React.createElement(Button, { onClick: onSend, disabled }, disabled ? "Sending…" : "Send")
  );
}
