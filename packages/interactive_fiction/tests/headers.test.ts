import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

const root = new URL("..", import.meta.url).pathname;
const read = (path: string) => readFileSync(join(root, path), "utf8");

/** The headers of the `/*` block of public/_headers, by lower-cased name. */
function headers(): Map<string, string> {
  const found = new Map<string, string>();
  let inBlock = false;
  for (const line of read("public/_headers").split("\n")) {
    if (line.startsWith("#") || !line.trim()) continue;
    if (!line.startsWith(" ")) {
      inBlock = line.trim() === "/*";
      continue;
    }
    if (!inBlock) continue;
    const at = line.indexOf(":");
    found.set(line.slice(0, at).trim().toLowerCase(), line.slice(at + 1).trim());
  }
  return found;
}

function csp(): Map<string, string[]> {
  const policy = new Map<string, string[]>();
  for (const part of headers().get("content-security-policy")!.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) policy.set(name, sources);
  }
  return policy;
}

function files(dir: string, extension: string): string[] {
  return readdirSync(join(root, dir)).flatMap((name) => {
    const path = `${dir}/${name}`;
    return statSync(join(root, path)).isDirectory() ? files(path, extension) : path.endsWith(extension) ? [path] : [];
  });
}

describe("response headers", () => {
  test("every response forbids framing, sniffing and referrer leaks, and uses HTTPS", () => {
    const sent = headers();
    expect(sent.get("x-frame-options")).toBe("DENY");
    expect(sent.get("x-content-type-options")).toBe("nosniff");
    expect(sent.get("referrer-policy")).toBe("same-origin");
    expect(sent.get("strict-transport-security")).toMatch(/^max-age=\d{7,}$/);
    expect(csp().get("frame-ancestors")).toEqual(["'none'"]);
  });

  test("the policy denies by default and allows only this origin and the favicon's data: URL", () => {
    const policy = csp();
    expect(policy.get("default-src")).toEqual(["'none'"]);
    expect(policy.get("script-src")).toEqual(["'self'"]);
    expect(policy.get("connect-src")).toEqual(["'self'"]);
    expect(policy.get("img-src")).toEqual(["'self'", "data:"]);
    for (const directive of ["object-src", "base-uri", "form-action"]) {
      expect(policy.get(directive)).toEqual(["'none'"]);
    }
    for (const sources of policy.values()) {
      expect(sources.join(" ")).not.toMatch(/https?:|\*|unsafe-eval/);
    }
  });

  test("the powerful browser features the reader never uses are denied", () => {
    const denied = headers().get("permissions-policy")!;
    for (const feature of ["camera", "microphone", "geolocation", "payment", "usb"]) {
      expect(denied).toContain(`${feature}=()`);
    }
  });

  test("the source loads nothing the policy forbids: no inline script, no remote host, no eval", () => {
    const page = read("index.html");
    const scripts = [...page.matchAll(/<script\b[^>]*>/g)].map((match) => match[0]);
    expect(scripts.length).toBeGreaterThan(0);
    for (const tag of scripts) expect(tag).toMatch(/\ssrc="[^"h][^"]*"/);
    expect(page).not.toMatch(/<script\b(?![^>]*\ssrc=)[^>]*>\s*[^<\s]/);
    expect(page).not.toMatch(/\son\w+\s*=/);
    expect(page).not.toMatch(/(?:src|href)="https?:/);

    for (const path of files("src", ".ts")) {
      const code = read(path);
      expect(code, path).not.toMatch(/\bnew Function\(|(?<![.\w])(?<!private )eval\(|\bimportScripts\(|\b(?:window|globalThis)\.eval\b/);
      expect(code, path).not.toMatch(/\b(?:fetch|import)\(\s*["'`]https?:/);
      expect(code, path).not.toMatch(/\bnew (?:Worker|WebSocket|EventSource)\(/);
    }
    for (const path of files("src", ".css")) {
      const css = read(path);
      expect(css, path).not.toMatch(/@import|url\(\s*["']?(?:https?:|\/\/)/);
    }
  });
});
