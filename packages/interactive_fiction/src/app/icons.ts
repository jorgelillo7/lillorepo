/** The reader's line icons, drawn in the text colour. Decorative: the control carries the label. */

const icon = (paths: string) =>
  `<svg class="icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;

export const ICONS = {
  back: icon(`<path d="M15 5l-7 7 7 7"/>`),
  text: icon(`<path d="M4 5h7a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4z"/><path d="M20 5h-5a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h5z"/>`),
  scene: icon(`<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="9.5" r="1.2"/>`),
  sound: icon(`<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4 4 0 0 1 0 6"/><path d="M18 6.5a7.5 7.5 0 0 1 0 11"/>`),
  muted: icon(`<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M16 9.5l5 5"/><path d="M21 9.5l-5 5"/>`),
  settings: icon(`<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/><path d="M4 17h2"/><path d="M10 17h10"/><circle cx="8" cy="17" r="2"/>`),
  undo: icon(`<path d="M8 5L4 9l4 4"/><path d="M4 9h9.5a5.5 5.5 0 0 1 0 11H10"/>`),
  restart: icon(`<path d="M5 12a7 7 0 1 0 2.2-5.1"/><path d="M5 4.5V8h3.5"/>`),
} as const;
