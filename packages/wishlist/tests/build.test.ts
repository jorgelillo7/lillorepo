import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { problems, type GiftList } from "../scripts/build.ts";

const gift = { id: "whirly-derby", title: "Whirly Derby", photo: "whirly-derby.jpg" };

describe("gift list", () => {
  test("the list in the repo is valid", () => {
    const list = JSON.parse(readFileSync(new URL("../gifts.json", import.meta.url), "utf8")) as GiftList;
    expect(problems(list, readdirSync(new URL("../photos", import.meta.url)))).toEqual([]);
  });

  test("repeated ids, bad ids, missing titles and missing photos are all reported", () => {
    const list: GiftList = {
      title: "Navidad",
      gifts: [gift, gift, { id: "Bad Id", title: "", photo: "nope.jpg" }],
    };
    const found = problems(list, ["whirly-derby.jpg"]);
    expect(found).toHaveLength(4);
    expect(found.join("\n")).toMatch(/repeated/);
    expect(found.join("\n")).toMatch(/lowercase/);
    expect(found.join("\n")).toMatch(/no title/);
    expect(found.join("\n")).toMatch(/nope\.jpg does not exist/);
  });

  test("a gift for someone not among the recipients is reported", () => {
    const recipients = [{ id: "older", label: "Hermano mayor" }];
    const ok: GiftList = { title: "Navidad", recipients, gifts: [{ ...gift, for: "older" }] };
    expect(problems(ok, ["whirly-derby.jpg"])).toEqual([]);
    const wrong: GiftList = { title: "Navidad", recipients, gifts: [{ ...gift, for: "cousin" }] };
    expect(problems(wrong, ["whirly-derby.jpg"])).toEqual([
      'gift 1 (whirly-derby): "cousin" is not one of the recipients',
    ]);
  });

  test("an empty list is refused", () => {
    expect(problems({ title: "", gifts: [] }, [])).toEqual(["the list has no title", "the list has no gifts"]);
  });
});
