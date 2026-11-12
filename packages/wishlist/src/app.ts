// What the gift list Worker does; src/worker.ts only hands requests here, because a
// Worker module may export nothing but its handlers. The list page is public: anyone with the address can claim a
// gift, mark it bought or let it go. Who claimed it is kept by a random token in an
// HttpOnly cookie, so only that browser can change its own claim. Names are optional
// and only /admin, behind Basic auth, ever shows them.

import { addGift, adminList, deleteGift, editGift, giftExists, hideGift, publicList, servePhoto, uploadPhoto } from "./gifts.ts";
import { NO_STORE, SECURITY, fromThisSite, json, notFound, sha256 } from "./http.ts";
import type { Env } from "./types.ts";

export type { Database, Env, Statement } from "./types.ts";

interface Claim {
  gift_id: string;
  name: string | null;
  token_hash: string;
  reserved_at: string;
  bought_at: string | null;
}

export const NAME_LIMIT = 40;
const COOKIE = "wl";
// 400 days, the longest a browser keeps a cookie. Claims are made in November and
// bought in December, so the token has to outlive Safari's 7-day limit on storage
// that scripts write.
const COOKIE_AGE = 400 * 24 * 60 * 60;
const CHALLENGE = 'Basic realm="wishlist-admin", charset="UTF-8"';

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

const JSON_LIMIT = 4096;

/**
 * The JSON body of a POST from this site, or a response that refuses it. `admin` is
 * stricter: Basic credentials travel without being asked, like a cookie, so a write
 * must prove it came from this site's own page.
 */
async function readJson(request: Request, admin: boolean): Promise<Record<string, unknown> | Response> {
  if (!fromThisSite(request, admin)) return json({ error: "origin" }, 403);
  if (!(request.headers.get("Content-Type") ?? "").startsWith("application/json")) {
    return json({ error: "json" }, 415);
  }
  if (Number(request.headers.get("Content-Length") ?? 0) > JSON_LIMIT) return json({ error: "size" }, 413);
  try {
    const body = await request.json();
    if (body && typeof body === "object" && !Array.isArray(body)) return body as Record<string, unknown>;
  } catch {
    // Falls through to the refusal below.
  }
  return json({ error: "json" }, 400);
}

/** The gift id of a JSON POST from this site, or a response that refuses it. */
async function readGift(
  request: Request,
  env: Env,
  admin: boolean,
): Promise<{ id: string; body: Record<string, unknown> } | Response> {
  const body = await readJson(request, admin);
  if (body instanceof Response) return body;
  if (typeof body.id !== "string" || !(await giftExists(env, body.id, admin))) return json({ error: "gift" }, 400);
  return { id: body.id, body };
}

/** Claims on gifts that exist; the public ones leave out hidden gifts. */
async function claims(env: Env, withHidden: boolean): Promise<Claim[]> {
  const { results } = await env.DB.prepare(
    "SELECT c.gift_id, c.name, c.token_hash, c.reserved_at, c.bought_at FROM claims c " +
      `JOIN gifts g ON g.id = c.gift_id ${withHidden ? "" : "WHERE g.hidden = 0"}`,
  )
    .bind()
    .all<Claim>();
  return results;
}

async function publicState(request: Request, env: Env): Promise<Response> {
  const token = readToken(request);
  const mine = token ? await sha256(token) : null;
  return json(
    (await claims(env, false)).map((claim) => ({
      id: claim.gift_id,
      reservedAt: claim.reserved_at,
      boughtAt: claim.bought_at,
      mine: claim.token_hash === mine,
    })),
  );
}

async function reserve(request: Request, env: Env): Promise<Response> {
  const gift = await readGift(request, env, false);
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
  const gift = await readGift(request, env, false);
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
    (await claims(env, true)).map((claim) => ({
      id: claim.gift_id,
      name: claim.name,
      reservedAt: claim.reserved_at,
      boughtAt: claim.bought_at,
    })),
  );
}

async function adminChange(request: Request, env: Env, sql: string, withTime: boolean): Promise<Response> {
  const gift = await readGift(request, env, true);
  if (gift instanceof Response) return gift;
  const values = withTime ? [new Date().toISOString(), gift.id] : [gift.id];
  const { meta } = await env.DB.prepare(sql)
    .bind(...values)
    .run();
  return meta.changes === 0 ? json({ error: "unchanged" }, 409) : json({ ok: true });
}

/** Admin writes that take a JSON body and hand it to the gift module. */
async function adminWrite(
  request: Request,
  env: Env,
  action: (body: Record<string, unknown>, env: Env) => Promise<Response>,
): Promise<Response> {
  const body = await readJson(request, true);
  return body instanceof Response ? body : action(body, env);
}

async function route(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const { pathname: path } = url;
  const get = request.method === "GET";
  const post = request.method === "POST";

  if (path === "/api/state" && get) return publicState(request, env);
  if (path === "/api/list" && get) return publicList(env);
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

  const uploaded = path.match(/^\/photos\/u\/([0-9a-f-]{36})\.jpg$/);
  if (uploaded && get) return (await servePhoto(env, uploaded[1])) ?? notFound();

  if (path === "/admin" || path.startsWith("/admin/")) {
    if (!(await isAdmin(request, env))) return challenge();
    if (path === "/admin" && get) {
      const page = await env.ASSETS.fetch(new Request(new URL("/admin", url), request));
      return new Response(page.body, { status: page.status, headers: { ...Object.fromEntries(page.headers), ...NO_STORE } });
    }
    if (path === "/admin/api/state" && get) return adminState(env);
    if (path === "/admin/api/gifts" && get) return adminList(env);
    if (path === "/admin/api/photo" && post) {
      return fromThisSite(request, true) ? uploadPhoto(request, env) : json({ error: "origin" }, 403);
    }
    if (path === "/admin/api/gift/add" && post) return adminWrite(request, env, addGift);
    if (path === "/admin/api/gift/edit" && post) return adminWrite(request, env, editGift);
    if (path === "/admin/api/gift/hide" && post) return adminWrite(request, env, hideGift);
    if (path === "/admin/api/gift/delete" && post) return adminWrite(request, env, deleteGift);
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

export async function handle(request: Request, env: Env): Promise<Response> {
  const response = await route(request, env);
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY)) headers.set(name, value);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
