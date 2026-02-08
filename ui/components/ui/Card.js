// ui/components/ui/Card.js
import { styles } from "../styles.js";

export default function Card({ children }) {
  return React.createElement("div", { style: styles.card }, children);
}

Card.Header = function CardHeader({ title, subtitle, right }) {
  return React.createElement(
    "div",
    { style: styles.headerRow },
    React.createElement(
      "div",
      null,
      React.createElement("div", { style: styles.title }, title),
      subtitle ? React.createElement("div", { style: styles.subtitle }, subtitle) : null
    ),
    right ? right : null
  );
};

Card.Body = function CardBody({ children }) {
  return React.createElement("div", null, children);
};

Card.Footer = function CardFooter({ children }) {
  return React.createElement("div", { style: styles.actions }, children);
};
