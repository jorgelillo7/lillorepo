/** Tailwind v3 config for the Biwenger web; compiled by //tools/bazel:tailwind.bzl. */
const colors = require("tailwindcss/colors");
const plugin = require("tailwindcss/plugin");

// Dark mode follows the system (prefers-color-scheme). Every palette colour the
// templates use reads a CSS variable, so one set of variables per scheme
// re-themes all ~900 class uses without `dark:` variants.
const FAMILIES = ["gray", "green", "red", "amber", "purple", "blue", "yellow", "orange"];
const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];

// Light shade -> the light-mode shade that plays its role on a dark page:
// tinted backgrounds go deep, text goes light, mid greys stay readable.
const DARK_OF = {
  50: "950", 100: "900", 200: "800", 300: "700", 400: "500", 500: "400",
  600: "300", 700: "200", 800: "100", 900: "50", 950: "50",
};

// Grey carries the surfaces, so it gets a hand-tuned ramp: cards sit on
// `white` (#111827), 50/100 stay distinguishable from them for hovers and chips.
const DARK_GRAY = {
  50: "#1a2231", 100: "#1f2937", 200: "#374151", 300: "#4b5563", 400: "#6b7280",
  500: "#9ca3af", 600: "#d1d5db", 700: "#e5e7eb", 800: "#f3f4f6", 900: "#f9fafb",
  950: "#ffffff",
};
const DARK_WHITE = "#111827";

const channels = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};
const varName = (family, shade) => `--c-${family}-${shade}`;

const themed = {};
const lightVars = { "--c-white": channels("#ffffff") };
const darkVars = { "--c-white": channels(DARK_WHITE) };
for (const family of FAMILIES) {
  themed[family] = {};
  for (const shade of SHADES) {
    themed[family][shade] = `rgb(var(${varName(family, shade)}) / <alpha-value>)`;
    lightVars[varName(family, shade)] = channels(colors[family][shade]);
    darkVars[varName(family, shade)] = channels(
      family === "gray" ? DARK_GRAY[shade] : colors[family][DARK_OF[shade]],
    );
  }
}
themed.white = "rgb(var(--c-white) / <alpha-value>)";

module.exports = {
  content: {
    relative: true,
    files: ["./templates/**/*.html", "./static/**/*.js", "./**/*.py"],
  },
  theme: { extend: { colors: themed } },
  plugins: [
    require("@tailwindcss/typography"),
    plugin(({ addBase }) => {
      addBase({
        ":root": { ...lightVars, colorScheme: "light dark" },
        "@media (prefers-color-scheme: dark)": { ":root": darkVars },
      });
    }),
  ],
};
