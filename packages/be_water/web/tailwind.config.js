/** Tailwind v3 config for Be Water; compiled by //tools/bazel:tailwind.bzl. */

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
  safelist: TONES.flatMap((tone) => TONE_SHAPES.map((shape) => shape.replace("TONE", tone))),
};
