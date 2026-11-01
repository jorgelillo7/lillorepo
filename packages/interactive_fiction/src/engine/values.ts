/** Harlowe values and the operations the supported subset needs. */

import type { Expr } from "./expr.ts";

export interface CodeHook {
  kind: "hook";
  src: string;
}

export interface Lambda {
  kind: "lambda";
  temp: string;
  where?: Expr;
}

export interface Colour {
  kind: "colour";
  css: string;
}

export type Value = boolean | number | string | Value[] | CodeHook | Lambda | Colour;

export class StoryError extends Error {}

export function isHook(v: Value): v is CodeHook {
  return typeof v === "object" && !Array.isArray(v) && v.kind === "hook";
}

function typeName(v: Value): string {
  if (Array.isArray(v)) return "array";
  if (typeof v === "object") return v.kind;
  return typeof v;
}

export function equals(a: Value, b: Value): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => equals(x, b[i]));
  }
  if (typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b)) {
    return JSON.stringify(a) === JSON.stringify(b);
  }
  return a === b;
}

export function add(a: Value, b: Value): Value {
  if (Array.isArray(a) && Array.isArray(b)) return [...a, ...b];
  if (typeof a === "number" && typeof b === "number") return a + b;
  if (typeof a === "string" && typeof b === "string") return a + b;
  throw new StoryError(`Cannot add ${typeName(a)} and ${typeName(b)}.`);
}

export function num(v: Value, op: string): number {
  if (typeof v !== "number") throw new StoryError(`"${op}" needs numbers, got ${typeName(v)}.`);
  return v;
}

export function bool(v: Value, op: string): boolean {
  if (typeof v !== "boolean") throw new StoryError(`"${op}" needs true/false, got ${typeName(v)}.`);
  return v;
}

export function isIn(item: Value, container: Value): boolean {
  if (Array.isArray(container)) return container.some((x) => equals(x, item));
  if (typeof container === "string" && typeof item === "string") return container.includes(item);
  throw new StoryError(`"is in" needs an array or a string, got ${typeName(container)}.`);
}

/** How a value prints in prose. */
export function toText(v: Value): string {
  if (Array.isArray(v)) return v.map(toText).join(",");
  if (typeof v === "object") return v.kind === "hook" ? v.src : "";
  return String(v);
}

/** Harlowe's built-in colour names. */
export const COLOURS: Record<string, string> = {
  red: "#e61919",
  orange: "#e68019",
  yellow: "#e5e619",
  lime: "#80e619",
  green: "#19e619",
  aqua: "#19e5e6",
  cyan: "#19e5e6",
  blue: "#197fe6",
  navy: "#1919e6",
  purple: "#7f19e6",
  fuchsia: "#e619e5",
  magenta: "#e619e5",
  white: "#ffffff",
  black: "#000000",
  grey: "#888888",
  gray: "#888888",
};
