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
});

module.exports = {
  content: {
    relative: true,
    files: ["./templates/**/*.html", "./static/**/*.js", "./**/*.py"],
  },
  theme: { extend: { colors: palette.colors } },
  plugins: [require("@tailwindcss/typography"), palette.plugin],
};
