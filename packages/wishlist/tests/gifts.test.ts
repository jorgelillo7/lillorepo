import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, test } from "vitest";
import { PHOTO_MAX_BYTES, slugify } from "../src/gifts.ts";
import { fromBase64 } from "../src/http.ts";
import worker from "../src/worker.ts";
import type { Env } from "../src/types.ts";
import { ADMIN, ORIGIN, asText, database, environment, phonePhoto } from "./support.ts";
import type { DatabaseSync } from "node:sqlite";

let env: Env;
let sqlite: DatabaseSync;

beforeEach(() => {
  const made = database();
  sqlite = made.sqlite;
  env = environment(made.db);
});

const count = (sql: string, ...values: unknown[]) =>
  Number((sqlite.prepare(sql).get(...(values as never[])) as { n: number }).n);

/** An admin request: credentials, and by default the origin a real admin page sends. */
function admin(path: string, body?: unknown, headers: Record<string, string> = {}) {
  const raw = body instanceof Uint8Array;
  return worker.fetch(
    new Request(ORIGIN + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: ADMIN,
        ...(body === undefined ? {} : { Origin: ORIGIN }),
        ...(raw
          ? { "Content-Type": "image/jpeg", "Content-Length": String(body.length) }
          : body === undefined
            ? {}
            : { "Content-Type": "application/json" }),
        ...headers,
      },
      body: body === undefined ? undefined : raw ? (body as Uint8Array<ArrayBuffer>) : JSON.stringify(body),
    }),
    env,
  );
}

const publicList = async () => (await worker.fetch(new Request(ORIGIN + "/api/list"), env)).json();

async function upload(bytes = phonePhoto()): Promise<string> {
  const response = await admin("/admin/api/photo", bytes);
  expect(response.status).toBe(200);
  return (await response.json()).photo;
}

async function addGift(fields: Record<string, unknown> = {}): Promise<{ id: string; photo: string }> {
  const photo = await upload();
  const response = await admin("/admin/api/gift/add", { title: "Camión de bomberos", recipient: "younger", photo, ...fields });
  expect(response.status).toBe(200);
  return response.json();
}

describe("the list in D1", () => {
  test("the first list is imported with its ids, recipients and static photos", async () => {
    const seed = JSON.parse(readFileSync(new URL("../gifts.json", import.meta.url), "utf8"));
    const list = await publicList();
    expect(list.title).toBe(seed.title);
    expect(list.recipients).toEqual(seed.recipients);
    expect(list.gifts.map((g: { id: string }) => g.id)).toEqual(seed.gifts.map((g: { id: string }) => g.id));
    expect(list.gifts[0]).toMatchObject({ for: seed.gifts[0].for, photo: `/photos/${seed.gifts[0].photo}` });
    expect(list.gifts.some((g: { hidden?: boolean }) => "hidden" in g)).toBe(false);
  });

  test("a new gift gets an id from its title, the last place, and shows on the public list", async () => {
    const { id } = await addGift({ detail: "  Con   escalera ", note: "Visto en la tienda del centro" });
    expect(id).toBe("camion-de-bomberos");
    const list = await publicList();
    expect(list.gifts.at(-1)).toMatchObject({
      id,
      for: "younger",
      title: "Camión de bomberos",
      detail: "Con escalera",
      note: "Visto en la tienda del centro",
    });
    expect((await addGift()).id).toBe("camion-de-bomberos-2");
    expect(slugify("¡Qué Ñandú!")).toBe("que-nandu");
  });

  test("a gift needs a title, a known recipient and an uploaded photo nobody else uses", async () => {
    const photo = await upload();
    const send = async (fields: Record<string, unknown>) =>
      (await admin("/admin/api/gift/add", { title: "Tren", photo, ...fields })).status;
    expect(await send({ title: "  " })).toBe(400);
    expect(await send({ recipient: "cousin" })).toBe(400);
    expect(await send({ photo: "/photos/u/00000000-0000-0000-0000-000000000000.jpg" })).toBe(400);
    expect(await send({ photo: "/photos/whirly-derby.jpg" })).toBe(400);
    expect(await send({})).toBe(200);
    expect(await send({})).toBe(400);
  });
});

describe("photos", () => {
  test("an uploaded photo is served from D1 with an immutable cache and nothing but the image", async () => {
    const { photo } = await addGift();
    const response = await worker.fetch(new Request(ORIGIN + photo), env);
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("image/jpeg");
    expect(response.headers.get("Cache-Control")).toBe("public, max-age=31536000, immutable");
    const served = new Uint8Array(await response.arrayBuffer());
    expect(served.subarray(0, 2)).toEqual(new Uint8Array([0xff, 0xd8]));
    expect(served.subarray(-2)).toEqual(new Uint8Array([0xff, 0xd9]));
  });

  test("the stored bytes carry no EXIF, GPS, IPTC, comment or appended second picture", async () => {
    await addGift();
    const rows = sqlite.prepare("SELECT data, bytes FROM photos").all() as { data: string; bytes: number }[];
    expect(rows).toHaveLength(1);
    const stored = fromBase64(rows[0].data);
    const text = asText(stored);
    expect(text).not.toMatch(/Exif|GPS|Latitude|MPF|Photoshop|IPTC|shot at home/);
    expect(rows[0].bytes).toBe(stored.length);
    const markers: number[] = [];
    for (let at = 2; stored[at] === 0xff && stored[at + 1] !== 0xda; at += 2 + ((stored[at + 2] << 8) | stored[at + 3])) {
      markers.push(stored[at + 1]);
    }
    expect(markers).toEqual([0xe0, 0xdb, 0xc0, 0xc4]);
    expect(stored.filter((byte, i) => byte === 0xff && stored[i + 1] === 0xd9)).toHaveLength(1);
    expect(text.endsWith("\xff\xd9")).toBe(true);
  });

  test("what is not a clean baseline JPEG, or is too big, is refused and nothing is stored", async () => {
    const send = async (bytes: Uint8Array, headers: Record<string, string> = {}) =>
      (await admin("/admin/api/photo", bytes, headers)).status;
    expect(await send(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0]))).toBe(400);
    expect(await send(phonePhoto({ frame: 0xc2 }))).toBe(400);
    expect(await send(phonePhoto({ width: 5000 }))).toBe(400);
    expect(await send(phonePhoto({ orientation: 6 }))).toBe(400);
    expect(await send(phonePhoto({ padding: PHOTO_MAX_BYTES }))).toBe(413);
    expect(await send(phonePhoto(), { "Content-Type": "image/png" })).toBe(415);
    expect(await send(phonePhoto().subarray(0, 60))).toBe(400);
    expect(count("SELECT COUNT(*) AS n FROM photos")).toBe(0);
  });

  test("an upload no gift took is discarded on the next upload after a day", async () => {
    const forgotten = await upload();
    const id = forgotten.slice("/photos/u/".length, -".jpg".length);
    sqlite.prepare("UPDATE photos SET created_at = ?").run(new Date(Date.now() - 25 * 3600_000).toISOString());
    const kept = await addGift();
    expect(count("SELECT COUNT(*) AS n FROM photos WHERE id = ?", id)).toBe(0);
    expect(count("SELECT COUNT(*) AS n FROM photos")).toBe(1);
    expect((await worker.fetch(new Request(ORIGIN + kept.photo), env)).status).toBe(200);
  });
});

describe("editing, hiding and deleting", () => {
  test("a gift's text and photo can change; the old uploaded photo goes", async () => {
    const first = await addGift();
    const photo = await upload();
    const response = await admin("/admin/api/gift/edit", { id: first.id, title: "Camión grande", recipient: "older", detail: "", photo });
    expect(response.status).toBe(200);
    expect((await publicList()).gifts.at(-1)).toMatchObject({ id: first.id, title: "Camión grande", for: "older", detail: null, photo });
    expect((await worker.fetch(new Request(ORIGIN + first.photo), env)).status).toBe(404);
    expect((await admin("/admin/api/gift/edit", { id: first.id, title: "" })).status).toBe(400);
    expect((await admin("/admin/api/gift/edit", { id: "pony", title: "x" })).status).toBe(400);
  });

  test("a hidden gift leaves the public list and cannot be reserved, but keeps its claim", async () => {
    const reserve = (id: string) =>
      worker.fetch(
        new Request(ORIGIN + "/api/reserve", {
          method: "POST",
          headers: { "Content-Type": "application/json", Origin: ORIGIN },
          body: JSON.stringify({ id }),
        }),
        env,
      );
    expect((await reserve("whirly-derby")).status).toBe(200);
    expect((await admin("/admin/api/gift/hide", { id: "whirly-derby", hidden: true })).status).toBe(200);
    expect((await publicList()).gifts.map((g: { id: string }) => g.id)).not.toContain("whirly-derby");
    expect(await (await worker.fetch(new Request(ORIGIN + "/api/state"), env)).json()).toEqual([]);
    expect((await reserve("whirly-derby")).status).toBe(400);
    const all = await (await admin("/admin/api/gifts")).json();
    expect(all.gifts.find((g: { id: string }) => g.id === "whirly-derby").hidden).toBe(true);
    expect((await (await admin("/admin/api/state")).json()).map((c: { id: string }) => c.id)).toEqual(["whirly-derby"]);
    await admin("/admin/api/gift/hide", { id: "whirly-derby", hidden: false });
    expect((await publicList()).gifts.map((g: { id: string }) => g.id)).toContain("whirly-derby");
  });

  test("deleting removes the gift and its uploaded photo; a claimed gift needs force", async () => {
    const free = await addGift();
    expect((await admin("/admin/api/gift/delete", { id: free.id })).status).toBe(200);
    expect(count("SELECT COUNT(*) AS n FROM gifts WHERE id = ?", free.id)).toBe(0);
    expect(count("SELECT COUNT(*) AS n FROM photos")).toBe(0);

    const claimed = await addGift();
    sqlite
      .prepare("INSERT INTO claims (gift_id, name, token_hash, reserved_at) VALUES (?, 'Ana', 'x', 'now')")
      .run(claimed.id);
    expect((await admin("/admin/api/gift/delete", { id: claimed.id })).status).toBe(409);
    expect(count("SELECT COUNT(*) AS n FROM gifts WHERE id = ?", claimed.id)).toBe(1);
    expect((await admin("/admin/api/gift/delete", { id: claimed.id, force: false })).status).toBe(409);
    expect((await admin("/admin/api/gift/delete", { id: claimed.id, force: true })).status).toBe(200);
    expect(count("SELECT COUNT(*) AS n FROM claims WHERE gift_id = ?", claimed.id)).toBe(0);
    expect(count("SELECT COUNT(*) AS n FROM photos")).toBe(0);
  });

  test("existing claims survive the move to D1 and still show for the same ids", async () => {
    sqlite
      .prepare("INSERT INTO claims (gift_id, name, token_hash, reserved_at) VALUES ('lobito-book', 'Ana', 'x', 'now')")
      .run();
    const state = await (await admin("/admin/api/state")).json();
    expect(state).toEqual([{ id: "lobito-book", name: "Ana", reservedAt: "now", boughtAt: null }]);
  });
});
