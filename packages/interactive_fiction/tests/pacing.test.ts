// @vitest-environment happy-dom
import { expect, test } from "vitest";
import { pace, segment } from "../src/app/pacing.ts";

function passage(html: string): HTMLElement {
  const el = document.createElement("tw-passage");
  el.innerHTML = html;
  return el;
}

const long = (word: string) => `${word} `.repeat(Math.ceil(320 / (word.length + 1))).trim();

test("paragraphs split at line breaks, short lines are joined, and nothing is lost, in order", () => {
  const html = `${long("one")}<br>${long("two")}<br>Short.<br><br>Also short.<br>${long("three")}<br><div class="page">A <br><br> page</div><br>Tail.`;
  const p = passage(html);
  const segs = segment(p);
  expect(segs).toHaveLength(3);
  expect(segs[1].textContent).toBe(long("two"));
  // Short lines ride along with what follows; a short tail joins the last paragraph.
  expect(segs[2].textContent).toBe(`Short.Also short.${long("three")}A  pageTail.`);
  expect(p.textContent).toBe(passage(html).textContent);
  expect(p.innerHTML.replace(/<\/?tw-seg>/g, "")).toBe(passage(html).innerHTML);
});

test("an element is never split, even with blank lines inside it", () => {
  const segs = segment(passage('<div id="hud">a<br><br>b</div>'));
  expect(segs).toHaveLength(1);
  expect(segs[0].querySelector("#hud")?.textContent).toBe("ab");
});

test("reading reveals one paragraph at a time and calls back once at the end", () => {
  const p = passage(`${long("a")}<br>${long("b")}<br>${long("c")}`);
  let done = 0;
  const reading = pace(p, false, () => done++);
  const visible = () => [...p.querySelectorAll("tw-seg")].filter((s) => !(s as HTMLElement).hidden).length;
  expect(visible()).toBe(1);
  reading.next();
  expect(visible()).toBe(2);
  expect(done).toBe(0);
  reading.next();
  expect(visible()).toBe(3);
  expect(done).toBe(1);
  reading.next();
  expect(done).toBe(1);
});

test("an instant reveal, or a single paragraph, is done straight away", () => {
  let done = 0;
  pace(passage(`${long("a")}<br>${long("b")}`), true, () => done++);
  pace(passage("Only one."), false, () => done++);
  expect(done).toBe(2);
});
