// ui/components/ui/Pre.js
import { styles } from "../styles.js";
export default function Pre({ children }) {
  return React.createElement("pre", { style: styles.pre }, children || "");
}
