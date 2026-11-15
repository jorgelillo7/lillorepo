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

/**
 * Show `dialog` as a modal: the browser keeps focus inside it and closes it on Escape; a click on
 * the dimmed page around its sheet closes it too. Closed, it leaves the page and focus returns to
 * whatever opened it.
 */
export function openModal(dialog: HTMLDialogElement, focus?: string): void {
  const opener = document.activeElement as HTMLElement | null;
  dialog.addEventListener("click", (ev) => {
    if (ev.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus();
  });
  document.body.appendChild(dialog);
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  if (focus) dialog.querySelector<HTMLElement>(focus)?.focus();
}

/** 1 → I, 4 → IV, 12 → XII: how a book numbers its chapters. */
export function roman(n: number): string {
  const steps: [number, string][] = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let out = "";
  for (const [value, mark] of steps) {
    while (n >= value) {
      out += mark;
      n -= value;
    }
  }
  return out;
}

/**
 * A little air after each line of the passage: every line of the story's source is a paragraph or a
 * line of dialogue, separated only by a line break, and a browser gives a `<br>` no height to style.
 * An empty spacer goes after each top-level break; the text is untouched.
 */
export function paragraphGaps(passage: HTMLElement): void {
  for (const br of passage.querySelectorAll(":scope > br, :scope > tw-seg > br")) {
    if (br.nextElementSibling?.classList.contains("par-gap")) continue;
    const gap = document.createElement("span");
    gap.className = "par-gap";
    gap.setAttribute("aria-hidden", "true");
    br.after(gap);
  }
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
