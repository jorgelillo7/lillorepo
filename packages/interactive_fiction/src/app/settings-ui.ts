/** The settings sheet, opened over whatever is on screen. Changes apply at once. */

import { applyVolume } from "./audio.ts";
import { el } from "./dom.ts";
import { loadMode, storeMode } from "./save.ts";
import { settings, updateSettings, type Settings } from "./settings.ts";

function choice<K extends keyof Settings>(key: K, value: Settings[K], label: string): string {
  const on = settings()[key] === value;
  return `<button class="chip${on ? " on" : ""}" data-set="${key}" data-value="${String(value)}" aria-pressed="${on}">${label}</button>`;
}

/** `onChange` re-renders the page underneath, for settings it shows (text size, mode). */
export function openSettings(onChange: () => void = () => {}): void {
  const s = settings();
  const mode = loadMode();
  const sheet = el(`<div class="status-overlay settings-overlay" role="dialog" aria-label="Ajustes">
    <div class="status-sheet settings-sheet">
      <h3>Ajustes</h3>
      <label class="setting">Volumen
        <input type="range" min="0" max="100" value="${Math.round(s.volume * 100)}" data-volume>
      </label>
      <div class="setting">Sonido ${choice("muted", false, "Activado")}${choice("muted", true, "Silencio")}</div>
      <div class="setting">Texto ${choice("pacing", "paragraph", "Párrafo a párrafo")}${choice("pacing", "all", "De golpe")}</div>
      <div class="setting">Tamaño ${choice("textSize", "s", "A−")}${choice("textSize", "m", "A")}${choice("textSize", "l", "A+")}</div>
      <div class="setting">Efectos ${choice("effects", true, "Sí")}${choice("effects", false, "No")}</div>
      <div class="setting">Escenas
        <button class="chip${mode === "game" ? " on" : ""}" data-mode="game">Imágenes</button>
        <button class="chip${mode === "text" ? " on" : ""}" data-mode="text">Solo texto</button>
      </div>
      <div class="setting">Opciones ${choice("sceneChoices", "image", "En la imagen")}${choice("sceneChoices", "both", "También como botones")}</div>
      <p class="settings-note">Los efectos (temblores, viñetas, parpadeos) también se apagan si tu sistema pide reducir el movimiento.</p>
      <button class="button secondary status-close">Cerrar</button>
    </div></div>`);
  sheet.addEventListener("input", (ev) => {
    const t = ev.target as HTMLInputElement;
    if (t.dataset.volume !== undefined) {
      updateSettings({ volume: Number(t.value) / 100 });
      applyVolume();
    }
  });
  sheet.addEventListener("click", (ev) => {
    const t = ev.target as HTMLElement;
    const set = t.closest<HTMLElement>("[data-set]");
    const modeButton = t.closest<HTMLElement>("[data-mode]");
    if (set) {
      const key = set.dataset.set as keyof Settings;
      const raw = set.dataset.value!;
      const value = raw === "true" ? true : raw === "false" ? false : raw;
      updateSettings({ [key]: value } as Partial<Settings>);
      applyVolume();
      sheet.querySelectorAll(`[data-set="${key}"]`).forEach((b) => {
        const on = b === set;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", String(on));
      });
      onChange();
    } else if (modeButton) {
      storeMode(modeButton.dataset.mode as "game" | "text");
      sheet.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b === modeButton));
      onChange();
    } else if (t.closest(".status-close") || t === sheet) sheet.remove();
  });
  document.body.appendChild(sheet);
  sheet.querySelector<HTMLElement>(".status-close")!.focus();
}
