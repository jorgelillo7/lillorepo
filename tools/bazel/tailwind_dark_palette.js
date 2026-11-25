/**
 * Dark mode for a Tailwind v3 config without `dark:` variants.
 *
 * `darkPalette({families, neutral, darkNeutral, darkWhite, tokens, darkRules})`
 * returns `{colors, plugin}`. Every shade of the listed families (and `white`)
 * reads a CSS variable; the plugin sets one set of variables per scheme.
 * Chromatic shades swap to the shade that plays their role on a dark page
 * (tinted backgrounds go deep, text goes light); the neutral family gets the
 * hand-tuned `darkNeutral` ramp, and `white`, the card surface, `darkWhite`.
 * `tokens` ({light, dark}) adds the site's own variables, and `darkRules`
 * ({selector: declarations}) rules that apply only in dark.
 *
 * The scheme is the system's unless `<meta name="color-scheme">` pins one
 * (`light` or `dark`), which is what the theme toggle in base.html does. The
 * plugin also hides whichever half of a `.theme-to-dark` / `.theme-to-light`
 * toggle does not apply, so the control is right without JS.
 */
const colors = require("tailwindcss/colors");
const plugin = require("tailwindcss/plugin");

const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];
const DARK_OF = {
  50: "950", 100: "900", 200: "800", 300: "700", 400: "500", 500: "400",
  600: "300", 700: "200", 800: "100", 900: "50", 950: "50",
};

const PINNED = (scheme) => `:has(> head > meta[name="color-scheme"][content="${scheme}"])`;
// Dark when the system is dark and nothing pins light, or when dark is pinned.
const DARK_ROOTS = [`:root:not(${PINNED("light")})`, `:root${PINNED("dark")}`];

const channels = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};
const varName = (family, shade) => `--c-${family}-${shade}`;

function darkPalette({
  families, neutral, darkNeutral, darkWhite, tokens = { light: {}, dark: {} }, darkRules = {},
}) {
  const themed = { white: "rgb(var(--c-white) / <alpha-value>)" };
  const light = { "--c-white": channels("#ffffff"), ...tokens.light };
  const dark = { "--c-white": channels(darkWhite), ...tokens.dark };
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

  // `root` is the selector that means "dark"; `rootDeclarations` adds to its own rule.
  const whenDark = (root, rootDeclarations = {}) => {
    const rules = {
      [root]: { ...dark, ...rootDeclarations },
      [`${root} .theme-to-dark`]: { display: "none" },
    };
    rules[`${root} .theme-to-light`] = { display: "inline-flex" };
    for (const [selector, declarations] of Object.entries(darkRules)) {
      rules[`${root} ${selector}`] = declarations;
    }
    return rules;
  };

  return {
    colors: themed,
    plugin: plugin(({ addBase }) => {
      addBase({
        ":root": { ...light, colorScheme: "light dark" },
        [`:root${PINNED("light")}`]: { colorScheme: "light" },
        ".theme-to-dark": { display: "inline-flex" },
        ".theme-to-light": { display: "none" },
        "@media (prefers-color-scheme: dark)": whenDark(DARK_ROOTS[0]),
        ...whenDark(DARK_ROOTS[1], { colorScheme: "dark" }),
      });
    }),
  };
}

module.exports = { darkPalette };
