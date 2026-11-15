/**
 * Keeps coloured text readable. A story colours who is speaking with plain
 * colour names, some too dark for the page behind them; a colour under the
 * WCAG AA contrast of 4.5:1 is moved along its own hue, just far enough, so
 * each voice keeps its colour and can be read.
 */

export type Rgb = [r: number, g: number, b: number];

/** WCAG AA for body text. */
export const AA = 4.5;

function luminance([r, g, b]: Rgb): number {
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** The WCAG contrast ratio of two colours, from 1 to 21. */
export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function toHsl([r, g, b]: Rgb): [number, number, number] {
  const [rn, gn, bn] = [r / 255, g / 255, b / 255];
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === rn ? (gn - bn) / d + (gn < bn ? 6 : 0) : max === gn ? (bn - rn) / d + 2 : (rn - gn) / d + 4;
  return [h * 60, s, l];
}

function fromHsl(h: number, s: number, l: number): Rgb {
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}

/**
 * `colour` as it is when it already reads on `background`; otherwise the nearest colour of the same
 * hue and saturation that reaches `ratio`: lighter on a dark background, darker on a light one.
 */
export function legible(colour: Rgb, background: Rgb, ratio = AA): Rgb {
  if (contrast(colour, background) >= ratio) return colour;
  const [h, s, l] = toHsl(colour);
  const lighten = luminance(background) < 0.18;
  let near = l;
  let far = lighten ? 1 : 0;
  for (let i = 0; i < 20; i++) {
    const mid = (near + far) / 2;
    if (contrast(fromHsl(h, s, mid), background) >= ratio) far = mid;
    else near = mid;
  }
  return fromHsl(h, s, far);
}

const RGBA = /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,/\s]+([\d.]+)(%?))?\s*\)$/;

/** `rgb(1, 2, 3)` or `rgba(1, 2, 3, 0.5)` as the browser computes it, with its alpha from 0 to 1; null for anything else. */
export function parseRgba(css: string): [...Rgb, number] | null {
  const m = RGBA.exec(css.trim());
  if (!m) return null;
  const alpha = m[4] === undefined ? 1 : parseFloat(m[4]) / (m[5] ? 100 : 1);
  return [Number(m[1]), Number(m[2]), Number(m[3]), Math.min(1, alpha)];
}

/** `rgb(1, 2, 3)` or `rgba(1, 2, 3, 0.5)` as the browser computes it; null for anything else, and for a transparent colour. */
export function parseRgb(css: string): Rgb | null {
  const c = parseRgba(css);
  return c && c[3] > 0 ? [c[0], c[1], c[2]] : null;
}

/**
 * The colour behind `el` as the eye sees it: every background from `el` up to the first opaque one,
 * translucent ones laid over what is under them; black, the page's own, at the bottom.
 */
export function backgroundBehind(el: Element): Rgb {
  const layers: [...Rgb, number][] = [];
  for (let node: Element | null = el; node; node = node.parentElement) {
    const painted = parseRgba(getComputedStyle(node).backgroundColor);
    if (!painted || painted[3] === 0) continue;
    layers.push(painted);
    if (painted[3] >= 1) break;
  }
  let seen: Rgb = [0, 0, 0];
  for (const [r, g, b, a] of layers.reverse()) {
    seen = [r * a + seen[0] * (1 - a), g * a + seen[1] * (1 - a), b * a + seen[2] * (1 - a)].map(Math.round) as Rgb;
  }
  return seen;
}

/** Bring every text colour the story sets inline under `root` up to AA against what is behind it. */
export function legibleColours(root: ParentNode): void {
  for (const el of root.querySelectorAll<HTMLElement>("[style*='color']")) {
    if (!el.style.color) continue;
    const colour = parseRgb(getComputedStyle(el).color);
    if (!colour) continue;
    const [r, g, b] = legible(colour, backgroundBehind(el));
    if (r !== colour[0] || g !== colour[1] || b !== colour[2]) el.style.color = `rgb(${r}, ${g}, ${b})`;
  }
}
