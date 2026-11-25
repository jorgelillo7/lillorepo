/** Tailwind v3 config for the Biwenger web; compiled by //tools/bazel:tailwind.bzl. */
const { darkPalette } = require("../../../tools/bazel/tailwind_dark_palette.js");

// Dark mode follows the system; see DESIGN.md § Dark mode.
const palette = darkPalette({
  families: ["gray", "green", "red", "amber", "purple", "blue", "yellow", "orange"],
  neutral: "gray",
  // Cards sit on `white` (#111827); 50/100 stay distinguishable for hovers and chips.
  darkNeutral: {
    50: "#1a2231", 100: "#1f2937", 200: "#374151", 300: "#4b5563", 400: "#6b7280",
    500: "#9ca3af", 600: "#d1d5db", 700: "#e5e7eb", 800: "#f3f4f6", 900: "#f9fafb",
    950: "#ffffff",
  },
  darkWhite: "#111827",
  // The hand-written CSS in the templates reads these (DESIGN.md § Dark mode).
  tokens: {
    light: {
      "--page-bg": "#f7fafc", "--page-text": "#2d3748", "--card-bg": "#ffffff",
      "--card-border": "#e2e8f0", "--nav-text": "#4a5568", "--nav-text-strong": "#1a202c",
      "--accent": "#2f855a", "--accent-bright": "#38a169", "--focus": "#2f855a",
      "--tab-bg": "#f1f5f9", "--tab-text": "#64748b", "--rule": "#edf2f7",
      "--yes": "#38a169", "--no": "#e53e3e", "--lift": "0%", "--sink": "0%",
    },
    dark: {
      "--page-bg": "#0b1220", "--page-text": "#e5e7eb", "--card-bg": "#111827",
      "--card-border": "#1f2937", "--nav-text": "#9ca3af", "--nav-text-strong": "#f9fafb",
      "--accent-bright": "#4ade80", "--focus": "#4ade80",
      "--tab-bg": "#1f2937", "--tab-text": "#9ca3af", "--rule": "#1f2937",
      "--yes": "#4ade80", "--no": "#f87171", "--lift": "35%", "--sink": "100%",
    },
  },
  darkRules: {
    ".prose": {
      "--tw-prose-body": "var(--tw-prose-invert-body)",
      "--tw-prose-headings": "var(--tw-prose-invert-headings)",
      "--tw-prose-lead": "var(--tw-prose-invert-lead)",
      "--tw-prose-links": "var(--tw-prose-invert-links)",
      "--tw-prose-bold": "var(--tw-prose-invert-bold)",
      "--tw-prose-counters": "var(--tw-prose-invert-counters)",
      "--tw-prose-bullets": "var(--tw-prose-invert-bullets)",
      "--tw-prose-hr": "var(--tw-prose-invert-hr)",
      "--tw-prose-quotes": "var(--tw-prose-invert-quotes)",
      "--tw-prose-quote-borders": "var(--tw-prose-invert-quote-borders)",
      "--tw-prose-captions": "var(--tw-prose-invert-captions)",
      "--tw-prose-code": "var(--tw-prose-invert-code)",
      "--tw-prose-pre-code": "var(--tw-prose-invert-pre-code)",
      "--tw-prose-pre-bg": "var(--tw-prose-invert-pre-bg)",
      "--tw-prose-th-borders": "var(--tw-prose-invert-th-borders)",
      "--tw-prose-td-borders": "var(--tw-prose-invert-td-borders)",
    },
    // Photos and covers keep their own colours but stop glaring.
    'img:not([src$=".svg"])': { filter: "brightness(.92)" },
  },
});

module.exports = {
  content: {
    relative: true,
    files: ["./templates/**/*.html", "./static/**/*.js", "./**/*.py"],
  },
  theme: { extend: { colors: palette.colors } },
  plugins: [require("@tailwindcss/typography"), palette.plugin],
};
