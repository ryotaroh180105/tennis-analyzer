// テーマ切替（11 §両テーマ必須。13 E': data-themeを設定する箇所がフロントに無く、
// globals.cssのダークトークンが到達不能だった問題の修正）。
// OSのprefers-color-schemeには自動追従しない設計のまま（globals.css既存コメント通り）、
// 明示トグルのみでdata-themeを切り替える。

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "tennis-analyzer:theme";

export function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

// レイアウトの<head>にインラインscriptとして埋め込み、ペイント前にdata-themeを
// 確定させる（FOUC防止）。未設定時はlight固定（既存方針：OS追従しない）。
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var t = window.localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    document.documentElement.setAttribute("data-theme", t === "dark" ? "dark" : "light");
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "light");
  }
})();
`;
