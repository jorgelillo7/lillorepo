// Response and request helpers shared by the routes.

export const NO_STORE = { "Cache-Control": "no-store", "X-Robots-Tag": "noindex" };

/** Sent on every response: the pages cannot be framed, so no click can be lured onto them. */
export const SECURITY = {
  "Content-Security-Policy": "frame-ancestors 'none'",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
};

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...NO_STORE, ...headers },
  });
}

export const notFound = () => new Response("No encontrado.\n", { status: 404, headers: NO_STORE });

export async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Whether a state-changing request was sent by a page of this site. Browsers attach
 * `Origin` to every cross-site POST and `Sec-Fetch-Site` to every request, so a forged
 * form or fetch fails here even though the browser sends Basic credentials unasked.
 * `strict` also refuses a request that names no origin at all.
 */
export function fromThisSite(request: Request, strict: boolean): boolean {
  const origin = request.headers.get("Origin");
  if (origin === null ? strict : origin !== new URL(request.url).origin) return false;
  const site = request.headers.get("Sec-Fetch-Site");
  return site === null || site === "same-origin";
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function fromBase64(text: string): Uint8Array {
  return Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
}
