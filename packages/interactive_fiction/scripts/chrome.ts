/**
 * Headless Chrome for the scripts that check the reader in a real browser:
 * launch it, and drive one page over the DevTools Protocol with the built-in
 * WebSocket. Needs Google Chrome; set CHROME_PATH if it is not in the usual place.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function chromePath(): string {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ];
  const found = candidates.find((c) => c && existsSync(c));
  if (!found) throw new Error("Google Chrome not found: set CHROME_PATH.");
  return found;
}

export async function waitFor(url: string, what: string): Promise<void> {
  for (let i = 0; i < 80; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // Not up yet.
    }
    await sleep(250);
  }
  throw new Error(`${what} did not start.`);
}

type Reply = { result?: { result?: { value?: unknown }; data?: string } };

/** A minimal DevTools client for the first page of the Chrome on `port`. */
export async function devtools(port: number) {
  const pages = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()) as {
    type: string;
    webSocketDebuggerUrl: string;
  }[];
  const ws = new WebSocket(pages.find((p) => p.type === "page")!.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const pending = new Map<number, (v: Reply) => void>();
  const errors: string[] = [];
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(String(m.data));
    if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text);
    if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") errors.push(JSON.stringify(d.params.args));
    pending.get(d.id)?.(d);
    pending.delete(d.id);
  });
  const send = (method: string, params: object = {}) =>
    new Promise<Reply>((r) => {
      const i = ++id;
      pending.set(i, r);
      ws.send(JSON.stringify({ id: i, method, params }));
    });
  await send("Runtime.enable");
  const ev = async <T>(expression: string): Promise<T> =>
    (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value as T;
  /** A real mouse click (a user gesture), at the centre of the element the expression returns. */
  const click = async (expression: string): Promise<boolean> => {
    const box = await ev<{ x: number; y: number } | null>(`(() => { const e = ${expression}; if (!e) return null;
      e.scrollIntoView({ block: "center" }); const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    if (!box) return false;
    for (const type of ["mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
    }
    return true;
  };
  return { send, ev, click, errors, close: () => ws.close() };
}

export type Devtools = Awaited<ReturnType<typeof devtools>>;

/**
 * Run `work` against a fresh headless Chrome, closed and its profile removed
 * afterwards — also when the script is interrupted. One fixed profile folder
 * per port, emptied before each run, so a run killed outright leaves at most
 * one behind instead of one more each time. `gpu` keeps hardware rendering
 * (the 3D draft's splats do not draw without it).
 */
export async function withChrome<T>(port: number, work: (c: Devtools) => Promise<T>, opts: { gpu?: boolean } = {}): Promise<T> {
  const profile = join(tmpdir(), `if-chrome-${port}`);
  rmSync(profile, { recursive: true, force: true });
  mkdirSync(profile, { recursive: true });
  const chrome: ChildProcess = spawn(
    chromePath(),
    ["--headless=new", ...(opts.gpu ? [] : ["--disable-gpu"]), "--window-size=1400,900", `--remote-debugging-port=${port}`, "--remote-debugging-address=127.0.0.1", `--user-data-dir=${profile}`, "about:blank"],
    { stdio: "ignore" },
  );
  const stop = () => {
    chrome.kill();
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  };
  const onSignal = (signal: NodeJS.Signals) => {
    stop();
    process.exit(signal === "SIGINT" ? 130 : 143);
  };
  process.once("SIGINT", onSignal);
  process.once("SIGTERM", onSignal);
  process.once("exit", () => chrome.kill());
  try {
    await waitFor(`http://127.0.0.1:${port}/json/version`, "Chrome");
    const c = await devtools(port);
    try {
      return await work(c);
    } finally {
      c.close();
    }
  } finally {
    process.off("SIGINT", onSignal);
    process.off("SIGTERM", onSignal);
    const exited = new Promise((r) => chrome.once("exit", r));
    chrome.kill();
    await exited;
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
