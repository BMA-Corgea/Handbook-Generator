// ui/components/ui/Code.js
import { styles } from "../styles.js";
export default function Code({ children }) {
  return React.createElement("span", { style: styles.code }, children);
}
