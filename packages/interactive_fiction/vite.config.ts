import { existsSync, readFileSync } from "node:fs";
import type { Plugin } from "vite";
import { titlePreload } from "./src/app/picture.ts";
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

/** The library the stories build wrote, read when the page is built; empty before any story is built. */
const LIBRARY = new URL("./public/stories/library.json", import.meta.url).pathname;

/** Adds a `<link rel="preload" as="image">` for the title picture when the site holds one series, so it starts with the page and not after the script reads the library. */
export function preloadTitleImage(): Plugin {
  return {
    name: "preload-title-image",
    transformIndexHtml: {
      order: "post",
      handler() {
        if (!existsSync(LIBRARY)) return [];
        const attrs = titlePreload(JSON.parse(readFileSync(LIBRARY, "utf8")));
        return attrs ? [{ tag: "link", attrs, injectTo: "head" as const }] : [];
      },
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [preloadFonts(), preloadTitleImage()],
  build: { outDir: "dist", emptyOutDir: true },
  test: { include: ["tests/**/*.test.ts"] },
});
