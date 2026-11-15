// @vitest-environment happy-dom
import { beforeEach, describe, expect, test, vi } from "vitest";

// dom.ts looks the app's root up when it loads.
document.body.innerHTML = `<div id="app"></div>`;
const { armed, openModal, paragraphGaps, roman } = await import("../src/app/dom.ts");
const { muteButton, toolbar } = await import("../src/app/views.ts");

const series = { id: "s", title: "S", carry: null, about: [], credits: [], game: {}, chapters: [] };

describe("the pages around the story", () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="app"></div>`;
  });

  test("chapters are numbered as a book numbers them", () => {
    expect([1, 2, 3, 4, 5, 9, 10, 14, 19, 20].map(roman)).toEqual(["I", "II", "III", "IV", "V", "IX", "X", "XIV", "XIX", "XX"]);
  });

  test("every line break of the passage gets one spacer after it, and the text stays as it was", () => {
    const passage = document.createElement("tw-passage");
    passage.innerHTML = `<tw-seg>One.<br>Two.<br><br></tw-seg><tw-seg><div class="page">Inside<br>a document</div>Three.<br></tw-seg>`;
    const before = passage.textContent;
    paragraphGaps(passage);
    paragraphGaps(passage);
    expect(passage.querySelectorAll(".par-gap")).toHaveLength(4);
    expect(passage.querySelector(".page .par-gap")).toBeNull();
    expect(passage.querySelectorAll("br")).toHaveLength(5);
    expect(passage.textContent).toBe(before);
    for (const gap of passage.querySelectorAll(".par-gap")) expect(gap.getAttribute("aria-hidden")).toBe("true");
  });

  test("every control of the toolbar has a name, and the sound switch says whether it is pressed", () => {
    const bar = document.createElement("div");
    bar.innerHTML = toolbar({ series, title: "Capitulo 1 - The Door", canUndo: false, gameMode: true, muted: false });
    const tools = [...bar.querySelectorAll<HTMLElement>(".tool")];
    expect(tools.length).toBe(6);
    for (const tool of tools) expect(tool.getAttribute("aria-label"), tool.outerHTML).toBeTruthy();
    expect(bar.querySelector(".tool-title")!.textContent).toBe("The Door");
    expect(bar.querySelector('[data-tool="undo"]')!.hasAttribute("disabled")).toBe(true);
    expect(muteButton(false)).toContain('aria-pressed="false"');
    expect(muteButton(true)).toContain('aria-pressed="true"');
    expect(bar.querySelector("nav")!.getAttribute("aria-label")).toBeTruthy();
  });

  test("a sheet opens as a modal dialog, and closing it removes it and gives focus back", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `<div class="sheet"><button class="close">Close</button></div>`;
    openModal(dialog, ".close");
    expect(dialog.isConnected).toBe(true);
    expect(dialog.open).toBe(true);
    expect(document.activeElement).toBe(dialog.querySelector(".close"));
    dialog.close();
    expect(dialog.isConnected).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  test("a click on the dimmed page around the sheet closes the dialog; a click inside does not", () => {
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `<div class="sheet"><button class="close">Close</button></div>`;
    openModal(dialog);
    dialog.querySelector<HTMLElement>(".sheet")!.click();
    expect(dialog.open).toBe(true);
    dialog.click();
    expect(dialog.isConnected).toBe(false);
  });

  test("closing a sheet after a setting redrew the page gives focus to the new copy of its opener", () => {
    document.getElementById("app")!.innerHTML = `<nav><button data-tool="settings" aria-label="Ajustes">⚙</button></nav>`;
    document.querySelector<HTMLElement>('[data-tool="settings"]')!.focus();
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `<button class="close">Close</button>`;
    openModal(dialog, ".close");
    document.getElementById("app")!.innerHTML = `<nav><button data-tool="settings" aria-label="Ajustes">⚙</button></nav>`;
    dialog.close();
    expect(document.activeElement).toBe(document.querySelector('[data-tool="settings"]'));
  });

  test("an armed restart is named by its question, which the live region reads, and rests again after 4 s", () => {
    vi.useFakeTimers();
    try {
      document.getElementById("app")!.innerHTML = `<button data-tool="restart" aria-label="Reiniciar el capítulo"><svg></svg><span>Reiniciar</span></button>`;
      const tool = document.querySelector<HTMLElement>('[data-tool="restart"]')!;
      expect(armed(tool, "¿Seguro? Toca otra vez")).toBe(false);
      expect(tool.hasAttribute("aria-label")).toBe(false);
      expect(tool.textContent).toBe("¿Seguro? Toca otra vez");
      expect(document.getElementById("announcer")!.textContent).toBe("¿Seguro? Toca otra vez");
      expect(armed(tool, "¿Seguro? Toca otra vez")).toBe(true);
      vi.advanceTimersByTime(4000);
      expect(tool.getAttribute("aria-label")).toBe("Reiniciar el capítulo");
      expect(tool.querySelector("span")!.textContent).toBe("Reiniciar");
      expect(tool.dataset.armed).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });
});
