// Entry point: global styles (design tokens first) and the React root.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/theme.css";
import "./styles/index.css";
import App from "./App.jsx";

// Attach the React app to the #root element in index.html.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
