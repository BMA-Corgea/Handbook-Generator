// ui/components/ui/Stack.js
export default function Stack({ gap, children }) {
  return React.createElement("div", { style: { display: "flex", flexDirection: "column", gap: gap ?? 12 } }, children);
}
