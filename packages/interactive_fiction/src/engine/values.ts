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

/** A `(dm:)`: string keys in insertion order. Treated as immutable; changing a key builds a new one. */
export interface DataMap {
  kind: "datamap";
  entries: Record<string, Value>;
}

export type Value = boolean | number | string | Value[] | CodeHook | Lambda | Colour | DataMap;

export class StoryError extends Error {}

export function isHook(v: Value): v is CodeHook {
  return typeof v === "object" && !Array.isArray(v) && v.kind === "hook";
}

export function isDataMap(v: Value): v is DataMap {
  return typeof v === "object" && !Array.isArray(v) && v.kind === "datamap";
}

/** A `(dm:)` from its alternating key, value arguments. */
export function dataMap(args: Value[]): DataMap {
  if (args.length % 2 === 1) throw new StoryError("(dm:) needs pairs of key, value.");
  const entries: Record<string, Value> = {};
  for (let i = 0; i < args.length; i += 2) entries[mapKey(args[i])] = args[i + 1];
  return { kind: "datamap", entries };
}

function mapKey(k: Value): string {
  if (typeof k === "string") return k;
  if (typeof k === "number") return String(k);
  throw new StoryError(`A datamap key must be a string or a number, got ${typeName(k)}.`);
}

/** `container's key`: a datamap's value, or an array's item counted from 1 (negative from the end). */
export function property(container: Value, key: Value): Value {
  if (isDataMap(container)) {
    const v = container.entries[mapKey(key)];
    if (v === undefined) throw new StoryError(`The datamap has no "${toText(key)}".`);
    return v;
  }
  if (Array.isArray(container) && typeof key === "number") {
    const v = container[key < 0 ? container.length + key : key - 1];
    if (v === undefined) throw new StoryError(`The array has no item ${key}.`);
    return v;
  }
  throw new StoryError(`Cannot read "${toText(key)}" of ${typeName(container)}.`);
}

/** `container` with `key` set to `v`, as a new value; the original is left untouched. */
export function withProperty(container: Value, key: Value, v: Value): Value {
  if (isDataMap(container)) return { kind: "datamap", entries: { ...container.entries, [mapKey(key)]: v } };
  if (Array.isArray(container) && typeof key === "number") {
    const i = key < 0 ? container.length + key : key - 1;
    if (i < 0 || i >= container.length) throw new StoryError(`The array has no item ${key}.`);
    return container.map((x, j) => (j === i ? v : x));
  }
  throw new StoryError(`Cannot set "${toText(key)}" of ${typeName(container)}.`);
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
  if (isDataMap(a) && isDataMap(b)) {
    const keys = Object.keys(a.entries);
    return keys.length === Object.keys(b.entries).length && keys.every((k) => k in b.entries && equals(a.entries[k], b.entries[k]));
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
  // Harlowe's `$map contains "key"` asks about the keys.
  if (isDataMap(container) && (typeof item === "string" || typeof item === "number")) return mapKey(item) in container.entries;
  throw new StoryError(`"is in" needs an array or a string, got ${typeName(container)}.`);
}

/** How a value prints in prose. */
export function toText(v: Value): string {
  if (Array.isArray(v)) return v.map(toText).join(",");
  if (isDataMap(v)) return Object.entries(v.entries).map(([k, x]) => `${k}: ${toText(x)}`).join(", ");
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
