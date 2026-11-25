import { describe, expect, test } from "vitest";
// @ts-expect-error: a plain browser module without types
import { nameMatches } from "../web/match.js";

describe("searching gifts by name", () => {
  test("ignores case and accents, in both directions", () => {
    expect(nameMatches("Camión de bomberos", "camion")).toBe(true);
    expect(nameMatches("Camion de bomberos", "CAMIÓN")).toBe(true);
  });

  test("every word must appear, in any order", () => {
    expect(nameMatches("Lego coche de policía", "policia lego")).toBe(true);
    expect(nameMatches("Lego coche de policía", "lego tren")).toBe(false);
  });

  test("an empty search matches everything", () => {
    expect(nameMatches("Puzle", "")).toBe(true);
    expect(nameMatches("Puzle", "   ")).toBe(true);
  });
});
