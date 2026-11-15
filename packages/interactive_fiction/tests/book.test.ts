// @vitest-environment happy-dom
import { beforeEach, describe, expect, test, vi } from "vitest";

// dom.ts looks the app's root up when it loads.
document.body.innerHTML = `<div id="app"></div>`;
const { STATUS_MS, armed, focusHeading, openModal, paragraphGaps, roman, showStatus } = await import("../src/app/dom.ts");
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
    dialog.innerHTML = `<form method="dialog"><button class="close" autofocus>Close</button></form>`;
    openModal(dialog);
    expect(dialog.isConnected).toBe(true);
    expect(dialog.open).toBe(true);
    dialog.close();
    expect(dialog.isConnected).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  test("where the browser lacks closedby, a press and release outside a light-dismiss sheet close it; one inside does not", () => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("closedby", "any");
    dialog.innerHTML = `<button class="close">Close</button>`;
    openModal(dialog);
    dialog.getBoundingClientRect = () => new DOMRect(100, 100, 200, 200);
    const at = (type: string, x: number) => dialog.dispatchEvent(new PointerEvent(type, { clientX: x, clientY: 150 }));
    at("pointerdown", 150);
    at("pointerup", 20);
    expect(dialog.open).toBe(true);
    at("pointerdown", 20);
    at("pointerup", 20);
    expect(dialog.isConnected).toBe(false);
  });

  test("the settings and status sheets are native dialogs: named, light-dismissed, closed by a dialog form", async () => {
    const { openSettings } = await import("../src/app/settings-ui.ts");
    openSettings();
    const sheet = document.querySelector("dialog")!;
    expect(sheet.classList.contains("status-sheet")).toBe(true);
    expect(sheet.getAttribute("aria-labelledby")).toBe("settings-title");
    expect(sheet.getAttribute("closedby")).toBe("any");
    expect(sheet.querySelector('form[method="dialog"] .status-close[autofocus]')).not.toBeNull();
    expect(sheet.querySelector("[role=dialog], [aria-modal]")).toBeNull();
    sheet.close();
  });

  test("closing a sheet after a setting redrew the page gives focus to the new copy of its opener", () => {
    document.getElementById("app")!.innerHTML = `<nav><button data-tool="settings" aria-label="Ajustes">⚙</button></nav>`;
    document.querySelector<HTMLElement>('[data-tool="settings"]')!.focus();
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `<button class="close">Close</button>`;
    openModal(dialog);
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
      expect(document.getElementById("announcer")!.textContent).toBe("");
    } finally {
      vi.useRealTimers();
    }
  });

  test("a page reached by a link puts focus on its heading, which takes focus without entering the tab order", () => {
    document.getElementById("app")!.innerHTML = `<main><h1>Índice</h1><a href="#/">Portada</a></main>`;
    focusHeading(document.getElementById("app")!);
    const h1 = document.querySelector("h1")!;
    expect(document.activeElement).toBe(h1);
    expect(h1.tabIndex).toBe(-1);
  });

  test("a copied link is reported in a visible status that clears itself", () => {
    vi.useFakeTimers();
    try {
      document.getElementById("app")!.innerHTML = `<footer><p class="share-status" role="status"></p></footer>`;
      const region = document.querySelector<HTMLElement>(".share-status")!;
      showStatus(region, "Enlace copiado");
      expect(region.textContent).toBe("Enlace copiado");
      vi.advanceTimersByTime(STATUS_MS);
      expect(region.textContent).toBe("");
    } finally {
      vi.useRealTimers();
    }
  });

  test("a link that could not be copied stays on screen in a selected read-only field, once", () => {
    document.getElementById("app")!.innerHTML = `<footer><p class="share-status" role="status"></p></footer>`;
    const region = document.querySelector<HTMLElement>(".share-status")!;
    showStatus(region, "No se ha podido copiar. Este es el enlace:", "https://x.test/leer/s/01/");
    showStatus(region, "No se ha podido copiar. Este es el enlace:", "https://x.test/leer/s/01/");
    const fields = document.querySelectorAll<HTMLInputElement>(".status-link");
    expect(fields).toHaveLength(1);
    expect(fields[0].readOnly).toBe(true);
    expect(fields[0].value).toBe("https://x.test/leer/s/01/");
    expect(document.activeElement).toBe(fields[0]);
    expect(region.textContent).toContain("No se ha podido copiar");
  });
});
