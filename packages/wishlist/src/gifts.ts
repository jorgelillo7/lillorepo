// The gifts themselves: the public list, and what /admin does to it. Gifts and their
// uploaded photos live in D1 (migrations/0002_gifts.sql).

import { fromBase64, json, toBase64 } from "./http.ts";
import { cleanBaseline } from "./jpeg.ts";
import type { Env } from "./types.ts";

export const TITLE_LIMIT = 120;
export const DETAIL_LIMIT = 200;
export const NOTE_LIMIT = 400;
/** Hard cap on an uploaded JPEG. As base64 it is ~800 KB, well under D1's 2 MB row limit. */
export const PHOTO_MAX_BYTES = 600 * 1024;
export const PHOTO_MAX_SIDE = 1600;
/** An upload never added to a gift is discarded after this long. */
const ORPHAN_HOURS = 24;
const UPLOADED = /^\/photos\/u\/([0-9a-f-]{36})\.jpg$/;

interface GiftRow {
  id: string;
  recipient: string | null;
  title: string;
  detail: string | null;
  note: string | null;
  photo: string;
  hidden: number;
}

interface EventRow {
  slug: string;
  title: string;
  subtitle: string | null;
}

interface Recipient {
  id: string;
  label: string;
}

const rows = async <T>(env: Env, sql: string, ...values: unknown[]): Promise<T[]> =>
  (await env.DB.prepare(sql).bind(...values).all<T>()).results;

/** One line of text: spaces collapsed, cut at `limit`; empty is none. */
export function cleanText(value: unknown, limit: number): string | null {
  if (typeof value !== "string") return null;
  return value.replace(/\s+/g, " ").trim().slice(0, limit) || null;
}

/** Lowercase words joined by dashes, from a title; the id of a new gift. */
export function slugify(title: string): string {
  const slug = title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/, "");
  return slug || "regalo";
}

async function currentEvent(env: Env): Promise<EventRow | null> {
  return (await rows<EventRow>(env, "SELECT slug, title, subtitle FROM events WHERE current = 1 LIMIT 1"))[0] ?? null;
}

async function listOf(env: Env, withHidden: boolean): Promise<Response> {
  const event = await currentEvent(env);
  if (!event) return json({ title: "Regalos", recipients: [], gifts: [] });
  const recipients = await rows<Recipient>(
    env,
    "SELECT id, label FROM recipients WHERE event = ? ORDER BY position",
    event.slug,
  );
  const gifts = await rows<GiftRow>(
    env,
    "SELECT id, recipient, title, detail, note, photo, hidden FROM gifts " +
      `WHERE event = ? ${withHidden ? "" : "AND hidden = 0"} ORDER BY position, created_at`,
    event.slug,
  );
  return json({
    title: event.title,
    subtitle: event.subtitle,
    recipients,
    gifts: gifts.map((gift) => ({
      id: gift.id,
      for: gift.recipient,
      title: gift.title,
      detail: gift.detail,
      note: gift.note,
      photo: gift.photo,
      ...(withHidden ? { hidden: gift.hidden === 1 } : {}),
    })),
  });
}

/** The public list: the current event's visible gifts. */
export const publicList = (env: Env) => listOf(env, false);
/** The same with hidden gifts, for /admin. */
export const adminList = (env: Env) => listOf(env, true);

/** Whether a gift exists, and is visible unless `anyway`. */
export async function giftExists(env: Env, id: string, anyway: boolean): Promise<boolean> {
  const found = await rows<{ id: string }>(
    env,
    `SELECT id FROM gifts WHERE id = ? ${anyway ? "" : "AND hidden = 0"}`,
    id,
  );
  return found.length > 0;
}

/** An uploaded photo, by the id in its address. */
export async function servePhoto(env: Env, id: string): Promise<Response | null> {
  const [photo] = await rows<{ data: string }>(env, "SELECT data FROM photos WHERE id = ?", id);
  if (!photo) return null;
  return new Response(fromBase64(photo.data) as Uint8Array<ArrayBuffer>, {
    headers: {
      "Content-Type": "image/jpeg",
      // The id changes whenever the photo does, so a copy is good for as long as anyone keeps it.
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}

/** Store a photo sent from /admin: the raw JPEG as the body. */
export async function uploadPhoto(request: Request, env: Env): Promise<Response> {
  if ((request.headers.get("Content-Type") ?? "") !== "image/jpeg") return json({ error: "photo-type" }, 415);
  const declared = Number(request.headers.get("Content-Length") ?? NaN);
  if (!Number.isFinite(declared) || declared > PHOTO_MAX_BYTES) return json({ error: "photo-size" }, 413);
  const body = new Uint8Array(await request.arrayBuffer());
  if (body.length > PHOTO_MAX_BYTES) return json({ error: "photo-size" }, 413);
  const clean = cleanBaseline(body, PHOTO_MAX_SIDE);
  if (!clean.ok) return json({ error: "photo", reason: clean.reason }, 400);
  const id = crypto.randomUUID();
  const now = new Date();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM photos WHERE created_at < ? AND ('/photos/u/' || id || '.jpg') NOT IN (SELECT photo FROM gifts)").bind(
      new Date(now.getTime() - ORPHAN_HOURS * 3600_000).toISOString(),
    ),
    env.DB.prepare("INSERT INTO photos (id, data, bytes, created_at) VALUES (?, ?, ?, ?)").bind(
      id,
      toBase64(clean.bytes),
      clean.bytes.length,
      now.toISOString(),
    ),
  ]);
  return json({ photo: `/photos/u/${id}.jpg`, bytes: clean.bytes.length });
}

type Fields = Record<string, unknown>;

/** The recipient id when it is one of the event's, null for none, undefined when invalid. */
async function recipientOf(env: Env, event: string, value: unknown): Promise<string | null | undefined> {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string") return undefined;
  const found = await rows<{ id: string }>(env, "SELECT id FROM recipients WHERE event = ? AND id = ?", event, value);
  return found.length ? value : undefined;
}

/** Whether `photo` is an upload that exists and no gift uses yet (unless `gift` itself does). */
async function freePhoto(env: Env, photo: unknown, gift?: string): Promise<string | null> {
  const id = typeof photo === "string" ? photo.match(UPLOADED)?.[1] : undefined;
  if (!id || !(await rows(env, "SELECT id FROM photos WHERE id = ?", id)).length) return null;
  const users = await rows<{ id: string }>(env, "SELECT id FROM gifts WHERE photo = ?", photo);
  return users.every((user) => user.id === gift) ? (photo as string) : null;
}

async function newId(env: Env, title: string): Promise<string> {
  const base = slugify(title);
  for (let n = 1; n < 100; n++) {
    const id = n === 1 ? base : `${base}-${n}`;
    if (!(await giftExists(env, id, true))) return id;
  }
  return `${base}-${crypto.randomUUID().slice(0, 8)}`;
}

export async function addGift(body: Fields, env: Env): Promise<Response> {
  const event = await currentEvent(env);
  const title = cleanText(body.title, TITLE_LIMIT);
  if (!event || !title) return json({ error: "title" }, 400);
  const recipient = await recipientOf(env, event.slug, body.recipient);
  if (recipient === undefined) return json({ error: "recipient" }, 400);
  const photo = await freePhoto(env, body.photo);
  if (!photo) return json({ error: "photo" }, 400);
  const id = await newId(env, title);
  const { meta } = await env.DB.prepare(
    "INSERT INTO gifts (id, event, recipient, title, detail, note, photo, position, created_at) " +
      "SELECT ?, ?, ?, ?, ?, ?, ?, COALESCE(MAX(position), -1) + 1, ? FROM gifts WHERE event = ?",
  )
    .bind(
      id,
      event.slug,
      recipient,
      title,
      cleanText(body.detail, DETAIL_LIMIT),
      cleanText(body.note, NOTE_LIMIT),
      photo,
      new Date().toISOString(),
      event.slug,
    )
    .run();
  return meta.changes === 0 ? json({ error: "conflict" }, 409) : json({ ok: true, id, photo });
}

export async function editGift(body: Fields, env: Env): Promise<Response> {
  const id = typeof body.id === "string" ? body.id : "";
  const [gift] = await rows<GiftRow & { event: string }>(env, "SELECT id, event, photo FROM gifts WHERE id = ?", id);
  if (!gift) return json({ error: "gift" }, 400);
  const title = cleanText(body.title, TITLE_LIMIT);
  if (!title) return json({ error: "title" }, 400);
  const recipient = await recipientOf(env, gift.event, body.recipient);
  if (recipient === undefined) return json({ error: "recipient" }, 400);
  let photo = gift.photo;
  if (body.photo !== undefined && body.photo !== gift.photo) {
    const next = await freePhoto(env, body.photo, id);
    if (!next) return json({ error: "photo" }, 400);
    photo = next;
  }
  const statements = [
    env.DB.prepare("UPDATE gifts SET title = ?, recipient = ?, detail = ?, note = ?, photo = ? WHERE id = ?").bind(
      title,
      recipient,
      cleanText(body.detail, DETAIL_LIMIT),
      cleanText(body.note, NOTE_LIMIT),
      photo,
      id,
    ),
  ];
  const old = gift.photo.match(UPLOADED)?.[1];
  if (old && photo !== gift.photo) statements.push(env.DB.prepare("DELETE FROM photos WHERE id = ?").bind(old));
  await env.DB.batch(statements);
  return json({ ok: true, photo });
}

export async function hideGift(body: Fields, env: Env): Promise<Response> {
  if (typeof body.id !== "string" || typeof body.hidden !== "boolean") return json({ error: "gift" }, 400);
  const { meta } = await env.DB.prepare("UPDATE gifts SET hidden = ? WHERE id = ?")
    .bind(body.hidden ? 1 : 0, body.id)
    .run();
  return meta.changes === 0 ? json({ error: "gift" }, 400) : json({ ok: true });
}

/** Delete a gift with its claim and its uploaded photo; a claimed one only with `force`. */
export async function deleteGift(body: Fields, env: Env): Promise<Response> {
  const id = typeof body.id === "string" ? body.id : "";
  const [gift] = await rows<{ photo: string }>(env, "SELECT photo FROM gifts WHERE id = ?", id);
  if (!gift) return json({ error: "gift" }, 400);
  const claimed = (await rows(env, "SELECT gift_id FROM claims WHERE gift_id = ?", id)).length > 0;
  if (claimed && body.force !== true) return json({ error: "claimed" }, 409);
  const statements = [
    env.DB.prepare("DELETE FROM claims WHERE gift_id = ?").bind(id),
    env.DB.prepare("DELETE FROM gifts WHERE id = ?").bind(id),
  ];
  const upload = gift.photo.match(UPLOADED)?.[1];
  if (upload) statements.push(env.DB.prepare("DELETE FROM photos WHERE id = ?").bind(upload));
  await env.DB.batch(statements);
  return json({ ok: true });
}
