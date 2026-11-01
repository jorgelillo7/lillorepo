/** A story as both Twine formats describe it: Twee 3 source or a published HTML build. */

export interface Passage {
  name: string;
  tags: string[];
  text: string;
}

export interface Story {
  title: string;
  start: string;
  format: string;
  formatVersion: string;
  stylesheet: string;
  passages: Passage[];
}

const SPECIAL = new Set(["StoryTitle", "StoryData"]);

function unescapeTweeName(raw: string): string {
  return raw.replace(/\\(.)/g, "$1");
}

/** Split a Twee 3 header (`:: Name [tags] {meta}`) into name and tags. */
function parseTweeHeader(header: string): { name: string; tags: string[] } {
  let name = "";
  let i = 0;
  while (i < header.length) {
    const c = header[i];
    if (c === "\\" && i + 1 < header.length) {
      name += header[i] + header[i + 1];
      i += 2;
      continue;
    }
    if (c === "[" || c === "{") break;
    name += c;
    i++;
  }
  const rest = header.slice(i);
  const tagMatch = /^\[([^\]]*)\]/.exec(rest);
  const tags = tagMatch ? tagMatch[1].split(/\s+/).filter(Boolean) : [];
  return { name: unescapeTweeName(name.trim()), tags };
}

export function parseTwee(src: string): Story {
  const text = src.replace(/\r\n?/g, "\n");
  const chunks = text.split(/^:: /m).slice(1);
  let title = "";
  let data: Record<string, unknown> = {};
  const stylesheets: string[] = [];
  const passages: Passage[] = [];
  for (const chunk of chunks) {
    const newline = chunk.indexOf("\n");
    const header = newline === -1 ? chunk : chunk.slice(0, newline);
    const body = (newline === -1 ? "" : chunk.slice(newline + 1))
      .replace(/^\\::/gm, "::")
      .replace(/\s+$/, "");
    const { name, tags } = parseTweeHeader(header);
    if (name === "StoryTitle") title = body.trim();
    else if (name === "StoryData") data = JSON.parse(body);
    else if (tags.includes("stylesheet")) stylesheets.push(body);
    else if (tags.includes("script")) {
      if (body.trim()) throw new Error(`Story JavaScript is not supported (passage "${name}").`);
    } else if (!SPECIAL.has(name)) passages.push({ name, tags, text: body });
  }
  const start = String(data.start ?? passages[0]?.name ?? "");
  return {
    title,
    start,
    format: String(data.format ?? ""),
    formatVersion: String(data["format-version"] ?? ""),
    stylesheet: stylesheets.join("\n"),
    passages,
  };
}

export function unescapeHtml(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#x([0-9a-f]+);/gi, (_, h: string) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d: string) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&amp;/g, "&");
}

function attr(attrs: string, name: string): string {
  const m = new RegExp(`\\b${name}="([^"]*)"`).exec(attrs);
  return m ? unescapeHtml(m[1]) : "";
}

export function parseTwineHtml(html: string): Story {
  const storyData = /<tw-storydata\b([^>]*)>/.exec(html);
  if (!storyData) throw new Error("No <tw-storydata> element: not a Twine 2 build.");
  const attrs = storyData[1];
  const css = /<style[^>]*id="twine-user-stylesheet"[^>]*>([\s\S]*?)<\/style>/.exec(html);
  const script = /<script[^>]*id="twine-user-script"[^>]*>([\s\S]*?)<\/script>/.exec(html);
  if (script && script[1].trim()) throw new Error("Story JavaScript is not supported.");
  const startPid = attr(attrs, "startnode");
  let start = "";
  const passages: Passage[] = [];
  for (const m of html.matchAll(/<tw-passagedata\b([^>]*)>([\s\S]*?)<\/tw-passagedata>/g)) {
    const name = attr(m[1], "name");
    if (attr(m[1], "pid") === startPid) start = name;
    passages.push({
      name,
      tags: attr(m[1], "tags").split(/\s+/).filter(Boolean),
      text: unescapeHtml(m[2]),
    });
  }
  return {
    title: attr(attrs, "name"),
    start,
    format: attr(attrs, "format"),
    formatVersion: attr(attrs, "format-version"),
    stylesheet: css ? css[1] : "",
    passages,
  };
}

/** Parse either format, decided by the content. */
export function parseStory(src: string): Story {
  return /<tw-storydata\b/.test(src) ? parseTwineHtml(src) : parseTwee(src);
}
