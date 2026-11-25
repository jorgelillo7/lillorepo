/**
 * Dark mode for a Tailwind v3 config without `dark:` variants.
 *
 * `darkPalette({families, neutral, darkNeutral, darkWhite})` returns
 * `{colors, plugin}`: every shade of the listed families (and `white`) reads a
 * CSS variable, and the plugin sets one set of variables per
 * `prefers-color-scheme`. Chromatic shades swap to the shade that plays their
 * role on a dark page (tinted backgrounds go deep, text goes light); the
 * neutral family gets the hand-tuned `darkNeutral` ramp, and `white`, the card
 * surface, becomes `darkWhite`.
 */
const colors = require("tailwindcss/colors");
const plugin = require("tailwindcss/plugin");

const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];
const DARK_OF = {
  50: "950", 100: "900", 200: "800", 300: "700", 400: "500", 500: "400",
  600: "300", 700: "200", 800: "100", 900: "50", 950: "50",
};

const channels = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};
const varName = (family, shade) => `--c-${family}-${shade}`;

function darkPalette({ families, neutral, darkNeutral, darkWhite }) {
  const themed = { white: "rgb(var(--c-white) / <alpha-value>)" };
  const light = { "--c-white": channels("#ffffff") };
  const dark = { "--c-white": channels(darkWhite) };
  for (const family of families) {
    themed[family] = {};
    for (const shade of SHADES) {
      themed[family][shade] = `rgb(var(${varName(family, shade)}) / <alpha-value>)`;
      light[varName(family, shade)] = channels(colors[family][shade]);
      dark[varName(family, shade)] = channels(
        family === neutral ? darkNeutral[shade] : colors[family][DARK_OF[shade]],
      );
    }
  }
  return {
    colors: themed,
    plugin: plugin(({ addBase }) => {
      addBase({
        ":root": { ...light, colorScheme: "light dark" },
        "@media (prefers-color-scheme: dark)": { ":root": dark },
      });
    }),
  };
}

module.exports = { darkPalette };
