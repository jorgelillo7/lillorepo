/** Tailwind v3 config for the Biwenger web; compiled by //tools/bazel:tailwind.bzl. */
module.exports = {
  content: {
    relative: true,
    files: ["./templates/**/*.html", "./static/**/*.js", "./**/*.py"],
  },
  plugins: [require("@tailwindcss/typography")],
};
