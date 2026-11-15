import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** The fonts every page sets its first text in: fetched with the page, not after its stylesheet has been read. */
const FIRST_FONTS = [/literata-latin-wght-normal-.*\.woff2$/, /cormorant-garamond-latin-500-normal-.*\.woff2$/];

/** Adds a `<link rel="preload">` to the built page for each of FIRST_FONTS, by its hashed name. */
export function preloadFonts(): Plugin {
  return {
    name: "preload-fonts",
    transformIndexHtml: {
      order: "post",
      handler(_html, ctx) {
        const files = Object.keys(ctx.bundle ?? {});
        return FIRST_FONTS.flatMap((font) => files.filter((f) => font.test(f))).map((file) => ({
          tag: "link",
          attrs: { rel: "preload", as: "font", type: "font/woff2", href: `./${file}`, crossorigin: "" },
          injectTo: "head" as const,
        }));
      },
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [preloadFonts()],
  build: { outDir: "dist", emptyOutDir: true },
  test: { include: ["tests/**/*.test.ts"] },
});
