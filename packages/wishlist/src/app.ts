// What the gift list Worker does; src/worker.ts only hands requests here, because a
// Worker module may export nothing but its handlers. The list page is public: anyone with the address can claim a
// gift, mark it bought or let it go. Who claimed it is kept by a random token in an
// HttpOnly cookie, so only that browser can change its own claim. Names are optional
// and only /admin, behind Basic auth, ever shows them.

import list from "../gifts.json";

export interface Statement {
  bind(...values: unknown[]): Statement;
  run(): Promise<{ meta: { changes: number } }>;
  all<T>(): Promise<{ results: T[] }>;
}

export interface Database {
  prepare(sql: string): Statement;
}

export interface Env {
  DB: Database;
  ASSETS: { fetch(request: Request): Promise<Response> };
  ADMIN_USER?: string;
  ADMIN_PASSWORD?: string;
}

interface Claim {
  gift_id: string;
  name: string | null;
  token_hash: string;
  reserved_at: string;
  bought_at: string | null;
}

export const NAME_LIMIT = 40;
const GIFT_IDS = new Set(list.gifts.map((gift) => gift.id));
const COOKIE = "wl";
// 400 days, the longest a browser keeps a cookie. Claims are made in November and
// bought in December, so the token has to outlive Safari's 7-day limit on storage
// that scripts write.
const COOKIE_AGE = 400 * 24 * 60 * 60;
const CHALLENGE = 'Basic realm="wishlist-admin", charset="UTF-8"';
const NO_STORE = { "Cache-Control": "no-store", "X-Robots-Tag": "noindex" };

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...NO_STORE, ...headers },
  });
}

const notFound = () => new Response("No encontrado.\n", { status: 404, headers: NO_STORE });

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Compare two strings in constant time, by their SHA-256 digests. */
async function sameText(given: string, expected: string): Promise<boolean> {
  const [a, b] = await Promise.all([sha256(given), sha256(expected)]);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

/** True when the request carries the admin's Basic credentials; false while unset. */
export async function isAdmin(request: Request, env: Env): Promise<boolean> {
  if (!env.ADMIN_USER || !env.ADMIN_PASSWORD) return false;
  const match = (request.headers.get("Authorization") ?? "").match(/^Basic ([A-Za-z0-9+/=]+)$/);
  if (!match) return false;
  let decoded: string;
  try {
    decoded = new TextDecoder().decode(Uint8Array.from(atob(match[1]), (c) => c.charCodeAt(0)));
  } catch {
    return false;
  }
  const colon = decoded.indexOf(":");
  if (colon < 0) return false;
  const [user, password] = await Promise.all([
    sameText(decoded.slice(0, colon), env.ADMIN_USER),
    sameText(decoded.slice(colon + 1), env.ADMIN_PASSWORD),
  ]);
  return user && password;
}

function challenge(): Response {
  return new Response("Acceso restringido.\n", {
    status: 401,
    headers: { ...NO_STORE, "WWW-Authenticate": CHALLENGE },
  });
}

function readToken(request: Request): string | null {
  const match = (request.headers.get("Cookie") ?? "").match(
    new RegExp(`(?:^|;\\s*)${COOKIE}=([0-9a-f-]{36})(?:;|$)`),
  );
  return match ? match[1] : null;
}

/** Collapse spaces and cut the optional name; an empty name is no name. */
export function cleanName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const name = value.replace(/\s+/g, " ").trim().slice(0, NAME_LIMIT);
  return name || null;
}

/** The gift id of a JSON POST from this site, or a response that refuses it. */
async function readGift(request: Request): Promise<{ id: string; body: Record<string, unknown> } | Response> {
  const origin = request.headers.get("Origin");
  if (origin && origin !== new URL(request.url).origin) return json({ error: "origin" }, 403);
  if (!(request.headers.get("Content-Type") ?? "").startsWith("application/json")) {
    return json({ error: "json" }, 415);
  }
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return json({ error: "json" }, 400);
  }
  if (typeof body.id !== "string" || !GIFT_IDS.has(body.id)) return json({ error: "gift" }, 400);
  return { id: body.id, body };
}

async function claims(env: Env): Promise<Claim[]> {
  const { results } = await env.DB.prepare(
    "SELECT gift_id, name, token_hash, reserved_at, bought_at FROM claims",
  )
    .bind()
    .all<Claim>();
  return results.filter((claim) => GIFT_IDS.has(claim.gift_id));
}

async function publicState(request: Request, env: Env): Promise<Response> {
  const token = readToken(request);
  const mine = token ? await sha256(token) : null;
  return json(
    (await claims(env)).map((claim) => ({
      id: claim.gift_id,
      reservedAt: claim.reserved_at,
      boughtAt: claim.bought_at,
      mine: claim.token_hash === mine,
    })),
  );
}

async function reserve(request: Request, env: Env): Promise<Response> {
  const gift = await readGift(request);
  if (gift instanceof Response) return gift;
  const existing = readToken(request);
  const token = existing ?? crypto.randomUUID();
  const { meta } = await env.DB.prepare(
    "INSERT INTO claims (gift_id, name, token_hash, reserved_at) VALUES (?, ?, ?, ?) " +
      "ON CONFLICT (gift_id) DO NOTHING",
  )
    .bind(gift.id, cleanName(gift.body.name), await sha256(token), new Date().toISOString())
    .run();
  if (meta.changes === 0) return json({ error: "taken" }, 409);
  const cookie = `${COOKIE}=${token}; Max-Age=${COOKIE_AGE}; Path=/api; HttpOnly; Secure; SameSite=Strict`;
  return json({ ok: true }, 200, existing ? {} : { "Set-Cookie": cookie });
}

/** Mark bought or release a claim, only from the browser that made it. */
async function ownClaim(request: Request, env: Env, sql: string, withTime: boolean): Promise<Response> {
  const gift = await readGift(request);
  if (gift instanceof Response) return gift;
  const token = readToken(request);
  if (!token) return json({ error: "not-yours" }, 403);
  const values = withTime
    ? [new Date().toISOString(), gift.id, await sha256(token)]
    : [gift.id, await sha256(token)];
  const { meta } = await env.DB.prepare(sql)
    .bind(...values)
    .run();
  return meta.changes === 0 ? json({ error: "not-yours" }, 403) : json({ ok: true });
}

async function adminState(env: Env): Promise<Response> {
  return json(
    (await claims(env)).map((claim) => ({
      id: claim.gift_id,
      name: claim.name,
      reservedAt: claim.reserved_at,
      boughtAt: claim.bought_at,
    })),
  );
}

async function adminChange(request: Request, env: Env, sql: string, withTime: boolean): Promise<Response> {
  const gift = await readGift(request);
  if (gift instanceof Response) return gift;
  const values = withTime ? [new Date().toISOString(), gift.id] : [gift.id];
  const { meta } = await env.DB.prepare(sql)
    .bind(...values)
    .run();
  return meta.changes === 0 ? json({ error: "unchanged" }, 409) : json({ ok: true });
}

export async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const { pathname: path } = url;
  const post = request.method === "POST";

  if (path === "/api/state" && request.method === "GET") return publicState(request, env);
  if (path === "/api/reserve" && post) return reserve(request, env);
  if (path === "/api/bought" && post) {
    return ownClaim(
      request,
      env,
      "UPDATE claims SET bought_at = ? WHERE gift_id = ? AND token_hash = ? AND bought_at IS NULL",
      true,
    );
  }
  if (path === "/api/release" && post) {
    return ownClaim(
      request,
      env,
      "DELETE FROM claims WHERE gift_id = ? AND token_hash = ? AND bought_at IS NULL",
      false,
    );
  }
  if (path.startsWith("/api/")) return notFound();

  if (path === "/admin" || path.startsWith("/admin/")) {
    if (!(await isAdmin(request, env))) return challenge();
    if (path === "/admin" && request.method === "GET") {
      return env.ASSETS.fetch(new Request(new URL("/admin", url), request));
    }
    if (path === "/admin/api/state" && request.method === "GET") return adminState(env);
    if (path === "/admin/api/release" && post) {
      return adminChange(request, env, "DELETE FROM claims WHERE gift_id = ?", false);
    }
    if (path === "/admin/api/bought" && post) {
      return adminChange(
        request,
        env,
        "UPDATE claims SET bought_at = ? WHERE gift_id = ? AND bought_at IS NULL",
        true,
      );
    }
    return notFound();
  }

  // The pages are served by their clean paths only, so admin.html cannot be reached
  // around the credential check.
  if (path.endsWith(".html")) return notFound();
  return env.ASSETS.fetch(request);
}
