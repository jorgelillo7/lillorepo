/**
 * The survival-horror status: a heartbeat line in the toolbar coloured by the
 * story's own condition, and a status screen with the inventory. Item
 * descriptions are sentences quoted from the story (see the game config);
 * an item without one shows only its name.
 */

import type { ConditionState, GameConfig } from "../engine/game.ts";
import { el, esc } from "./dom.ts";

const ECG_PATH = "M0 20 H30 L36 8 L42 32 L48 4 L54 26 L60 20 H100 L106 12 L112 28 L118 20 H160";

function ecg(state: ConditionState | undefined, big = false): string {
  const level = state?.level ?? "fine";
  return `<svg class="ecg ecg-${level}${big ? " ecg-big" : ""}" viewBox="0 0 160 40" aria-hidden="true">
    <path class="ecg-base" d="${ECG_PATH}" /><path class="ecg-pulse" d="${ECG_PATH}" pathLength="100" /></svg>`;
}

/** The toolbar button, or nothing when the chapter tracks neither condition nor inventory. */
export function statusButton(state: ConditionState | undefined, items: string[] | undefined): string {
  if (!state && !items) return "";
  const label = state ? esc(state.label) : "Objetos";
  return `<button class="tool status-button" data-tool="status" aria-label="Estado: ${label}">${ecg(state)}<span>${label}</span></button>`;
}

/** The status screen over the page; closes on its button or a tap outside the sheet. */
export function openStatus(config: GameConfig, state: ConditionState | undefined, items: string[] | undefined): void {
  const quotes = config.inventory?.items ?? {};
  const cells = (items ?? [])
    .map((name, i) => `<button class="item" data-item="${i}"><span>${esc(name)}</span></button>`)
    .join("");
  const empty = items && !items.length ? `<p class="status-empty">No llevas nada.</p>` : "";
  const overlay = el(`<div class="status-overlay" role="dialog" aria-label="Estado">
    <div class="status-sheet">
      ${state ? `<div class="status-condition">${ecg(state, true)}<div class="status-label status-${state.level}">${esc(state.label)}</div></div>` : ""}
      ${items ? `<h3>Objetos</h3><div class="items">${cells}</div>${empty}` : ""}
      <p class="item-detail" aria-live="polite"></p>
      <button class="button secondary status-close">Cerrar</button>
    </div></div>`);
  overlay.addEventListener("click", (ev) => {
    const t = ev.target as HTMLElement;
    const item = t.closest<HTMLElement>("[data-item]");
    if (item) {
      const name = items![Number(item.dataset.item)];
      overlay.querySelectorAll(".item").forEach((x) => x.classList.toggle("selected", x === item));
      const quote = quotes[name]?.quote.text;
      overlay.querySelector(".item-detail")!.innerHTML = `<b>${esc(name)}</b>${quote ? `<br><i>${esc(quote)}</i>` : ""}`;
      return;
    }
    if (t.closest(".status-close") || t === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
  overlay.querySelector<HTMLElement>(".status-close")!.focus();
}
