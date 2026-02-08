// ui/components/ui/Notice.js
import { styles } from "../styles.js";

export default function Notice({ variant, title, children }) {
  const boxStyle = variant === "error" ? styles.errorBox : styles.notice;
  return React.createElement(
    "div",
    { style: boxStyle },
    title ? React.createElement("div", { style: { fontWeight: 900, marginBottom: 6 } }, title) : null,
    React.createElement("div", null, children)
  );
}
