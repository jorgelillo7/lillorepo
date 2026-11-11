// @vitest-environment happy-dom
import { beforeEach, expect, test } from "vitest";
import { arriveAt } from "../src/app/dom.ts";

function page(text: string): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = `<div class="toolbar"><button>Deshacer</button></div><tw-story><tw-passage>${text}</tw-passage></tw-story>`;
  document.body.appendChild(root);
  return root;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

test("a new passage takes the focus", () => {
  const root = page("<p>Samantha abre la puerta.</p>");
  root.querySelector("button")!.focus();
  arriveAt(root);
  expect(document.activeElement?.tagName).toBe("TW-PASSAGE");
});

test("a polite live region reads the passage's opening", () => {
  arriveAt(page("<p>El pasillo   está\n vacío.</p><p>Un ruido.</p>"));
  const region = document.getElementById("announcer")!;
  expect(region.getAttribute("aria-live")).toBe("polite");
  expect(region.textContent).toBe("El pasillo está vacío.Un ruido.");
});

test("a long passage is announced by its opening only", () => {
  arriveAt(page(`<p>${"palabra ".repeat(200)}</p>`));
  expect(document.getElementById("announcer")!.textContent!.length).toBeLessThanOrEqual(280);
});

test("the live region is one, and survives redrawing the page", () => {
  arriveAt(page("<p>Uno.</p>"));
  document.querySelectorAll("div:not(#announcer)").forEach((d) => d.remove());
  arriveAt(page("<p>Dos.</p>"));
  expect(document.querySelectorAll("#announcer")).toHaveLength(1);
  expect(document.getElementById("announcer")!.textContent).toBe("Dos.");
});
