// ui/components/ui/Badge.js
import { styles } from "../styles.js";

export default function Badge({ children }) {
  return React.createElement("div", { style: styles.badge }, children);
}
