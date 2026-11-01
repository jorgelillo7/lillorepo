/** The survival-horror door between rooms. Click to skip; off when the reader asks for less motion. */

import { el, reducedMotion } from "./dom.ts";

export function playDoor(): void {
  if (reducedMotion()) return;
  const door = el(`<div class="door-transition" aria-hidden="true">
    <div class="door-frame"><div class="door-leaf"><span class="door-knob"></span></div></div></div>`);
  const done = () => door.remove();
  door.addEventListener("click", done);
  door.addEventListener("animationend", (e) => {
    if ((e as AnimationEvent).animationName === "door-fade") done();
  });
  document.body.appendChild(door);
}
