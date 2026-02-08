// ui/components/ui/Table.js
import { styles } from "../styles.js";

export default function Table({ columns, rows, rowKey }) {
  return React.createElement(
    "div",
    { style: styles.tableWrap },
    React.createElement(
      "table",
      { style: styles.table },
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          null,
          (columns || []).map((c) => React.createElement("th", { key: c.key, style: styles.th }, c.title))
        )
      ),
      React.createElement(
        "tbody",
        null,
        (rows || []).map((r, idx) =>
          React.createElement(
            "tr",
            { key: rowKey ? rowKey(r) : String(idx) },
            (columns || []).map((c) =>
              React.createElement("td", { key: c.key, style: c.tdStyle ? { ...styles.td, ...c.tdStyle } : styles.td }, c.render(r, idx))
            )
          )
        )
      )
    )
  );
}
