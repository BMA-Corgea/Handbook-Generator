// ui/components/ui/Field.js
import { styles } from "../styles.js";

export function FieldRow({ children }) {
  return React.createElement("div", { style: { display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" } }, children);
}

export function Label({ children }) {
  return React.createElement("div", { style: { fontSize: 12, opacity: 0.75, fontWeight: 800, letterSpacing: 0.2 } }, children);
}

export function TextInput({ value, onChange, placeholder, width, title }) {
  return React.createElement("input", {
    title,
    style: { ...styles.input, ...(width ? { width } : {}) },
    value: value ?? "",
    placeholder: placeholder || "",
    onChange: (e) => onChange && onChange(e.target.value),
  });
}

export function NumberInput({ value, onChange, placeholder, width, title }) {
  return React.createElement("input", {
    type: "number",
    title,
    style: { ...styles.input, ...(width ? { width } : {}) },
    value: value ?? "",
    placeholder: placeholder || "",
    onChange: (e) => onChange && onChange(e.target.value),
  });
}

export function Select({ value, onChange, options, title }) {
  return React.createElement(
    "select",
    { title, style: styles.select, value: value ?? "", onChange: (e) => onChange && onChange(e.target.value) },
    (options || []).map((opt) => React.createElement("option", { key: opt.value, value: opt.value }, opt.label))
  );
}

export function Checkbox({ checked, onChange, label }) {
  return React.createElement(
    "label",
    { style: styles.checkboxRow },
    React.createElement("input", { type: "checkbox", checked: !!checked, onChange: (e) => onChange && onChange(e.target.checked) }),
    React.createElement("span", null, label || "")
  );
}
