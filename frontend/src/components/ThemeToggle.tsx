"use client";

import { useEffect, useState } from "react";
import { applyTheme, getStoredTheme, type Theme } from "@/lib/theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(getStoredTheme() ?? "light");
  }, []);

  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    applyTheme(next);
    setTheme(next);
  };

  return (
    <button
      onClick={toggle}
      aria-label={theme === "light" ? "ダークテーマに切り替え" : "ライトテーマに切り替え"}
      style={{
        position: "fixed",
        top: 12,
        right: 12,
        zIndex: 50,
        width: 32,
        height: 32,
        borderRadius: "50%",
        border: "1px solid var(--line-hair)",
        background: "var(--surface-raised)",
        color: "var(--ink)",
        fontSize: 14,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {theme === "light" ? "夜" : "昼"}
    </button>
  );
}
