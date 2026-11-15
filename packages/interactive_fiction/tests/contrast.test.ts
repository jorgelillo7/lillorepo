// @vitest-environment happy-dom
import { describe, expect, test } from "vitest";
import { AA, contrast, legible, legibleColours, parseRgb, type Rgb } from "../src/app/contrast.ts";

const BLACK: Rgb = [0, 0, 0];
const PAPER: Rgb = [243, 232, 201];
const NAVY: Rgb = [0, 0, 128];
const PURPLE: Rgb = [128, 0, 128];

/** Hue in degrees. */
function hue([r, g, b]: Rgb): number {
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("coloured text stays readable", () => {
  test("the contrast ratio follows WCAG", () => {
    expect(contrast([255, 255, 255], BLACK)).toBeCloseTo(21, 5);
    expect(contrast(NAVY, BLACK)).toBeCloseTo(1.3, 1);
    expect(contrast(PURPLE, BLACK)).toBeCloseTo(2.2, 1);
  });

  test("a colour too dark for a dark page is lightened to AA along its own hue", () => {
    for (const colour of [NAVY, PURPLE]) {
      const fixed = legible(colour, BLACK);
      expect(contrast(fixed, BLACK)).toBeGreaterThanOrEqual(AA);
      expect(contrast(fixed, BLACK)).toBeLessThan(AA + 0.4);
      expect(Math.abs(hue(fixed) - hue(colour))).toBeLessThan(3);
    }
  });

  test("a colour that already reads is left exactly as the story set it", () => {
    expect(legible([255, 0, 0], BLACK)).toEqual([255, 0, 0]);
    expect(legible([255, 255, 0], BLACK)).toEqual([255, 255, 0]);
    expect(legible(NAVY, PAPER)).toEqual(NAVY);
  });

  test("a colour too light for a light page is darkened instead", () => {
    const fixed = legible([255, 255, 0], PAPER);
    expect(contrast(fixed, PAPER)).toBeGreaterThanOrEqual(AA);
  });

  test("computed colours are read, transparent ones ignored", () => {
    expect(parseRgb("rgb(0, 0, 128)")).toEqual(NAVY);
    expect(parseRgb("rgba(0, 0, 128, 0.5)")).toEqual(NAVY);
    expect(parseRgb("rgba(0, 0, 0, 0)")).toBeNull();
    expect(parseRgb("navy")).toBeNull();
  });

  test("on the page, only inline colours under AA change, against the background behind them", () => {
    const root = document.createElement("div");
    root.innerHTML =
      `<tw-hook id="dark" style="color: rgb(0, 0, 128)">A:</tw-hook><tw-hook id="fine" style="color: rgb(255, 255, 0)">B:</tw-hook>` +
      `<div style="background-color: rgb(243, 232, 201)"><tw-hook id="paper" style="color: rgb(0, 0, 128)">C:</tw-hook></div>`;
    document.body.replaceChildren(root);
    legibleColours(root);
    const colour = (id: string) => parseRgb(root.querySelector<HTMLElement>(`#${id}`)!.style.color)!;
    expect(contrast(colour("dark"), BLACK)).toBeGreaterThanOrEqual(AA);
    expect(colour("fine")).toEqual([255, 255, 0]);
    expect(colour("paper")).toEqual(NAVY);
  });
});
