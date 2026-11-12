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

/** Longest announcement: the opening of a passage, not all of it — the reader goes on from the focus. */
const ANNOUNCE_CHARS = 280;

/**
 * A new passage is on screen: focus moves to it (so keyboard and screen-reader users start there,
 * not on a control of the previous page) and a polite live region reads its opening.
 */
export function arriveAt(root: ParentNode): void {
  const passage = root.querySelector<HTMLElement>("tw-passage");
  if (!passage) return;
  passage.tabIndex = -1;
  passage.focus({ preventScroll: true });
  const opening = (passage.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, ANNOUNCE_CHARS);
  announcer().textContent = opening;
}

/** The page's one polite live region, outside #app so redrawing a page never removes it. */
function announcer(): HTMLElement {
  let region = document.getElementById("announcer");
  if (!region) {
    region = document.createElement("div");
    region.id = "announcer";
    region.className = "sr-only";
    region.setAttribute("aria-live", "polite");
    document.body.appendChild(region);
  }
  return region;
}
