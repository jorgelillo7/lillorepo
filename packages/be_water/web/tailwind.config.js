/** Tailwind v3 config for Be Water; compiled by //tools/bazel:tailwind.bzl. */
const { darkPalette } = require("../../../tools/bazel/tailwind_dark_palette.js");

// Dark mode follows the system; see DESIGN.md § Dark mode.
const palette = darkPalette({
  families: ["slate", "sky", "amber", "rose", "teal", "cyan", "emerald"],
  neutral: "slate",
  // The page is slate-50 (#020617), cards sit on `white` (#0f172a), chips on 100.
  darkNeutral: {
    50: "#020617", 100: "#1e293b", 200: "#334155", 300: "#475569", 400: "#64748b",
    500: "#94a3b8", 600: "#cbd5e1", 700: "#e2e8f0", 800: "#f1f5f9", 900: "#f8fafc",
    950: "#ffffff",
  },
  darkWhite: "#0f172a",
  tokens: {
    light: { "--glass": "rgba(255,255,255,.82)", "--accent": "#0369a1" },
    dark: { "--glass": "rgba(2,6,23,.78)", "--accent": "#38bdf8" },
  },
  // Bottle photos are shot on white; dim them so they do not glare.
  darkRules: { 'img:not([src$=".svg"])': { filter: "brightness(.9)" } },
});

// Templates compose the mineralization tone into class names
// (`text-{{ tone }}-700`), which the scanner cannot see: every shape used
// there, for every tone `_water_card.html`, `water.html` and `profile.html` pick.
const TONES = ["sky", "teal", "amber", "rose", "slate"];
const TONE_SHAPES = [
  "bg-TONE-100", "bg-TONE-200/70", "from-TONE-50", "to-TONE-100",
  "ring-TONE-200", "ring-TONE-200/60", "text-TONE-600/70", "text-TONE-600/80",
  "text-TONE-700", "text-TONE-700/70", "text-TONE-800",
];

module.exports = {
  content: {
    relative: true,
    files: ["./templates/**/*.html", "./static/**/*.js", "./**/*.py"],
  },
  theme: { extend: { colors: palette.colors } },
  plugins: [palette.plugin],
  safelist: TONES.flatMap((tone) => TONE_SHAPES.map((shape) => shape.replace("TONE", tone))),
};
