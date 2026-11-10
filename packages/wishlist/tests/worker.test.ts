import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, test } from "vitest";
import { NAME_LIMIT, cleanName, type Database, type Env, type Statement } from "../src/app.ts";
import worker from "../src/worker.ts";

const ORIGIN = "https://wishlist.test";
const GIFT = "whirly-derby";
const OTHER_GIFT = "lobito-book";
const ADMIN = "Basic " + Buffer.from("me:long secret").toString("base64");

/** D1's surface over Node's SQLite, running the real migration. */
function database(): Database {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../migrations/0001_claims.sql", import.meta.url), "utf8"));
  return {
    prepare(sql: string): Statement {
      let values: unknown[] = [];
      const statement: Statement = {
        bind(...given: unknown[]) {
          values = given;
          return statement;
        },
        async run() {
          const result = db.prepare(sql).run(...(values as never[]));
          return { meta: { changes: Number(result.changes) } };
        },
        async all<T>() {
          return { results: db.prepare(sql).all(...(values as never[])) as T[] };
        },
      };
      return statement;
    },
  };
}

let env: Env;
const served: string[] = [];

beforeEach(() => {
  served.length = 0;
  env = {
    DB: database(),
    ASSETS: {
      fetch: async (request: Request) => {
        served.push(new URL(request.url).pathname);
        return new Response("ASSET");
      },
    },
    ADMIN_USER: "me",
    ADMIN_PASSWORD: "long secret",
  };
});

/** A browser: it keeps the cookie the Worker sets, as a real one would. */
function visitor() {
  let cookie = "";
  return async (path: string, body?: unknown, headers: Record<string, string> = {}) => {
    const request = new Request(ORIGIN + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json", Origin: ORIGIN }),
        ...(cookie ? { Cookie: cookie } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const response = await worker.fetch(request, env);
    const set = response.headers.get("Set-Cookie");
    if (set) cookie = set.split(";")[0];
    return response;
  };
}

describe("claims", () => {
  test("a gift can be reserved once; a second visitor gets a conflict", async () => {
    const ana = visitor();
    const luis = visitor();
    expect((await ana("/api/reserve", { id: GIFT, name: "Ana" })).status).toBe(200);
    expect((await luis("/api/reserve", { id: GIFT, name: "Luis" })).status).toBe(409);
    expect((await luis("/api/reserve", { id: OTHER_GIFT })).status).toBe(200);
  });

  test("the state marks the visitor's own claims and never carries a name", async () => {
    const ana = visitor();
    const luis = visitor();
    await ana("/api/reserve", { id: GIFT, name: "Ana" });
    const seenByAna = await (await ana("/api/state")).json();
    const seenByLuis = await (await luis("/api/state")).json();
    expect(seenByAna).toEqual([
      { id: GIFT, reservedAt: expect.any(String), boughtAt: null, mine: true },
    ]);
    expect(seenByLuis[0].mine).toBe(false);
    expect(JSON.stringify(seenByLuis)).not.toContain("Ana");
  });

  test("only the browser that reserved a gift can mark it bought, with the time", async () => {
    const ana = visitor();
    const luis = visitor();
    await ana("/api/reserve", { id: GIFT });
    await luis("/api/reserve", { id: OTHER_GIFT });
    expect((await luis("/api/bought", { id: GIFT })).status).toBe(403);
    expect((await visitor()("/api/bought", { id: GIFT })).status).toBe(403);
    expect((await ana("/api/bought", { id: GIFT })).status).toBe(200);
    const [claim] = (await (await ana("/api/state")).json()).filter((c: { id: string }) => c.id === GIFT);
    expect(Date.parse(claim.boughtAt)).not.toBeNaN();
    expect((await ana("/api/bought", { id: GIFT })).status).toBe(403);
  });

  test("only the browser that reserved a gift can release it, and not once bought", async () => {
    const ana = visitor();
    await ana("/api/reserve", { id: GIFT });
    await ana("/api/reserve", { id: OTHER_GIFT });
    expect((await visitor()("/api/release", { id: GIFT })).status).toBe(403);
    expect((await ana("/api/release", { id: GIFT })).status).toBe(200);
    expect((await visitor()("/api/reserve", { id: GIFT })).status).toBe(200);
    await ana("/api/bought", { id: OTHER_GIFT });
    expect((await ana("/api/release", { id: OTHER_GIFT })).status).toBe(403);
  });

  test("a gift that is not on the list, or a request from another site, is refused", async () => {
    const ana = visitor();
    expect((await ana("/api/reserve", { id: "pony" })).status).toBe(400);
    expect((await ana("/api/reserve", { id: GIFT }, { Origin: "https://evil.test" })).status).toBe(403);
    expect((await ana("/api/reserve", { id: GIFT }, { "Content-Type": "text/plain" })).status).toBe(415);
    expect(await (await ana("/api/state")).json()).toEqual([]);
  });

  test("the name is optional, trimmed and cut at the limit", () => {
    expect(cleanName("  tía   Ana ")).toBe("tía Ana");
    expect(cleanName("   ")).toBeNull();
    expect(cleanName(undefined)).toBeNull();
    expect(cleanName(42)).toBeNull();
    expect(cleanName("x".repeat(100))).toHaveLength(NAME_LIMIT);
  });

  test("the token cookie is HttpOnly, scoped to the API and outlives Safari's 7 days", async () => {
    const response = await visitor()("/api/reserve", { id: GIFT });
    const cookie = response.headers.get("Set-Cookie") ?? "";
    expect(cookie).toMatch(/HttpOnly/);
    expect(cookie).toMatch(/Secure/);
    expect(cookie).toMatch(/SameSite=Strict/);
    expect(cookie).toMatch(/Path=\/api/);
    expect(Number(cookie.match(/Max-Age=(\d+)/)?.[1])).toBeGreaterThan(300 * 24 * 60 * 60);
  });
});

describe("admin", () => {
  test("asks for credentials, and stays closed while they are unset", async () => {
    const guest = visitor();
    for (const path of ["/admin", "/admin/api/state"]) {
      const response = await guest(path);
      expect(response.status).toBe(401);
      expect(response.headers.get("WWW-Authenticate")).toMatch(/^Basic/);
    }
    expect((await guest("/admin", undefined, { Authorization: "Basic " + btoa("me:guess") })).status).toBe(401);
    env.ADMIN_PASSWORD = undefined;
    expect((await guest("/admin/api/state", undefined, { Authorization: ADMIN })).status).toBe(401);
    expect(served).toEqual([]);
  });

  test("shows the names and can release or mark any claim", async () => {
    const ana = visitor();
    await ana("/api/reserve", { id: GIFT, name: "Ana" });
    await ana("/api/reserve", { id: OTHER_GIFT });
    const admin = visitor();
    const auth = { Authorization: ADMIN };
    expect((await admin("/admin", undefined, auth)).status).toBe(200);
    expect(served).toEqual(["/admin"]);
    const state = await (await admin("/admin/api/state", undefined, auth)).json();
    expect(state.map((c: { name: string | null }) => c.name).sort()).toEqual(["Ana", null]);
    expect((await admin("/admin/api/bought", { id: GIFT }, auth)).status).toBe(200);
    expect((await admin("/admin/api/release", { id: OTHER_GIFT }, auth)).status).toBe(200);
    const after = await (await ana("/api/state")).json();
    expect(after).toEqual([{ id: GIFT, reservedAt: expect.any(String), boughtAt: expect.any(String), mine: true }]);
  });
});

describe("pages", () => {
  test("serves the list and its files, the admin manifest without credentials, and no page by its .html path", async () => {
    const guest = visitor();
    expect((await guest("/")).status).toBe(200);
    expect((await guest("/gifts.json")).status).toBe(200);
    expect((await guest("/admin.webmanifest")).status).toBe(200);
    expect((await guest("/admin.html")).status).toBe(404);
    expect((await guest("/index.html")).status).toBe(404);
    expect((await guest("/api/nothing")).status).toBe(404);
    expect(served).toEqual(["/", "/gifts.json", "/admin.webmanifest"]);
  });
});
