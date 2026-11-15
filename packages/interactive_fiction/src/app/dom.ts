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

/** A selector that finds `el` again after the page under it is redrawn; null when it has nothing stable to go by. */
function selectorOf(el: HTMLElement): string | null {
  if (el.id) return `#${CSS.escape(el.id)}`;
  for (const { name, value } of el.attributes) {
    if (name.startsWith("data-")) return `[${name}="${value.replace(/["\\]/g, "\\$&")}"]`;
  }
  return null;
}

/**
 * Show `dialog` as a modal: the browser keeps focus inside it and closes it on Escape; a click on
 * the dimmed page around its sheet closes it too. Closed, it leaves the page and focus returns to
 * whatever opened it, or to its replacement when a setting redrew the page meanwhile.
 */
export function openModal(dialog: HTMLDialogElement, focus?: string): void {
  const opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
  const reopen = opener && selectorOf(opener);
  dialog.addEventListener("click", (ev) => {
    if (ev.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    dialog.remove();
    const back = opener?.isConnected ? opener : reopen ? document.querySelector<HTMLElement>(reopen) : null;
    back?.focus();
  });
  document.body.appendChild(dialog);
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  if (focus) dialog.querySelector<HTMLElement>(focus)?.focus();
}

/**
 * Asks for a second tap within 4 s before a destructive action (embedded viewers block
 * window.confirm()): true on the second tap. While armed the button's visible question is its
 * name, so its `aria-label` steps aside, and the live region reads the question.
 */
export function armed(tool: HTMLElement, question: string): boolean {
  if (tool.dataset.armed) return true;
  const resting = tool.innerHTML;
  const label = tool.getAttribute("aria-label");
  tool.dataset.armed = "1";
  tool.removeAttribute("aria-label");
  tool.textContent = question;
  tool.classList.add("armed");
  announce(question);
  setTimeout(() => {
    if (!tool.isConnected) return;
    delete tool.dataset.armed;
    tool.innerHTML = resting;
    if (label !== null) tool.setAttribute("aria-label", label);
    tool.classList.remove("armed");
  }, 4000);
  return false;
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
  announce((passage.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, ANNOUNCE_CHARS));
}

/** Read `text` out through the page's polite live region. */
export function announce(text: string): void {
  announcer().textContent = text;
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
