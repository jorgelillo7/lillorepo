/**
 * Every Harlowe macro the reader supports, with its kind and its other names.
 * Adding a macro starts here: the parser normalizes aliases to these names,
 * the validator accepts exactly these, and the runtime implements them.
 */

export type MacroKind = "changer" | "command" | "value";

const MACROS: Record<string, { kind: MacroKind; aliases?: string[] }> = {
  // Changers take a hook: [ … ] right after them.
  if: { kind: "changer" },
  unless: { kind: "changer" },
  else: { kind: "changer" },
  "else-if": { kind: "changer", aliases: ["elseif"] },
  for: { kind: "changer", aliases: ["loop"] },
  link: { kind: "changer" },
  "text-colour": { kind: "changer", aliases: ["text-color", "colour", "color"] },
  // Commands act or print.
  set: { kind: "command" },
  display: { kind: "command" },
  goto: { kind: "command" },
  print: { kind: "command" },
  input: { kind: "command" },
  // Values compute something.
  a: { kind: "value", aliases: ["array"] },
  str: { kind: "value", aliases: ["string"] },
  uppercase: { kind: "value" },
  cond: { kind: "value" },
  find: { kind: "value" },
};

const BY_NAME = new Map<string, string>();
for (const [name, m] of Object.entries(MACROS)) {
  BY_NAME.set(name, name);
  for (const alias of m.aliases ?? []) BY_NAME.set(alias, name);
}

/** The macro's own name for any of its names; an unsupported name comes back unchanged. */
export function canonical(name: string): string {
  return BY_NAME.get(name.toLowerCase()) ?? name.toLowerCase();
}

/** Its kind, or undefined when the reader does not support it. */
export function kindOf(name: string): MacroKind | undefined {
  return MACROS[canonical(name)]?.kind;
}
