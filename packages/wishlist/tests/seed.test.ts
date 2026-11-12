import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import type { GiftList } from "../scripts/build.ts";
import { seedSql } from "../scripts/seed.ts";

test("the committed seed migration is exactly what gifts.json generates", () => {
  const list = JSON.parse(readFileSync(new URL("../gifts.json", import.meta.url), "utf8")) as GiftList;
  const committed = readFileSync(new URL("../migrations/0003_seed_gifts.sql", import.meta.url), "utf8");
  expect(committed).toBe(seedSql(list));
});

test("quotes in a title are escaped in the seed", () => {
  const sql = seedSql({ title: "It's", gifts: [{ id: "a", title: "Tom's", photo: "a.jpg" }] });
  expect(sql).toContain("'It''s'");
  expect(sql).toContain("'Tom''s'");
});
