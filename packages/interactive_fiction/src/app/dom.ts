/** Small DOM helpers shared by the app's screens. */

export const app = document.getElementById("app")!;

export function el(html: string): HTMLElement {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild as HTMLElement;
}

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Chapter titles come as "Capitulo 2 - ¿Qué es este lugar?"; lists show the part after the dash. */
export function shortTitle(title: string): string {
  const m = /^\s*cap[ií]tulo\s+\d+\s*[-–—:]\s*(.+)$/i.exec(title);
  return m ? m[1].trim() : title;
}

export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

/** The current chapter's own stylesheet; empty outside a chapter. */
export function setStoryCss(css: string): void {
  let tag = document.getElementById("story-css");
  if (!tag) {
    tag = document.createElement("style");
    tag.id = "story-css";
    document.head.appendChild(tag);
  }
  tag.textContent = css;
}

export function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
