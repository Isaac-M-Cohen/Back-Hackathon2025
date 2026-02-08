import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

try {
  const savedTheme = window.localStorage.getItem("easy-theme");
  if (savedTheme) {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const isDark =
      savedTheme === "dark" || (savedTheme === "system" && media.matches);
    document.documentElement.classList.toggle("dark", isDark);
  }
} catch {
  // Ignore theme persistence errors in non-browser contexts.
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
