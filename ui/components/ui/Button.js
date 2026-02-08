// ui/components/ui/Button.js
import { styles } from "../styles.js";

export default function Button({ children, onClick, disabled, title, style }) {
  return React.createElement(
    "button",
    {
      title,
      onClick,
      disabled: !!disabled,
      style: { ...styles.button, ...(disabled ? styles.buttonDisabled : {}), ...(style || {}) },
    },
    children
  );
}

export function TinyButton({ children, onClick, disabled, title, style }) {
  return React.createElement(
    "button",
    {
      title,
      onClick,
      disabled: !!disabled,
      style: { ...styles.tinyBtn, ...(disabled ? styles.buttonDisabled : {}), ...(style || {}) },
    },
    children
  );
}
